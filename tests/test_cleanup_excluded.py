"""Tests for cleanup-repository detecting files excluded by the current config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.repo_env import (
    MACHINE,
    collected,
    make_file_manager,
    place,
    repo_has,
    write_file,
)
from triton_dotfiles.managers.file_manager import FileManager


class TestExcludedByTargetPattern:
    """T1: files excluded by a target's ! pattern are cleaned up."""

    def test_dry_run_lists_only_excluded_file(self, env, capsys):
        place(env, ".claude/skills/a/SKILL.md")
        place(env, ".claude/skills/synced/x/y.py")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.claude",
                    "recursive": True,
                    "files": ["skills/**/*", "!skills/synced/**"],
                }
            ],
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == [".claude/skills/synced/x/y.py"]
        assert result["deleted"] == []
        assert repo_has(env, ".claude/skills/synced/x/y.py")

        out = capsys.readouterr().out
        assert (
            "  Excluded: .claude/skills/synced/x/y.py "
            "(no longer matched by config, matched: !skills/synced/**)"
        ) in out
        assert "Found 1 excluded file(s) (no longer backed up by current config)" in (
            out
        )

    def test_real_run_deletes_excluded_and_empty_dirs(self, env, capsys):
        place(env, ".claude/skills/a/SKILL.md")
        place(env, ".claude/skills/synced/x/y.py")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.claude",
                    "recursive": True,
                    "files": ["skills/**/*", "!skills/synced/**"],
                }
            ],
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=False)

        assert result["deleted"] == [".claude/skills/synced/x/y.py"]
        assert result["errors"] == []
        assert repo_has(env, ".claude/skills/a/SKILL.md")
        assert not repo_has(env, ".claude/skills/synced")
        assert (env["home"] / ".claude/skills/synced/x/y.py").exists()
        assert "Deleted: .claude/skills/synced/x/y.py (excluded)" in (
            capsys.readouterr().out
        )


class TestExcludedByBlacklist:
    """T2: globally blacklisted files are cleaned up."""

    def test_blacklisted_file_deleted(self, env, capsys):
        place(env, ".config/app/foo.bak")
        place(env, ".config/app/conf.yml")
        fm = make_file_manager(
            env,
            [{"path": "~/.config/app", "recursive": True, "files": ["**/*"]}],
            blacklist=["*.bak"],
        )

        dry = fm.cleanup_repository_files(MACHINE, dry_run=True)
        assert dry["would_delete"] == [".config/app/foo.bak"]
        assert "matched: *.bak" in capsys.readouterr().out

        result = fm.cleanup_repository_files(MACHINE, dry_run=False)
        assert result["deleted"] == [".config/app/foo.bak"]
        assert repo_has(env, ".config/app/conf.yml")


