"""Tests for backup skip reporting: file size limit and pattern summary output."""

from __future__ import annotations

from tests.repo_env import MACHINE, make_file_manager, repo_has, write_file

SMALL_LIMIT_MB = 0.001  # about 1KB


def _setup_files(env: dict) -> None:
    write_file(env["home"] / ".dots" / "small.txt", b"x" * 10)
    write_file(env["home"] / ".dots" / "big.bin", b"x" * 5_000)


class TestMaxFileSize:
    """max_file_size_mb is enforced by backup."""

    def test_oversize_file_skipped_and_reported(self, env, capsys):
        _setup_files(env)
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
            max_file_size_mb=SMALL_LIMIT_MB,
        )

        results = fm.backup_files(MACHINE)

        assert repo_has(env, ".dots/small.txt")
        assert not repo_has(env, ".dots/big.bin")
        assert results["copied"] == ["small.txt"]
        assert results["skipped"] == [
            f"Exceeds {SMALL_LIMIT_MB}MB limit: big.bin (0.0MB)"
        ]
        out = capsys.readouterr().out
        assert f"Warning: Skipped (exceeds {SMALL_LIMIT_MB}MB limit): big.bin" in out

    def test_dry_run_reports_oversize_file(self, env, capsys):
        _setup_files(env)
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
            max_file_size_mb=SMALL_LIMIT_MB,
        )

        results = fm.backup_files(MACHINE, dry_run=True)

        assert results["copied"] == ["small.txt"]
        assert len(results["skipped"]) == 1
        assert "Warning: Skipped (exceeds" in capsys.readouterr().out

    def test_direct_path_oversize_skipped(self, env):
        write_file(env["home"] / "proj" / "sub" / "big.bin", b"x" * 5_000)
        fm = make_file_manager(
            env,
            [{"path": "~/proj", "files": ["sub/big.bin"]}],
            max_file_size_mb=SMALL_LIMIT_MB,
        )

        results = fm.backup_files(MACHINE)

        assert results["copied"] == []
        assert not repo_has(env, "proj/sub/big.bin")

    def test_zero_limit_disables_check(self, env):
        _setup_files(env)
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*"]}],
            max_file_size_mb=0,
        )

        results = fm.backup_files(MACHINE)

        assert sorted(results["copied"]) == ["big.bin", "small.txt"]
        assert results["skipped"] == []


class TestPatternSummaryOutput:
    """The dry-run pattern summary headings carry no stray labels."""

    def test_excluded_heading_has_no_error_label(self, env, capsys):
        write_file(env["home"] / ".dots" / "keep.txt")
        write_file(env["home"] / ".dots" / "drop.log")
        fm = make_file_manager(
            env,
            [{"path": "~/.dots", "recursive": True, "files": ["**/*", "!*.log"]}],
        )

        fm.backup_files(MACHINE, dry_run=True, verbose=True)

        out = capsys.readouterr().out
        assert "Excluded by pattern:" in out
        assert "Error:" not in out
