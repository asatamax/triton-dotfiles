#!/usr/bin/env python3
"""
Direct Path Optimization Tests for Triton

Tests the direct path detection and separation functionality that enables
efficient file collection by avoiding full directory scans when relative
paths are specified.
"""

from triton_dotfiles.utils import is_direct_path, separate_direct_and_pattern_files


class TestIsDirectPath:
    """Tests for is_direct_path() function"""

    def test_direct_path_with_forward_slash(self):
        """Paths with forward slash are direct paths"""
        assert is_direct_path("b4f-apps/.env")
        assert is_direct_path("src/main/config.yml")
        assert is_direct_path("deep/nested/path/file.txt")
        assert is_direct_path("a/b")

    def test_direct_path_with_backslash(self):
        """Paths with backslash (Windows) are direct paths"""
        assert is_direct_path("src\\config.yml")
        assert is_direct_path("deep\\nested\\file.txt")
        assert is_direct_path("a\\b")

    def test_simple_filename_not_direct(self):
        """Simple filenames without path separators are not direct paths"""
        assert not is_direct_path(".zshrc")
        assert not is_direct_path("config.yml")
        assert not is_direct_path(".env")
        assert not is_direct_path("Makefile")

    def test_glob_patterns_not_direct(self):
        """Patterns with glob characters are not direct paths"""
        assert not is_direct_path("*.yml")
        assert not is_direct_path("**/*.py")
        assert not is_direct_path("src/*.py")
        assert not is_direct_path("config.???")
        assert not is_direct_path("file[0-9].txt")

    def test_glob_with_path_not_direct(self):
        """Paths containing glob characters are patterns, not direct"""
        assert not is_direct_path("src/**/*.py")
        assert not is_direct_path("app/*.env")
        assert not is_direct_path("config/[dev].yml")
        assert not is_direct_path("data/file?.txt")

    def test_exclusion_patterns_not_direct(self):
        """Exclusion patterns (starting with !) are not direct paths"""
        assert not is_direct_path("!b4f-apps/.env")
        assert not is_direct_path("!*.log")
        assert not is_direct_path("!src/config.yml")

    def test_empty_string(self):
        """Empty string is not a direct path"""
        assert not is_direct_path("")

    def test_special_filenames(self):
        """Special filenames without slashes are not direct paths"""
        assert not is_direct_path(".DS_Store")
        assert not is_direct_path(".gitignore")
        assert not is_direct_path("README.md")


class TestSeparateDirectAndPatternFiles:
    """Tests for separate_direct_and_pattern_files() function"""

    def test_mixed_patterns(self):
        """Correctly separates mixed direct paths and patterns"""
        patterns = [
            "b4f-apps/.env",
            "*.yml",
            "!*.log",
            "src/config.xml",
        ]
        direct, glob = separate_direct_and_pattern_files(patterns)
        assert direct == ["b4f-apps/.env", "src/config.xml"]
        assert glob == ["*.yml", "!*.log"]

    def test_only_direct_paths(self):
        """All direct paths returns empty pattern list"""
        patterns = ["a/b.txt", "c/d/e.py", "x/y/z"]
        direct, glob = separate_direct_and_pattern_files(patterns)
        assert direct == ["a/b.txt", "c/d/e.py", "x/y/z"]
        assert glob == []

    def test_only_patterns(self):
        """All patterns returns empty direct path list"""
        patterns = ["*.py", "**/*.yml", "!*.log", ".zshrc"]
        direct, glob = separate_direct_and_pattern_files(patterns)
        assert direct == []
        assert glob == ["*.py", "**/*.yml", "!*.log", ".zshrc"]

    def test_empty_list(self):
        """Empty list returns two empty lists"""
        direct, glob = separate_direct_and_pattern_files([])
        assert direct == []
        assert glob == []

    def test_preserves_order(self):
        """Original order is preserved within each category"""
        patterns = ["a/b.txt", "*.py", "c/d.txt", "*.yml", "e/f.txt"]
        direct, glob = separate_direct_and_pattern_files(patterns)
        assert direct == ["a/b.txt", "c/d.txt", "e/f.txt"]
        assert glob == ["*.py", "*.yml"]

    def test_real_world_config(self):
        """Realistic config file patterns are correctly separated"""
        patterns = [
            "core2.code-workspace",  # simple filename -> pattern
            "b4f-apps/.env",  # direct path
            "b4f-client-http/src/main/resources/application-user.yml",  # direct path
            "**/*.log",  # glob pattern
            "!important.log",  # exclusion pattern
        ]
        direct, glob = separate_direct_and_pattern_files(patterns)
        assert direct == [
            "b4f-apps/.env",
            "b4f-client-http/src/main/resources/application-user.yml",
        ]
        assert glob == [
            "core2.code-workspace",
            "**/*.log",
            "!important.log",
        ]