class TestOverlappingTargets:
    """T3: a file kept by any target is never deleted."""

    def test_direct_path_in_other_target_keeps_file(self, env):
        place(env, ".claude/settings.json")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.claude",
                    "recursive": True,
                    "files": ["**/*", "!settings.json"],
                },
                {"path": "~", "files": [".claude/settings.json"]},
            ],
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == []

    def test_nested_target_keeps_only_its_matches(self, env):
        place(env, "proj/sub/a.yml")
        place(env, "proj/sub/b.txt")
        fm = make_file_manager(
            env,
            [
                {"path": "~/proj", "recursive": True, "files": ["**/*", "!sub/**"]},
                {"path": "~/proj/sub", "recursive": True, "files": ["*.yml"]},
            ],
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == ["proj/sub/b.txt"]


class TestNonPatternSkipsAreKept:
    """T4: files backup skips for non-pattern reasons stay in the repository."""

    def test_file_over_size_limit_kept(self, env):
        place(env, ".dots/big.bin", content=b"x" * 20_000)
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
            max_file_size_mb=0.001,
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_file_under_skip_dirs_kept(self, env):
        place(env, ".dots/build/out.bin")
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
            skip_dirs=["build"],
        )

        assert "build/out.bin" not in collected(fm)
        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_file_under_symlinked_dir_kept(self, env):
        elsewhere = env["tmp"] / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "notes.txt").write_text("n")
        (env["home"] / ".dots").mkdir()
        (env["home"] / ".dots" / "linked").symlink_to(elsewhere)
        place(env, None, repo_rel=".dots/linked/notes.txt")
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
        )

        assert "linked/notes.txt" not in collected(fm)
        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_special_file_kept(self, env):
        (env["home"] / ".dots").mkdir()
        os.mkfifo(env["home"] / ".dots" / "pipe")
        place(env, None, repo_rel=".dots/pipe")
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
        )

        assert "pipe" not in collected(fm)
        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_target_with_undefined_env_var_kept(self, env):
        place(env, ".dots/a.txt")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.dots",
                    "recursive": True,
                    "files": ["${TRITON_TEST_UNDEFINED_VAR}/**"],
                }
            ],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_encrypt_list_with_encryption_disabled_kept(self, env):
        place(env, ".ssh/id_rsa", repo_rel=".ssh/id_rsa.enc")
        fm = make_file_manager(
            env,
            [{"path": "~/.ssh", "recursive": True, "files": ["**/*"]}],
            encrypt_list=["id_rsa"],
            encryption=False,
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []


class TestEncryptedFiles:
    """T5: .enc files are judged by their local plaintext path."""

    def _fm(self, env) -> FileManager:
        return make_file_manager(
            env,
            [
                {
                    "path": "~/.config/app",
                    "recursive": True,
                    "files": ["**/*", "!old/**"],
                    "encrypt_files": ["**/.env"],
                }
            ],
            encryption=True,
        )

    def test_matching_enc_kept_and_excluded_enc_deleted(self, env, capsys):
        place(env, ".config/app/.env", repo_rel=".config/app/.env.enc")
        place(env, ".config/app/old/.env", repo_rel=".config/app/old/.env.enc")
        fm = self._fm(env)

        dry = fm.cleanup_repository_files(MACHINE, dry_run=True)
        assert dry["would_delete"] == [".config/app/old/.env.enc"]
        assert "  Excluded: .config/app/old/.env.enc [encrypted]" in (
            capsys.readouterr().out
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=False)
        assert result["deleted"] == [".config/app/old/.env.enc"]
        assert repo_has(env, ".config/app/.env.enc")

    def test_excluded_stale_pair_listed_once_each(self, env, capsys):
        place(env, ".config/app/old/.env")
        place(env, None, repo_rel=".config/app/old/.env.enc")
        fm = self._fm(env)

        dry = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert sorted(dry["would_delete"]) == [
            ".config/app/old/.env",
            ".config/app/old/.env.enc",
        ]
        out = capsys.readouterr().out
        assert "Stale:" not in out

        result = fm.cleanup_repository_files(MACHINE, dry_run=False)
        assert sorted(result["deleted"]) == sorted(dry["would_delete"])
        assert result["errors"] == []


class TestOutOfScope:
    """T6: files under no target are kept."""

    def test_file_under_no_target_kept(self, env):
        place(env, ".misc/file.txt")
        fm = make_file_manager(
            env,
            [{"path": "~/.claude", "recursive": True, "files": ["**/*"]}],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_subdir_of_non_recursive_home_target_kept(self, env):
        place(env, ".zshrc")
        place(env, ".misc/file.txt")
        fm = make_file_manager(env, [{"path": "~", "files": [".zshrc"]}])

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []


class TestExistingCleanupBehavior:
    """T7: orphaned and stale detection keep working."""

    def test_orphaned_file_deleted_as_orphaned(self, env, capsys):
        place(env, ".claude/keep.md")
        place(env, None, repo_rel=".claude/gone.md")
        fm = make_file_manager(
            env,
            [{"path": "~/.claude", "recursive": True, "files": ["**/*"]}],
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=False)

        assert result["deleted"] == [".claude/gone.md"]
        assert repo_has(env, ".claude/keep.md")
        assert "Deleted: .claude/gone.md (orphaned)" in capsys.readouterr().out

    def test_stale_plaintext_deleted(self, env, capsys):
        place(env, ".config/app/.env")
        place(env, None, repo_rel=".config/app/.env.enc")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.config/app",
                    "recursive": True,
                    "files": ["**/*"],
                    "encrypt_files": ["**/.env"],
                }
            ],
            encryption=True,
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=False)

        assert result["deleted"] == [".config/app/.env"]
        assert repo_has(env, ".config/app/.env.enc")
        assert "Deleted: .config/app/.env (stale plaintext)" in (
            capsys.readouterr().out
        )

    def test_nothing_found_message(self, env, capsys):
        place(env, ".claude/keep.md")
        fm = make_file_manager(
            env,
            [{"path": "~/.claude", "recursive": True, "files": ["**/*"]}],
        )

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == []
        assert "No orphaned, stale, or excluded files found in repository" in (
            capsys.readouterr().out
        )


