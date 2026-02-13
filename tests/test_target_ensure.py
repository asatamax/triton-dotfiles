"""Tests for target ensure command (ensure_file_backed_up)."""

from pathlib import Path

import yaml

from triton_dotfiles.config import ConfigManager


class TestEnsureFileBackedUp:
    """Tests for ensure_file_backed_up() method."""

    def get_minimal_config(self, targets: list, tmp_path: Path) -> dict:
        return {
            "config": {
                "repository": {"path": str(tmp_path / "repo")},
                "targets": targets,
                "encryption": {"enabled": False},
            }
        }

    def create_config_manager(
        self, config_dict: dict, tmp_path: Path
    ) -> tuple[ConfigManager, str]:
        config_path = tmp_path / "config.yml"
        config_path.write_text(yaml.dump(config_dict))
        manager = ConfigManager(str(config_path))
        manager.load_config()
        return manager, str(config_path)

    def test_already_backed_up_returns_action_none(self, tmp_path):
        """File already backed up returns action='none'."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        test_file = target_dir / "CLAUDE.md"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["CLAUDE.md"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result["success"] is True
        assert result["action"] == "none"
        assert result["backed_up"] is True
        assert result["matched_pattern"] == "CLAUDE.md"

    def test_add_to_existing_target(self, tmp_path):
        """File under existing target but not matched adds to target."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        test_file = target_dir / "new_file.md"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": ["existing.md"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result["success"] is True
        assert result["action"] == "added_to_existing"
        assert result["backed_up"] is True
        assert result["target"] == str(target_dir)

        # Verify file was actually added
        manager._config = None
        manager.load_config()
        target = manager.config.targets[0]
        assert "new_file.md" in target.files

    def test_create_new_target(self, tmp_path):
        """File with no matching target creates new target."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        new_dir = tmp_path / "newdir"
        new_dir.mkdir()
        test_file = new_dir / "config.yml"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(other_dir), "recursive": True}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result["success"] is True
        assert result["action"] == "created_target"
        assert result["backed_up"] is True
        assert result["file"] == "config.yml"

        # Verify target was created
        manager._config = None
        manager.load_config()
        assert len(manager.config.targets) == 2

    def test_directory_rejected(self, tmp_path):
        """Passing a directory returns error."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config([], tmp_path)
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_file_backed_up(str(target_dir), backup=False)
        assert result["success"] is False
        assert result["action"] == "error"

    def test_idempotent_second_call_is_noop(self, tmp_path):
        """Running ensure twice: second call returns action='none'."""
        new_dir = tmp_path / "newdir"
        new_dir.mkdir()
        test_file = new_dir / "file.txt"
        test_file.touch()

        config = self.get_minimal_config([], tmp_path)
        manager, _ = self.create_config_manager(config, tmp_path)

        # First call: creates target
        result1 = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result1["action"] == "created_target"

        # Second call: should be noop
        result2 = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result2["success"] is True
        assert result2["action"] == "none"
        assert result2["backed_up"] is True

    def test_deepest_target_preferred(self, tmp_path):
        """With nested targets, file is added to the deepest one."""
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        child_dir = parent_dir / "child"
        child_dir.mkdir()
        test_file = child_dir / "new.txt"
        test_file.touch()

        config = self.get_minimal_config(
            [
                {"path": str(parent_dir), "files": ["README.md"]},
                {"path": str(child_dir), "files": ["existing.txt"]},
            ],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result["success"] is True
        assert result["action"] == "added_to_existing"
        assert result["target"] == str(child_dir)

        # Verify file was added to child, not parent
        manager._config = None
        manager.load_config()
        child_target = None
        parent_target = None
        for t in manager.config.targets:
            if t.path == str(child_dir):
                child_target = t
            elif t.path == str(parent_dir):
                parent_target = t
        assert "new.txt" in child_target.files
        assert "new.txt" not in parent_target.files

    def test_nonexistent_file_still_adds(self, tmp_path):
        """Non-existent file is still added (for future files)."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": ["existing.md"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        # File doesn't exist but target dir does
        nonexistent = target_dir / "future.md"
        result = manager.ensure_file_backed_up(str(nonexistent), backup=False)
        assert result["success"] is True
        assert result["action"] == "added_to_existing"

    def test_recursive_target_with_pattern_not_matching(self, tmp_path):
        """File under recursive target with non-matching pattern gets added."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        test_file = target_dir / "new.txt"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["*.yml"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_file_backed_up(str(test_file), backup=False)
        assert result["success"] is True
        assert result["action"] == "added_to_existing"

        # Verify pattern was added
        manager._config = None
        manager.load_config()
        target = manager.config.targets[0]
        assert "new.txt" in target.files
