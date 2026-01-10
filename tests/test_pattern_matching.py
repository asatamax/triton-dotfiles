#!/usr/bin/env python3
"""
Pattern Matching Tests for Triton

Tests pattern matching functionality including:
- Basic glob patterns
- Globstar patterns (**)
- Negation patterns (!)
- Re-inclusion patterns
- Sequential pattern evaluation
"""

import pytest
from pathlib import Path

from triton_dotfiles.utils import matches_glob_pattern
from triton_dotfiles.managers.file_manager import (
    separate_patterns,
    evaluate_patterns_sequential,
)


class TestMatchesGlobPattern:
    """Basic pattern matching tests"""

    def test_exact_filename(self):
        """Exact filename match"""
        assert matches_glob_pattern(Path("cli.py"), "cli.py")
        assert not matches_glob_pattern(Path("cli.py"), "config.py")

    def test_wildcard_extension(self):
        """Wildcard extension match (*.py)"""
        assert matches_glob_pattern(Path("cli.py"), "*.py")
        assert matches_glob_pattern(Path("config.py"), "*.py")
        assert not matches_glob_pattern(Path("main.tcss"), "*.py")

    def test_wildcard_prefix(self):
        """Wildcard prefix match (config.*)"""
        assert matches_glob_pattern(Path("config.py"), "config.*")
        assert matches_glob_pattern(Path("config.yml"), "config.*")
        assert not matches_glob_pattern(Path("cli.py"), "config.*")

    def test_substring_match(self):
        """Substring match (*manager*)"""
        assert matches_glob_pattern(Path("file_manager.py"), "*manager*")
        assert matches_glob_pattern(Path("git_manager.py"), "*manager*")
        assert not matches_glob_pattern(Path("cli.py"), "*manager*")

    def test_question_mark_wildcard(self):
        """Single character wildcard (?)"""
        assert matches_glob_pattern(Path("cli.py"), "???.py")
        assert not matches_glob_pattern(Path("config.py"), "???.py")


class TestGlobstarPattern:
    """Globstar (**) pattern tests"""

    def test_globstar_any_extension(self):
        """Match any file in any subdirectory"""
        assert matches_glob_pattern(Path("managers/file_manager.py"), "**/*.py")
        assert matches_glob_pattern(Path("tui_textual/widgets/dialogs.py"), "**/*.py")
        assert matches_glob_pattern(Path("cli.py"), "**/*.py")

    def test_globstar_specific_dir(self):
        """Match files in specific directory pattern"""
        assert matches_glob_pattern(
            Path("managers/file_manager.py"), "**/managers/*.py"
        )
        assert not matches_glob_pattern(Path("encryption/real.py"), "**/managers/*.py")

    def test_globstar_nested(self):
        """Match deeply nested files"""
        assert matches_glob_pattern(
            Path("tui_textual/widgets/dialogs.py"), "**/widgets/*.py"
        )
        assert matches_glob_pattern(
            Path("tui_textual/adapters/file_adapter.py"), "**/adapters/*.py"
        )

    def test_globstar_directory_tree(self):
        """Match entire directory tree"""
        assert matches_glob_pattern(Path("tui_textual/app.py"), "tui_textual/**")
        assert matches_glob_pattern(
            Path("tui_textual/widgets/dialogs.py"), "tui_textual/**"
        )
        assert not matches_glob_pattern(Path("cli.py"), "tui_textual/**")


class TestSeparatePatterns:
    """Pattern separation tests"""

    def test_separate_mixed_patterns(self):
        """Separate inclusion and exclusion patterns"""
        patterns = ["**/*.py", "!**/__pycache__/**", "**/*.tcss", "!**/test_*"]
        include, exclude = separate_patterns(patterns)

        assert include == ["**/*.py", "**/*.tcss"]
        assert exclude == ["**/__pycache__/**", "**/test_*"]

    def test_separate_only_inclusion(self):
        """All inclusion patterns"""
        patterns = ["*.py", "*.tcss", "*.yml"]
        include, exclude = separate_patterns(patterns)

        assert include == ["*.py", "*.tcss", "*.yml"]
        assert exclude == []

    def test_separate_only_exclusion(self):
        """All exclusion patterns"""
        patterns = ["!*.log", "!*.tmp", "!*.bak"]
        include, exclude = separate_patterns(patterns)

        assert include == []
        assert exclude == ["*.log", "*.tmp", "*.bak"]

    def test_separate_empty_patterns(self):
        """Empty pattern list"""
        include, exclude = separate_patterns([])
        assert include == []
        assert exclude == []