class TestRepoSideTargetResolution:
    """Exclusion is decided from every target that backs up into the repo path."""

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
    def test_symlinked_target_roots_keep_file(self, env):
        outside = env["tmp"] / "outside" / "dots"
        write_file(outside / "config.json")
        (env["home"] / "dots").symlink_to(outside)
        place(env, None, repo_rel="dots/config.json")
        fm = make_file_manager(
            env,
            [
                {"path": str(outside), "recursive": True, "files": ["*.json"]},
                {"path": "~/dots", "recursive": True, "files": ["*.txt"]},
            ],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_colliding_out_of_home_and_in_home_targets_keep_file(self, env):
        outside = env["tmp"] / "outside" / "shared"
        write_file(outside / "config.json")
        place(env, "shared/config.json", repo_rel="shared/config.json")
        fm = make_file_manager(
            env,
            [
                {"path": str(outside), "recursive": True, "files": ["*.json"]},
                {"path": "~/shared", "recursive": True, "files": ["*.txt"]},
            ],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_direct_path_with_parent_reference_keeps_file(self, env):
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        write_file(env["home"] / "proj" / "keep.json")
        write_file(env["home"] / "proj" / "drop.json")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/proj",
                    "recursive": True,
                    "files": ["sub/../keep.json", "*.txt"],
                }
            ],
        )
        fm.backup_files(MACHINE)
        assert repo_has(env, "proj/keep.json")
        write_file(env["backup_dir"] / "proj" / "drop.json")

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == ["proj/drop.json"]


class TestPatternSemanticsMatchBackup:
    """Cleanup mirrors the ordering rules backup applies."""

    def test_ordered_reinclude(self, env):
        for name in ("a.log", "important.log", "conf.txt"):
            place(env, f".app/{name}")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.app",
                    "recursive": True,
                    "files": ["*", "!*.log", "important.log"],
                }
            ],
        )
        assert collected(fm) == {"important.log", "conf.txt"}

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == [".app/a.log"]

    def test_direct_path_wins_over_later_negation(self, env):
        place(env, "proj/sub/keep.json")
        place(env, "proj/sub/other.json")
        place(env, "proj/top.json")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/proj",
                    "recursive": True,
                    "files": ["**/*", "sub/keep.json", "!sub/**"],
                }
            ],
        )
        assert collected(fm) == {"sub/keep.json", "top.json"}

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == ["proj/sub/other.json"]


