"""
File list widget for the Textual TUI
"""

from textual.widgets import ListView, ListItem, Label, Input
from textual.containers import Vertical
from textual.message import Message
from textual.binding import Binding
from textual.fuzzy import Matcher
from textual import events
from rich.text import Text
from typing import List, Dict, Set, Optional
import os
import pathlib


def smart_shorten_path(path: str, max_width: int) -> str:
    """
    パスを賢く省略する（利用可能幅を最大限活用）
    後ろから積み上げて、収まる限り多くの情報を表示
    """
    ELLIPSIS = "…"

    if len(path) <= max_width:
        return path

    # pathlib で分割
    parts = list(pathlib.PurePath(path).parts)

    if len(parts) <= 1:
        # ファイル名のみの場合
        if len(path) <= max_width:
            return path
        # 先頭...末尾形式でファイル名を省略
        if max_width <= 6:
            return path[:max_width]
        keep_end = (max_width - 3) // 2
        keep_start = max_width - 3 - keep_end
        return path[:keep_start] + ELLIPSIS + path[-keep_end:]

    # 後ろから積み上げ方式
    filename = parts[-1]

    # ファイル名が幅を超える場合は省略
    if len(filename) > max_width:
        if max_width <= 6:
            return filename[:max_width]
        keep_end = (max_width - 3) // 2
        keep_start = max_width - 3 - keep_end
        return filename[:keep_start] + ELLIPSIS + filename[-keep_end:]

    # 後ろから順番に追加していく
    result_parts = [filename]
    current_length = len(filename)

    # 親ディレクトリを後ろから順に追加
    for i in range(len(parts) - 2, -1, -1):
        part = parts[i]
        # セパレータ分も考慮
        needed_length = current_length + len(os.sep) + len(part)

        if needed_length <= max_width:
            # 収まる場合は追加
            result_parts.insert(0, part)
            current_length = needed_length
        else:
            # 収まらない場合は省略して先頭部分を追加
            available_for_first = (
                max_width - current_length - len(os.sep) - 3
            )  # "..." 分

            if available_for_first > 0:
                # 先頭部分だけでも表示
                if len(part) <= available_for_first:
                    # パート全体が収まる場合（複数の省略されたディレクトリがある）
                    result_parts.insert(0, ELLIPSIS)
                    result_parts.insert(0, part)
                else:
                    # パートの一部のみ表示
                    if available_for_first >= 4:  # 最低限の文字数
                        truncated_part = part[:available_for_first] + ELLIPSIS
                        result_parts.insert(0, truncated_part)
                    else:
                        result_parts.insert(0, ELLIPSIS)
            else:
                # 先頭省略のみ
                result_parts.insert(0, ELLIPSIS)
            break

    return os.sep.join(result_parts)


class FileSelected(Message):
    """ファイル選択時のメッセージ"""

    def __init__(self, file_info: dict, index: int):
        self.file_info = file_info
        self.index = index
        super().__init__()


class DividerListItem(ListItem):
    """ターゲットグループの区切りヘッダー（選択不可）"""

    DEFAULT_CSS = """
    DividerListItem {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    DividerListItem:hover {
        background: $surface;
    }

    DividerListItem.-highlight {
        background: $surface;
    }

    DividerListItem > Label {
        text-style: bold;
        width: 100%;
    }
    """

    def __init__(self, target_name: str, file_count: int = 0):
        super().__init__()
        self.target_name = target_name
        self.file_count = file_count
        self.disabled = True  # 選択を無効化
        self.index = -1  # DividerはFileListItemとは別扱い

    def compose(self):
        """区切りヘッダーの構成"""
        display_text = f"{self.target_name} ({self.file_count})"
        yield Label(display_text)


class SpacerListItem(ListItem):
    """グループ間の空白行（選択不可）"""

    DEFAULT_CSS = """
    SpacerListItem {
        height: 1;
        background: transparent;
        padding: 0;
    }

    SpacerListItem:hover {
        background: transparent;
    }

    SpacerListItem.-highlight {
        background: transparent;
    }
    """

    def __init__(self):
        super().__init__()
        self.disabled = True  # 選択を無効化
        self.index = -1  # SpacerはFileListItemとは別扱い

    def compose(self):
        """空白行の構成"""
        yield Label("")


