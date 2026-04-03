"""Tests for skip_dirs directory pruning in recursive file collection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from triton_dotfiles.config import ConfigManager
from triton_dotfiles.managers.file_manager import FileManager


def _create_config_and_manager(
    config_dict: dict,
) -> tuple[ConfigManager, FileManager, str]:
    """Create ConfigManager and FileManager from a config dict."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.dump(config_dict, f)
        temp_path = f.name
    manager = ConfigManager(temp_path)
    manager.load_config()
    file_manager = FileManager(manager)
    return manager, file_manager, temp_path


def _minimal_config(targets: list, skip_dirs: list[str] | None = None) -> dict:
    """Create a minimal config dict with optional skip_dirs."""
    config: dict = {
        "config": {
            "repository": {"path": "/tmp/test-repo"},
            "targets": targets,
            "encryption": {"enabled": False},
        }
    }
    if skip_dirs is not None:
        config["config"]["skip_dirs"] = skip_dirs
    return config


def _collect_relative_paths(file_manager: FileManager, target) -> set[str]:
    """Collect all relative paths from a target."""
    return {rel for _abs, rel in file_manager.collect_target_files(target)}


class TestSkipDirs:
    """Test skip_dirs directory pruning behavior."""

    def test_skip_dirs_prunes_directory(self, tmp_path):
        """Files inside skip_dirs should not be yielded."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        (target_dir / "main.py").touch()
        build_dir = target_dir / "build"
        build_dir.mkdir()
        (build_dir / "output.bin").touch()

        config = _minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}],
            skip_dirs=["build"],
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            assert "main.py" in paths
            assert "build/output.bin" not in paths
        finally:
            Path(temp_path).unlink()

    def test_skip_dirs_empty_yields_all_files(self, tmp_path):
        """Empty skip_dirs should yield all files (rglob-compatible)."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        (target_dir / "main.py").touch()
        build_dir = target_dir / "build"
        build_dir.mkdir()
        (build_dir / "output.bin").touch()

        config = _minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}],
            skip_dirs=[],
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            assert "main.py" in paths
            assert "build/output.bin" in paths
        finally:
            Path(temp_path).unlink()

    def test_skip_dirs_not_set_backward_compat(self, tmp_path):
        """Config without skip_dirs key should work (backward compatibility)."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        (target_dir / "main.py").touch()
        node_dir = target_dir / "node_modules"
        node_dir.mkdir()
        (node_dir / "pkg.json").touch()

        config = _minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}],
            skip_dirs=None,  # Not set in config
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            # Without skip_dirs, node_modules should be traversed
            assert "main.py" in paths
            assert "node_modules/pkg.json" in paths
        finally:
            Path(temp_path).unlink()

    def test_direct_path_bypasses_skip_dirs(self, tmp_path):
        """Direct paths (Phase 1) should bypass skip_dirs."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        build_dir = target_dir / "build"
        build_dir.mkdir()
        (build_dir / "config.json").touch()

        config = _minimal_config(
            [
                {
                    "path": str(target_dir),
                    "recursive": True,
                    "files": ["build/config.json"],
                }
            ],
            skip_dirs=["build"],
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            assert "build/config.json" in paths
        finally:
            Path(temp_path).unlink()

    def test_multiple_skip_dirs(self, tmp_path):
        """Multiple skip_dirs should all be pruned."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        (target_dir / "main.py").touch()
        for dirname in ["build", "dist", "node_modules"]:
            d = target_dir / dirname
            d.mkdir()
            (d / "file.txt").touch()

        config = _minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}],
            skip_dirs=["build", "dist", "node_modules"],
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            assert "main.py" in paths
            assert "build/file.txt" not in paths
            assert "dist/file.txt" not in paths
            assert "node_modules/file.txt" not in paths
        finally:
            Path(temp_path).unlink()

    def test_nested_skip_dirs(self, tmp_path):
        """skip_dirs should work at any nesting depth."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        (target_dir / "main.py").touch()
        # Create nested node_modules: project/sub/node_modules/pkg.json
        sub_dir = target_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "index.js").touch()
        nested_nm = sub_dir / "node_modules"
        nested_nm.mkdir()
        (nested_nm / "pkg.json").touch()

        config = _minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}],
            skip_dirs=["node_modules"],
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            assert "main.py" in paths
            assert "sub/index.js" in paths
            assert "sub/node_modules/pkg.json" not in paths
        finally:
            Path(temp_path).unlink()

    def test_skip_dirs_does_not_affect_non_recursive(self, tmp_path):
        """skip_dirs should not affect non-recursive targets (iterdir)."""
        target_dir = tmp_path / "project"
        target_dir.mkdir()
        (target_dir / "main.py").touch()
        # "build" is a file at top level, not a directory to skip
        (target_dir / "build").touch()

        config = _minimal_config(
            [{"path": str(target_dir), "files": ["*"], "recursive": False}],
            skip_dirs=["build"],
        )
        _cm, fm, temp_path = _create_config_and_manager(config)
        try:
            paths = _collect_relative_paths(fm, _cm.config.targets[0])
            assert "main.py" in paths
            # "build" file at top level should still be yielded
            assert "build" in paths
        finally:
            Path(temp_path).unlink()