class TestRepoSideOrphanAndStale:
    """Orphan and stale detection consider every target writing to the repo path."""

    def _colliding(
        self, env, encrypt_outside: bool = False
    ) -> tuple[Path, FileManager]:
        outside = env["tmp"] / "outside" / "shared"
        outside.mkdir(parents=True)
        (env["home"] / "shared").mkdir()
        outside_target: dict = {
            "path": str(outside),
            "recursive": True,
            "files": ["**/*"],
        }
        if encrypt_outside:
            outside_target["encrypt_files"] = [".env"]
        fm = make_file_manager(
            env,
            [
                outside_target,
                {"path": "~/shared", "recursive": True, "files": ["**/*"]},
            ],
            encryption=encrypt_outside,
        )
        return outside, fm

    def test_not_orphaned_when_other_colliding_target_has_file(self, env):
        outside, fm = self._colliding(env)
        write_file(outside / "config.json")
        place(env, None, repo_rel="shared/config.json")

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_orphaned_when_missing_for_every_target(self, env, capsys):
        _outside, fm = self._colliding(env)
        place(env, None, repo_rel="shared/config.json")

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == ["shared/config.json"]
        assert "  Orphaned: shared/config.json" in capsys.readouterr().out

    def test_stale_judged_by_target_whose_local_file_exists(self, env):
        outside, fm = self._colliding(env, encrypt_outside=True)
        write_file(outside / ".env")
        place(env, None, repo_rel="shared/.env")
        place(env, None, repo_rel="shared/.env.enc")

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == ["shared/.env"]

    def test_stale_pair_kept_when_colliding_targets_disagree(self, env, capsys):
        outside, fm = self._colliding(env, encrypt_outside=True)
        write_file(outside / ".env")
        write_file(env["home"] / "shared" / ".env")
        place(env, None, repo_rel="shared/.env")
        place(env, None, repo_rel="shared/.env.enc")

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == []
        assert "Stale:" not in capsys.readouterr().out


class TestEscapingDirectPathsAndUnresolvedTargets:
    """Targets that reach the repo path other than by their own prefix are honored."""

    def test_direct_path_escaping_its_target_keeps_file(self, env):
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        write_file(env["home"] / "proj" / "keep.json")
        fm = make_file_manager(
            env,
            [
                {"path": "~/proj/sub", "files": ["../keep.json"]},
                {"path": "~/proj", "recursive": True, "files": ["*.txt"]},
            ],
        )
        fm.backup_files(MACHINE)
        assert repo_has(env, "proj/keep.json")

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_unresolved_target_path_colliding_with_resolved_target_keeps_file(
        self, env, monkeypatch
    ):
        monkeypatch.delenv("TRITON_TEST_UNDEFINED_ROOT", raising=False)
        place(env, "dots/a.json")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "${TRITON_TEST_UNDEFINED_ROOT}/dots",
                    "recursive": True,
                    "files": ["**/*"],
                },
                {"path": "~/dots", "recursive": True, "files": ["*.txt"]},
            ],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_unresolved_only_coverage_with_missing_local_not_orphaned(
        self, env, monkeypatch
    ):
        monkeypatch.delenv("TRITON_TEST_UNDEFINED_ROOT", raising=False)
        place(env, None, repo_rel="dots/a.json")
        fm = make_file_manager(
            env,
            [
                {
                    "path": "${TRITON_TEST_UNDEFINED_ROOT}/dots",
                    "recursive": True,
                    "files": ["**/*"],
                }
            ],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []


class TestDirectPathThroughSourceSymlink:
    """A direct path is resolved on the source side exactly as backup reads it."""

    def _setup(self, env) -> tuple[Path, FileManager]:
        source = env["tmp"] / "source"
        (source / "sub").mkdir(parents=True)
        write_file(source / "keep.json", b"source")
        (env["home"] / "proj").mkdir()
        (env["home"] / "proj" / "link").symlink_to(source / "sub")
        fm = make_file_manager(
            env, [{"path": "~/proj", "files": ["link/../keep.json"]}]
        )
        fm.backup_files(MACHINE)
        assert (env["backup_dir"] / "proj" / "keep.json").read_bytes() == b"source"
        return source, fm

    def test_backed_up_file_kept(self, env):
        _source, fm = self._setup(env)

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_orphaned_when_source_removed(self, env, capsys):
        source, fm = self._setup(env)
        (source / "keep.json").unlink()

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == ["proj/keep.json"]
        assert "  Orphaned: proj/keep.json" in capsys.readouterr().out