class FileListItem(ListItem):
    """ファイル一覧の個別アイテム"""

    def __init__(self, file_info: dict, index: int, selected: bool = False):
        self.file_info = file_info
        self.index = index
        self._selected = selected
        super().__init__()

        # ファイル状態に応じてCSSクラスを設定
        if file_info.get("local_only", False):
            # ローカル専用ファイル（new/adding）
            self.add_class("local-only")
        elif not file_info.get("local_exists", True):
            self.add_class("missing")
        elif file_info.get("changed", False):
            change_type = file_info.get("change_type")
            if change_type == "ahead":
                self.add_class("changed-ahead")
            elif change_type == "behind":
                self.add_class("changed-behind")
            else:
                # change_typeがNoneの場合は従来の'changed'クラス
                self.add_class("changed")

    def compose(self):
        """アイテムの構成

        選択マーカー+アイコン+ファイル名を単一Labelで描画する。
        行ごとのCheckboxウィジェットは数百ファイルで描画負荷が高いため
        テキストマーカー（[x]）方式に統一。
        """
        self.file_label = Label("")
        self.file_label.styles.width = "auto"  # 内容に応じてサイズを調整
        yield self.file_label

    def on_mount(self) -> None:
        """マウント時に表示を更新"""
        self.update_display()

    def on_resize(self) -> None:
        """リサイズ時に表示を更新"""
        self.update_display()

    def update_display(self) -> None:
        """利用可能幅に応じてファイル名表示を更新"""
        if not hasattr(self, "file_label"):
            return

        # 親コンテナの幅を取得
        parent_width = self.parent.size.width if self.parent else 50

        # 利用可能幅を計算（マーカー4 + パディング2 + スクロールバー1を除く）
        # 拡張子が切れる問題を解決するため、3文字分の余裕を追加
        available_width = max(20, parent_width - 10)

        # アイコン: 暗号化の有無のみ表示（local_onlyはカラーで識別可能）
        if self.file_info.get("encrypted", False):
            icon = "🔐"  # 暗号化ファイル
        else:
            icon = "📄"  # 通常ファイル（暗号化されていない）
        filename = self.file_info.get("name", "Unknown")

        # アイコン分（2文字）を除いた幅でファイル名を省略
        text_width = available_width - 2

        # pathlibベースの賢い省略を使用
        shortened_filename = smart_shorten_path(filename, text_width)

        # リッチテキスト作成
        text = Text()
        if self._selected:
            text.append("[x] ", style="bold green")
        else:
            text.append("[ ] ", style="dim")
        text.append(f"{icon} ")
        text.append(shortened_filename)

        self.file_label.update(text)

    def toggle_selection(self):
        """選択状態をトグル"""
        self._selected = not self._selected
        self.update_display()
        return self._selected


