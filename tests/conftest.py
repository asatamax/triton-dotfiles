"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from tests.repo_env import MACHINE


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated HOME / TRITON_DIR / repository layout."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TRITON_DIR", str(tmp_path / "triton"))

    repo = tmp_path / "repo"
    backup_dir = repo / MACHINE
    backup_dir.mkdir(parents=True)

    return {"tmp": tmp_path, "home": home, "repo": repo, "backup_dir": backup_dir}
