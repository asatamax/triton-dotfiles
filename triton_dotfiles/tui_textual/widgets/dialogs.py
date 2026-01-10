"""
Dialog widgets for the Textual TUI
"""

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Center, Middle
from textual.widgets import (
    Button,
    Label,
    Input,
    ProgressBar,
    ListItem,
    ListView,
    RichLog,
)
from textual.app import ComposeResult
from textual.message import Message
from rich.text import Text
from typing import List, Dict, Union


class DialogResult(Message):
    """ダイアログの結果メッセージ"""

    def __init__(self, result: bool, data: any = None):
        self.result = result  # True: OK/Yes, False: Cancel/No
        self.data = data
        super().__init__()


class ConfirmationDialog(ModalScreen[bool]):
    """確認ダイアログ"""

    DEFAULT_CSS = """
    ConfirmationDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 80;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    .dialog-content {
        height: auto;
        text-align: center;
        margin: 1 0;
        width: 1fr;
    }
    
    .dialog-content Label {
        text-wrap: wrap;
        width: 1fr;
    }
    
    .dialog-buttons {
        height: 3;
        align: center middle;
    }
    
    .dialog-buttons Button {
        margin: 0 1;
        min-width: 8;
    }
    """

    def __init__(self, title: str, message: str, submessage: str = ""):
        super().__init__()
        self.title = title
        self.message = message
        self.submessage = submessage

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
                        yield Button("No", variant="default", id="no-button")

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


