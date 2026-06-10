"""
Status bar widget for the Textual TUI.

Displays the selected file path (left), the repository drift indicator and
update notifications (right).
"""

from rich.cells import cell_len
from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    """Status bar with file path, git drift indicator, and update notice.

    Left side: full local path for the current machine's files, or the
    repository-relative path with a [repo] prefix for other machines.

    Right side: repository drift warning (uncommitted / unpushed / behind).
    Drift is the real risk in a sync tool, so it stays visible until the
    repository is fully synced. An update notification is appended when a
    new version is available.

    Attributes:
        _current_path: The currently displayed path.
        _is_current_machine: Whether the selected machine is the current one.
        _git_status: Latest git status summary dict, or None.
        _update_message: Optional update notification message.
    """

    def __init__(self) -> None:
        """Initialize the status bar with empty content."""
        super().__init__("")
        self._current_path: str = ""
        self._is_current_machine: bool = True
        self._git_status: dict | None = None
        self._update_message: str | None = None

    def set_update_message(self, message: str | None) -> None:
        """Set the update notification message.

        Args:
            message: Update message like "Update available: v1.0.1" or None to clear.
        """
        self._update_message = message
        self._refresh_display()

    def set_git_status(self, summary: dict | None) -> None:
        """Set the repository drift summary.

        Args:
            summary: GitManager.get_status_summary() result, or None to clear.
        """
        self._git_status = summary
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

    def _build_drift_text(self) -> Text:
        """Build the drift warning segment (empty when fully synced)."""
        text = Text()
        status = self._git_status
        if not status or not status.get("success"):
            return text

        segments: list[tuple[str, str]] = []
        if status.get("behind", 0) > 0:
            segments.append((f"↓{status['behind']} behind", "bold red"))
        if status.get("uncommitted", 0) > 0:
            segments.append((f"● {status['uncommitted']} uncommitted", "bold yellow"))
        if status.get("ahead", 0) > 0:
            segments.append((f"↑{status['ahead']} unpushed", "bold yellow"))

        for i, (label, style) in enumerate(segments):
            if i > 0:
                text.append(" │ ", style="dim")
            text.append(label, style=style)
        return text

    def _refresh_display(self) -> None:
        """Refresh the status bar with path (left) and indicators (right)."""
        if self._current_path:
            if self._is_current_machine:
                left_text = self._current_path
            else:
                left_text = f"[repo] {self._current_path}"
        else:
            left_text = ""

        # Right side: drift indicator + optional update message
        right = self._build_drift_text()
        if self._update_message:
            if right.plain:
                right.append("  ", style="dim")
            right.append(self._update_message, style="bold yellow")

        if not right.plain:
            self.update(left_text)
            return

        text = Text()
        text.append(left_text)

        try:
            width = self.size.width
        except Exception:
            width = 80  # fallback

        # cell_len: CJK等の全角文字でも右寄せがズレないようセル幅で計算
        padding = max(1, width - cell_len(left_text) - cell_len(right.plain) - 2)
        text.append(" " * padding)
        text.append_text(right)

        self.update(text)

    def clear(self) -> None:
        """Clear the path display (keeps drift indicator and update message)."""
        self._current_path = ""
        self._refresh_display()

    def on_resize(self, event) -> None:
        """Handle resize to recalculate padding."""
        self._refresh_display()
