"""
Main Textual application for triton-dotfiles TUI
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer
from textual.command import Hit, Hits, Provider
from rich.text import Text

from .screens.main_screen import MainScreen
from .screens.startup_screen import StartupScreen, StartupComplete
from .widgets.status_bar import StatusBar
from ..__version__ import get_version


class TritonCommandProvider(Provider):
    """Custom command provider for Triton TUI."""

    async def search(self, query: str) -> Hits:
        """Search commands."""
        matcher = self.matcher(query)

        commands = [
            (
                "Show in Finder",
                self.app.action_show_in_finder,
                "Show current file in Finder (macOS only)",
            ),
            (
                "Git Pull",
                self.app.action_git_pull,
                "Pull latest changes from git repository",
            ),
            (
                "Git Commit Push",
                self.app.action_git_commit_push,
                "Commit and push changes to remote repository",
            ),
            (
                "Backup",
                self.app.action_backup,
                "Backup current machine files to repository",
            ),
            (
                "Cleanup Repository",
                self.app.action_cleanup_repository,
                "Delete orphaned files from repository (current machine only)",
            ),
            (
                "Select Machine",
                self.app.action_select_machine,
                "Select a different machine/backup",
            ),
            (
                "Export Files",
                self.app.action_export_files,
                "Export selected files to directory",
            ),
            (
                "Restore Files",
                self.app.action_restore_files,
                "Restore selected files to local system",
            ),
            (
                "VSCode Diff",
                self.app.action_open_vscode_diff,
                "Open local vs database diff in VSCode/Cursor/Windsurf",
            ),
            (
                "Edit in VSCode",
                self.app.action_open_vscode_edit,
                "Edit local file directly in VSCode/Cursor/Windsurf",
            ),
            ("Refresh", self.app.action_refresh, "Refresh the current view"),
            (
                "Show Help",
                self.app.action_show_help,
                "Show keyboard shortcuts and help",
            ),
            (
                "Show Config in Finder",
                self.app.action_show_config_in_finder,
                "Show config.yml file in Finder (macOS only)",
            ),
            (
                "Show Repository in Finder",
                self.app.action_show_repository_in_finder,
                "Show repository folder in Finder (macOS only)",
            ),
            (
                "Show Archive in Finder",
                self.app.action_show_archive_in_finder,
                "Show archives folder in Finder (macOS only)",
            ),
        ]

        for command_name, callback, help_text in commands:
            score = matcher.match(command_name)
            if score > 0:
                yield Hit(
                    score, matcher.highlight(command_name), callback, help=help_text
                )


class TritonTUIApp(App):
    """Triton TUI メインアプリケーション"""

    CSS_PATH = "styles/main.tcss"
    COMMANDS = App.COMMANDS | {TritonCommandProvider}

    def __init__(self, skip_startup: bool = False):
        super().__init__()
        self.skip_startup = skip_startup

    BINDINGS = [
        # システム
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("?", "show_help", "Help"),
        # ナビゲーション
        Binding("left", "focus_left", "Focus Left"),
        Binding("right", "focus_right", "Focus Right"),
        # ファイル操作
        Binding("space", "toggle_selection", "Toggle"),
        Binding("enter", "select_file", "Select"),
        # 表示モード
        Binding("p", "toggle_preview", "Prev"),
        Binding("l", "toggle_local", "Local"),
        Binding("d", "toggle_diff", "Diff"),
        Binding("i", "toggle_info", "Info"),
        Binding("s", "toggle_split", "Split"),
        # 数字キーでタブ切り替え（フッターには表示しない）
        Binding("1", "toggle_preview", "Tab 1", show=False),
        Binding("2", "toggle_local", "Tab 2", show=False),
        Binding("3", "toggle_diff", "Tab 3", show=False),
        Binding("4", "toggle_info", "Tab 4", show=False),
        Binding("5", "toggle_split", "Tab 5", show=False),
        Binding("D", "open_vscode_diff", "VSCode Diff"),
        Binding("E", "open_vscode_edit", "Edit in VSCode"),
        # アクション
        Binding("R", "restore_files", "Restore"),
        Binding("x", "export_files", "Export"),
        Binding("B", "backup", "Backup"),
        Binding("P", "git_pull", "Git Pull"),
        Binding("C", "git_commit_push", "Git Commit Push"),
        Binding("ctrl+r", "refresh", "Refresh", show=False),
        # マシン選択
        Binding("m", "select_machine", "Select Machine"),
        # ファイル操作
        Binding("F", "show_in_finder", "Finder"),
        # UI 操作
        Binding("t", "toggle_left_pane", "Toggle Pane"),
    ]

    def compose(self) -> ComposeResult:
        """アプリケーションのレイアウトを構成"""
        header = Header()
        header.tall = True
        yield header
        if self.skip_startup:
            # skip_startup時は直接MainScreenを表示
            yield MainScreen(skip_startup=True)
        else:
            # 通常起動時はStartupScreenを表示
            yield StartupScreen()
        yield StatusBar()
        yield Footer()

    async def on_startup_complete(self, message: StartupComplete) -> None:
        """StartupScreen完了時のハンドラ"""
        try:
            startup_screen = self.query_one(StartupScreen)
            header = self.query_one(Header)

            # StartupScreenを即座に非表示にしてから処理
            startup_screen.display = False

            # MainScreenをマウント
            main_screen = MainScreen(skip_startup=True)
            await self.mount(main_screen, after=header)

            # StartupScreenを削除（既に非表示なので見た目には影響しない）
            await startup_screen.remove()
        except Exception:
            pass

    def on_mount(self) -> None:
        """アプリケーション起動時の初期化"""
        version = get_version()
        self.title = f"Triton TUI Browser {version}"
        self.sub_title = "Dotfiles Management"

        # Check for updates in background (non-blocking)
        self.run_worker(self._check_for_updates, exclusive=False)

    async def _check_for_updates(self) -> None:
        """Check for updates in background and update status bar."""
        try:
            from ..version_check import get_update_message

            # Run in thread to avoid blocking (network I/O)
            import asyncio

            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(None, get_update_message)

            if message:
                # Update status bar on main thread
                self.call_from_thread(self._set_update_message, message)
        except Exception:
            # Silently ignore any errors during version check
            pass

    def _set_update_message(self, message: str) -> None:
        """Set update message on status bar (called from main thread)."""
        try:
            from .widgets.status_bar import StatusBar

            status_bar = self.query_one(StatusBar)
            status_bar.set_update_message(message)
        except Exception:
            pass

    def action_show_help(self) -> None:
        """ヘルプを表示"""
        from .widgets.dialogs import MessageDialog

        help_text = Text()

        def section(title: str) -> None:
            """セクションヘッダーを追加"""
            help_text.append(f"\n{title}\n", style="bold cyan")

        def key_line(key: str, desc: str) -> None:
            """キーバインド行を追加"""
            help_text.append(f"  {key:<10}", style="bold green")
            help_text.append(f"{desc}\n")

        # タイトル
        help_text.append("Keyboard Shortcuts\n", style="bold")

        section("Navigation")
        key_line("↑/↓", "Move up/down in file list")
        key_line("←", "Focus left pane")
        key_line("→", "Focus right pane")

        section("File Operations")
        key_line("Space", "Toggle file selection")
        key_line("Enter", "Select/view file")
        key_line("R", "Restore selected files")
        key_line("x", "Export selected files")
        key_line("B", "Backup current machine")
        key_line("/", "Filter files")

        section("View Modes")
        key_line("p", "Preview view")
        key_line("l", "Local file view")
        key_line("d", "Diff view")
        key_line("i", "File info view")
        key_line("s", "Split view (Local + Preview)")
        key_line("1-5", "Quick tab switching")

        section("External Editor")
        key_line("D", "VSCode Diff - Compare local vs database")
        key_line("E", "VSCode Edit - Edit local file directly")

        section("System")
        key_line("m", "Select machine")
        key_line("P", "Git pull repository")
        key_line("C", "Git commit push")
        key_line("F", "Show in Finder (macOS)")
        key_line("t", "Toggle left pane visibility")
        key_line("Ctrl+R", "Refresh data")
        key_line("Ctrl+P", "Command palette")
        key_line("?", "Show this help")
        key_line("q", "Quit")

        section("Multi-selection")
        help_text.append("  Use ", style="dim")
        help_text.append("Space", style="bold green")
        help_text.append(" to select multiple files, then ", style="dim")
        help_text.append("R", style="bold green")
        help_text.append(" or ", style="dim")
        help_text.append("x", style="bold green")
        help_text.append(" to operate.\n", style="dim")

        self.push_screen(MessageDialog("Help", help_text, "info"))

    def action_select_machine(self) -> None:
        """マシン選択ダイアログを開く"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.show_machine_select_dialog())

    def action_toggle_diff(self) -> None:
        """差分表示モードに切り替え"""
        main_screen = self.query_one(MainScreen)
        main_screen.set_view_mode("diff")

    def action_toggle_preview(self) -> None:
        """プレビューモードに切り替え"""
        main_screen = self.query_one(MainScreen)
        main_screen.set_view_mode("preview")

    def action_toggle_local(self) -> None:
        """ローカルファイル表示モードに切り替え"""
        main_screen = self.query_one(MainScreen)
        main_screen.set_view_mode("local")

    def action_toggle_info(self) -> None:
        """情報表示モードに切り替え"""
        main_screen = self.query_one(MainScreen)
        main_screen.set_view_mode("info")

    def action_toggle_split(self) -> None:
        """スプリット表示モードに切り替え"""
        main_screen = self.query_one(MainScreen)
        main_screen.set_view_mode("split")

    def action_toggle_left_pane(self) -> None:
        """左ペインの表示/非表示を切り替え"""
        main_screen = self.query_one(MainScreen)
        main_screen.toggle_left_pane()

    def action_open_vscode_diff(self) -> None:
        """VSCodeで差分表示を開く"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.open_vscode_diff())

    def action_open_vscode_edit(self) -> None:
        """VSCodeでローカルファイルを編集する"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.open_vscode_edit())

    def action_toggle_selection(self) -> None:
        """ファイル選択をトグル"""
        main_screen = self.query_one(MainScreen)
        main_screen.toggle_file_selection()

    def action_restore_files(self) -> None:
        """ファイル復元を実行"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.restore_files())

    def action_export_files(self) -> None:
        """ファイルエクスポートを実行"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.export_files())

    def action_refresh(self) -> None:
        """画面を更新（マシン選択を維持）"""
        main_screen = self.query_one(MainScreen)
        main_screen._refresh_data_preserve_machine()

    def action_git_pull(self) -> None:
        """Git pullを実行"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.git_pull_repository())

    def action_show_in_finder(self) -> None:
        """ファイルをFinderで表示"""
        main_screen = self.query_one(MainScreen)
        main_screen.show_in_finder()

    def action_show_config_in_finder(self) -> None:
        """Config.ymlファイルをFinderで表示"""
        main_screen = self.query_one(MainScreen)
        main_screen.show_config_in_finder()

    def action_show_repository_in_finder(self) -> None:
        """リポジトリフォルダをFinderで表示"""
        main_screen = self.query_one(MainScreen)
        main_screen.show_repository_in_finder()

    def action_show_archive_in_finder(self) -> None:
        """アーカイブフォルダをFinderで表示"""
        main_screen = self.query_one(MainScreen)
        main_screen.show_archive_in_finder()

    def action_backup(self) -> None:
        """バックアップを実行"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.backup_current_machine())

    def action_git_commit_push(self) -> None:
        """Git commit pushを実行"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.git_commit_push_repository())

    def action_cleanup_repository(self) -> None:
        """リポジトリクリーンアップを実行"""
        main_screen = self.query_one(MainScreen)
        self.run_worker(main_screen.cleanup_repository())


def run_textual_tui(skip_startup: bool = False):
    """Textual TUIを実行"""
    app = TritonTUIApp(skip_startup=skip_startup)
    app.run()