class InputDialog(ModalScreen[str]):
    """入力ダイアログ"""

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    .dialog-content {
        height: auto;
        margin: 1 0;
    }
    
    .dialog-input {
        margin: 1 0;
    }
    
    .dialog-buttons {
        height: 3;
        align: center middle;
    }
    
    .dialog-buttons Button {
        margin: 0 1;
        min-width: 8;
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok-button":
            value = self.input_field.value.strip()
            if value:
                self.dismiss(value)
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self.dismiss(value)
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class MessageDialog(ModalScreen):
    """メッセージダイアログ"""

    DEFAULT_CSS = """
    MessageDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 90;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .dialog-content {
        height: auto;
        text-align: left;
        margin: 1 0;
    }
    
    .dialog-buttons {
        height: 3;
        align: center middle;
    }
    
    .success-icon {
        color: $success;
    }
    
    .error-icon {
        color: $error;
    }
    
    .warning-icon {
        color: $warning;
    }
    
    .info-icon {
        color: $accent;
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
        # アイコンを選択
        icons = {"success": "✓", "error": "✗", "warning": "⚠", "info": "ℹ"}
        icon = icons.get(self.message_type, "ℹ")

        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    yield Label(self.title, classes="dialog-title")
                    with Vertical(classes="dialog-content"):
                        icon_text = Text()
                        # Textual組み込みの色名を使用
                        color_map = {
                            "success": "green",
                            "error": "red",
                            "warning": "yellow",
                            "info": "blue",
                        }
                        icon_color = color_map.get(self.message_type, "white")
                        icon_text.append(icon, style=icon_color)
                        icon_text.append(" ")
                        # Text objectの場合はそのまま追加（スタイル保持）
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


class ThreeChoiceDialog(ModalScreen[str]):
    """3択ダイアログ（Yes/No/Dry Run）"""

    DEFAULT_CSS = """
    ThreeChoiceDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 80;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    .dialog-content {
        height: auto;
        text-align: center;
        margin: 1 0;
        width: 1fr;
    }
    
    .dialog-content Label {
        text-wrap: wrap;
        width: 1fr;
    }
    
    .dialog-buttons {
        height: 3;
        align: center middle;
    }
    
    .dialog-buttons Button {
        margin: 0 1;
        min-width: 10;
    }
    """

    def __init__(self, title: str, message: str, submessage: str = ""):
        super().__init__()
        self.title = title
        self.message = message
        self.submessage = submessage

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


class ProgressDialog(ModalScreen):
    """プログレスダイアログ"""

    DEFAULT_CSS = """
    ProgressDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    .dialog-content {
        height: auto;
        margin: 1 0;
    }
    
    .progress-container {
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


class MachineSelectDialog(ModalScreen):
    """マシン選択ダイアログ"""

    DEFAULT_CSS = """
    MachineSelectDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 60;
        height: 20;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    .dialog-content {
        height: 1fr;
        margin: 1 0;
    }
    
    .machine-list {
        height: 1fr;
        border: solid $primary;
    }
    
    .dialog-buttons {
        height: 3;
        align: center middle;
    }
    
    .dialog-buttons Button {
        margin: 0 1;
        min-width: 8;
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
                from rich.text import Text

                item_text = Text.assemble(
                    ("🌟 ", "bold yellow"),
                    (machine["name"], "bold green"),
                    (" (Current)", "dim cyan"),
                    (f" ({description})", "dim"),
                )
            else:
                # 他のマシンは通常表示
                from rich.text import Text

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


class ScrollableMessageDialog(ModalScreen):
    """スクロール可能な詳細メッセージダイアログ"""

    DEFAULT_CSS = """
    ScrollableMessageDialog {
        align: center middle;
    }

    .dialog-container {
        width: 90;
        height: 30;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .dialog-header {
        height: 3;
        text-align: center;
        margin-bottom: 1;
    }

    .dialog-content {
        height: 1fr;
        margin: 1 0;
    }

    .content-area {
        height: 1fr;
        border: solid $primary;
        scrollbar-gutter: stable;
    }

    .dialog-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    .success-title {
        color: $success;
    }

    .error-title {
        color: $error;
    }

    .warning-title {
        color: $warning;
    }

    .info-title {
        color: $accent;
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
        # アイコンを選択
        icons = {"success": "✓", "error": "✗", "warning": "⚠", "info": "ℹ"}
        icon = icons.get(self.message_type, "ℹ")
        title_class = f"{self.message_type}-title"

        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    with Vertical(classes="dialog-header"):
                        icon_text = Text()
                        # Textual組み込みの色名を使用
                        color_map = {
                            "success": "green",
                            "error": "red",
                            "warning": "yellow",
                            "info": "blue",
                        }
                        icon_color = color_map.get(self.message_type, "white")
                        icon_text.append(
                            f"{icon} {self.title}", style=f"bold {icon_color}"
                        )
                        yield Label(icon_text, classes=title_class)

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
        # コンテンツを結合
        full_content = self.message
        if self.details:
            full_content += f"\n\n{self.details}"

        # ANSIコードをRich Textに変換して表示
        rich_text = Text.from_ansi(full_content)
        self.rich_log.write(rich_text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def on_key(self, event) -> None:
        if event.key in ("enter", "escape", "space"):
            self.dismiss()


class BackupSuccessDialog(ModalScreen[str]):
    """バックアップ成功後のダイアログ（Commit&Push遷移オプション付き）"""

    DEFAULT_CSS = """
    BackupSuccessDialog {
        align: center middle;
    }

    .dialog-container {
        width: 90;
        height: 30;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    .dialog-header {
        height: 3;
        text-align: center;
        margin-bottom: 1;
    }

    .dialog-content {
        height: 1fr;
        margin: 1 0;
    }

    .content-area {
        height: 1fr;
        border: solid $primary;
        scrollbar-gutter: stable;
    }

    .dialog-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    .dialog-buttons Button {
        margin: 0 1;
        min-width: 14;
    }

    .success-title {
        color: $success;
    }
    """

    def __init__(self, title: str, message: str, details: str = ""):
        super().__init__()
        self.title = title
        self.message = message
        self.details = details

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(classes="dialog-container"):
                    with Vertical(classes="dialog-header"):
                        icon_text = Text()
                        icon_text.append(f"✓ {self.title}", style="bold green")
                        yield Label(icon_text, classes="success-title")

                    with Vertical(classes="dialog-content"):
                        # RichLogでANSIコード対応の表示
                        self.rich_log = RichLog(
                            highlight=False,
                            markup=False,
                            classes="content-area",
                        )
                        yield self.rich_log

                    with Horizontal(classes="dialog-buttons"):
                        yield Button(
                            "Commit & Push",
                            variant="primary",
                            id="commit-button",
                        )
                        yield Button("Dry Run", variant="default", id="dry-button")
                        yield Button("Close", variant="default", id="close-button")

    def on_mount(self) -> None:
        # コンテンツを結合
        full_content = self.message
        if self.details:
            full_content += f"\n\n{self.details}"

        # ANSIコードをRich Textに変換して表示
        rich_text = Text.from_ansi(full_content)
        self.rich_log.write(rich_text)

        # Commit & Pushボタンにフォーカス（Enterで即実行可能に）
        self.query_one("#commit-button", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "commit-button":
            self.dismiss("commit")
        elif event.button.id == "dry-button":
            self.dismiss("dry")
        else:
            self.dismiss("close")

    def on_key(self, event) -> None:
        if event.key == "c":
            self.dismiss("commit")
        elif event.key == "d":
            self.dismiss("dry")
        elif event.key == "escape":
            self.dismiss("close")
