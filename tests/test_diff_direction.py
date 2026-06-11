#!/usr/bin/env python3
"""
Restore-semantics direction tests for generate_local_backup_diff.

The diff must always answer "what happens to the local file if this
backup is restored": lines added by restore are "+", lines removed
are "-", regardless of which machine's backup is being viewed.
"""

from pathlib import Path

from triton_dotfiles.managers.file_comparison_manager import FileComparisonManager


def _generate(tmp_path: Path, local_text: str, backup_text: str) -> list[str]:
    local_file = tmp_path / "local.zshrc"
    backup_file = tmp_path / "backup.zshrc"
    local_file.write_text(local_text)
    backup_file.write_text(backup_text)

    manager = FileComparisonManager()
    result = manager.generate_local_backup_diff(
        local_file, backup_file, encrypted=False, display_name=".zshrc"
    )
    assert "error" not in result
    return result["diff_lines"]


def test_line_only_in_backup_is_shown_as_added(tmp_path: Path):
    """A line restore would add to local must appear as '+'."""
    diff_lines = _generate(
        tmp_path,
        local_text="alias a='1'\n",
        backup_text="alias a='1'\nalias b='2'\n",
    )

    assert "+alias b='2'" in diff_lines
    assert not any(line.startswith("-alias") for line in diff_lines)


def test_line_only_in_local_is_shown_as_removed(tmp_path: Path):
    """A line restore would remove from local must appear as '-'."""
    diff_lines = _generate(
        tmp_path,
        local_text="alias a='1'\nalias b='2'\n",
        backup_text="alias a='1'\n",
    )

    assert "-alias b='2'" in diff_lines
    assert not any(line.startswith("+alias") for line in diff_lines)


def test_headers_label_local_as_current_and_backup_as_result(tmp_path: Path):
    """Headers must present local as the current state and backup as the restore result."""
    diff_lines = _generate(
        tmp_path,
        local_text="old\n",
        backup_text="new\n",
    )

    assert diff_lines[0].startswith("--- local/.zshrc")
    assert diff_lines[1].startswith("+++ backup/.zshrc")
