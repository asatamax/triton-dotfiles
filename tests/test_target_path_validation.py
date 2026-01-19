"""
Tests for target path validation and normalization.

Reproduces bug: triton config target remove で ~/. を削除しようとすると ~/ が削除される
Issue: Path normalization converts ~/. to ~/, causing wrong target to be removed.
"""

import tempfile
from pathlib import Path

import yaml

from triton_dotfiles.config import ConfigManager


class TestNormalizePath:
    """Tests for normalize_path method behavior with edge cases."""

    def create_config_manager(self, config_dict: dict) -> tuple[ConfigManager, str]:
        """Helper to create a ConfigManager with given config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        manager = ConfigManager(temp_path)
        manager.load_config()
        return manager, temp_path

    def get_minimal_config(self) -> dict:
        """Create a minimal valid config."""
        return {
            "config": {
                "repository": {
                    "path": "/tmp/test-repo",
                },
                "targets": [],
                "encryption": {
                    "enabled": False,
                },
            }
        }

    def test_normalize_path_dot_ending_same_as_parent(self):
        """
        normalize_path returns same result for ~/. and ~/ (known behavior).

        This is technically correct filesystem behavior (. = current directory),
        but it's confusing for target management. The solution is to use
        validate_target_path() BEFORE normalize_path() to reject such paths.
        """
        config_dict = self.get_minimal_config()
        manager, temp_path = self.create_config_manager(config_dict)

        try:
            # normalize_path itself still normalizes ~/. to ~/
            # This is expected - the fix is in validate_target_path
            normalized_dot = manager.normalize_path("~/.")
            normalized_home = manager.normalize_path("~/")
            assert normalized_dot == normalized_home == "~/"

            # But validate_target_path should reject ~/.
            is_valid, error_msg = manager.validate_target_path("~/.")
            assert not is_valid, "validate_target_path should reject ~/."
            assert "invalid" in error_msg.lower() or "trailing" in error_msg.lower()

            # While ~/ should be valid
            is_valid, error_msg = manager.validate_target_path("~/")
            assert is_valid, f"~/ should be valid, but got: {error_msg}"
        finally:
            Path(temp_path).unlink()

    def test_normalize_path_trailing_dot_in_subpath_same_as_parent(self):
        """
        normalize_path returns same result for ~/foo/. and ~/foo (known behavior).

        The fix is in validate_target_path() which rejects such paths.
        """
        config_dict = self.get_minimal_config()
        manager, temp_path = self.create_config_manager(config_dict)

        try:
            # normalize_path still normalizes them to the same value
            normalized_with_dot = manager.normalize_path("~/foo/.")
            normalized_without_dot = manager.normalize_path("~/foo")
            assert normalized_with_dot == normalized_without_dot == "~/foo"

            # But validate_target_path should reject ~/foo/.
            is_valid, error_msg = manager.validate_target_path("~/foo/.")
            assert not is_valid, "validate_target_path should reject ~/foo/."

            # While ~/foo should be valid
            is_valid, error_msg = manager.validate_target_path("~/foo")
            assert is_valid, f"~/foo should be valid, but got: {error_msg}"
        finally:
            Path(temp_path).unlink()

    def test_normalize_path_double_dot_handling(self):
        """
        Paths with .. should be handled carefully.
        ~/foo/.. should not be silently normalized to ~/ without validation.
        """
        config_dict = self.get_minimal_config()
        manager, temp_path = self.create_config_manager(config_dict)

        try:
            # ~/foo/.. resolves to ~/, which may be surprising
            # At minimum, this should be documented behavior
            normalized = manager.normalize_path("~/foo/..")
            # We expect this to either raise or normalize to ~/
            # but it should be explicit, not a silent side effect
            assert normalized == "~/", (
                f"Expected ~/foo/.. to normalize to ~/, got {normalized}"
            )
        finally:
            Path(temp_path).unlink()


class TestTargetRemovePathConfusion:
    """
    Reproduces the main bug: removing ~/. incorrectly removes ~/.

    This is the actual bug reported in the issue.
    """

    def get_config_with_both_targets(self) -> dict:
        """
        Create config with both ~/. and ~/ as targets.

        Note: ~/. being a valid target is itself questionable,
        but we need to test the current behavior first.
        """
        return {
            "config": {
                "repository": {
                    "path": "/tmp/test-repo",
                },
                "targets": [
                    {
                        "path": "~/",
                        "files": [".zshrc", ".bashrc"],
                    },
                    {
                        "path": "~/.",
                        "files": [".profile"],
                    },
                ],
                "encryption": {
                    "enabled": False,
                },
            }
        }

    def test_remove_dot_target_does_not_remove_home_target(self):
        """
        BUG REPRODUCTION: Removing ~/. should not remove ~/.

        Current behavior (BUG):
            1. User has both ~/. and ~/ as targets
            2. User runs: triton config target remove '~/.'
            3. ~/ is removed instead of ~/.
            4. ~/. remains in config

        Expected behavior:
            1. ~/. should be removed (or error if invalid)
            2. ~/ should remain unchanged
        """
        config_dict = self.get_config_with_both_targets()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            manager = ConfigManager(temp_path)
            manager.load_config()

            # Verify initial state: both targets exist
            initial_paths = [t.path for t in manager.config.targets]
            assert "~/" in initial_paths, "Setup error: ~/ target not found"
            assert "~/." in initial_paths, "Setup error: ~/. target not found"

            # Try to remove ~/.
            result = manager.remove_target("~/.")

            # Reload config to see actual changes
            manager._config = None
            manager.load_config()

            final_paths = [t.path for t in manager.config.targets]

            # BUG: Currently ~/ gets removed, and ~/. remains
            # Expected: ~/. gets removed, ~/ remains

            # This assertion currently FAILS, demonstrating the bug
            assert "~/" in final_paths, (
                f"BUG: ~/ was incorrectly removed! "
                f"Final targets: {final_paths}. "
                "Expected ~/ to remain after removing ~/."
            )

            # Either ~/. should be removed, or an error should be raised
            if result["success"]:
                assert "~/." not in final_paths, (
                    f"~/. should have been removed but is still present. "
                    f"Final targets: {final_paths}"
                )
            else:
                # If removal failed, both should still exist
                assert "~/." in final_paths, (
                    f"If removal failed, ~/. should still exist. "
                    f"Final targets: {final_paths}"
                )

        finally:
            Path(temp_path).unlink()

    def test_remove_target_with_trailing_dot_should_fail_or_be_exact(self):
        """
        Alternative expected behavior: ~/. should be an invalid path.

        If we decide ~/. is invalid, then:
        1. add_target('~/.') should fail
        2. remove_target('~/.') should fail with "invalid path" error
        """
        config_dict = {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": [{"path": "~/", "files": [".zshrc"]}],
                "encryption": {"enabled": False},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            manager = ConfigManager(temp_path)
            manager.load_config()

            # Trying to remove ~/. when only ~/ exists
            # Should either:
            # A) Fail with "invalid path" (preferred)
            # B) Fail with "target not found" (exact matching)
            # Should NOT: Successfully remove ~/

            result = manager.remove_target("~/.")

            manager._config = None
            manager.load_config()
            final_paths = [t.path for t in manager.config.targets]

            if result["success"]:
                # If it succeeded, it should NOT have removed ~/
                assert "~/" in final_paths, (
                    "BUG: ~/. removal succeeded but removed ~/ instead!"
                )
            else:
                # If it failed, ~/ should remain
                assert "~/" in final_paths, (
                    "~/ should still exist after failed removal of ~/."
                )

        finally:
            Path(temp_path).unlink()


class TestTargetAddPathValidation:
    """
    Tests for add_target path validation.

    The bug report suggests ~/. should not be addable as a target.
    """

    def get_minimal_config(self) -> dict:
        return {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": [],
                "encryption": {"enabled": False},
            }
        }

    def test_add_target_with_trailing_dot_should_fail(self):
        """
        Adding ~/. as a target should fail validation.

        ~/. is semantically meaningless (same as ~/) and should be rejected.
        """
        config_dict = self.get_minimal_config()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            manager = ConfigManager(temp_path)
            manager.load_config()

            # Attempt to add ~/. - should fail
            result = manager.add_target("~/.", files=[".test"])

            # Currently this SUCCEEDS (bug), but should FAIL
            assert not result["success"], (
                "BUG: Adding ~/. should fail but succeeded. "
                "~/. is a semantically meaningless path."
            )
            assert (
                "invalid" in result["message"].lower()
                or "error" in result["message"].lower()
            ), "Error message should indicate invalid path"

        finally:
            Path(temp_path).unlink()

    def test_add_target_with_trailing_dot_in_subpath_should_fail(self):
        """
        Adding ~/foo/. as a target should fail validation.
        """
        config_dict = self.get_minimal_config()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            manager = ConfigManager(temp_path)
            manager.load_config()

            result = manager.add_target("~/foo/.", files=[".test"])

            assert not result["success"], (
                "BUG: Adding ~/foo/. should fail but succeeded."
            )

        finally:
            Path(temp_path).unlink()

    def test_add_duplicate_via_dot_normalization_should_fail(self):
        """
        If ~/ exists, adding ~/. should fail as duplicate.

        Even if we don't reject ~/. as invalid, adding it when ~/
        already exists should be detected as a duplicate.
        """
        config_dict = {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": [{"path": "~/", "files": [".zshrc"]}],
                "encryption": {"enabled": False},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            manager = ConfigManager(temp_path)
            manager.load_config()

            result = manager.add_target("~/.", files=[".test"])

            # This should fail - either as "invalid path" or "duplicate"
            assert not result["success"], (
                "Adding ~/. when ~/ exists should fail as duplicate or invalid"
            )

        finally:
            Path(temp_path).unlink()


class TestFindTargetByPathExactMatch:
    """
    Tests for find_target_by_path exact matching behavior.
    """

    def test_find_target_distinguishes_similar_paths(self):
        """
        find_target_by_path should use exact matching or properly validate.

        If both ~/. and ~/ are stored (which itself may be a bug),
        searching for one should not return the other.
        """
        config_dict = {
            "config": {
                "repository": {"path": "/tmp/test-repo"},
                "targets": [
                    {"path": "~/", "files": [".zshrc"]},
                    {"path": "~/.", "files": [".bashrc"]},
                ],
                "encryption": {"enabled": False},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_dict, f)
            temp_path = f.name

        try:
            manager = ConfigManager(temp_path)
            manager.load_config()

            # Search for ~/
            home_target = manager.find_target_by_path("~/")
            assert home_target is not None, "~/ target should be found"
            assert home_target.path == "~/", (
                f"Found target has wrong path: {home_target.path}"
            )

            # Search for ~/. - should either:
            # A) Return the ~/. target exactly
            # B) Return None (if ~/. is normalized and not found)
            # Should NOT return ~/ target
            dot_target = manager.find_target_by_path("~/.")

            # This is the bug - searching for ~/. finds ~/ instead
            if dot_target is not None:
                assert dot_target.path == "~/.", (
                    f"BUG: Searching for ~/. found {dot_target.path} instead. "
                    "find_target_by_path should match exactly."
                )

        finally:
            Path(temp_path).unlink()
