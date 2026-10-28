"""Tests for v1.3.2 restore, archive and machine-dir safety fixes (A2, A7, A8, A9)."""

from __future__ import annotations

import os
import shutil
import stat
from datetime import datetime as real_datetime
from pathlib import Path

import pytest
import yaml

import triton_dotfiles.config as config_module
from tests.repo_env import MACHINE, make_file_manager, write_file
from triton_dotfiles.config import ConfigManager
from triton_dotfiles.encryption import create_encryption_key
from triton_dotfiles.utils import machine_name_violation


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _encrypted_backup(env) -> object:
    """Back up ~/.secrets/token (encrypted) and remove the local copy."""
    create_encryption_key(env["tmp"] / "master.key")
    write_file(env["home"] / ".secrets" / "token", b"s3cret")
    fm = make_file_manager(
        env,
        [
            {
                "path": "~/.secrets",
                "recursive": True,
                "encrypt_files": ["token"],
            }
        ],
        encryption=True,
    )
    fm.backup_files(MACHINE)
    assert (env["backup_dir"] / ".secrets" / "token.enc").exists()
    shutil.rmtree(env["home"] / ".secrets")
    return fm


class TestDecryptedOutputPermissions:
    """A2: decrypted plaintext is created owner-only."""

    def test_restore_all_creates_private_file_and_dir(self, env):
        fm = _encrypted_backup(env)

        results = fm.restore_files(MACHINE)

        token = env["home"] / ".secrets" / "token"
        assert results["errors"] == []
        assert token.read_bytes() == b"s3cret"
        assert _mode(token) == 0o600
        assert _mode(token.parent) == 0o700

    def test_restore_keeps_existing_mode(self, env):
        fm = _encrypted_backup(env)
        token = env["home"] / ".secrets" / "token"
        write_file(token, b"old")
        token.chmod(0o640)

        fm.restore_files(MACHINE)

        assert token.read_bytes() == b"s3cret"
        assert _mode(token) == 0o640

    def test_selective_restore_creates_private_file(self, env):
        fm = _encrypted_backup(env)

        fm.restore_files(MACHINE, file_patterns=[".secrets/token.enc"])

        assert _mode(env["home"] / ".secrets" / "token") == 0o600

    def test_export_decrypted_is_private(self, env):
        fm = _encrypted_backup(env)
        out = env["tmp"] / "export" / "token"

        fm.export_file(MACHINE, ".secrets/token.enc", str(out))

        assert out.read_bytes() == b"s3cret"
        assert _mode(out) == 0o600
        assert _mode(out.parent) == 0o700

    def test_master_key_created_private_without_chmod(self, env, monkeypatch):
        monkeypatch.setattr(os, "chmod", lambda *args, **kwargs: None)
        key = env["tmp"] / "keys" / "master.key"

        create_encryption_key(key)

        assert _mode(key) == 0o600


class TestArchiveFailure:
    """A7: a file whose archive copy fails is not overwritten."""

    def test_archive_failure_skips_file(self, env, monkeypatch, capsys):
        write_file(env["home"] / ".app" / "conf", b"new")
        fm = make_file_manager(env, [{"path": "~/.app", "recursive": True}])
        fm.backup_files(MACHINE)
        write_file(env["home"] / ".app" / "conf", b"old")
        real_copy2 = shutil.copy2

        def failing_copy2(src, dst, *args, **kwargs):
            if "archives" in str(dst):
                raise OSError("disk full")
            return real_copy2(src, dst, *args, **kwargs)

        monkeypatch.setattr(shutil, "copy2", failing_copy2)
        capsys.readouterr()

        results = fm.restore_files(MACHINE)

        assert (env["home"] / ".app" / "conf").read_bytes() == b"old"
        assert len(results["errors"]) == 1
        assert results["restored"] == []
        assert "Existing files were archived" not in capsys.readouterr().out


class _FrozenDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025, 1, 2, 3, 4, 5)


