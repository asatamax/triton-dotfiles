"""Tests for git-commit-push scope, unpushed commits, status and TUI adapter results."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from triton_dotfiles.cli import _get_git_status_string
from triton_dotfiles.managers.git_manager import GitManager
from triton_dotfiles.tui_textual.adapters.file_adapter import TUIFileAdapter

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _committed_files(repo: Path, rev: str = "HEAD") -> set[str]:
    out = _git(repo, "show", "--name-only", "--format=", rev)
    return {line for line in out.splitlines() if line}


def _staged_files(repo: Path) -> set[str]:
    out = _git(repo, "diff", "--cached", "--name-only")
    return {line for line in out.splitlines() if line}


def _init_identity(repo: Path) -> None:
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    return origin


@pytest.fixture
def repo(tmp_path: Path, remote: Path) -> Path:
    """upstream付きのクローン。M/ と Other/ のマシンフォルダを持つ"""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _git(repo_path, "init", "-b", "main")
    _init_identity(repo_path)
    _write(repo_path / "M" / "a.txt", "a")
    _write(repo_path / "Other" / "o.txt", "o")
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-m", "initial")
    _git(repo_path, "remote", "add", "origin", str(remote))
    _git(repo_path, "push", "-u", "origin", "main")
    return repo_path


def _remote_head(remote: Path) -> str:
    return _git(remote, "rev-parse", "main").strip()


# --- B1: commit scope ---


def test_commit_excludes_paths_staged_outside_machine_dir(repo: Path) -> None:
    _write(repo / "Other" / "o.txt", "other edit")
    _git(repo, "add", "Other/o.txt")
    _write(repo / "M" / "a.txt", "machine edit")

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is True, result
    assert _committed_files(repo) == {"M/a.txt"}
    assert _staged_files(repo) == {"Other/o.txt"}
    assert result["other_staged"] == ["Other/o.txt"]


def test_staged_check_is_scoped_to_machine_dir(repo: Path, remote: Path) -> None:
    head_before = _git(repo, "rev-parse", "HEAD").strip()
    _write(repo / "Other" / "o.txt", "other edit")
    _git(repo, "add", "Other/o.txt")

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is True, result
    assert result.get("skipped") is True
    assert _git(repo, "rev-parse", "HEAD").strip() == head_before
    assert _remote_head(remote) == head_before
    assert _staged_files(repo) == {"Other/o.txt"}
    assert result["other_staged"] == ["Other/o.txt"]


def test_glob_characters_in_machine_name_are_literal(repo: Path) -> None:
    _write(repo / "M[1]" / "x.txt", "x")
    _write(repo / "M1" / "y.txt", "y")

    result = GitManager(repo).commit_and_push_machine("M[1]")

    assert result["success"] is True, result
    assert _committed_files(repo) == {"M[1]/x.txt"}
    assert "M1/y.txt" not in _staged_files(repo)


def test_pathspec_magic_in_machine_name_is_literal(repo: Path) -> None:
    # ":!M/" はpathspecの除外マジックとして解釈されるとM/以外を全てaddする
    _write(repo / ":!M" / "x.txt", "x")
    _write(repo / "Other" / "o.txt", "unstaged edit on another machine")

    result = GitManager(repo).commit_and_push_machine(":!M")

    assert result["success"] is True, result
    assert _committed_files(repo) == {":!M/x.txt"}
    assert _staged_files(repo) == set()
    assert "Other/o.txt" in _git(repo, "diff", "--name-only")


def test_machine_name_starting_with_dash_is_not_an_option(repo: Path) -> None:
    _write(repo / "-n" / "x.txt", "x")

    result = GitManager(repo).commit_and_push_machine("-n")

    assert result["success"] is True, result
    assert _committed_files(repo) == {"-n/x.txt"}


def test_commit_includes_deletions_inside_machine_dir(repo: Path) -> None:
    (repo / "M" / "a.txt").unlink()
    _write(repo / "M" / "b.txt", "b")

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is True, result
    assert _committed_files(repo) == {"M/a.txt", "M/b.txt"}
    assert not _git(repo, "ls-files", "M/a.txt").strip()


def test_dry_run_shows_literal_pathspec_commands(repo: Path) -> None:
    result = GitManager(repo).commit_and_push_machine("M", dry_run=True)

    assert result["success"] is True
    assert "git add -- ':(literal)M/'" in result["output"]
    assert "-- ':(literal)M/'" in result["output"].split("git commit", 1)[1]
    assert "git push" in result["output"]


# --- B2: unpushed commits ---


def test_existing_unpushed_commits_are_pushed(repo: Path, remote: Path) -> None:
    _write(repo / "M" / "a.txt", "committed but never pushed")
    _git(repo, "add", "M/a.txt")
    _git(repo, "commit", "-m", "previous run whose push failed")
    local_head = _git(repo, "rev-parse", "HEAD").strip()
    assert _remote_head(remote) != local_head

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is True, result
    assert _remote_head(remote) == local_head
    assert result.get("skipped") is not True
    assert result["pushed_existing"] == 1
    assert "pushed 1 existing commit(s)" in result["message"]


def test_nothing_to_commit_and_nothing_ahead_is_skipped(
    repo: Path, remote: Path
) -> None:
    head_before = _remote_head(remote)

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is True
    assert result.get("skipped") is True
    assert not result.get("pushed_existing")
    assert _remote_head(remote) == head_before


# --- B6: porcelain parsing ---


def test_unstaged_modification_not_reported_as_staged(repo: Path) -> None:
    _write(repo / "M" / "a.txt", "unstaged edit")

    status = GitManager(repo).is_working_directory_clean()

    assert status["is_clean"] is False
    assert status["has_unstaged"] is True
    assert status["has_staged"] is False


def test_staged_modification_still_reported_as_staged(repo: Path) -> None:
    _write(repo / "M" / "a.txt", "staged edit")
    _git(repo, "add", "M/a.txt")

    status = GitManager(repo).is_working_directory_clean()

    assert status["has_staged"] is True
    assert status["has_unstaged"] is False


# --- B4: triton status remote part ---


def _status_string(repo: Path) -> str:
    fm = SimpleNamespace(git_manager=GitManager(repo))
    return ANSI.sub("", _get_git_status_string(fm))


def test_status_reports_unpushed_commits(repo: Path) -> None:
    _write(repo / "M" / "a.txt", "local only")
    _git(repo, "commit", "-am", "local")

    assert _status_string(repo) == "clean, ↑1 unpushed"


def test_status_reports_behind(repo: Path, tmp_path: Path, remote: Path) -> None:
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(remote), str(other))
    _init_identity(other)
    _write(other / "Other" / "o.txt", "from another machine")
    _git(other, "commit", "-am", "other machine")
    _git(other, "push")

    assert _status_string(repo) == "clean, ↓1 behind"


def test_status_up_to_date(repo: Path) -> None:
    assert _status_string(repo) == "clean, up-to-date"


def test_status_without_upstream_is_unknown(tmp_path: Path) -> None:
    lone = tmp_path / "lone"
    lone.mkdir()
    _git(lone, "init", "-b", "main")
    _init_identity(lone)
    _write(lone / "f.txt")
    _git(lone, "add", ".")
    _git(lone, "commit", "-m", "init")

    assert _status_string(lone) == "clean, remote unknown"


def test_status_with_failing_fetch_is_unknown(repo: Path, tmp_path: Path) -> None:
    _git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))

    assert _status_string(repo) == "clean, remote unknown"


# --- B2/B5: TUI adapter ---


def _adapter(result: dict, machine: str = "M") -> TUIFileAdapter:
    adapter = TUIFileAdapter.__new__(TUIFileAdapter)
    adapter.config_manager = SimpleNamespace(get_machine_name=lambda: machine)
    adapter.file_manager = SimpleNamespace(
        git_commit_push_repository=lambda machine_name, dry_run=False: result
    )
    return adapter


def test_adapter_propagates_pull_required(
    repo: Path, tmp_path: Path, remote: Path
) -> None:
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(remote), str(other))
    _init_identity(other)
    _write(other / "Other" / "o.txt", "from another machine")
    _git(other, "commit", "-am", "other machine")
    _git(other, "push")
    _write(repo / "M" / "a.txt", "local edit")

    raw = GitManager(repo).commit_and_push_machine("M")
    result = _adapter(raw).git_commit_push_repository()

    assert result["success"] is False
    assert result["need_pull"] is True
    assert result["commits_behind"] == 1
    assert result["message"] == raw["message"]
    assert "ahead by 1 commit(s)" in result["message"]


def test_adapter_reports_nothing_to_commit() -> None:
    raw = {
        "success": True,
        "message": "No changes to commit - repository is already up to date",
        "output": "",
        "error": "",
        "skipped": True,
        "other_staged": [],
    }
    result = _adapter(raw).git_commit_push_repository()

    assert result["success"] is True
    assert "committed and pushed" not in result["message"]
    assert "Nothing to commit" in result["message"]
    assert "pushed to the remote" not in result["details"]


def test_adapter_reports_pushed_existing_commits() -> None:
    raw = {
        "success": True,
        "message": "Nothing new to commit for M; pushed 2 existing commit(s)",
        "output": "=== git push ===",
        "error": "",
        "pushed_existing": 2,
        "other_staged": [],
    }
    result = _adapter(raw).git_commit_push_repository()

    assert result["success"] is True
    assert "committed and pushed" not in result["message"]
    assert "pushed 2 existing commit(s)" in result["message"]


def test_adapter_lists_other_staged_paths() -> None:
    raw = {
        "success": True,
        "message": "Successfully committed and pushed M",
        "output": "",
        "error": "",
        "commit_message": "updated M 2026-01-01",
        "other_staged": ["Other/o.txt"],
    }
    result = _adapter(raw).git_commit_push_repository()

    assert "Other/o.txt" in result["details"]
    assert "Successfully committed and pushed M" == result["message"]


# --- round 2: unknown remote state / gone upstream ---


def _make_upstream_gone(repo: Path, remote: Path) -> None:
    _git(remote, "update-ref", "-d", "refs/heads/main")
    _git(repo, "fetch", "--prune")


def _commit_locally(repo: Path) -> str:
    _write(repo / "M" / "a.txt", "committed, push failed")
    _git(repo, "commit", "-am", "previous run whose push failed")
    return _git(repo, "rev-parse", "HEAD").strip()


def test_no_upstream_with_unpushed_commit_is_not_up_to_date(repo: Path) -> None:
    _git(repo, "branch", "--unset-upstream")
    _commit_locally(repo)

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is False, result
    assert not result.get("skipped")
    assert "no upstream branch" in result["error"]


def test_gone_upstream_with_unpushed_commit_is_pushed(repo: Path, remote: Path) -> None:
    _make_upstream_gone(repo, remote)
    local_head = _commit_locally(repo)

    result = GitManager(repo).commit_and_push_machine("M")

    assert result["success"] is True, result
    assert not result.get("skipped")
    assert _remote_head(remote) == local_head


def test_status_summary_flags_gone_upstream(repo: Path, remote: Path) -> None:
    _make_upstream_gone(repo, remote)

    summary = GitManager(repo).get_status_summary()

    assert summary["upstream_gone"] is True


def test_status_with_gone_upstream_is_not_up_to_date(repo: Path, remote: Path) -> None:
    _make_upstream_gone(repo, remote)

    assert _status_string(repo) == "clean, upstream gone"


# --- round 2: TUI bulk export directory permissions ---


def test_bulk_export_creates_private_directories(tmp_path: Path) -> None:
    adapter = TUIFileAdapter.__new__(TUIFileAdapter)

    def fake_export(machine_id, name, destination, decrypt=True):
        Path(destination).write_text("secret")

    adapter.file_manager = SimpleNamespace(export_file=fake_export)
    destination = tmp_path / "exports" / "nested"
    old_umask = os.umask(0o022)
    try:
        result = adapter.export_files_to_directory(
            "M", [{"name": ".ssh/id_ed25519"}], str(destination)
        )
    finally:
        os.umask(old_umask)

    assert result["success"] is True, result
    assert stat.S_IMODE((tmp_path / "exports").stat().st_mode) == 0o700
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert (destination / ".ssh_id_ed25519").read_text() == "secret"


def test_bulk_export_keeps_existing_directory_mode(tmp_path: Path) -> None:
    adapter = TUIFileAdapter.__new__(TUIFileAdapter)
    adapter.file_manager = SimpleNamespace(
        export_file=lambda m, n, d, decrypt=True: Path(d).write_text("x")
    )
    destination = tmp_path / "existing"
    destination.mkdir()
    destination.chmod(0o755)

    result = adapter.export_files_to_directory("M", [{"name": "f"}], str(destination))

    assert result["success"] is True, result
    assert stat.S_IMODE(destination.stat().st_mode) == 0o755
