"""Tests for target check backup coverage (backed_up field)."""

import tempfile
from pathlib import Path

import yaml

from triton_dotfiles.config import ConfigManager


class TestMatchFileAgainstTarget:
    """Tests for _match_file_against_target() method."""

    def get_minimal_config(self, targets: list) -> dict:
        return {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": targets,
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

    def test_recursive_target_no_files_matches_everything(self, tmp_path):
        """Recursive target with no files filter matches all files."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        (target_dir / "CLAUDE.md").touch()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            target = manager.config.targets[0]
            matched, pattern = manager._match_file_against_target(
                str(target_dir / "CLAUDE.md"), target
            )
            assert matched is True
            assert pattern == "**/*"
        finally:
            Path(temp_path).unlink()

    def test_recursive_target_with_pattern_match(self, tmp_path):
        """Recursive target with specific pattern matches correctly."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        (target_dir / "CLAUDE.md").touch()

        config = self.get_minimal_config(
            [
                {
                    "path": str(target_dir),
                    "recursive": True,
                    "files": ["CLAUDE.md", "*.yml"],
                }
            ]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            target = manager.config.targets[0]
            matched, pattern = manager._match_file_against_target(
                str(target_dir / "CLAUDE.md"), target
            )
            assert matched is True
            assert pattern == "CLAUDE.md"
        finally:
            Path(temp_path).unlink()

    def test_recursive_target_with_pattern_no_match(self, tmp_path):
        """Recursive target with specific pattern does not match unrelated files."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["*.yml"]}]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            target = manager.config.targets[0]
            matched, pattern = manager._match_file_against_target(
                str(target_dir / "CLAUDE.md"), target
            )
            assert matched is False
            assert pattern is None
        finally:
            Path(temp_path).unlink()

    def test_glob_star_star_matches_all(self, tmp_path):
        """**/* pattern matches everything."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["**/*"]}]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            target = manager.config.targets[0]
            matched, pattern = manager._match_file_against_target(
                str(target_dir / "sub" / "deep" / "file.txt"), target
            )
            assert matched is True
            assert pattern == "**/*"
        finally:
            Path(temp_path).unlink()

    def test_file_outside_target_no_match(self, tmp_path):
        """File outside target directory does not match."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        other_dir = tmp_path / ".other"
        other_dir.mkdir()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            target = manager.config.targets[0]
            matched, pattern = manager._match_file_against_target(
                str(other_dir / "file.txt"), target
            )
            assert matched is False
            assert pattern is None
        finally:
            Path(temp_path).unlink()


class TestIsPathBackedUp:
    """Tests for is_path_backed_up() method."""

    def get_minimal_config(self, targets: list) -> dict:
        return {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": targets,
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

    def test_file_in_recursive_target_with_pattern_match(self, tmp_path):
        """File matching a recursive target's pattern is backed up."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        test_file = target_dir / "CLAUDE.md"
        test_file.touch()

        config = self.get_minimal_config(
            [
                {
                    "path": str(target_dir),
                    "recursive": True,
                    "files": ["CLAUDE.md", "*.yml"],
                }
            ]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            backed_up, target_info, pattern = manager.is_path_backed_up(
                str(target_dir / "CLAUDE.md")
            )
            assert backed_up is True
            assert target_info["path"] == str(target_dir)
            assert target_info["recursive"] is True
            assert pattern == "CLAUDE.md"
        finally:
            Path(temp_path).unlink()

    def test_file_in_recursive_target_no_pattern_match(self, tmp_path):
        """File under recursive target but not matching patterns is NOT backed up."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        test_file = target_dir / "random.txt"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["*.yml"]}]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            backed_up, target_info, pattern = manager.is_path_backed_up(
                str(target_dir / "random.txt")
            )
            assert backed_up is False
            assert target_info is None
            assert pattern is None
        finally:
            Path(temp_path).unlink()

    def test_file_in_non_recursive_target(self, tmp_path):
        """File listed in non-recursive target's files is backed up."""
        target_dir = tmp_path / "home"
        target_dir.mkdir()
        test_file = target_dir / ".zshrc"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "files": [".zshrc", ".bashrc"]}]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            backed_up, target_info, pattern = manager.is_path_backed_up(
                str(target_dir / ".zshrc")
            )
            assert backed_up is True
            assert target_info["path"] == str(target_dir)
            assert target_info["recursive"] is False
            assert pattern == ".zshrc"
        finally:
            Path(temp_path).unlink()

    def test_file_not_in_any_target(self, tmp_path):
        """File not belonging to any target is NOT backed up."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        other_dir = tmp_path / ".other"
        other_dir.mkdir()
        test_file = other_dir / "file.txt"
        test_file.touch()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            backed_up, target_info, pattern = manager.is_path_backed_up(
                str(other_dir / "file.txt")
            )
            assert backed_up is False
            assert target_info is None
            assert pattern is None
        finally:
            Path(temp_path).unlink()

    def test_directory_exact_match(self, tmp_path):
        """Directory matching an existing target exactly is backed up."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            normalized = manager.normalize_path(str(target_dir))
            backed_up, target_info, pattern = manager.is_path_backed_up(normalized)
            assert backed_up is True
            assert target_info is not None
        finally:
            Path(temp_path).unlink()

    def test_directory_under_recursive_target(self, tmp_path):
        """Directory under a recursive target is backed up."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        sub_dir = target_dir / "skills"
        sub_dir.mkdir()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            backed_up, target_info, pattern = manager.is_path_backed_up(
                manager.normalize_path(str(sub_dir))
            )
            assert backed_up is True
            assert target_info["recursive"] is True
        finally:
            Path(temp_path).unlink()

    def test_nonexistent_file_path_still_checks_patterns(self, tmp_path):
        """Non-existent file path still checks target patterns."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["*.md"]}]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            # Non-existent file with matching extension
            backed_up, target_info, pattern = manager.is_path_backed_up(
                str(target_dir / "future.md")
            )
            assert backed_up is True
            assert pattern == "*.md"

            # Non-existent file with non-matching extension
            backed_up2, _, _ = manager.is_path_backed_up(str(target_dir / "future.txt"))
            assert backed_up2 is False
        finally:
            Path(temp_path).unlink()

    def test_recursive_target_no_files_backs_up_everything(self, tmp_path):
        """Recursive target with no files filter backs up all files."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        test_file = target_dir / "anything.xyz"
        test_file.touch()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            backed_up, target_info, pattern = manager.is_path_backed_up(
                str(target_dir / "anything.xyz")
            )
            assert backed_up is True
            assert pattern == "**/*"
        finally:
            Path(temp_path).unlink()


class TestCheckTargetPathCoverage:
    """Tests for backup coverage fields in check_target_path() response."""

    def get_minimal_config(self, targets: list) -> dict:
        return {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": targets,
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

    def test_check_includes_backed_up_fields(self, tmp_path):
        """check_target_path() includes backed_up, matched_target, matched_pattern."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        test_file = target_dir / "CLAUDE.md"
        test_file.touch()

        config = self.get_minimal_config(
            [{"path": str(target_dir), "recursive": True, "files": ["CLAUDE.md"]}]
        )
        manager, temp_path = self.create_config_manager(config)
        try:
            result = manager.check_target_path(str(test_file))
            assert "backed_up" in result
            assert "matched_target" in result
            assert "matched_pattern" in result
            assert result["backed_up"] is True
            assert result["matched_pattern"] == "CLAUDE.md"
        finally:
            Path(temp_path).unlink()

    def test_check_not_backed_up(self, tmp_path):
        """check_target_path() returns backed_up=False for uncovered path."""
        target_dir = tmp_path / ".claude"
        target_dir.mkdir()
        other_dir = tmp_path / ".other"
        other_dir.mkdir()

        config = self.get_minimal_config([{"path": str(target_dir), "recursive": True}])
        manager, temp_path = self.create_config_manager(config)
        try:
            result = manager.check_target_path(str(other_dir))
            assert result["backed_up"] is False
            assert result["matched_target"] is None
            assert result["matched_pattern"] is None
        finally:
            Path(temp_path).unlink()

    def test_check_invalid_path_includes_backed_up_false(self):
        """check_target_path() with invalid path still includes backed_up=False."""
        config = self.get_minimal_config([])
        manager, temp_path = self.create_config_manager(config)
        try:
            result = manager.check_target_path("~/.")
            assert result["backed_up"] is False
            assert result["matched_target"] is None
            assert result["matched_pattern"] is None
        finally:
            Path(temp_path).unlink()