class TestEvaluatePatternsSequential:
    """Sequential pattern evaluation tests (re-inclusion support)"""

    def test_simple_inclusion(self):
        """Simple inclusion pattern"""
        patterns = ["**/*.py"]
        included, matched = evaluate_patterns_sequential(Path("cli.py"), patterns)

        assert included is True
        assert matched == "**/*.py"

    def test_simple_exclusion(self):
        """Simple exclusion pattern"""
        patterns = ["**/*.py", "!**/cli.py"]
        included, matched = evaluate_patterns_sequential(Path("cli.py"), patterns)

        assert included is False
        assert matched == "!**/cli.py"

    def test_re_inclusion(self):
        """Re-inclusion: exclude then include specific file"""
        patterns = [
            "**/*.py",  # Include all Python files
            "!**/tui_textual/**",  # Exclude TUI directory
            "**/tui_textual/app.py",  # But include app.py
        ]

        # app.py should be included (re-inclusion)
        included, matched = evaluate_patterns_sequential(
            Path("tui_textual/app.py"), patterns
        )
        assert included is True
        assert matched == "**/tui_textual/app.py"

        # Other TUI files should be excluded
        included, matched = evaluate_patterns_sequential(
            Path("tui_textual/widgets/dialogs.py"), patterns
        )
        assert included is False
        assert matched == "!**/tui_textual/**"

        # Non-TUI files should be included
        included, matched = evaluate_patterns_sequential(Path("cli.py"), patterns)
        assert included is True
        assert matched == "**/*.py"

    def test_re_inclusion_xml_example(self):
        """Re-inclusion example from specification"""
        patterns = [
            "**/*.xml",  # Include all XML
            "!**/confs/*.xml",  # Exclude confs directory
            "**/confs/my-settings.xml",  # But include my-settings.xml
        ]

        # my-settings.xml should be included
        included, matched = evaluate_patterns_sequential(
            Path("confs/my-settings.xml"), patterns
        )
        assert included is True
        assert matched == "**/confs/my-settings.xml"

        # Other confs files should be excluded
        included, matched = evaluate_patterns_sequential(
            Path("confs/other.xml"), patterns
        )
        assert included is False
        assert matched == "!**/confs/*.xml"

        # Non-confs XML should be included
        included, matched = evaluate_patterns_sequential(Path("data.xml"), patterns)
        assert included is True
        assert matched == "**/*.xml"

    def test_no_match(self):
        """File doesn't match any pattern"""
        patterns = ["**/*.py"]
        included, matched = evaluate_patterns_sequential(Path("main.tcss"), patterns)

        assert included is False
        assert matched is None

    def test_last_match_wins(self):
        """Last matching pattern wins"""
        patterns = [
            "**/*.py",  # Include
            "!**/*.py",  # Exclude all
            "cli.py",  # Include cli.py specifically
        ]

        # cli.py matches last pattern
        included, matched = evaluate_patterns_sequential(Path("cli.py"), patterns)
        assert included is True
        assert matched == "cli.py"

        # config.py matches second-to-last pattern (exclusion)
        included, matched = evaluate_patterns_sequential(Path("config.py"), patterns)
        assert included is False
        assert matched == "!**/*.py"

    def test_exclusion_only_patterns(self):
        """Only exclusion patterns (nothing should be included)"""
        patterns = ["!**/__pycache__/**", "!**/*.pyc"]
        included, matched = evaluate_patterns_sequential(
            Path("__pycache__/cli.cpython-314.pyc"), patterns
        )

        assert included is False

    def test_complex_pattern_chain(self):
        """Complex pattern chain with multiple re-inclusions"""
        patterns = [
            "**/*",  # Include all
            "!**/__pycache__/**",  # Exclude pycache
            "!**/tui_textual/**",  # Exclude TUI
            "**/tui_textual/__init__.py",  # Include TUI __init__.py
            "**/tui_textual/app.py",  # Include TUI app.py
        ]

        # __init__.py in TUI should be included
        included, _ = evaluate_patterns_sequential(
            Path("tui_textual/__init__.py"), patterns
        )
        assert included is True

        # app.py in TUI should be included
        included, _ = evaluate_patterns_sequential(Path("tui_textual/app.py"), patterns)
        assert included is True

        # Other TUI files should be excluded
        included, _ = evaluate_patterns_sequential(
            Path("tui_textual/widgets/dialogs.py"), patterns
        )
        assert included is False

        # pycache should be excluded
        included, _ = evaluate_patterns_sequential(
            Path("__pycache__/cli.cpython-314.pyc"), patterns
        )
        assert included is False

        # Regular files should be included
        included, _ = evaluate_patterns_sequential(Path("cli.py"), patterns)
        assert included is True


