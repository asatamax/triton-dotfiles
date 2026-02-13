"""Tests for target list --path filter option."""

import tempfile
from pathlib import Path

import yaml

from triton_dotfiles.config import ConfigManager


class TestTargetListFilter:
    """Tests for --path filter in target list."""

    def get_config_with_targets(self, tmp_path) -> dict:
        target1 = tmp_path / ".claude"
        target1.mkdir(exist_ok=True)
        target2 = tmp_path / ".ssh"
        target2.mkdir(exist_ok=True)
        target3 = tmp_path / ".docker"
        target3.mkdir(exist_ok=True)
        return {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": [
                    {"path": str(target1), "recursive": True},
                    {"path": str(target2), "files": ["config", "known_hosts"]},
                    {"path": str(target3), "recursive": True},
                ],
                "encryption": {"enabled": False},
            }
        }

    def create_config_manager(self, config_dict: dict) -> tuple[ConfigManager, str]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name
        manager = ConfigManager(temp_path)
        manager.load_config()
        return manager, temp_path

    def test_filter_returns_matching_target(self, tmp_path):
        """--path filter returns only the matching target."""
        config = self.get_config_with_targets(tmp_path)
        manager, temp_path = self.create_config_manager(config)
        try:
            ssh_path = str(tmp_path / ".ssh")
            normalized = manager.normalize_path(ssh_path)
            all_targets = list(enumerate(manager.config.targets))
            filtered = [
                (i, t)
                for i, t in all_targets
                if manager.normalize_path(t.path) == normalized
            ]
            assert len(filtered) == 1
            assert filtered[0][1].path == ssh_path
        finally:
            Path(temp_path).unlink()

    def test_filter_returns_empty_for_no_match(self, tmp_path):
        """--path filter returns empty when no target matches."""
        config = self.get_config_with_targets(tmp_path)
        manager, temp_path = self.create_config_manager(config)
        try:
            nonexistent = str(tmp_path / ".nonexistent")
            normalized = manager.normalize_path(nonexistent)
            all_targets = list(enumerate(manager.config.targets))
            filtered = [
                (i, t)
                for i, t in all_targets
                if manager.normalize_path(t.path) == normalized
            ]
            assert len(filtered) == 0
        finally:
            Path(temp_path).unlink()

    def test_no_filter_returns_all(self, tmp_path):
        """Without --path, all targets are returned."""
        config = self.get_config_with_targets(tmp_path)
        manager, temp_path = self.create_config_manager(config)
        try:
            all_targets = list(enumerate(manager.config.targets))
            assert len(all_targets) == 3
        finally:
            Path(temp_path).unlink()

    def test_filter_with_unnormalized_path(self, tmp_path):
        """Filter works with paths that need normalization."""
        config = self.get_config_with_targets(tmp_path)
        manager, temp_path = self.create_config_manager(config)
        try:
            # Use absolute path instead of normalized ~/format
            abs_path = str(tmp_path / ".claude")
            normalized_filter = manager.normalize_path(abs_path)
            all_targets = list(enumerate(manager.config.targets))
            filtered = [
                (i, t)
                for i, t in all_targets
                if manager.normalize_path(t.path) == normalized_filter
            ]
            assert len(filtered) == 1
        finally:
            Path(temp_path).unlink()