class FileList(Vertical):
    """ファイル一覧ウィジェット"""

    BINDINGS = [
        Binding("/", "focus_filter", "Filter"),
        Binding("-", "toggle_dividers", "Toggle Dividers", show=False),
        Binding(".", "toggle_changed_filter", "Changed Only", show=False),
        Binding("A", "deselect_all", "Deselect All", show=False),
    ]

    DEFAULT_CSS = """
    FileList {
        border: solid $primary;
        height: 1fr;
        width: 1fr;
    }
    
    FileList > Label {
        height: 1;
        margin: 0 1;
    }
    
    FileList > Input {
        margin: 0 1;
        height: 1;
        max-height: 3;
        min-height: 3;
    }
    
    FileList > ListView {
        height: 1fr;
        width: 1fr;
        overflow-x: scroll;
        overflow-y: auto;
        scrollbar-size-horizontal: 1;
    }
    
    FileList ListItem {
        height: 1;
        padding: 0 1;
        width: auto;
    }

    FileList ListItem Label {
        width: auto;
        text-overflow: clip;
    }
    
    /* ファイル状態の基本背景色 */
    FileList ListItem.missing {
        /*background: $secondary-muted;*/
        color: $text-disabled;
    }
    
    FileList ListItem.changed {
        background: $warning-muted;
        color: $text-warning;
    }
    
    FileList ListItem.changed-behind {
        background: $warning-muted;
        color: $text-warning;
    }
    
    FileList ListItem.changed-ahead {
        background: $success-muted;
        color: $text-success;
    }
    
    FileList ListItem.local-only {
        background: $accent-muted;
        color: $text-accent;
    }
    
    /* マシン名ヘッダー */
    #machine-header {
        text-style: bold;
        color: $text;
        background: $surface;
        padding: 0 1;
        text-align: center;
    }
    """

    def __init__(self, file_adapter=None):
        super().__init__()
        self.files: List[Dict] = []
        self.filtered_files: List[Dict] = []  # フィルタ後のファイルリスト
        self._index_by_id: Dict[int, int] = {}  # id(file_info) → files内インデックス
        self.selected_files: Set[int] = set()
        self.current_machine: str = ""
        self.file_adapter = file_adapter
        self.filter_query: str = ""  # 現在のフィルタクエリ
        self.show_dividers: bool = False  # targetごとのdivider表示フラグ
        self.show_changed_only: bool = False  # 変更ファイルのみ表示フラグ
        # フォーカス可能にする
        self.can_focus = True

    def on_resize(self) -> None:
        """リサイズ時に全アイテムの表示を更新"""
        # 全てのFileListItemの表示を更新
        for item in self.list_view.children:
            if isinstance(item, FileListItem) and hasattr(item, "update_display"):
                item.update_display()

    def _update_header(self):
        """ヘッダー情報を更新"""
        total_files = len(self.files)
        filtered_count = len(self.filtered_files)
        encrypted_count = sum(1 for f in self.files if f.get("encrypted", False))
        selected_count = len(self.selected_files)

        # フィルタ状態インジケータ
        indicators = []
        if self.show_dividers:
            indicators.append("grouped")
        if self.show_changed_only:
            indicators.append("changed")
        indicator_str = " [" + ", ".join(indicators) + "]" if indicators else ""

        # フィルタ適用中はフィルタ後件数を表示
        is_filtered = self.filter_query or self.show_changed_only
        if is_filtered:
            header_text = f"Files ({filtered_count}/{total_files} shown, {encrypted_count} encrypted, {selected_count} selected){indicator_str}"
        else:
            header_text = f"Files ({total_files} total, {encrypted_count} encrypted, {selected_count} selected){indicator_str}"
        self.query_one("#file-list-header", Label).update(header_text)

    def compose(self):
        """ウィジェットの構成"""
        self.list_view = ListView()
        yield Label("💾 No Machine", id="machine-header")
        yield Label("Files", id="file-list-header")
        # フィルタ入力欄を追加（初期状態では非表示）
        self.filter_input = Input(
            placeholder="Type to filter files... (fuzzy search)", id="file-filter"
        )
        self.filter_input.display = False  # 初期状態では非表示
        yield self.filter_input
        # ListViewを直接使用（内蔵の自動スクロール機能を有効化）
        yield self.list_view

    def load_files(self, machine_name: str, files: List[Dict]):
        """ファイル一覧を読み込み"""
        self.current_machine = machine_name
        self.files = files
        self.filtered_files = files.copy()  # 初期状態は全ファイル表示
        # files.index()のO(n²)を避けるためインデックスを事前構築
        self._index_by_id = {id(f): i for i, f in enumerate(files)}
        self.selected_files.clear()
        self.filter_query = ""
        self.filter_input.value = ""  # フィルタをクリア

        # マシン名ヘッダーを更新（現在のマシンかチェック）
        is_current_machine = False
        if self.file_adapter and machine_name != "No Machines":
            try:
                current_machine_name = (
                    self.file_adapter.config_manager.get_machine_name()
                )
                is_current_machine = machine_name == current_machine_name
            except Exception:
                pass

        if machine_name == "No Machines":
            machine_text = Text("💾 No Machine")
        elif is_current_machine:
            # 現在のマシンは星と装飾付き
            machine_text = Text.assemble(
                ("🌟 ", "bold yellow"),
                (machine_name, "bold green"),
                (" (Current)", "dim cyan"),
            )
        else:
            # 他のマシンは通常表示
            machine_text = Text(f"💾 {machine_name}")

        self.query_one("#machine-header", Label).update(machine_text)

        # フィルタを再適用（show_changed_only等の状態を維持）
        self._apply_filter()

    def on_input_changed(self, event: Input.Changed) -> None:
        """フィルタ入力が変更されたときの処理"""
        if event.input.id == "file-filter":
            self.filter_query = event.value
            self._apply_filter()
            # 入力内容に応じて表示/非表示を更新
            self._update_filter_visibility()

    @staticmethod
    def _is_changed_file(file_info: dict) -> bool:
        """ファイルが変更状態かどうかを判定"""
        if file_info.get("changed", False):
            return True
        if file_info.get("local_only", False):
            return True
        if not file_info.get("local_exists", True):
            return True
        return False

    def _apply_filter(self) -> None:
        """フィルタを適用してリストを更新（変更フィルタ + ファジー検索）"""
        # Step 1: 変更フィルタ適用
        if self.show_changed_only:
            base_files = [f for f in self.files if self._is_changed_file(f)]
        else:
            base_files = self.files.copy()

        # Step 2: ファジー検索フィルタ適用
        if not self.filter_query:
            self.filtered_files = base_files
        else:
            matcher = Matcher(self.filter_query)
            filtered = []

            for file_info in base_files:
                file_name = file_info.get("name", "")
                score = matcher.match(file_name)
                if score > 0:
                    filtered.append((score, file_info))

            filtered.sort(key=lambda x: x[0], reverse=True)
            self.filtered_files = [f[1] for f in filtered]

        # ListViewを更新
        self._update_list_view()

        # ヘッダーを更新
        self._update_header()

    def _update_list_view(self) -> None:
        """フィルタ結果に基づいてListViewを更新"""
        self.list_view.clear()

        if self.show_dividers:
            # targetごとにグループ化
            files_by_target = {}
            for file_info in self.filtered_files:
                target = file_info.get("target", "other")
                if target not in files_by_target:
                    files_by_target[target] = []
                files_by_target[target].append(file_info)

            # targetをソートして表示（"other"は最後に）
            sorted_targets = sorted(
                files_by_target.keys(), key=lambda x: (x == "other", x)
            )

            for target in sorted_targets:
                target_files = files_by_target[target]
                # dividerを追加
                divider = DividerListItem(target, len(target_files))
                self.list_view.append(divider)

                # targetに属するファイルを追加
                for file_info in target_files:
                    original_index = self._index_by_id[id(file_info)]
                    is_selected = original_index in self.selected_files
                    item = FileListItem(file_info, original_index, is_selected)
                    self.list_view.append(item)
                    self.call_after_refresh(
                        lambda i=item: (
                            i.update_display() if hasattr(i, "update_display") else None
                        )
                    )

                # グループ末尾に空白行を追加
                spacer = SpacerListItem()
                self.list_view.append(spacer)
        else:
            # 通常表示（dividerなし）
            for file_info in self.filtered_files:
                # 元のインデックスを保持（選択状態の管理のため）
                original_index = self._index_by_id[id(file_info)]
                is_selected = original_index in self.selected_files
                item = FileListItem(file_info, original_index, is_selected)
                self.list_view.append(item)
                # アイテムがマウントされた後に表示を更新
                self.call_after_refresh(
                    lambda i=item: (
                        i.update_display() if hasattr(i, "update_display") else None
                    )
                )

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """ファイル選択時の処理"""
        # 全ての項目からハイライトクラスを削除
        for item in self.list_view.children:
            if isinstance(item, FileListItem):
                item.remove_class("highlighted")

        # DividerListItem/SpacerListItemの場合は何もしない
        if event.item is not None and isinstance(
            event.item, (DividerListItem, SpacerListItem)
        ):
            return

        # 新しくハイライトされた項目にクラスを追加
        if event.item is not None and hasattr(event.item, "index"):
            event.item.add_class("highlighted")

            # FileListItemが保持している元のインデックスを使用
            original_index = event.item.index
            if 0 <= original_index < len(self.files):
                file_info = self.files[original_index]
                self.post_message(FileSelected(file_info, original_index))

    def toggle_file_selection(self, index: Optional[int] = None) -> Optional[bool]:
        """ファイルの選択状態をトグル

        Args:
            index: トグルするファイルのインデックス。Noneの場合はハイライト中のアイテム

        Returns:
            新しい選択状態。操作が行われなかった場合はNoneまたはFalse
        """
        if index is None:
            if (
                hasattr(self.list_view, "highlighted_child")
                and self.list_view.highlighted_child
            ):
                # ハイライトされているアイテムの元のインデックスを取得
                index = self.list_view.highlighted_child.index
            else:
                return

        if 0 <= index < len(self.files):
            # 現在の選択状態を確認
            is_selected = index in self.selected_files
            new_state = not is_selected

            # 選択状態を更新
            if new_state:
                self.selected_files.add(index)
            else:
                self.selected_files.discard(index)

            # ListItemの表示を更新
            for item in self.list_view.children:
                if isinstance(item, FileListItem) and item.index == index:
                    item._selected = new_state
                    item.update_display()
                    break

            # ヘッダーを更新
            self._update_header()
            return new_state
        return False

    def get_selected_files(self) -> List[Dict]:
        """選択されたファイルのリストを取得"""
        return [self.files[i] for i in self.selected_files if i < len(self.files)]

    def select_all(self) -> None:
        """すべてのファイルを選択（フィルタ中は表示されているファイルのみ）"""
        for file_info in self.filtered_files:
            self.selected_files.add(self._index_by_id[id(file_info)])
        self._update_list_view()

    def deselect_all(self) -> None:
        """すべてのファイルの選択を解除"""
        self.selected_files.clear()
        self._update_list_view()
        self._update_header()

    def action_deselect_all(self) -> None:
        """全選択解除（Aキー）"""
        count = len(self.selected_files)
        if count == 0:
            self.app.notify("No files selected", severity="warning")
            return
        self.deselect_all()
        self.app.notify(f"Deselected {count} file(s)")

    def get_current_file(self) -> Optional[Dict]:
        """現在選択されているファイルを取得

        Returns:
            現在ハイライトされているファイルの情報。選択がない場合はNone
        """
        if (
            hasattr(self.list_view, "highlighted_child")
            and self.list_view.highlighted_child
        ):
            original_index = self.list_view.highlighted_child.index
            if 0 <= original_index < len(self.files):
                return self.files[original_index]
        return None

    def action_focus_filter(self) -> None:
        """フィルタ入力欄にフォーカスを移動"""
        self.filter_input.display = True  # 表示してからフォーカス
        self.filter_input.focus()

    def action_toggle_dividers(self) -> None:
        """targetごとのdivider表示をトグル"""
        self.show_dividers = not self.show_dividers
        self._update_list_view()
        self._update_header()

    def action_toggle_changed_filter(self) -> None:
        """変更ファイルのみ表示をトグル"""
        self.show_changed_only = not self.show_changed_only
        self._apply_filter()

    def _update_filter_visibility(self) -> None:
        """フィルタ入力欄の表示/非表示を制御"""
        # フォーカスがあるか、文字が入っている場合のみ表示
        should_show = self.filter_input.has_focus or bool(self.filter_input.value)
        self.filter_input.display = should_show

    def on_input_focus(self, event: events.Focus) -> None:
        """入力ウィジェットのフォーカスイベントの処理"""
        self.call_after_refresh(self._update_filter_visibility)

    def on_input_blur(self, event: events.Blur) -> None:
        """入力ウィジェットのフォーカス喪失イベントの処理"""
        self.call_after_refresh(self._update_filter_visibility)

    def on_key(self, event) -> None:
        """キーイベントの処理"""
        # フィルタ入力欄がフォーカスされている時の特殊キー処理
        if self.filter_input.has_focus:
            if event.key == "escape":
                # ESC: 文字が入っている場合はクリア、空の場合はフォーカス移動
                if self.filter_input.value:
                    self.filter_input.value = ""
                    self.filter_query = ""
                    self._apply_filter()
                    self._update_filter_visibility()  # 表示状態を更新
                else:
                    self.list_view.focus()
                    # フォーカス移動後に表示状態を更新（次のレンダリングサイクル後）
                    self.call_after_refresh(self._update_filter_visibility)
                event.prevent_default()
            elif event.key == "enter":
                # Enter: フィルタ結果がある場合はファイルリストにフォーカス移動
                if self.filtered_files:
                    self.list_view.focus()
                    # フォーカス移動後に表示状態を更新（次のレンダリングサイクル後）
                    self.call_after_refresh(self._update_filter_visibility)
                    event.prevent_default()
        # ファイルリストがフォーカスされている時の特殊キー処理
        elif self.list_view.has_focus:
            if event.key == "escape":
                # ESC: フィルタ文字があり、結果があり、ファイルリストにフォーカスがある場合
                # → フィルタ入力欄にフォーカスを戻す
                if self.filter_input.value and self.filtered_files:
                    self.filter_input.display = True  # 表示してからフォーカス
                    self.filter_input.focus()
                    event.prevent_default()
