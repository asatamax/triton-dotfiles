"""Tests for keeping direct-path backup destinations inside the machine directory."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
import yaml

from tests.repo_env import MACHINE, make_file_manager, place, repo_has, write_file
from triton_dotfiles.config import ConfigManager
from triton_dotfiles.encryption import create_encryption_key
from triton_dotfiles.init_wizard import InitWizard
from triton_dotfiles.utils import target_backup_subdir
from triton_dotfiles.wizard_common import (
    report_unsafe_machine_name,
    update_config_repository_settings,
)

# Absolute (POSIX, home, Windows drive, UNC) and machine-dir-escaping entries
INVALID_DIRECT_PATHS = (
    "/etc/hosts",
    "~/x/y",
    "C:\\Users\\x",
    "\\\\server\\share",
    "../../x",
)


def _config_manager_on_disk(env: dict, targets: list[dict]) -> ConfigManager:
    """Write a config.yml under tmp so add/modify operations can persist."""
    config_path = env["tmp"] / "config.yml"
    config_path.write_text(
        yaml.dump(
            {
                "config": {
                    "targets": targets,
                    "repository": {
                        "path": str(env["repo"]),
                        "use_hostname": False,
                        "machine_name": MACHINE,
                    },
                    "blacklist": [],
                    "encrypt_list": [],
                    "encryption": {"enabled": False},
                }
            }
        )
    )
    return ConfigManager(str(config_path))


class TestBackupContainment:
    """backup never writes outside <repo>/<machine>/."""

    def test_absolute_direct_path_rejected(self, env, capsys):
        secret = env["tmp"] / "outside" / "secret.txt"
        write_file(secret, b"original")
        fm = make_file_manager(env, [{"path": "~/proj", "files": [str(secret)]}])
        (env["home"] / "proj").mkdir()

        results = fm.backup_files(MACHINE)

        assert results["copied"] == []
        assert len(results["errors"]) == 1
        assert "absolute paths are not allowed" in results["errors"][0]
        assert secret.read_bytes() == b"original"
        assert "Error: Rejected" in capsys.readouterr().out

    def test_absolute_direct_path_with_encryption_writes_no_enc(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        secret = env["tmp"] / "outside" / "secret.txt"
        write_file(secret, b"original")
        (env["home"] / "proj").mkdir()
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/proj",
                    "files": [str(secret)],
                    "encrypt_files": ["**/*"],
                }
            ],
            encrypt_list=["secret.txt"],
            encryption=True,
        )

        results = fm.backup_files(MACHINE)

        assert not secret.with_name("secret.txt.enc").exists()
        assert secret.read_bytes() == b"original"
        assert len(results["errors"]) == 1

    def test_parent_reference_escaping_machine_dir_rejected(self, env):
        write_file(env["tmp"] / "outside.txt")
        (env["home"] / "proj").mkdir()
        fm = make_file_manager(
            env, [{"path": "~/proj", "files": ["../../outside.txt"]}]
        )

        results = fm.backup_files(MACHINE)

        assert not (env["repo"] / "outside.txt").exists()
        assert results["copied"] == []
        assert len(results["errors"]) == 1

    def test_dry_run_reports_rejection(self, env, capsys):
        write_file(env["tmp"] / "outside.txt")
        (env["home"] / "proj").mkdir()
        fm = make_file_manager(
            env, [{"path": "~/proj", "files": ["../../outside.txt"]}]
        )

        results = fm.backup_files(MACHINE, dry_run=True)

        assert len(results["errors"]) == 1
        assert "Would reject ../../outside.txt" in capsys.readouterr().out

    def test_parent_reference_inside_machine_dir_still_backed_up(self, env):
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        write_file(env["home"] / "proj" / "keep.json")
        fm = make_file_manager(env, [{"path": "~/proj/sub", "files": ["../keep.json"]}])

        results = fm.backup_files(MACHINE)

        assert results["errors"] == []
        assert repo_has(env, "proj/keep.json")


class TestConfigValidation:
    """Invalid direct paths are reported and refused by config operations."""

    def test_validate_reports_invalid_direct_paths(self, env):
        cm = _config_manager_on_disk(
            env,
            [
                {
                    "path": "~/proj",
                    "files": [*INVALID_DIRECT_PATHS, "../keep.json", "a/b"],
                }
            ],
        )

        errors = cm.get_validation_errors()

        for entry in INVALID_DIRECT_PATHS:
            assert any(entry in e and e.startswith("✗") for e in errors), entry
        assert not any("keep.json" in e or "'a/b'" in e for e in errors)

    def test_add_target_refuses_invalid_direct_path(self, env):
        (env["home"] / "proj").mkdir()
        cm = _config_manager_on_disk(env, [{"path": "~/other", "files": [".x"]}])

        result = cm.add_target("~/proj", files=["/etc/hosts"], backup=False)

        assert result["success"] is False
        assert "/etc/hosts" in result["message"]
        assert len(cm.config.targets) == 1

    def test_modify_and_ensure_refuse_invalid_direct_path(self, env):
        (env["home"] / "proj").mkdir()
        cm = _config_manager_on_disk(env, [{"path": "~/proj", "files": [".x"]}])

        modified = cm.modify_target("~/proj", add_files=["../../x"], backup=False)
        ensured = cm.ensure_target_files("~/proj", ["/etc/hosts"], backup=False)

        assert modified["success"] is False
        assert ensured["success"] is False
        assert cm.config.targets[0].files == [".x"]

    def test_valid_parent_reference_accepted(self, env):
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        cm = _config_manager_on_disk(env, [{"path": "~/other", "files": [".x"]}])

        result = cm.add_target("~/proj/sub", files=["../keep.json"], backup=False)

        assert result["success"] is True


class TestCleanupIgnoresRejectedEntries:
    """Cleanup builds no candidates from rejected direct paths."""

    def test_rejected_direct_paths_absent_from_scopes(self, env):
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/proj",
                    "files": ["/etc/hosts", "../../x", "../ok.json", "a/b.json"],
                }
            ],
        )

        (scope,) = fm._build_target_scopes()

        assert set(scope.direct_paths.values()) == {"../ok.json", "a/b.json"}
        assert scope.direct_destinations == {
            Path("ok.json"): ["../ok.json"],
            Path("proj/a/b.json"): ["a/b.json"],
        }

    def test_cleanup_keeps_file_backed_up_by_valid_entry(self, env):
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        write_file(env["home"] / "proj" / "keep.json")
        absolute = env["tmp"] / "outside" / "abs.json"
        write_file(absolute)
        fm = make_file_manager(
            env,
            [{"path": "~/proj/sub", "files": ["../keep.json", str(absolute)]}],
        )
        fm.backup_files(MACHINE)

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == []
        assert repo_has(env, "proj/keep.json")
        assert not Path(f"{absolute}.enc").exists()


class TestBackupSymlinkContainment:
    """Symlinks inside the repository cannot redirect backup writes outside it."""

    def test_symlinked_destination_file_not_followed(self, env, capsys):
        outside = env["tmp"] / "outside" / "target.txt"
        write_file(outside, b"outside")
        (env["backup_dir"] / ".zshrc").symlink_to(outside)
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        dry = fm.backup_files(MACHINE, dry_run=True)
        results = fm.backup_files(MACHINE)

        assert outside.read_bytes() == b"outside"
        assert len(dry["errors"]) == 1
        assert len(results["errors"]) == 1
        assert results["copied"] == []
        out = capsys.readouterr().out
        assert "Would reject .zshrc" in out
        assert "Error: Rejected .zshrc" in out
        assert "symlink" in results["errors"][0]

    def test_symlinked_destination_directory_not_followed(self, env):
        outside_dir = env["tmp"] / "outside_ssh"
        outside_dir.mkdir()
        (env["backup_dir"] / ".ssh").symlink_to(outside_dir)
        write_file(env["home"] / ".ssh" / "config")
        write_file(env["home"] / ".ssh" / "sub" / "known")
        fm = make_file_manager(env, [{"path": "~/.ssh", "recursive": True}])

        results = fm.backup_files(MACHINE)

        assert list(outside_dir.iterdir()) == []
        assert len(results["errors"]) == 2
        assert results["copied"] == []

    def test_symlinked_parent_with_parent_reference_not_followed(self, env):
        outside_deep = env["tmp"] / "outside_deep" / "a" / "b"
        outside_deep.mkdir(parents=True)
        (env["backup_dir"] / "proj").mkdir()
        (env["backup_dir"] / "proj" / "sub").symlink_to(outside_deep)
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        write_file(env["home"] / "proj" / "keep.json")
        fm = make_file_manager(env, [{"path": "~/proj/sub", "files": ["../keep.json"]}])

        results = fm.backup_files(MACHINE)

        # 宛先は字句的に正規化され、シンボリックリンクの".."を辿らずマシンディレクトリ内に書く
        assert list((env["tmp"] / "outside_deep" / "a").iterdir()) == [outside_deep]
        assert list(outside_deep.iterdir()) == []
        assert results["errors"] == []
        assert (env["backup_dir"] / "proj" / "keep.json").is_file()

    def test_repository_reached_through_symlink_still_backs_up(self, env):
        link = env["tmp"] / "repo_link"
        link.symlink_to(env["repo"])
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(
            {**env, "repo": link}, [{"path": "~", "files": [".zshrc"]}]
        )

        results = fm.backup_files(MACHINE)

        assert results["errors"] == []
        assert (env["backup_dir"] / ".zshrc").read_bytes() == b"new"

    def test_machine_dir_symlinked_still_backs_up(self, env):
        real_machine = env["tmp"] / "real_machine"
        real_machine.mkdir()
        env["backup_dir"].rmdir()
        env["backup_dir"].symlink_to(real_machine)
        write_file(env["home"] / ".config" / "app" / "conf.yml", b"c")
        fm = make_file_manager(env, [{"path": "~/.config/app", "recursive": True}])

        results = fm.backup_files(MACHINE)

        assert results["errors"] == []
        assert (real_machine / ".config" / "app" / "conf.yml").read_bytes() == b"c"


class TestBackupDestinationEdgeCases:
    """Destinations that are directories, loops or symlinked .enc files."""

    def test_destination_directory_not_written_into(self, env):
        victim = env["tmp"] / "victim"
        write_file(victim, b"victim")
        (env["backup_dir"] / ".zshrc").mkdir()
        (env["backup_dir"] / ".zshrc" / ".zshrc").symlink_to(victim)
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        results = fm.backup_files(MACHINE)

        assert victim.read_bytes() == b"victim"
        assert len(results["errors"]) == 1
        assert "not a regular file" in results["errors"][0]

    def test_symlink_loop_rejected_and_backup_continues(self, env):
        (env["backup_dir"] / "proj").symlink_to("proj")
        write_file(env["home"] / "proj" / "a.txt")
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(
            env,
            [
                {"path": "~/proj", "recursive": True},
                {"path": "~", "files": [".zshrc"]},
            ],
        )

        results = fm.backup_files(MACHINE)

        assert len(results["errors"]) == 1
        assert "proj" not in results["copied"]
        assert results["copied"] == [".zshrc"]

    def test_symlinked_enc_destination_rejected(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        victim = env["tmp"] / "victim"
        write_file(victim, b"victim")
        (env["backup_dir"] / ".zshrc.enc").symlink_to(victim)
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(
            env,
            [{"path": "~", "files": [".zshrc"], "encrypt_files": [".zshrc"]}],
            encryption=True,
        )

        results = fm.backup_files(MACHINE)

        assert victim.read_bytes() == b"victim"
        assert len(results["errors"]) == 1

    def test_rejected_destination_keeps_stale_counterpart(self, env):
        victim = env["tmp"] / "victim"
        write_file(victim, b"victim")
        (env["backup_dir"] / ".zshrc").symlink_to(victim)
        write_file(env["backup_dir"] / ".zshrc.enc", b"old-encrypted")
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        results = fm.backup_files(MACHINE)

        assert (env["backup_dir"] / ".zshrc.enc").read_bytes() == b"old-encrypted"
        assert results["cleaned"] == []
        assert len(results["errors"]) == 1


class TestCleanupWithOnlyInvalidDirectPaths:
    """A target whose direct paths are all invalid is still direct-only."""

    def test_non_direct_file_not_excluded(self, env):
        place(env, "proj/keep.json")
        fm = make_file_manager(env, [{"path": "~/proj", "files": ["../../x"]}])

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []


class TestHomePrefixIsComponentBased:
    """A sibling directory sharing the home prefix is outside home."""

    def test_sibling_of_home_uses_directory_name(self, env):
        sibling = env["tmp"] / "home-work" / "proj"
        write_file(sibling / "a.txt")
        fm = make_file_manager(env, [{"path": str(sibling), "recursive": True}])

        results = fm.backup_files(MACHINE)

        assert results["errors"] == []
        assert repo_has(env, "proj/a.txt")
        assert not (env["backup_dir"] / "-work").exists()
        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_target_backup_subdir_rules(self, env):
        home = env["home"]

        assert target_backup_subdir(home) == ""
        assert target_backup_subdir(home / ".ssh") == ".ssh"
        assert target_backup_subdir(home / ".config" / "app") == ".config/app"
        assert target_backup_subdir(env["tmp"] / "home-work" / "proj") == "proj"
        assert target_backup_subdir(Path("/opt/dots")) == "dots"

    def test_vault_path_shortened_only_under_home(self, env):
        template = "config:\n  repository:\n    path: ~/dotfiles-repo\n"
        sibling_config = env["tmp"] / "sibling.yml"
        home_config = env["tmp"] / "home.yml"
        sibling_config.write_text(template)
        home_config.write_text(template)
        sibling_vault = env["tmp"] / "home-work" / "vault"

        update_config_repository_settings(sibling_config, vault_path=sibling_vault)
        update_config_repository_settings(home_config, vault_path=env["home"] / "v")

        assert f"path: {sibling_vault}\n" in sibling_config.read_text()
        assert "path: ~/v\n" in home_config.read_text()


class TestNormalizedDestination:
    """The repository side never traverses a '..' segment."""

    def _setup(self, env) -> Path:
        outside_b = env["tmp"] / "outside_b"
        outside_b.mkdir()
        (env["backup_dir"] / "b").symlink_to(outside_b)
        (env["home"] / "a").mkdir()
        write_file(env["home"] / "b" / "config", b"new")
        return outside_b

    def test_parent_reference_after_missing_dir_does_not_follow_symlink(self, env):
        outside_b = self._setup(env)
        fm = make_file_manager(env, [{"path": "~", "files": ["a/../b/config"]}])

        results = fm.backup_files(MACHINE)

        assert list(outside_b.iterdir()) == []
        assert not (env["backup_dir"] / "a").exists()
        assert len(results["errors"]) == 1

    def test_parent_reference_after_missing_dir_encrypted(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        outside_b = self._setup(env)
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~",
                    "files": ["a/../b/config"],
                    "encrypt_files": ["**/config"],
                }
            ],
            encryption=True,
        )

        results = fm.backup_files(MACHINE)

        assert list(outside_b.iterdir()) == []
        assert not (env["backup_dir"] / "a").exists()
        assert len(results["errors"]) == 1


class TestRuntimeDirectPathValidation:
    """Direct paths the validator rejects are not copied at runtime."""

    def test_home_shorthand_and_drive_entries_rejected(self, env, capsys):
        write_file(env["home"] / "proj" / "~other" / "config")
        write_file(env["home"] / "proj" / "C:" / "x")
        fm = make_file_manager(
            env, [{"path": "~/proj", "files": ["~other/config", "C:/x"]}]
        )

        dry = fm.backup_files(MACHINE, dry_run=True)
        results = fm.backup_files(MACHINE)

        assert results["copied"] == []
        assert len(results["errors"]) == 2
        assert len(dry["errors"]) == 2
        assert not (env["backup_dir"] / "proj").exists()
        out = capsys.readouterr().out
        assert "Would reject ~other/config" in out
        assert "Error: Rejected C:/x" in out

    def test_other_files_still_collected(self, env):
        write_file(env["home"] / "proj" / "~other" / "config")
        write_file(env["home"] / "proj" / "ok" / "config")
        fm = make_file_manager(
            env, [{"path": "~/proj", "files": ["~other/config", "ok/config"]}]
        )

        results = fm.backup_files(MACHINE)

        assert results["copied"] == ["ok/config"]
        assert len(results["errors"]) == 1


@pytest.mark.skipif(os.name == "nt", reason="backslash is a separator on Windows")
class TestBackslashInScannedNames:
    """A backslash in a scanned file name is part of the name, not a separator."""

    def test_backslash_name_and_subdirectory_stay_distinct(self, env):
        write_file(env["home"] / "proj" / "a\\b", b"backslash")
        write_file(env["home"] / "proj" / "a" / "b", b"nested")
        fm = make_file_manager(env, [{"path": "~/proj", "recursive": True}])

        results = fm.backup_files(MACHINE)

        assert results["errors"] == []
        assert (env["backup_dir"] / "proj" / "a\\b").read_bytes() == b"backslash"
        assert (env["backup_dir"] / "proj" / "a" / "b").read_bytes() == b"nested"
        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_cleanup_keeps_backslash_name_backup(self, env):
        write_file(env["home"] / "proj" / "a\\b", b"backslash")
        fm = make_file_manager(env, [{"path": "~/proj", "recursive": True}])
        fm.backup_files(MACHINE)

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == []
        assert repo_has(env, "proj/a\\b")


UNSAFE_MACHINE_NAMES = ("/tmp/victim", "../x", "a/b", "..", ".", "", "a\\b", "C:x")
SAFE_MACHINE_NAMES = ("work-laptop-M2", "My Mac.local")


class TestMachineNameValidation:
    """The machine name must be a single safe path component."""

    @pytest.mark.parametrize("name", UNSAFE_MACHINE_NAMES)
    def test_validation_reports_unsafe_name(self, env, name):
        fm = make_file_manager(
            env, [{"path": "~", "files": [".zshrc"]}], machine_name=name
        )

        errors = fm.config_manager.get_validation_errors()

        assert any("machine name" in e.lower() for e in errors), errors

    @pytest.mark.parametrize("name", SAFE_MACHINE_NAMES)
    def test_validation_accepts_safe_name(self, env, name):
        fm = make_file_manager(
            env, [{"path": "~", "files": [".zshrc"]}], machine_name=name
        )

        errors = fm.config_manager.get_validation_errors()

        assert not any("machine name" in e.lower() for e in errors), errors

    @pytest.mark.parametrize("name", [n for n in UNSAFE_MACHINE_NAMES if n])
    def test_settings_writer_refuses_unsafe_name(self, env, name):
        cm = _config_manager_on_disk(env, [{"path": "~", "files": [".zshrc"]}])

        result = cm.set_setting("repository.machine_name", name, backup=False)

        assert result["success"] is False
        assert cm.config.repository.machine_name == MACHINE

    @pytest.mark.parametrize("name", SAFE_MACHINE_NAMES)
    def test_settings_writer_accepts_safe_name(self, env, name):
        cm = _config_manager_on_disk(env, [{"path": "~", "files": [".zshrc"]}])

        result = cm.set_setting("repository.machine_name", name, backup=False)

        assert result["success"] is True

    def test_backup_refuses_escaping_machine_name(self, env):
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(
            env, [{"path": "~", "files": [".zshrc"]}], machine_name="../victim"
        )

        with pytest.raises(ValueError, match="machine name"):
            fm.backup_files("../victim")

        assert not (env["tmp"] / "victim").exists()

    def test_cleanup_refuses_escaping_machine_name(self, env):
        victim = env["tmp"] / "victim"
        write_file(victim / "orphan.txt", b"keep me")
        fm = make_file_manager(
            env, [{"path": "~", "files": [".zshrc"]}], machine_name="../victim"
        )

        with pytest.raises(ValueError, match="machine name"):
            fm.cleanup_repository_files("../victim")

        assert (victim / "orphan.txt").read_bytes() == b"keep me"

    def test_git_commit_push_refuses_unsafe_machine_name(self, env):
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        result = fm.git_manager.commit_and_push_machine(".", dry_run=True)

        assert result["success"] is False
        assert "machine name" in result["message"].lower()

    def test_unsafe_auto_detected_name_fails_with_hint(self, env, monkeypatch):
        monkeypatch.setattr(socket, "gethostname", lambda: "evil/../../x")
        fm = make_file_manager(
            env,
            [{"path": "~", "files": [".zshrc"]}],
            machine_name=None,
            use_hostname=True,
        )
        name = fm.config_manager.get_machine_name()

        with pytest.raises(ValueError, match="repository.machine_name"):
            fm.backup_files(name)
        errors = fm.config_manager.get_validation_errors()

        assert any("repository.machine_name" in e for e in errors), errors

    def test_symlinked_machine_dir_still_supported(self, env):
        real_machine = env["tmp"] / "real_machine"
        real_machine.mkdir()
        env["backup_dir"].rmdir()
        env["backup_dir"].symlink_to(real_machine)
        write_file(env["home"] / ".zshrc", b"new")
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        results = fm.backup_files(MACHINE)

        assert results["errors"] == []
        assert (real_machine / ".zshrc").read_bytes() == b"new"


class TestWizardMachineName:
    """Wizards refuse unsafe machine names instead of sanitizing them."""

    def test_report_unsafe_machine_name(self, capsys):
        assert report_unsafe_machine_name("../x") is not None
        assert "Error:" in capsys.readouterr().out
        assert report_unsafe_machine_name("My Mac.local") is None

    def test_init_non_interactive_refuses_unsafe_auto_name(self, monkeypatch):
        monkeypatch.setattr(
            "triton_dotfiles.config.get_machine_name_unified",
            lambda use_hostname=True, configured_machine_name=None: "a/b",
        )
        wizard = InitWizard(non_interactive=True)

        assert wizard._step_machine_name() is False
        assert wizard.result.machine_name is None
        assert any("a/b" in e for e in wizard.result.errors)