class TestArchiveNames:
    """A8: archive runs and archived paths never collide."""

    def test_restore_archive_dirs_unique_within_one_second(self, env):
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        first = fm.create_restore_archive("20250102_030405")
        second = fm.create_restore_archive("20250102_030405")

        assert first != second
        assert first.name == "20250102_030405"
        assert second.name == "20250102_030405_1"

    def test_config_archives_unique_within_one_second(self, env, monkeypatch):
        monkeypatch.setattr(config_module, "datetime", _FrozenDatetime)
        config_path = env["tmp"] / "config.yml"
        config_path.write_text(yaml.dump({"config": {"targets": []}}))
        cm = ConfigManager(str(config_path))

        first = cm.backup_config_file()
        second = cm.backup_config_file()

        assert first != second
        assert first.exists() and second.exists()

    def test_parse_archive_run_name(self):
        from triton_dotfiles.utils import parse_archive_run_name

        assert parse_archive_run_name("20250102_030405") == (
            real_datetime(2025, 1, 2, 3, 4, 5),
            0,
        )
        assert parse_archive_run_name("20250102_030405_2") == (
            real_datetime(2025, 1, 2, 3, 4, 5),
            2,
        )
        assert parse_archive_run_name("config") is None
        assert parse_archive_run_name("20250102_030405_x") is None
        assert parse_archive_run_name("20250102_030405_0") is None
        assert parse_archive_run_name("20250102_030405_01") is None

    def test_out_of_home_paths_do_not_collide(self, env):
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])
        root = env["tmp"] / "archive_run"
        root.mkdir()
        first = env["tmp"] / "opt" / "a_b" / "c"
        second = env["tmp"] / "opt" / "a" / "b_c"
        write_file(first, b"1")
        write_file(second, b"2")

        archived_first = fm.archive_existing_file(first, root)
        archived_second = fm.archive_existing_file(second, root)

        assert archived_first != archived_second
        assert archived_first.read_bytes() == b"1"
        assert archived_second.read_bytes() == b"2"
        assert archived_first == root / "_root" / str(first).lstrip("/")

    def test_in_home_layout_unchanged(self, env):
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])
        root = env["tmp"] / "archive_run"
        root.mkdir()
        local = env["home"] / ".config" / "app" / "conf"
        write_file(local)

        assert fm.archive_existing_file(local, root) == root / ".config/app/conf"


class TestMachineDirHardening:
    """A9: dot-prefixed machine names and symlinked machine dirs are refused."""

    @pytest.mark.parametrize("name", [".git", ".github", ".hidden"])
    def test_dot_prefixed_names_rejected(self, name):
        assert machine_name_violation(name) is not None

    @pytest.mark.parametrize("name", ["work-laptop-M2", "My Mac.local"])
    def test_regular_names_accepted(self, name):
        assert machine_name_violation(name) is None

    def test_symlinked_machine_dir_refused(self, env):
        outside = env["tmp"] / "outside_machine"
        outside.mkdir()
        env["backup_dir"].rmdir()
        env["backup_dir"].symlink_to(outside)
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        with pytest.raises(ValueError, match="symlink"):
            fm.backup_files(MACHINE)

        assert list(outside.iterdir()) == []


class TestArchiveNeverOverwrites:
    """AA3: an archive run never overwrites a file it already holds."""

    def test_reserved_root_collision_keeps_both(self, env, capsys):
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])
        root = env["tmp"] / "archive_run"
        root.mkdir()
        outside = env["tmp"] / "opt" / "app" / "conf"
        inside = env["home"] / "_root" / Path(*outside.parts[1:])
        write_file(outside, b"outside")
        write_file(inside, b"inside")

        first = fm.archive_existing_file(inside, root)
        second = fm.archive_existing_file(outside, root)

        assert first != second
        assert first.read_bytes() == b"inside"
        assert second.read_bytes() == b"outside"
        assert second.name == "conf~1"
        assert "conf~1" in capsys.readouterr().out


class TestRestoreRunDirectories:
    """AA6: directories created by one restore run end up 0700 if they hold plaintext."""

    def _backup(self, env, files: dict[str, bytes]):
        create_encryption_key(env["tmp"] / "master.key")
        for rel, data in files.items():
            write_file(env["home"] / ".ssh" / rel, data)
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.ssh",
                    "recursive": True,
                    "encrypt_files": ["**/z_key"],
                }
            ],
            encryption=True,
        )
        fm.backup_files(MACHINE)
        return fm

    def test_dir_created_by_plain_file_tightened(self, env):
        fm = self._backup(
            env, {"a_config": b"c", "sub/a_known": b"k", "sub/z_key": b"s"}
        )
        shutil.rmtree(env["home"] / ".ssh")

        results = fm.restore_files(MACHINE)

        assert results["errors"] == []
        assert _mode(env["home"] / ".ssh") == 0o700
        assert _mode(env["home"] / ".ssh" / "sub") == 0o700
        assert _mode(env["home"] / ".ssh" / "sub" / "z_key") == 0o600

    def test_preexisting_dir_not_changed(self, env):
        fm = self._backup(env, {"a_config": b"c", "z_key": b"s"})
        shutil.rmtree(env["home"] / ".ssh")
        (env["home"] / ".ssh").mkdir()
        (env["home"] / ".ssh").chmod(0o755)

        fm.restore_files(MACHINE)

        assert _mode(env["home"] / ".ssh") == 0o755
        assert _mode(env["home"] / ".ssh" / "z_key") == 0o600
