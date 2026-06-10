"""
Dialog widgets for the Textual TUI
"""

from typing import Dict, List, Optional, Tuple, Union

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    Static,
)


class BaseDialog(ModalScreen):
    """全ダイアログ共通の基底クラス

    共通CSS（コンテナ/ボタン/キーヒント）、ステータスアイコン・色マップを
    一元管理する。個別のレイアウトとキーハンドリングはサブクラスが持つ。
    """

    ICONS = {
        "success": "✓",
        "partial": "!",
        "error": "✗",
        "warning": "⚠",
        "info": "ℹ",
    }

    COLORS = {
        "success": "green",
        "partial": "yellow",
        "error": "red",
        "warning": "yellow",
        "info": "blue",
    }

    DEFAULT_CSS = """
    BaseDialog {
        align: center middle;
    }

    BaseDialog .dialog-container {
        width: 80;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    BaseDialog .dialog-content {
        height: auto;
        margin: 1 0;
        width: 1fr;
    }

    BaseDialog .dialog-buttons {
        height: 3;
        align: center middle;
    }

    BaseDialog .dialog-buttons Button {
        margin: 0 1;
        min-width: 8;
    }

    BaseDialog .dialog-key-hints {
        height: 1;
        width: 1fr;
        text-align: center;
        color: $text-muted;
    }
    """

    def _icon_text(self, message_type: str, label: str = "") -> Text:
        """ステータスアイコン付きテキストを生成"""
        icon = self.ICONS.get(message_type, self.ICONS["info"])
        color = self.COLORS.get(message_type, "white")
        text = Text()
        text.append(icon, style=f"bold {color}")
        if label:
            text.append(f" {label}", style=f"bold {color}")
        return text