class TestRealWorldPatterns:
    """Real-world pattern scenarios using triton_dotfiles structure"""

    def test_all_python_files(self):
        """Collect all Python files"""
        patterns = ["**/*.py"]
        test_files = [
            ("cli.py", True),
            ("config.py", True),
            ("managers/file_manager.py", True),
            ("tui_textual/widgets/dialogs.py", True),
            ("tui_textual/styles/main.tcss", False),
        ]

        for path, expected in test_files:
            included, _ = evaluate_patterns_sequential(Path(path), patterns)
            assert included is expected, f"Failed for {path}"

    def test_exclude_pycache(self):
        """Exclude __pycache__ directories"""
        patterns = ["**/*.py", "!**/__pycache__/**"]
        test_files = [
            ("cli.py", True),
            ("managers/file_manager.py", True),
            ("__pycache__/cli.cpython-314.pyc", False),
            ("managers/__pycache__/file_manager.cpython-314.pyc", False),
        ]

        for path, expected in test_files:
            included, _ = evaluate_patterns_sequential(Path(path), patterns)
            assert included is expected, f"Failed for {path}"

    def test_managers_only(self):
        """Collect only managers module files"""
        patterns = ["managers/**/*.py", "!**/__pycache__/**"]
        test_files = [
            ("managers/file_manager.py", True),
            ("managers/git_manager.py", True),
            ("managers/__init__.py", True),
            ("cli.py", False),
            ("encryption/real.py", False),
            ("managers/__pycache__/file_manager.cpython-314.pyc", False),
        ]

        for path, expected in test_files:
            included, _ = evaluate_patterns_sequential(Path(path), patterns)
            assert included is expected, f"Failed for {path}"

    def test_exclude_tui_except_app(self):
        """Exclude TUI module except app.py"""
        patterns = [
            "**/*.py",
            "!**/tui_textual/**",
            "**/tui_textual/app.py",
            "!**/__pycache__/**",
        ]
        test_files = [
            ("cli.py", True),
            ("managers/file_manager.py", True),
            ("tui_textual/app.py", True),
            ("tui_textual/__init__.py", False),
            ("tui_textual/widgets/dialogs.py", False),
        ]

        for path, expected in test_files:
            included, _ = evaluate_patterns_sequential(Path(path), patterns)
            assert included is expected, f"Failed for {path}"

    def test_multiple_extensions(self):
        """Collect multiple file types"""
        patterns = ["**/*.py", "**/*.tcss", "**/*.yml"]
        test_files = [
            ("cli.py", True),
            ("tui_textual/styles/main.tcss", True),
            ("config.yml", True),
            ("README.md", False),
        ]

        for path, expected in test_files:
            included, _ = evaluate_patterns_sequential(Path(path), patterns)
            assert included is expected, f"Failed for {path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
