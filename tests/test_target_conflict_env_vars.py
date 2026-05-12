"""Regression tests for conflict detection with undefined environment variables.

When a target path contains an undefined environment variable (e.g.,
``${MATSUYA_REPOS_BASE}/matsuyaginza``), the literal ``${VAR}`` string would
previously be passed to ``Path(...).expanduser().resolve()`` and resolved as a
cwd-relative path. That caused false positives in conflict detection that
varied based on the user's current directory.

These tests cover the fix that skips such targets from conflict detection and
surfaces them as warnings instead.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from triton_dotfiles.config import ConfigManager


@pytest.fixture
def clear_env(monkeypatch):
    """Ensure the env vars used in fixtures are unset."""
    monkeypatch.delenv("TRITON_TEST_REPOS_BASE", raising=False)
    monkeypatch.delenv("TRITON_TEST_B4F_BASE", raising=False)
    return monkeypatch


def _minimal_config(targets: list) -> dict:
    return {
        "config": {
            "repository": {"path": "/tmp/test-repo"},
            "targets": targets,
            "encryption": {"enabled": False},
        }
    }


def _make_manager(config_dict: dict) -> tuple[ConfigManager, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_dict, f)
        temp_path = f.name
    manager = ConfigManager(temp_path)
    manager.load_config()
    return manager, temp_path


class TestWouldCoverIgnoresUndefinedEnvVars:
    """``would_cover_existing_targets`` must skip undefined-env-var targets."""

    def test_no_false_positive_when_cwd_matches_new_path(
        self, tmp_path, clear_env, monkeypatch
    ):
        """Regression: previously returned a bogus match when cwd == new_path."""
        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                    "files": ["**/.vscode/launch.json"],
                },
                {
                    "path": "${TRITON_TEST_B4F_BASE}/core2",
                    "files": ["README.md"],
                },
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            new_target = tmp_path / "agents"
            new_target.mkdir()

            monkeypatch.chdir(new_target)
            covered = manager.would_cover_existing_targets(
                manager.normalize_path(str(new_target)), recursive=True
            )
            assert covered == []

            # Changing cwd must not change the result.
            monkeypatch.chdir(tmp_path)
            covered = manager.would_cover_existing_targets(
                manager.normalize_path(str(new_target)), recursive=True
            )
            assert covered == []
        finally:
            Path(temp_path).unlink()

    def test_still_detects_real_coverage(self, tmp_path, clear_env):
        """Defined targets must still be reported as covered."""
        existing = tmp_path / "agents" / "subproject"
        existing.mkdir(parents=True)

        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                    "files": ["**/.vscode/launch.json"],
                },
                {
                    "path": str(existing),
                    "files": ["README.md"],
                },
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            new_target = tmp_path / "agents"
            covered = manager.would_cover_existing_targets(
                manager.normalize_path(str(new_target)), recursive=True
            )
            assert covered == [str(existing)]
        finally:
            Path(temp_path).unlink()


class TestIsPathCoveredByRecursiveIgnoresUndefinedEnvVars:
    """``is_path_covered_by_recursive`` must skip undefined-env-var targets."""

    def test_no_false_positive_when_cwd_matches_check_path(
        self, tmp_path, clear_env, monkeypatch
    ):
        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                }
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            check_path = tmp_path / "agents" / "nested"
            check_path.mkdir(parents=True)

            # Previously, putting cwd at the literal ``${TRITON_TEST_REPOS_BASE}/matsuyaginza``
            # parent caused the undefined env var to be resolved against cwd and
            # produced a false coverage hit.
            monkeypatch.chdir(check_path.parent)
            is_covered, covering = manager.is_path_covered_by_recursive(str(check_path))
            assert is_covered is False
            assert covering is None
        finally:
            Path(temp_path).unlink()


class TestCheckTargetPathConsistency:
    """``check_target_path`` and ``add_target`` must agree."""

    def test_check_with_recursive_matches_add_behavior(
        self, tmp_path, clear_env, monkeypatch
    ):
        new_target = tmp_path / "agents"
        new_target.mkdir()
        monkeypatch.chdir(new_target)

        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                    "files": ["**/.vscode/launch.json"],
                }
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            check_result = manager.check_target_path(str(new_target), recursive=True)
            add_result = manager.add_target(
                path=str(new_target), recursive=True, backup=False
            )

            # ``check`` should have reported no conflicts, and ``add`` should now succeed.
            assert check_result["conflicts"] == []
            assert add_result["success"] is True
        finally:
            Path(temp_path).unlink()

    def test_check_surfaces_undefined_env_var_as_warning(
        self, tmp_path, clear_env, monkeypatch
    ):
        new_target = tmp_path / "agents"
        new_target.mkdir()
        monkeypatch.chdir(new_target)

        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                }
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            result = manager.check_target_path(str(new_target), recursive=True)
            warnings_blob = " ".join(result["warnings"])
            assert "undefined environment variable" in warnings_blob
            assert "${TRITON_TEST_REPOS_BASE}/matsuyaginza" in warnings_blob
        finally:
            Path(temp_path).unlink()

    def test_check_without_recursive_skips_would_cover(
        self, tmp_path, clear_env, monkeypatch
    ):
        existing = tmp_path / "agents" / "subproject"
        existing.mkdir(parents=True)
        new_target = tmp_path / "agents"
        monkeypatch.chdir(tmp_path)

        config = _minimal_config([{"path": str(existing), "files": ["README.md"]}])
        manager, temp_path = _make_manager(config)
        try:
            result = manager.check_target_path(str(new_target), recursive=False)
            # Without --recursive, would_cover_existing_targets is skipped.
            assert result.get("would_cover", []) == []
            # And the conflict list does not include a "would cover" message.
            for conflict in result["conflicts"]:
                assert "would cover" not in conflict
        finally:
            Path(temp_path).unlink()


class TestAddTargetWithUndefinedEnvVars:
    """``add_target`` must not falsely reject due to undefined env vars."""

    def test_add_recursive_succeeds_when_only_envvar_targets_exist(
        self, tmp_path, clear_env, monkeypatch
    ):
        new_target = tmp_path / "agents"
        new_target.mkdir()
        # Reproduce the bug condition: cwd equals the new target.
        monkeypatch.chdir(new_target)

        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                    "files": ["**/.vscode/launch.json"],
                },
                {
                    "path": "${TRITON_TEST_B4F_BASE}/core2",
                    "files": ["README.md"],
                },
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            result = manager.add_target(
                path=str(new_target), recursive=True, backup=False
            )
            assert result["success"] is True, result.get("message")
        finally:
            Path(temp_path).unlink()


class TestTargetsWithUndefinedEnvVars:
    """``targets_with_undefined_env_vars`` reports skipped target paths."""

    def test_returns_undefined_target_paths(self, clear_env):
        config = _minimal_config(
            [
                {
                    "path": "${TRITON_TEST_REPOS_BASE}/matsuyaginza",
                    "recursive": True,
                },
                {
                    "path": str(Path.home()),
                    "files": ["nope.txt"],
                },
            ]
        )
        manager, temp_path = _make_manager(config)
        try:
            assert manager.targets_with_undefined_env_vars() == [
                "${TRITON_TEST_REPOS_BASE}/matsuyaginza"
            ]
        finally:
            Path(temp_path).unlink()
