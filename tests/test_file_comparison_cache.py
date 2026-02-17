#!/usr/bin/env python3
"""
Cache behavior tests for FileComparisonManager.
"""

from pathlib import Path

from triton_dotfiles.managers.file_comparison_manager import FileComparisonManager


def test_hash_cache_invalidates_when_mtime_or_size_changes(tmp_path: Path):
    """Updated file content must not reuse stale hash cache entry."""
    manager = FileComparisonManager()
    test_file = tmp_path / "sample.txt"
    test_file.write_text("before")

    hash_before = manager._calculate_file_hash(test_file)
    assert hash_before is not None

    test_file.write_text("after with different size")
    hash_after = manager._calculate_file_hash(test_file)

    assert hash_after is not None
    assert hash_before != hash_after


def test_hash_cache_reuses_value_for_same_file_state(tmp_path: Path):
    """Cache should be reused while file metadata and content stay unchanged."""
    manager = FileComparisonManager()
    test_file = tmp_path / "stable.txt"
    test_file.write_text("unchanged")

    hash_first = manager._calculate_file_hash(test_file)
    hash_second = manager._calculate_file_hash(test_file)

    assert hash_first is not None
    assert hash_first == hash_second
    assert len(manager._hash_cache) == 1
