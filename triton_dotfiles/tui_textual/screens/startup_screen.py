"""
Startup screen for the Textual TUI

Displays progress during startup sequence (hooks + git pull).
"""

import asyncio

from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.message import Message
from textual.widgets import Button, Label, Rule, Static

from ..adapters.file_adapter import TUIFileAdapter


class StartupComplete(Message):
    """起動処理完了を通知するメッセージ"""

    def __init__(self, has_errors: bool = False) -> None:
        self.has_errors = has_errors
        super().__init__()


class StartupScreen(Static):
    """起動時処理の進捗を表示するウィジェット"""

    DEFAULT_CSS = """
    StartupScreen {
        width: 100%;
        height: 1fr;
        align: center middle;
        background: $background-darken-2;
    }

    StartupScreen > Center {
        width: 100%;
    }

    StartupScreen > Center > Middle {
        width: 100%;
        align: center middle;
    }

    #startup-container {
        width: 70%;
        max-width: 120;
        height: auto;
        padding: 1 2;
        background: $surface-darken-1;
        border: heavy $primary;
    }

    #startup-logo {
        text-align: center;
        color: $primary;
        padding: 1 0;
    }

    #steps-container {
        padding: 1 0;
    }

    .step-box {
        border: round $primary-darken-2;
        padding: 0 1;
        margin: 0 1 1 1;
        height: auto;
        background: $surface-darken-1;
    }

    .step-box.status-running {
        border: round $primary;
        background: $surface;
    }

    .step-box.status-done {
        border: round $success-darken-1;
        background: $surface-darken-1;
    }

    .step-box.status-error {
        border: round $error;
        background: $surface-darken-1;
    }

    .step-box.status-skipped {
        border: round $warning-darken-1;
        background: $surface-darken-1;
    }

    .step-header {
        height: 1;
        padding: 0;
        text-style: bold;
    }

    .substep-row {
        height: 1;
        padding-left: 2;
        overflow: hidden;
    }

    .status-pending {
        color: $text-muted;
    }

    .status-running {
        color: $primary;
        text-style: bold;
    }

    .status-done {
        color: $success;
    }

    .status-error {
        color: $error;
    }

    .status-skipped {
        color: $warning;
    }

    #error-container {
        padding: 1 0;
        align: center middle;
    }

    #continue-button {
        margin-top: 1;
    }
    """

    # 状態アイコン
    ICON_PENDING = "◌"
    ICON_RUNNING = "◐"
    ICON_DONE = "✓"
    ICON_ERROR = "✗"
    ICON_SKIPPED = "⊘"

    # アニメーション用のスピナーアイコン
    SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]

    def __init__(self) -> None:
        super().__init__()
        self.file_adapter: TUIFileAdapter | None = None
        self.has_errors = False
        self.hooks_list: list[dict] = []
        self.auto_pull_enabled = False
        self._spinner_index = 0
        self._spinner_timer = None
        self._is_running = True
        self._current_running_step: str | None = None  # 現在実行中のステップID

    # アスキーアートロゴ
    LOGO = """\
▀█▀ █▀█ █ ▀█▀ █▀█ █▄ █
 █  █▀▄ █  █  █▄█ █ ▀█"""

    def compose(self) -> ComposeResult:
        """起動画面のレイアウト"""
        with Center():
            with Middle():
                with Vertical(id="startup-container"):
                    yield Static(self.LOGO, id="startup-logo")
                    yield Rule()
                    yield Vertical(id="steps-container")
                    yield Vertical(id="error-container")

    def on_mount(self) -> None:
        """画面マウント時に起動シーケンスを開始"""
        # エラーコンテナは初期状態では非表示
        self.query_one("#error-container").display = False

        # スピナーアニメーションを開始（0.15秒間隔）
        self._spinner_timer = self.set_interval(0.15, self._animate_spinner)

        # 非同期で起動シーケンスを実行
        self.run_worker(self._perform_startup())

    def _animate_spinner(self) -> None:
        """実行中のステップでスピナーアイコンをアニメーション"""
        if not self._is_running or not self._current_running_step:
            return

        self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
        icon = self.SPINNER_FRAMES[self._spinner_index]

        try:
            # 実行中のステップのヘッダーを更新
            step_header = self.query_one(f"#{self._current_running_step}", Label)
            current_text = step_header.renderable
            if isinstance(current_text, str):
                # 先頭のアイコン部分のみ更新（アイコン + スペース + テキスト）
                text_part = current_text[2:] if len(current_text) > 2 else current_text
                step_header.update(f"{icon} {text_part}")
        except Exception:
            pass

    async def _perform_startup(self) -> None:
        """起動シーケンスを実行"""
        try:
            # FileAdapterを初期化
            self.file_adapter = TUIFileAdapter()

            # テーマを適用
            self._apply_theme()

            # ステップを構築
            await self._build_steps()

            # 1. Hooks実行
            if self.hooks_list:
                await self._execute_hooks()

            # 2. Git pull実行
            if self.auto_pull_enabled:
                await self._execute_git_pull()

            # 3. 完了処理
            await self._complete_startup()

        except Exception as e:
            self.has_errors = True
            self._show_error(f"Startup failed: {str(e)}")

    def _apply_theme(self) -> None:
        """設定からテーマを適用"""
        if not self.file_adapter:
            return

        theme_name = self.file_adapter.config.tui.theme
        if theme_name:
            try:
                self.app.theme = theme_name
            except ValueError:
                pass  # 無効なテーマは無視

    async def _build_steps(self) -> None:
        """ステップUIを構築"""
        steps_container = self.query_one("#steps-container")

        # Hooks情報を取得
        if self.file_adapter and self.file_adapter.has_startup_hooks():
            hooks = self.file_adapter.config.hooks.on_startup
            self.hooks_list = [{"command": cmd, "status": "pending"} for cmd in hooks]

            # Hooksステップボックスを作成
            hooks_box = Vertical(id="hooks-box", classes="step-box status-pending")
            await steps_container.mount(hooks_box)

            # Hooksヘッダーを追加
            hooks_label = Label(
                f"{self.ICON_PENDING} Hooks (0/{len(self.hooks_list)})",
                id="hooks-step",
                classes="step-header status-pending",
            )
            await hooks_box.mount(hooks_label)

            # 各hookのサブステップを追加
            for i, hook in enumerate(self.hooks_list):
                substep = Label(
                    f"{self.ICON_PENDING} {hook['command']}",
                    id=f"hook-{i}",
                    classes="substep-row status-pending",
                )
                await hooks_box.mount(substep)

        # Auto-pull情報を取得
        if self.file_adapter and self.file_adapter.config.repository.auto_pull:
            self.auto_pull_enabled = True

            # Git pullステップボックスを作成
            git_box = Vertical(id="git-pull-box", classes="step-box status-pending")
            await steps_container.mount(git_box)

            git_label = Label(
                f"{self.ICON_PENDING} Git pull",
                id="git-pull-step",
                classes="step-header status-pending",
            )
            await git_box.mount(git_label)

    def _truncate_command(self, command: str, max_length: int = 40) -> str:
        """コマンドを短縮表示"""
        if len(command) <= max_length:
            return command
        return command[: max_length - 3] + "..."

    async def _execute_hooks(self) -> None:
        """Hooksを実行（別スレッドで非同期実行）"""
        if not self.file_adapter:
            return

        # Hooksステップを実行中に更新
        self._update_step("hooks-step", "running", f"Hooks (0/{len(self.hooks_list)})")

        # 別スレッドでhookを実行（UIをブロックしない）
        result = await asyncio.to_thread(
            self.file_adapter.run_startup_hooks_with_progress,
            on_hook_start=self._on_hook_start,
            on_hook_complete=self._on_hook_complete,
        )

        # 結果を集計
        succeeded = result.get("succeeded", 0)
        failed = result.get("failed", 0)
        skipped = result.get("skipped", 0)
        total = result.get("total", len(self.hooks_list))

        # Hooksステップを完了に更新
        if failed > 0 or skipped > 0:
            self.has_errors = True
            status = "error" if failed > 0 else "skipped"
            summary = f"Hooks ({succeeded}/{total})"
            if failed > 0:
                summary += f" - {failed} failed"
            if skipped > 0:
                summary += f" - {skipped} skipped"
            self._update_step("hooks-step", status, summary)
        else:
            self._update_step("hooks-step", "done", f"Hooks ({succeeded}/{total})")

    def _on_hook_start(self, index: int, command: str) -> None:
        """Hook開始時のコールバック（別スレッドから呼ばれる）"""
        self.app.call_from_thread(self._update_hook_status, index, "running")
        # Hooksステップのカウンターを更新
        total = len(self.hooks_list)
        self.app.call_from_thread(
            self._update_step,
            "hooks-step",
            "running",
            f"Hooks ({index}/{total})",
        )

    def _on_hook_complete(
        self, index: int, command: str, success: bool, skipped: bool = False
    ) -> None:
        """Hook完了時のコールバック（別スレッドから呼ばれる）"""
        if skipped:
            status = "skipped"
        elif success:
            status = "done"
        else:
            status = "error"
        self.app.call_from_thread(self._update_hook_status, index, status)

    def _update_hook_status(self, index: int, status: str) -> None:
        """Hook サブステップのステータスを更新"""
        try:
            hook_label = self.query_one(f"#hook-{index}", Label)
            icon = self._get_status_icon(status)
            command = self.hooks_list[index]["command"]

            hook_label.update(f"{icon} {command}")
            hook_label.set_classes(f"substep-row status-{status}")
        except Exception:
            pass  # クエリ失敗時は無視

    async def _execute_git_pull(self) -> None:
        """Git pullを実行（別スレッドで非同期実行）"""
        if not self.file_adapter:
            return

        # Git pullステップを実行中に更新
        self._update_step("git-pull-step", "running", "Git pull")

        try:
            # ワーキングディレクトリの状態を確認（別スレッドで実行）
            clean_status = await asyncio.to_thread(
                self.file_adapter.git_is_working_directory_clean
            )

            if not clean_status.get("success", False):
                self._update_step(
                    "git-pull-step",
                    "skipped",
                    f"Git pull (skipped: {clean_status.get('message', 'error')})",
                )
                return

            if not clean_status.get("is_clean", False):
                changes = []
                if clean_status.get("has_staged"):
                    changes.append("staged")
                if clean_status.get("has_unstaged"):
                    changes.append("unstaged")
                if clean_status.get("has_untracked"):
                    changes.append("untracked")
                self._update_step(
                    "git-pull-step",
                    "skipped",
                    f"Git pull (skipped: {', '.join(changes)})",
                )
                return

            # Git pullを実行（別スレッドで実行）
            result = await asyncio.to_thread(
                self.file_adapter.git_pull_repository,
                dry_run=False,
            )

            if result.get("success", False):
                output = result.get("details", result.get("message", ""))
                if "Already up to date" in output or "Already up-to-date" in output:
                    self._update_step("git-pull-step", "done", "Git pull (up to date)")
                else:
                    self._update_step("git-pull-step", "done", "Git pull (updated)")
            else:
                self.has_errors = True
                self._update_step(
                    "git-pull-step",
                    "error",
                    "Git pull (failed)",
                )

        except Exception:
            self.has_errors = True
            self._update_step("git-pull-step", "error", "Git pull (error)")

    def _update_step(self, step_id: str, status: str, text: str) -> None:
        """ステップの表示を更新"""
        try:
            step_label = self.query_one(f"#{step_id}", Label)
            icon = self._get_status_icon(status)
            step_label.update(f"{icon} {text}")
            step_label.set_classes(f"step-header status-{status}")

            # 枠（box）のスタイルも更新
            box_id = step_id.replace("-step", "-box")
            try:
                step_box = self.query_one(f"#{box_id}", Vertical)
                step_box.set_classes(f"step-box status-{status}")
            except Exception:
                pass

            # 実行中のステップを追跡（スピナーアニメーション用）
            if status == "running":
                self._current_running_step = step_id
            elif self._current_running_step == step_id:
                self._current_running_step = None

        except Exception:
            pass  # クエリ失敗時は無視

    def _get_status_icon(self, status: str) -> str:
        """ステータスに対応するアイコンを返す"""
        icons = {
            "pending": self.ICON_PENDING,
            "running": self.ICON_RUNNING,
            "done": self.ICON_DONE,
            "error": self.ICON_ERROR,
            "skipped": self.ICON_SKIPPED,
        }
        return icons.get(status, self.ICON_PENDING)

    async def _complete_startup(self) -> None:
        """起動処理を完了"""
        # スピナーアニメーションを停止
        self._is_running = False
        self._current_running_step = None
        if self._spinner_timer:
            self._spinner_timer.stop()

        if self.has_errors:
            # エラーがある場合はContinueボタンを表示
            self._show_continue_button()
        else:
            # 成功時は自動的にMainScreenへ遷移
            self.post_message(StartupComplete(has_errors=False))

    def _show_continue_button(self) -> None:
        """Continueボタンを表示"""
        error_container = self.query_one("#error-container")
        error_container.display = True

        # Continueボタンを追加
        button = Button("Continue", id="continue-button", variant="primary")
        error_container.mount(button)

    def _show_error(self, message: str) -> None:
        """エラーメッセージを表示"""
        # スピナーアニメーションを停止
        self._is_running = False
        self._current_running_step = None
        if self._spinner_timer:
            self._spinner_timer.stop()

        error_container = self.query_one("#error-container")
        error_container.display = True

        # エラーメッセージを追加
        error_label = Label(f"Error: {message}", classes="status-error")
        error_container.mount(error_label)

        # Continueボタンを追加
        button = Button("Continue", id="continue-button", variant="primary")
        error_container.mount(button)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """ボタン押下時の処理"""
        if event.button.id == "continue-button":
            self.post_message(StartupComplete(has_errors=self.has_errors))
