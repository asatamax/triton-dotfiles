"""Tests for target ensure command (ensure_target_files)."""

from pathlib import Path

import yaml

from triton_dotfiles.config import ConfigManager


class TestEnsureTargetFiles:
    """Tests for ensure_target_files() method."""

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

    def test_target_exists_all_files_covered_returns_none(self, tmp_path):
        """Existing target with all files already covered returns action='none'."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "CLAUDE.md").touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": ["CLAUDE.md", "AGENTS.md"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(
            str(target_dir), ["CLAUDE.md", "AGENTS.md"], backup=False
        )
        assert result["success"] is True
        assert result["action"] == "none"
        assert result["target"] == str(target_dir)
        assert result["added_files"] is None

    def test_target_exists_some_files_missing_adds_files(self, tmp_path):
        """Existing target missing some files adds them."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": ["existing.md"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(
            str(target_dir), ["existing.md", "new_file.md"], backup=False
        )
        assert result["success"] is True
        assert result["action"] == "added_files"
        assert result["added_files"] == ["new_file.md"]

        # Verify file was actually added
        manager._config = None
        manager.load_config()
        target = manager.config.targets[0]
        assert "new_file.md" in target.files
        assert "existing.md" in target.files

    def test_target_not_exists_creates_target(self, tmp_path):
        """Non-existent target creates a new target with files."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        new_dir = tmp_path / "newdir"
        new_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(other_dir), "recursive": True}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(
            str(new_dir), ["config.yml", ".env"], backup=False
        )
        assert result["success"] is True
        assert result["action"] == "created_target"
        assert result["files"] == ["config.yml", ".env"]

        # Verify target was created with correct files
        manager._config = None
        manager.load_config()
        assert len(manager.config.targets) == 2
        new_target = manager.config.targets[1]
        assert "config.yml" in new_target.files
        assert ".env" in new_target.files

    def test_idempotent_second_call_is_noop(self, tmp_path):
        """Running ensure twice: second call returns action='none'."""
        new_dir = tmp_path / "newdir"
        new_dir.mkdir()

        config = self.get_minimal_config([], tmp_path)
        manager, _ = self.create_config_manager(config, tmp_path)

        # First call: creates target
        result1 = manager.ensure_target_files(str(new_dir), ["file.txt"], backup=False)
        assert result1["action"] == "created_target"

        # Second call: should be noop
        result2 = manager.ensure_target_files(str(new_dir), ["file.txt"], backup=False)
        assert result2["success"] is True
        assert result2["action"] == "none"

    def test_multiple_files_partial_coverage(self, tmp_path):
        """With 3 files requested, 2 covered, 1 missing: adds only the missing one."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": ["a.md", "b.md"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(
            str(target_dir), ["a.md", "b.md", "c.md"], backup=False
        )
        assert result["success"] is True
        assert result["action"] == "added_files"
        assert result["added_files"] == ["c.md"]

    def test_files_with_subdirectory_paths(self, tmp_path):
        """Files with subdirectory paths (e.g., settings/mine.json) work correctly."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config([], tmp_path)
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(
            str(target_dir),
            ["settings/backup/mine.json", "src/resources/app.yml"],
            backup=False,
        )
        assert result["success"] is True
        assert result["action"] == "created_target"

        # Verify files in config
        manager._config = None
        manager.load_config()
        target = manager.config.targets[0]
        assert "settings/backup/mine.json" in target.files
        assert "src/resources/app.yml" in target.files

    def test_add_files_preserves_existing(self, tmp_path):
        """Adding files to existing target preserves the original files."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": ["original.md", "keep.txt"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(str(target_dir), ["new.md"], backup=False)
        assert result["success"] is True
        assert result["action"] == "added_files"

        # Verify all files present
        manager._config = None
        manager.load_config()
        target = manager.config.targets[0]
        assert "original.md" in target.files
        assert "keep.txt" in target.files
        assert "new.md" in target.files

    def test_empty_files_returns_error(self, tmp_path):
        """Empty files list returns error."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config([], tmp_path)
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(str(target_dir), [], backup=False)
        assert result["success"] is False
        assert result["action"] == "error"

    def test_recursive_target_wildcard_covers_all(self, tmp_path):
        """Recursive target with **/* pattern covers any file."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}],
            tmp_path,
        )
        manager, _ = self.create_config_manager(config, tmp_path)

        result = manager.ensure_target_files(
            str(target_dir), ["any_file.txt", "sub/dir/file.md"], backup=False
        )
        assert result["success"] is True
        assert result["action"] == "none"
