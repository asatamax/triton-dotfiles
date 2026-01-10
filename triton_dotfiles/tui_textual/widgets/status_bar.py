"""
Status bar widget for the Textual TUI.

Displays the full path of the currently selected file.
"""

from textual.widgets import Static


class StatusBar(Static):
    """Status bar widget that displays the path of the currently selected file.

    Shows the full local path when viewing the current machine's files,
    or the repository-relative path with a [repo] prefix when viewing
    files from other machines.

    Attributes:
        _current_path: The currently displayed path.
        _is_current_machine: Whether the selected machine is the current one.
    """

    def __init__(self) -> None:
        """Initialize the status bar with empty content."""
        super().__init__("")
        self._current_path: str = ""
        self._is_current_machine: bool = True

    def update_path(self, path: str, is_current_machine: bool = True) -> None:
        """Update the displayed path.

        Args:
            path: The path to display.
            is_current_machine: If True, displays the full local path.
                If False, displays the repo-relative path with [repo] prefix.
        """
        self._current_path = path
        self._is_current_machine = is_current_machine

        if path:
            if is_current_machine:
                display_text = path
            else:
                display_text = f"[repo] {path}"
            self.update(display_text)
        else:
            self.update("")

    def clear(self) -> None:
        """Clear the path display."""
        self._current_path = ""
        self.update("")
