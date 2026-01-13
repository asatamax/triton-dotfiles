"""
Status bar widget for the Textual TUI.

Displays the full path of the currently selected file and update notifications.
"""

from textual.widgets import Static
from rich.text import Text


class StatusBar(Static):
    """Status bar widget that displays file path and update notifications.

    Shows the full local path when viewing the current machine's files,
    or the repository-relative path with a [repo] prefix when viewing
    files from other machines. Also displays update notification on the right
    if a new version is available.

    Attributes:
        _current_path: The currently displayed path.
        _is_current_machine: Whether the selected machine is the current one.
        _update_message: Optional update notification message.
    """

    def __init__(self) -> None:
        """Initialize the status bar with empty content."""
        super().__init__("")
        self._current_path: str = ""
        self._is_current_machine: bool = True
        self._update_message: str | None = None

    def set_update_message(self, message: str | None) -> None:
        """Set the update notification message.

        Args:
            message: Update message like "Update available: v1.0.1" or None to clear.
        """
        self._update_message = message
        self._refresh_display()

    def update_path(self, path: str, is_current_machine: bool = True) -> None:
        """Update the displayed path.

        Args:
            path: The path to display.
            is_current_machine: If True, displays the full local path.
                If False, displays the repo-relative path with [repo] prefix.
        """
        self._current_path = path
        self._is_current_machine = is_current_machine
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the status bar display with current path and update message."""
        # Build left side (path)
        if self._current_path:
            if self._is_current_machine:
                left_text = self._current_path
            else:
                left_text = f"[repo] {self._current_path}"
        else:
            left_text = ""

        # If no update message, just show the path
        if not self._update_message:
            self.update(left_text)
            return

        # Build rich text with path on left, update message on right
        text = Text()
        text.append(left_text)

        # Calculate padding to right-align update message
        # Get terminal width (approximate, will be adjusted by Textual)
        try:
            width = self.size.width
        except Exception:
            width = 80  # fallback

        # Calculate needed padding
        left_len = len(left_text)
        right_len = len(self._update_message)
        padding = max(1, width - left_len - right_len - 2)

        text.append(" " * padding)
        text.append(self._update_message, style="bold yellow")

        self.update(text)

    def clear(self) -> None:
        """Clear the path display (keeps update message)."""
        self._current_path = ""
        self._refresh_display()

    def on_resize(self, event) -> None:
        """Handle resize to recalculate padding."""
        self._refresh_display()
