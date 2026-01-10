"""
Tests for config.yml roundtrip integrity.

Ensures that all configuration fields are properly read and written,
preventing issues like the excluded_directories read bug.
"""

import tempfile
from pathlib import Path

import yaml

from triton_dotfiles.config import (
    ConfigManager,
    EncryptionConfig,
    RepositoryConfig,
    Target,
    TUIConfig,
)
from triton_dotfiles.schema import CONFIG_FILE_SCHEMA


class TestConfigRoundtrip:
    """Test that config read/write preserves all fields."""

    def get_full_config_dict(self) -> dict:
        """Create a config dict with ALL fields populated."""
        return {
            "config": {
                "repository": {
                    "path": "~/test-repo",
                    "use_hostname": False,
                    "machine_name": "TestMachine",
                    "excluded_directories": ["docs", "temp", "backup"],
                    "auto_pull": False,
                },
                "targets": [
                    {
                        "path": "~/.ssh",
                        "files": ["**/*"],
                        "recursive": True,
                        "encrypt_files": ["id_*"],
                    },
                    {
                        "path": "~/",
                        "files": [".zshrc", ".bashrc"],
                        "recursive": False,
                        "encrypt_files": [],
                    },
                ],
                "encryption": {
                    "enabled": True,
                    "key_file": "~/.config/triton/master.key",
                },
                "blacklist": [".DS_Store", "*.log", "*.tmp"],
                "encrypt_list": ["id_rsa*", "*.pem", "*secret*"],
                "max_file_size_mb": 10.0,
                "tui": {
                    "hide_system_files": False,
                    "system_file_patterns": [".DS_Store", "Thumbs.db"],
                    "theme": "gruvbox",
                },
            }
        }

    def test_config_roundtrip_preserves_all_fields(self):
        """Config read -> write -> read should preserve all fields."""
        original_dict = self.get_full_config_dict()

        # Create a temporary config file and use ConfigManager
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(original_dict, f)
            temp_path = f.name

        try:
            # Load with ConfigManager
            manager = ConfigManager(temp_path)
            manager.load_config()

            # Get the dict representation
            result_dict = manager._config_to_dict()

            # Compare all repository fields
            orig_repo = original_dict["config"]["repository"]
            result_repo = result_dict["config"]["repository"]

            assert result_repo["path"] == orig_repo["path"]
            assert result_repo["use_hostname"] == orig_repo["use_hostname"]
            assert result_repo["machine_name"] == orig_repo["machine_name"]
            assert (
                result_repo["excluded_directories"] == orig_repo["excluded_directories"]
            ), "excluded_directories was not preserved!"
            assert result_repo["auto_pull"] == orig_repo["auto_pull"]

            # Compare encryption fields
            orig_enc = original_dict["config"]["encryption"]
            result_enc = result_dict["config"]["encryption"]

            assert result_enc["enabled"] == orig_enc["enabled"]
            assert result_enc["key_file"] == orig_enc["key_file"]

            # Compare TUI fields
            orig_tui = original_dict["config"]["tui"]
            result_tui = result_dict["config"]["tui"]

            assert result_tui["hide_system_files"] == orig_tui["hide_system_files"]
            assert (
                result_tui["system_file_patterns"] == orig_tui["system_file_patterns"]
            )
            assert result_tui["theme"] == orig_tui["theme"]

            # Compare other top-level fields
            assert (
                result_dict["config"]["blacklist"]
                == original_dict["config"]["blacklist"]
            )
            assert (
                result_dict["config"]["encrypt_list"]
                == original_dict["config"]["encrypt_list"]
            )
            assert (
                result_dict["config"]["max_file_size_mb"]
                == original_dict["config"]["max_file_size_mb"]
            )

            # Compare targets
            assert len(result_dict["config"]["targets"]) == len(
                original_dict["config"]["targets"]
            )
            for i, (result_target, orig_target) in enumerate(
                zip(
                    result_dict["config"]["targets"],
                    original_dict["config"]["targets"],
                )
            ):
                assert result_target["path"] == orig_target["path"], (
                    f"Target {i} path mismatch"
                )
                assert result_target.get("files") == orig_target.get("files"), (
                    f"Target {i} files mismatch"
                )
                # recursive defaults to False, so it may be omitted in output
                result_recursive = result_target.get("recursive", False)
                orig_recursive = orig_target.get("recursive", False)
                assert result_recursive == orig_recursive, (
                    f"Target {i} recursive mismatch"
                )

        finally:
            Path(temp_path).unlink()

    def test_config_save_and_reload(self):
        """Config should be identical after save and reload."""
        original_dict = self.get_full_config_dict()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(original_dict, f)
            temp_path = f.name

        try:
            # Load, save, and reload
            manager1 = ConfigManager(temp_path)
            manager1.load_config()
            manager1._save_config()

            manager2 = ConfigManager(temp_path)
            manager2.load_config()

            # Compare configs
            assert (
                manager2.config.repository.excluded_directories
                == original_dict["config"]["repository"]["excluded_directories"]
            )
            assert (
                manager2.config.repository.auto_pull
                == original_dict["config"]["repository"]["auto_pull"]
            )
            assert (
                manager2.config.tui.system_file_patterns
                == original_dict["config"]["tui"]["system_file_patterns"]
            )

        finally:
            Path(temp_path).unlink()


class TestSchemaConfigAlignment:
    """Test that schema matches actual Config implementation."""

    def test_repository_fields_in_schema(self):
        """All RepositoryConfig fields should be in schema."""
        schema_fields = set(
            CONFIG_FILE_SCHEMA["sections"]["repository"]["fields"].keys()
        )
        dataclass_fields = set(RepositoryConfig.__dataclass_fields__.keys())

        assert dataclass_fields == schema_fields, (
            f"Schema mismatch for repository. "
            f"Missing in schema: {dataclass_fields - schema_fields}, "
            f"Extra in schema: {schema_fields - dataclass_fields}"
        )

    def test_encryption_fields_in_schema(self):
        """All EncryptionConfig fields should be in schema."""
        schema_fields = set(
            CONFIG_FILE_SCHEMA["sections"]["encryption"]["fields"].keys()
        )
        dataclass_fields = set(EncryptionConfig.__dataclass_fields__.keys())

        assert dataclass_fields == schema_fields, (
            f"Schema mismatch for encryption. "
            f"Missing in schema: {dataclass_fields - schema_fields}, "
            f"Extra in schema: {schema_fields - dataclass_fields}"
        )

    def test_tui_fields_in_schema(self):
        """All TUIConfig fields should be in schema."""
        schema_fields = set(CONFIG_FILE_SCHEMA["sections"]["tui"]["fields"].keys())
        dataclass_fields = set(TUIConfig.__dataclass_fields__.keys())

        assert dataclass_fields == schema_fields, (
            f"Schema mismatch for tui. "
            f"Missing in schema: {dataclass_fields - schema_fields}, "
            f"Extra in schema: {schema_fields - dataclass_fields}"
        )

    def test_target_fields_in_schema(self):
        """All Target fields should be in schema."""
        schema_fields = set(
            CONFIG_FILE_SCHEMA["sections"]["targets"]["item_fields"].keys()
        )
        dataclass_fields = set(Target.__dataclass_fields__.keys())

        assert dataclass_fields == schema_fields, (
            f"Schema mismatch for targets. "
            f"Missing in schema: {dataclass_fields - schema_fields}, "
            f"Extra in schema: {schema_fields - dataclass_fields}"
        )
