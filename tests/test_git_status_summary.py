"""Tests for GitManager.get_status_summary (drift indicator backend)."""

import subprocess
from pathlib import Path

import pytest

from triton_dotfiles.managers.git_manager import GitManager


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """1コミット入りのローカルgitリポジトリを作成"""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _git(repo_path, "init", "-b", "main")
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "config", "user.name", "Test User")
    (repo_path / "initial.txt").write_text("initial")
    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-m", "initial")
    return repo_path


@pytest.fixture
def repo_with_upstream(repo: Path, tmp_path: Path) -> Path:
    """bareリポジトリをupstreamとして設定したリポジトリ"""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-u", "origin", "main")
    return repo


def test_not_a_repository(tmp_path: Path) -> None:
    summary = GitManager(tmp_path).get_status_summary()
    assert summary["success"] is False
    assert summary["uncommitted"] == 0
    assert summary["has_upstream"] is False


def test_clean_repository_without_upstream(repo: Path) -> None:
    summary = GitManager(repo).get_status_summary()
    assert summary["success"] is True
    assert summary["uncommitted"] == 0
    assert summary["ahead"] == 0
    assert summary["behind"] == 0
    assert summary["has_upstream"] is False


def test_uncommitted_changes_counted(repo: Path) -> None:
    (repo / "initial.txt").write_text("modified")
    (repo / "untracked.txt").write_text("new")

    summary = GitManager(repo).get_status_summary()
    assert summary["success"] is True
    assert summary["uncommitted"] == 2


def test_clean_and_synced_with_upstream(repo_with_upstream: Path) -> None:
    summary = GitManager(repo_with_upstream).get_status_summary()
    assert summary["success"] is True
    assert summary["has_upstream"] is True
    assert summary["uncommitted"] == 0
    assert summary["ahead"] == 0
    assert summary["behind"] == 0


def test_ahead_of_upstream(repo_with_upstream: Path) -> None:
    (repo_with_upstream / "second.txt").write_text("second")
    _git(repo_with_upstream, "add", ".")
    _git(repo_with_upstream, "commit", "-m", "second")

    summary = GitManager(repo_with_upstream).get_status_summary()
    assert summary["ahead"] == 1
    assert summary["behind"] == 0


def test_behind_upstream(repo_with_upstream: Path) -> None:
    (repo_with_upstream / "second.txt").write_text("second")
    _git(repo_with_upstream, "add", ".")
    _git(repo_with_upstream, "commit", "-m", "second")
    _git(repo_with_upstream, "push")
    # upstreamにあるコミットをローカルから巻き戻す → behind 1
    _git(repo_with_upstream, "reset", "--hard", "HEAD~1")

    summary = GitManager(repo_with_upstream).get_status_summary()
    assert summary["ahead"] == 0
    assert summary["behind"] == 1