class ConfirmationDialog(BaseDialog):
    """確認ダイアログ（Yes/No）

    Args:
        title: ダイアログタイトル
        message: メイン メッセージ
        submessage: 補足説明（dim表示）
        file_list: 対象ファイル一覧（指定時は先頭数件を表示）
        destructive: ローカル破壊系操作（Restore上書き等）の場合True。
            デフォルトフォーカスがNo側になる。
    """

    MAX_LIST_ITEMS = 8

    DEFAULT_CSS = """
    ConfirmationDialog .dialog-content {
        text-align: center;
    }

    ConfirmationDialog .dialog-content Label {
        text-wrap: wrap;
        width: 1fr;
    }

    ConfirmationDialog .dialog-file-list {
        margin: 1 2 0 2;
        height: auto;
        max-height: 10;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        submessage: str = "",
        file_list: Optional[List[str]] = None,
        destructive: bool = False,
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.submessage = submessage
        self.file_list = file_list or []
        self.destructive = destructive

    def _build_file_list_text(self) -> Text:
        text = Text()
        for name in self.file_list[: self.MAX_LIST_ITEMS]:
            text.append("• ", style="dim")
            text.append(f"{name}\n")
        remaining = len(self.file_list) - self.MAX_LIST_ITEMS
        if remaining > 0:
            text.append(f"... and {remaining} more", style="dim")
        return text

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label(self.title, classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        yield Label(self.message)
                        if self.file_list:
                            yield Static(
                                self._build_file_list_text(),
                                classes="dialog-file-list",
                            )
                        if self.submessage:
                            yield Label(Text(self.submessage, style="dim"))

                    with Horizontal(classes="dialog-buttons"):
                        yield Button("Yes", variant="primary", id="yes-button")
                        yield Button("No", variant="default", id="no-button")

    def on_mount(self) -> None:
        # 破壊的操作は安全側（No）をデフォルトフォーカスにする
        if self.destructive:
            self.query_one("#no-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-button":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss(True)
        elif event.key in ("n", "escape"):
            self.dismiss(False)


class InputDialog(BaseDialog):
    """入力ダイアログ"""

    DEFAULT_CSS = """
    InputDialog .dialog-container {
        width: 60;
    }

    InputDialog .dialog-input {
        margin: 1 0;
    }
    """

    def __init__(self, title: str, prompt: str, default_value: str = ""):
        super().__init__()
        self.title = title
        self.prompt = prompt
        self.default_value = default_value

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label(self.title, classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        yield Label(self.prompt)
                        self.input_field = Input(
                            value=self.default_value, classes="dialog-input"
                        )
                        yield self.input_field

                    with Horizontal(classes="dialog-buttons"):
                        yield Button("OK", variant="primary", id="ok-button")
                        yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self) -> None:
        self.input_field.focus()

    def _submit_value(self, raw_value: str) -> None:
        value = raw_value.strip()
        self.dismiss(value if value else None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok-button":
            self._submit_value(self.input_field.value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit_value(event.value)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class MessageDialog(BaseDialog):
    """メッセージダイアログ（Enter/Escで閉じる）"""

    DEFAULT_CSS = """
    MessageDialog .dialog-container {
        width: 90;
    }

    MessageDialog .dialog-content {
        text-align: left;
    }
    """

    def __init__(
        self, title: str, message: Union[str, Text], message_type: str = "info"
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.message_type = message_type

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label(self.title, classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        icon_text = self._icon_text(self.message_type)
                        icon_text.append(" ")
                        if isinstance(self.message, Text):
                            icon_text.append_text(self.message)
                        else:
                            icon_text.append(str(self.message))
                        yield Label(icon_text)

                    with Horizontal(classes="dialog-buttons"):
                        yield Button("OK", variant="primary", id="ok-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def on_key(self, event) -> None:
        if event.key in ("enter", "escape", "space"):
            self.dismiss()


class ThreeChoiceDialog(BaseDialog):
    """3択ダイアログ（Yes/Dry Run/No）

    Args:
        default: デフォルトフォーカスする選択肢（"yes" / "dry" / "no"）。
            同期を前進させる操作はyes、破壊的操作はdry/noを指定する。
    """

    DEFAULT_CSS = """
    ThreeChoiceDialog .dialog-content {
        text-align: center;
    }

    ThreeChoiceDialog .dialog-content Label {
        text-wrap: wrap;
        width: 1fr;
    }

    ThreeChoiceDialog .dialog-buttons Button {
        min-width: 10;
    }
    """

    def __init__(
        self, title: str, message: str, submessage: str = "", default: str = "yes"
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.submessage = submessage
        self.default = default if default in ("yes", "dry", "no") else "yes"

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label(self.title, classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        yield Label(self.message)
                        if self.submessage:
                            yield Label(Text(self.submessage, style="dim"))

                    with Horizontal(classes="dialog-buttons"):
                        yield Button("Yes", variant="primary", id="yes-button")
                        yield Button("Dry Run", variant="default", id="dry-button")
                        yield Button("No", variant="default", id="no-button")

    def on_mount(self) -> None:
        self.query_one(f"#{self.default}-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-button":
            self.dismiss("yes")
        elif event.button.id == "dry-button":
            self.dismiss("dry")
        else:
            self.dismiss("no")

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss("yes")
        elif event.key == "d":
            self.dismiss("dry")
        elif event.key in ("n", "escape"):
            self.dismiss("no")


class ProgressDialog(BaseDialog):
    """プログレスダイアログ"""

    DEFAULT_CSS = """
    ProgressDialog .dialog-container {
        width: 60;
    }

    ProgressDialog .progress-container {
        margin: 1 0;
    }
    """

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label(self.title, classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        yield Label(self.message, id="progress-message")
                        with Vertical(classes="progress-container"):
                            self.progress_bar = ProgressBar(show_eta=False)
                            yield self.progress_bar

    def update_progress(self, percentage: float, message: str = None):
        """プログレスを更新"""
        self.progress_bar.progress = percentage
        if message:
            self.query_one("#progress-message", Label).update(message)


class MachineSelectDialog(BaseDialog):
    """マシン選択ダイアログ"""

    DEFAULT_CSS = """
    MachineSelectDialog .dialog-container {
        width: 60;
        height: 20;
    }

    MachineSelectDialog .dialog-content {
        height: 1fr;
    }

    MachineSelectDialog .machine-list {
        height: 1fr;
        border: solid $primary;
    }
    """

    def __init__(
        self, machines: List[Dict], current_machine_id: str = "", file_adapter=None
    ):
        super().__init__()
        self.machines = machines
        self.current_machine_id = current_machine_id
        self.file_adapter = file_adapter
        self.selected_machine = None

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label("Select Machine", classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        self.machine_list = ListView(classes="machine-list")
                        yield self.machine_list

                    with Horizontal(classes="dialog-buttons"):
                        yield Button("Select", variant="primary", id="select-button")
                        yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self) -> None:
        # 現在のマシン名を取得
        current_machine_name = None
        if self.file_adapter:
            try:
                current_machine_name = (
                    self.file_adapter.config_manager.get_machine_name()
                )
            except Exception:
                pass

        # マシン一覧を追加
        for i, machine in enumerate(self.machines):
            description = machine.get(
                "description", f"{machine.get('file_count', 0)} files"
            )

            # 現在のマシンかどうか判定
            is_current_machine = (
                (machine["name"] == current_machine_name)
                if current_machine_name
                else False
            )
            is_selected = machine["id"] == self.current_machine_id

            if is_current_machine:
                # 現在のマシンは星と装飾付き
                item_text = Text.assemble(
                    ("🌟 ", "bold yellow"),
                    (machine["name"], "bold green"),
                    (" (Current)", "dim cyan"),
                    (f" ({description})", "dim"),
                )
            else:
                # 他のマシンは通常表示
                item_text = Text(f"💾 {machine['name']} ({description})")

            item = ListItem(Label(item_text))
            self.machine_list.append(item)

            if is_selected:
                # 選択されたマシンにフォーカスを設定
                self.machine_list.index = i

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if 0 <= event.index < len(self.machines):
            self.selected_machine = self.machines[event.index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-button":
            if self.selected_machine:
                self.dismiss(self.selected_machine)
            else:
                # 何も選択されていない場合は現在の選択を使用
                if (
                    hasattr(self.machine_list, "index")
                    and self.machine_list.index is not None
                ):
                    index = self.machine_list.index
                    if 0 <= index < len(self.machines):
                        self.dismiss(self.machines[index])
                else:
                    self.dismiss(None)
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "enter":
            # 現在選択されているマシンを返す
            if (
                hasattr(self.machine_list, "index")
                and self.machine_list.index is not None
            ):
                index = self.machine_list.index
                if 0 <= index < len(self.machines):
                    self.dismiss(self.machines[index])
        elif event.key == "escape":
            self.dismiss(None)


class ScrollableMessageDialog(BaseDialog):
    """スクロール可能な詳細メッセージダイアログ（閉じるだけの情報表示）"""

    DEFAULT_CSS = """
    ScrollableMessageDialog .dialog-container {
        width: 90;
        height: 30;
    }

    ScrollableMessageDialog .dialog-header {
        height: 3;
        text-align: center;
        margin-bottom: 1;
    }

    ScrollableMessageDialog .dialog-content {
        height: 1fr;
    }

    ScrollableMessageDialog .content-area {
        height: 1fr;
        border: solid $primary;
        scrollbar-gutter: stable;
    }

    ScrollableMessageDialog .dialog-buttons {
        margin-top: 1;
    }
    """

    def __init__(
        self, title: str, message: str, details: str = "", message_type: str = "info"
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.details = details
        self.message_type = message_type

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    with Vertical(classes="dialog-header"):
                        yield Label(self._icon_text(self.message_type, self.title))

                    with Vertical(classes="dialog-content"):
                        # RichLogでANSIコード対応の表示
                        self.rich_log = RichLog(
                            highlight=False,
                            markup=False,
                            classes="content-area",
                        )
                        yield self.rich_log

                    with Horizontal(classes="dialog-buttons"):
                        yield Button("OK", variant="primary", id="ok-button")

    def on_mount(self) -> None:
        """マウント時にコンテンツを書き込む"""
        full_content = self.message
        if self.details:
            full_content += f"\n\n{self.details}"

        # ANSIコードをRich Textに変換して表示
        self.rich_log.write(Text.from_ansi(full_content))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def on_key(self, event) -> None:
        if event.key in ("enter", "escape", "space"):
            self.dismiss()


class OperationReportDialog(BaseDialog):
    """操作結果の構造化レポート + 継続アクション

    Backup/Cleanup等の結果をサマリ行・変更ファイル一覧・折りたたみ
    セクションで表示し、次のアクション（Commit & Push等）へ進める。
    閉じるだけのScrollableMessageDialogと区別するため二重枠で表示する。

    Args:
        title: タイトル（例: "Backup complete"）
        status: "success" / "partial" / "warning"
        machine_label: タイトル右に添える文脈（例: "MacBook → repo"）
        counts: サマリ行 [(ラベル, 件数, 色), ...]
        changes: 変更ファイル行 [(プレフィックス, テキスト, 色), ...]
        collapsed_sections: 折りたたみ表示 [(タイトル, 行リスト), ...]
        actions: 継続アクション [(ボタンラベル, 結果キー), ...]。
            結果キーの頭文字がショートカットキーになる。
        focus_action: Trueなら先頭アクションをデフォルトフォーカス
            （Enterで標準経路を完走できる）。破壊的アクションはFalse。
    """

    DEFAULT_CSS = """
    OperationReportDialog .dialog-container {
        width: 90;
        height: 30;
        border: double $success;
    }

    OperationReportDialog .dialog-container.status-partial,
    OperationReportDialog .dialog-container.status-warning {
        border: double $warning;
    }

    OperationReportDialog .report-title {
        height: 1;
        width: 1fr;
        text-align: center;
        margin-bottom: 1;
    }

    OperationReportDialog .report-counts {
        height: 1;
        width: 1fr;
        text-align: center;
        margin-bottom: 1;
    }

    OperationReportDialog .report-body {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    OperationReportDialog .report-body Static {
        height: auto;
        width: 1fr;
    }

    OperationReportDialog Collapsible {
        border: none;
        padding: 0;
    }

    OperationReportDialog .dialog-buttons {
        margin-top: 1;
    }

    OperationReportDialog .dialog-buttons Button {
        min-width: 14;
    }
    """

    def __init__(
        self,
        title: str,
        status: str = "success",
        machine_label: str = "",
        counts: Optional[List[Tuple[str, int, str]]] = None,
        changes: Optional[List[Tuple[str, str, str]]] = None,
        collapsed_sections: Optional[List[Tuple[str, List[str]]]] = None,
        actions: Optional[List[Tuple[str, str]]] = None,
        focus_action: bool = True,
    ):
        super().__init__()
        self.title = title
        self.status = (
            status if status in ("success", "partial", "warning") else "success"
        )
        self.machine_label = machine_label
        self.counts = counts or []
        self.changes = changes or []
        self.collapsed_sections = collapsed_sections or []
        self.actions = actions or []
        self.focus_action = focus_action
        # 結果キーの頭文字 → 結果キー（例: "c" → "commit"）
        self._key_map = {key[0]: key for _, key in self.actions}

    def _build_title_text(self) -> Text:
        text = self._icon_text(self.status, self.title)
        if self.machine_label:
            text.append(f"   {self.machine_label}", style="dim")
        return text

    def _build_counts_text(self) -> Text:
        text = Text()
        for i, (label, value, style) in enumerate(self.counts):
            if i > 0:
                text.append("   ")
            text.append(f"{label} ", style="bold cyan")
            text.append(str(value), style=f"bold {style}")
        return text

    def _build_changes_text(self) -> Text:
        text = Text()
        for i, (prefix, line, style) in enumerate(self.changes):
            if i > 0:
                text.append("\n")
            text.append(f"{prefix} ", style=f"bold {style}")
            text.append(line)
        return text

    def _build_key_hints(self) -> str:
        hints = []
        for i, (label, key) in enumerate(self.actions):
            if i == 0 and self.focus_action:
                hints.append(f"Enter: {label}")
            else:
                hints.append(f"{key[0].upper()}: {label}")
        hints.append("Esc: Close")
        return "   ·   ".join(hints)

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes=f"dialog-container status-{self.status}"):
                    yield Label(self._build_title_text(), classes="report-title")
                    if self.counts:
                        yield Static(self._build_counts_text(), classes="report-counts")

                    with VerticalScroll(classes="report-body"):
                        if self.changes:
                            yield Static(self._build_changes_text())
                        for section_title, lines in self.collapsed_sections:
                            with Collapsible(
                                title=f"{section_title} ({len(lines)})",
                                collapsed=True,
                            ):
                                yield Static(Text("\n".join(lines), style="dim"))

                    with Horizontal(classes="dialog-buttons"):
                        for i, (label, key) in enumerate(self.actions):
                            yield Button(
                                label,
                                variant="primary" if i == 0 else "default",
                                id=f"action-{key}",
                            )
                        yield Button("Close", variant="default", id="close-button")

                    yield Label(self._build_key_hints(), classes="dialog-key-hints")

    def on_mount(self) -> None:
        if self.actions and self.focus_action:
            self.query_one(f"#action-{self.actions[0][1]}", Button).focus()
        else:
            self.query_one("#close-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("action-"):
            self.dismiss(button_id.removeprefix("action-"))
        else:
            self.dismiss("close")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss("close")
        elif event.key in self._key_map:
            self.dismiss(self._key_map[event.key])
