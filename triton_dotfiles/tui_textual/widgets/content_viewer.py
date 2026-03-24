"""
Content viewer widget for the Textual TUI
"""

from textual.widgets import Static, TabbedContent, TabPane
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.message import Message
from textual.app import ComposeResult
from rich.syntax import Syntax
from rich.text import Text
from typing import Dict, Optional

from ..constants import (
    MAX_PREVIEW_LINES,
    MAX_DIFF_LINES,
    BINARY_SAMPLE_SIZE,
    BINARY_CONTROL_CHAR_THRESHOLD,
    HEX_PREVIEW_MAX_SIZE,
    HEX_PREVIEW_BYTES,
    HEX_LINE_WIDTH,
)


class ViewModeChanged(Message):
    """表示モード変更時のメッセージ"""

    def __init__(self, mode: str):
        self.mode = mode  # diff, backup, info
        super().__init__()


def _is_binary_content(
    content_bytes: bytes, sample_size: int = BINARY_SAMPLE_SIZE
) -> bool:
    """ファイル内容がバイナリかどうかを判定

    Args:
        content_bytes: ファイルの内容（バイト）
        sample_size: 検査するバイト数

    Returns:
        bool: バイナリファイルの場合True
    """
    if not content_bytes:
        return False

    # 検査するサンプルサイズを制限
    sample = content_bytes[:sample_size]

    # null文字があればバイナリ
    if b"\x00" in sample:
        return True

    # 制御文字の比率をチェック（印刷可能文字以外）
    control_chars = 0
    total_chars = len(sample)

    for byte in sample:
        # 印刷可能文字、改行、タブ、復帰文字以外は制御文字
        if byte < 32 and byte not in (9, 10, 13):  # \t, \n, \r
            control_chars += 1

    # 制御文字がしきい値以上ならバイナリと判定
    return (
        (control_chars / total_chars) > BINARY_CONTROL_CHAR_THRESHOLD
        if total_chars > 0
        else False
    )


class ContentViewer(Vertical):
    """右ペインのタブ付きコンテンツビューアー"""

    DEFAULT_CSS = """
    ContentViewer {
        border: solid $primary;
        height: 1fr;
        width: 1fr;
        padding: 0;
        layout: vertical;
    }
    
    /* TabbedContentコンテナ */
    ContentViewer TabbedContent {
        height: 1fr;
        width: 1fr;
    }
    
    /* タブヘッダーの高さを調整 */
    ContentViewer TabbedContent > Tabs {
        height: 3;
        min-height: 3;
        max-height: 3;
        dock: top;
    }
    
    /* 各タブの表示 */
    ContentViewer TabbedContent Tab {
        min-width: 8;
        padding: 0 1;
    }
    
    /* アクティブタブの明確な表示 */
    ContentViewer TabbedContent Tab.-active {
        background: $primary;
        color: $text;
        text-style: bold;
    }
    
    /* ホバー効果 */
    ContentViewer TabbedContent Tab:hover {
        background: $accent;
    }
    
    /* タブコンテンツエリア */
    ContentViewer TabbedContent > ContentSwitcher {
        padding: 1;
        scrollbar-gutter: stable;
        height: 1fr;
        width: 1fr;
    }
    
    /* スクロール可能コンテナ */
    ContentViewer ScrollableContainer {
        width: 1fr;
        height: 1fr;
        scrollbar-gutter: stable;
    }
    
    ContentViewer ScrollableContainer > Static {
        width: 1fr;
        padding: 1;
        height: auto;
        min-height: 100vh;
    }
    
    /* Split view specific styles */
    #split-horizontal {
        layout: horizontal;
        height: 1fr;
        width: 1fr;
    }
    
    .split-left {
        width: 1fr;
        border-right: solid $primary;
    }
    
    .split-right {
        width: 1fr;
    }
    
    .split-left ScrollableContainer,
    .split-right ScrollableContainer {
        height: 1fr;
        width: 1fr;
    }
    """

    def __init__(self):
        super().__init__()
        self.current_file: Optional[Dict] = None
        self.current_machine: str = ""
        self.file_adapter = None
        self._tabbed_content: Optional[TabbedContent] = None

    def compose(self) -> ComposeResult:
        """タブ構成の定義"""
        with TabbedContent(initial="backup", id="main-tabs"):
            with TabPane("Backup", id="backup"):
                yield ScrollableContainer(
                    Static("Select a file to view backup content", id="backup-display"),
                    id="backup-container",
                )

            with TabPane("Local", id="local"):
                yield ScrollableContainer(
                    Static("Select a file to view local content", id="local-display"),
                    id="local-container",
                )

            with TabPane("Diff", id="diff"):
                yield ScrollableContainer(
                    Static("Select a file to view diff", id="diff-display"),
                    id="diff-container",
                )

            with TabPane("Info", id="info"):
                yield ScrollableContainer(
                    Static("Select a file to view info", id="info-display"),
                    id="info-container",
                )

            with TabPane("Split", id="split"):
                with Horizontal(id="split-horizontal"):
                    with Vertical(classes="split-left"):
                        yield ScrollableContainer(
                            Static(
                                "Local content will appear here",
                                id="split-local-display",
                            ),
                            id="split-local-container",
                        )
                    with Vertical(classes="split-right"):
                        yield ScrollableContainer(
                            Static(
                                "Backup content will appear here",
                                id="split-backup-display",
                            ),
                            id="split-backup-container",
                        )

    def set_file_adapter(self, adapter):
        """file_adapterを設定"""
        self.file_adapter = adapter

    def set_view_mode(self, mode: str):
        """表示モードを設定（キーボードショートカット連動）"""
        mode_mapping = {
            "local": "local",
            "backup": "backup",
            "diff": "diff",
            "info": "info",
            "split": "split",
        }

        if mode in mode_mapping:
            try:
                tabs = self.query_one("#main-tabs", TabbedContent)
                tabs.active = mode_mapping[mode]
                if self.current_file:
                    self._update_active_tab_content()
                self.post_message(ViewModeChanged(mode))
            except Exception:
                # TabbedContentがまだ初期化されていない場合は後で処理
                self.call_later(self._delayed_set_view_mode, mode)

    def _delayed_set_view_mode(self, mode: str):
        """遅延実行による表示モード設定"""
        mode_mapping = {
            "local": "local",
            "backup": "backup",
            "diff": "diff",
            "info": "info",
            "split": "split",
        }

        if mode in mode_mapping:
            try:
                tabs = self.query_one("#main-tabs", TabbedContent)
                tabs.active = mode_mapping[mode]
                if self.current_file:
                    self._update_active_tab_content()
                self.post_message(ViewModeChanged(mode))
            except Exception:
                # それでも失敗する場合はログに記録して無視
                pass

    def update_content(self, file_info: Dict, machine_id: str):
        """コンテンツを更新（全タブ対応）"""
        self.current_file = file_info
        self.current_machine = machine_id

        if not self.file_adapter:
            self._show_error_in_tab(self.active, "File adapter not initialized")
            return

        # 全タブのスクロール位置をトップにリセット
        self._reset_all_tab_scroll_positions()

        # 現在アクティブなタブのみ更新
        self._update_active_tab_content()

    def _reset_all_tab_scroll_positions(self):
        """全タブのスクロール位置をトップにリセット"""
        try:
            # 各タブのScrollableContainerを探してスクロール位置をリセット
            container_ids = [
                "backup-container",
                "local-container",
                "diff-container",
                "info-container",
                "split-local-container",
                "split-backup-container",
            ]
            for container_id in container_ids:
                try:
                    # ScrollableContainerを取得
                    scrollable = self.query_one(f"#{container_id}", ScrollableContainer)
                    # スクロール位置をトップにリセット
                    scrollable.scroll_home(animate=False)
                except Exception:
                    # コンテナが見つからない場合は無視
                    pass
        except Exception:
            # エラーが発生した場合は無視
            pass

    def _update_active_tab_content(self):
        """現在アクティブなタブのコンテンツを更新"""
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            active_tab = tabs.active

            if active_tab == "local":
                self._show_local_content(self.current_file)
            elif active_tab == "backup":
                self._show_backup(self.current_file, self.current_machine)
            elif active_tab == "diff":
                self._show_diff(self.current_file, self.current_machine)
            elif active_tab == "info":
                self._show_info(self.current_file)
            elif active_tab == "split":
                self._show_split_view(self.current_file, self.current_machine)
        except Exception:
            # タブがまだ利用できない場合は無視
            pass

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """タブがアクティブになった時の処理"""
        # タブが切り替わった時に現在のファイル情報でコンテンツを更新
        if self.current_file:
            self._update_active_tab_content()

    def _show_diff(self, file_info: Dict, machine_id: str):
        """差分表示"""
        try:
            # ローカル専用ファイルの場合は特別な処理
            if file_info.get("local_only", False):
                content_widget = self.query_one("#diff-display", Static)
                content = Text()
                content.append("🆕 Local-only file\n\n", style="cyan bold")
                content.append(
                    "This file exists only on your local machine.\n", style="white"
                )
                content.append("Use 'Backup' to add it to the repository.", style="dim")
                content_widget.update(content)
                return

            diff_data = self.file_adapter.get_file_diff(machine_id, file_info)
            content_widget = self.query_one("#diff-display", Static)

            if not diff_data.get("has_changes", False):
                if not diff_data.get("local_exists", True):
                    # 優しい警告表示
                    content = Text()
                    content.append("Local file does not exist\n\n", style="yellow")
                    content.append(
                        "Use 'Restore' (r) to restore from backup", style="dim"
                    )
                else:
                    content = Text("No differences found", style="green")
            else:
                # 差分を表示
                diff_lines = diff_data.get("diff_lines", [])
                content = Text()

                for i, line in enumerate(diff_lines[:MAX_DIFF_LINES]):
                    if i > 0:
                        content.append("\n")
                    formatted_line = self._format_diff_line(line)
                    if isinstance(formatted_line, Text):
                        content.append_text(formatted_line)
                    else:
                        content.append(str(formatted_line))

                if len(diff_lines) > MAX_DIFF_LINES:
                    content.append(
                        f"\n... and {len(diff_lines) - MAX_DIFF_LINES} more lines"
                    )

            content_widget.update(content)

        except Exception as e:
            self._show_error_in_tab("diff", f"Error loading diff: {str(e)}")

    def _show_backup(self, file_info: Dict, machine_id: str):
        """バックアップファイル内容表示"""
        try:
            # ローカル専用ファイルの場合は特別な処理
            if file_info.get("local_only", False):
                self._show_local_only_backup(file_info)
                return
            # 暗号化ファイルの場合は特別な処理
            if file_info.get("encrypted", False):
                self._show_encrypted_backup(file_info, machine_id)
                return

            # データベースファイルの内容を取得
            preview_lines = self.file_adapter.get_file_content_preview(
                machine_id, file_info, max_lines=MAX_PREVIEW_LINES
            )

            # 共通のコンテンツ処理メソッドを使用
            processed_content = self._process_file_content_for_display(
                preview_lines, file_info, "database"
            )

            content_widget = self.query_one("#backup-display", Static)
            content_widget.update(processed_content)

            # コンテンツの行数に応じて高さを動的に設定
            line_count = len(preview_lines) if preview_lines else 1
            content_widget.styles.height = line_count + 2  # 少し余裕を持たせる

        except Exception as e:
            self._show_error_in_tab("backup", f"Error loading backup: {str(e)}")

    def _show_encrypted_backup(self, file_info: Dict, machine_id: str):
        """暗号化ファイルのバックアップ内容表示"""
        # 暗号化ファイルの内容を取得
        preview_lines = self.file_adapter.get_file_content_preview(
            machine_id, file_info, max_lines=MAX_PREVIEW_LINES
        )

        # 共通のコンテンツ処理メソッドを使用
        processed_content = self._process_file_content_for_display(
            preview_lines, file_info, "encrypted database"
        )

        content_widget = self.query_one("#backup-display", Static)
        content_widget.update(processed_content)

        # コンテンツの行数に応じて高さを動的に設定
        line_count = len(preview_lines) if preview_lines else 1
        content_widget.styles.height = line_count + 2  # 少し余裕を持たせる

    def _show_local_only_backup(self, file_info: Dict):
        """ローカル専用ファイルのバックアップタブ表示"""
        try:
            # ローカルファイルの内容を取得
            preview_lines = self.file_adapter.get_local_file_content_preview(
                file_info, max_lines=MAX_PREVIEW_LINES
            )

            # 共通のコンテンツ処理メソッドを使用
            processed_content = self._process_file_content_for_display(
                preview_lines, file_info, "local"
            )

            content_widget = self.query_one("#backup-display", Static)
            content_widget.update(processed_content)

            # コンテンツの行数に応じて高さを動的に設定
            line_count = len(preview_lines) if preview_lines else 1
            content_widget.styles.height = line_count + 2  # 少し余裕を持たせる

        except Exception as e:
            self._show_error_in_tab("backup", f"Error loading local file: {str(e)}")

    def _show_info(self, file_info: Dict):
        """ファイル情報表示"""
        try:
            # ファイルサイズを人間可読形式に変換
            def format_size(size_bytes):
                if size_bytes == 0:
                    return "0 B"
                elif size_bytes < 1024:
                    return f"{size_bytes} B"
                elif size_bytes < 1024**2:
                    return f"{size_bytes / 1024:.1f} KB"
                elif size_bytes < 1024**3:
                    return f"{size_bytes / (1024**2):.1f} MB"
                else:
                    return f"{size_bytes / (1024**3):.1f} GB"

            # タイムスタンプを人間可読形式に変換
            def format_timestamp(timestamp):
                if timestamp is None:
                    return "N/A"
                import datetime

                dt = datetime.datetime.fromtimestamp(timestamp)
                return dt.strftime("%Y-%m-%d %H:%M:%S")

            # 同期ステータスを判定（既存のdiff機能を活用）
            def get_sync_status_and_direction():
                if file_info.get("local_only", False):
                    return "LOCAL-ONLY", "cyan", "+"
                elif not file_info.get("local_exists", False):
                    return "MISSING", "red", "↓"

                # 既存のget_file_diffを使用してファイル内容を比較
                try:
                    diff_data = self.file_adapter.get_file_diff(
                        self.current_machine, file_info
                    )
                    has_changes = diff_data.get("has_changes", False)

                    if not has_changes:
                        return "UP-TO-DATE", "green", "✓"
                    else:
                        # タイムスタンプで方向を判定
                        local_mtime = file_info.get("local_mtime", 0)
                        backup_mtime = file_info.get("backup_mtime", 0)
                        time_diff = local_mtime - backup_mtime

                        if time_diff > 2:  # ローカルが新しい
                            return "AHEAD", "yellow", "↑"
                        elif time_diff < -2:  # バックアップが新しい
                            return "BEHIND", "yellow", "↓"
                        else:
                            return "MODIFIED", "yellow", "M"

                except Exception:
                    # エラー時はタイムスタンプベースで判定
                    local_mtime = file_info.get("local_mtime", 0)
                    backup_mtime = file_info.get("backup_mtime", 0)
                    time_diff = local_mtime - backup_mtime

                    if abs(time_diff) < 2:
                        return "UP-TO-DATE", "green", "✓"
                    elif time_diff > 0:
                        return "AHEAD", "yellow", "↑"
                    else:
                        return "BEHIND", "yellow", "↓"

            # Git風の時刻比較アイコンを取得
            def get_time_comparison_icon():
                if file_info.get("local_only", False):
                    return "+"  # ローカル専用
                elif not file_info.get("local_exists", False):
                    return "✗"

                # 統一されたファイル状態分析を使用
                from pathlib import Path

                local_path = Path(file_info.get("local_path", ""))
                backup_path = Path(file_info.get("backup_path", ""))
                local_mtime = file_info.get("local_mtime", 0)
                backup_mtime = file_info.get("backup_mtime", 0)

                status = self.file_adapter.file_manager.analyze_file_status(
                    local_path, backup_path, local_mtime, backup_mtime
                )

                if not status["changed"]:
                    return "="  # equal
                elif status["change_type"] == "ahead":
                    return "↑"  # ahead
                elif status["change_type"] == "behind":
                    return "↓"  # behind
                else:
                    return "M"  # changed but unknown direction

            # 差分統計を取得（既存のdiff機能を活用）
            def get_diff_stats():
                if not file_info.get("local_exists", False):
                    return "Local file missing - needs restore"

                try:
                    # 既存のget_file_diffを使用
                    diff_data = self.file_adapter.get_file_diff(
                        self.current_machine, file_info
                    )
                    has_changes = diff_data.get("has_changes", False)

                    if not has_changes:
                        return "Content identical"
                    else:
                        # サイズ差も表示
                        local_size = file_info.get("local_size", 0)
                        backup_size = file_info.get("size", 0)
                        size_diff = local_size - backup_size

                        if size_diff == 0:
                            return "Content differs (same size)"
                        elif size_diff > 0:
                            return (
                                f"Content differs (+{format_size(size_diff)} locally)"
                            )
                        else:
                            return (
                                f"Content differs (-{format_size(-size_diff)} locally)"
                            )

                except Exception:
                    # エラー時はサイズベース比較
                    local_size = file_info.get("local_size", 0)
                    backup_size = file_info.get("size", 0)
                    size_diff = local_size - backup_size

                    if size_diff == 0:
                        return "Same size (comparison failed)"
                    elif size_diff > 0:
                        return f"+{format_size(size_diff)} larger locally"
                    else:
                        return f"-{format_size(-size_diff)} smaller locally"

            # 基本情報
            name = file_info.get("name", "Unknown")
            backup_size = file_info.get("size", 0)
            local_size = file_info.get("local_size", 0)
            encrypted = file_info.get("encrypted", False)
            local_exists = file_info.get("local_exists", False)

            # タイムスタンプ
            backup_mtime = file_info.get("backup_mtime")
            local_mtime = file_info.get("local_mtime")

            # ステータスと方向
            sync_status, sync_color, status_icon = get_sync_status_and_direction()
            time_icon = get_time_comparison_icon()
            diff_stats = get_diff_stats()

            # Rich Textでスタイル付きコンテンツを作成
            from rich.text import Text

            content = Text()

            # ファイル名（大きなヘッダー）
            content.append(f"{name}\n", style="bold")
            content.append("\n")

            # 同期ステータス（最重要情報を先頭に）
            content.append("Status: ", style="bold cyan")
            content.append(sync_status, style=f"bold {sync_color}")
            content.append(f" {status_icon}", style=sync_color)
            content.append("\n\n")

            # サイズ情報
            content.append("Size: ", style="bold cyan")
            content.append(f"Backup {format_size(backup_size)}")
            if local_exists:
                content.append(f" | Local {format_size(local_size)}")
            content.append("\n")

            # 暗号化状態
            content.append("Encrypted: ", style="bold cyan")
            if encrypted:
                content.append("Yes (AES-256-GCM)", style="green")
            else:
                content.append("No", style="dim")
            content.append("\n")

            # 最終更新日時
            content.append("\n")
            content.append("Last Modified", style="bold cyan")
            content.append(f" {time_icon}:\n")
            content.append("  Backup: ", style="dim")
            content.append(f"{format_timestamp(backup_mtime)}\n")
            if local_exists:
                content.append("  Local:  ", style="dim")
                content.append(f"{format_timestamp(local_mtime)}\n")
            else:
                content.append("  Local:  ", style="dim")
                content.append("File not found\n", style="red")

            # 差分統計（差分がある場合のみ表示）
            if diff_stats and diff_stats != "No differences":
                content.append("\n")
                content.append("Differences: ", style="bold cyan")
                content.append(diff_stats)
                content.append("\n")

            # パス情報
            content.append("\n")
            content.append("Paths:\n", style="bold cyan")
            content.append("  Local:  ", style="dim")
            content.append(f"{file_info.get('local_path', 'N/A')}\n")
            content.append("  Backup: ", style="dim")
            content.append(f"{file_info.get('backup_path', 'N/A')}")

            content_widget = self.query_one("#info-display", Static)
            content_widget.update(content)

        except Exception as e:
            self._show_error_in_tab("info", f"Error loading file info: {str(e)}")

    def _show_split_view(self, file_info: Dict, machine_id: str):
        """スプリットビュー表示（Local + Databaseコンテンツを並べて表示）"""
        try:
            # Local content
            try:
                local_lines = self.file_adapter.get_local_file_content_preview(
                    file_info, max_lines=MAX_PREVIEW_LINES
                )
                local_syntax = self._process_file_content_for_display(
                    local_lines, file_info, "local"
                )
            except Exception as e:
                local_syntax = Text(f"Error reading local file: {str(e)}", style="red")

            # Backup content
            try:
                # 暗号化ファイルも含めて通常通り取得（file_adapterが自動的に復号化処理を行う）
                backup_lines = self.file_adapter.get_file_content_preview(
                    machine_id, file_info, max_lines=MAX_PREVIEW_LINES
                )
                backup_syntax = self._process_file_content_for_display(
                    backup_lines, file_info, "database"
                )
            except Exception as e:
                backup_syntax = Text(
                    f"Error reading backup file: {str(e)}", style="red"
                )

            # Update both split displays
            local_widget = self.query_one("#split-local-display", Static)
            backup_widget = self.query_one("#split-backup-display", Static)

            local_widget.update(local_syntax)
            backup_widget.update(backup_syntax)

        except Exception as e:
            # Fallback error display
            try:
                local_widget = self.query_one("#split-local-display", Static)
                backup_widget = self.query_one("#split-backup-display", Static)
                error_text = Text(f"Error in split view: {str(e)}", style="red")
                local_widget.update(error_text)
                backup_widget.update(error_text)
            except Exception:
                # ウィジェットが見つからない場合は無視
                pass

    def _process_file_content_for_display(
        self, content_lines: list, file_info: Dict, content_type: str
    ):
        """
        ファイルコンテンツを表示用に処理（バイナリ判定、シンタックスハイライト含む）

        Args:
            content_lines: ファイルの内容（行のリスト）
            file_info: ファイル情報
            content_type: 'local' または 'database'

        Returns:
            Textualで表示可能なRichオブジェクト
        """
        try:
            # コンテンツが空またはエラーの場合
            if not content_lines or not isinstance(content_lines, list):
                return Text(
                    f"{content_type.title()} file not found or empty", style="dim"
                )

            # リストを文字列に結合
            content_str = "\n".join(content_lines)

            # エラーメッセージのチェック
            if content_str.startswith("Local file does not exist"):
                info_text = Text()
                info_text.append("Local file does not exist\n\n", style="yellow")
                info_text.append(
                    "Use 'Restore' (R) to restore from backup", style="dim"
                )
                return info_text
            elif content_str.startswith("File not found in backup"):
                return Text(
                    f"{content_type.title()} file not found in backup",
                    style="yellow",
                )

            # 内容が空の場合
            if not content_str.strip():
                return Text(f"{content_type.title()} file is empty", style="dim")

            # バイナリファイル判定
            content_bytes = content_str.encode("utf-8", errors="ignore")
            if _is_binary_content(content_bytes):
                # バイナリファイルの情報表示
                filename = file_info.get("name", "unknown")
                file_size = len(content_bytes)

                binary_info = Text()
                binary_info.append("Binary File\n\n", style="bold")
                binary_info.append("File: ", style="bold cyan")
                binary_info.append(f"{filename}\n")
                binary_info.append("Size: ", style="bold cyan")
                binary_info.append(f"{file_size} bytes\n")
                binary_info.append("Type: ", style="bold cyan")
                binary_info.append(f"{content_type.title()}\n\n")

                # 小さなファイルはヘックス表示
                if file_size <= HEX_PREVIEW_MAX_SIZE:
                    binary_info.append("Hex Preview:\n", style="dim")
                    hex_preview = content_bytes[:HEX_PREVIEW_BYTES].hex()
                    # 16バイトごとに改行
                    for i in range(0, len(hex_preview), HEX_LINE_WIDTH):
                        binary_info.append(
                            hex_preview[i : i + HEX_LINE_WIDTH] + "\n", style="dim"
                        )
                else:
                    binary_info.append(
                        "Use external tools to view binary content", style="dim"
                    )

                return binary_info

            # テキストファイルのシンタックスハイライト
            filename = file_info.get("name", "")
            try:
                lexer = Syntax.guess_lexer(filename, content_str)
                return Syntax(content_str, lexer, theme="monokai", line_numbers=True)
            except Exception:
                # シンタックスハイライトに失敗した場合はプレーンテキスト
                return Text(content_str)

        except Exception as e:
            return Text(
                f"Error processing {content_type} content: {str(e)}", style="red"
            )

    def _show_error_in_tab(self, tab_id: str, error_message: str) -> None:
        """指定されたタブにエラーメッセージを表示"""
        try:
            content_widget = self.query_one(f"#{tab_id}-display", Static)
            error_text = Text(f"Error: {error_message}", style="red")
            content_widget.update(error_text)
        except Exception:
            # ウィジェットが見つからない場合は無視
            pass

    def _show_local_content(self, file_info: Dict):
        """ローカルファイルの内容表示"""
        try:
            # ローカルファイルの内容を取得
            local_lines = self.file_adapter.get_local_file_content_preview(
                file_info,
                max_lines=MAX_PREVIEW_LINES,
            )

            # 共通のコンテンツ処理メソッドを使用
            processed_content = self._process_file_content_for_display(
                local_lines, file_info, "local"
            )

            content_widget = self.query_one("#local-display", Static)
            content_widget.update(processed_content)

            # コンテンツの行数に応じて高さを動的に設定
            line_count = len(local_lines) if local_lines else 1
            content_widget.styles.height = line_count + 2  # 少し余裕を持たせる

        except Exception as e:
            self._show_error_in_tab(
                "local", f"Error loading local file content: {str(e)}"
            )

    def _format_diff_line(self, line: str) -> Text:
        """差分行をフォーマット（Richマークアップの安全な使用）

        Args:
            line: フォーマットする差分行

        Returns:
            スタイル付きのRich Textオブジェクト
        """
        text = Text()

        if line.startswith("+"):
            text.append(line, style="green")
        elif line.startswith("-"):
            text.append(line, style="red")
        elif line.startswith("@@"):
            text.append(line, style="cyan")
        else:
            text.append(line)

        return text

    def get_copyable_text(self) -> tuple[str | None, str]:
        """現在アクティブなタブのプレーンテキストを取得

        Returns:
            (テキスト or None, タブ名) のタプル。
            Splitタブやコンテンツがない場合はNoneを返す。
        """
        try:
            tabs = self.query_one("#main-tabs", TabbedContent)
            active_tab = tabs.active
        except Exception:
            return None, ""

        if active_tab == "split":
            return None, "Split"

        display_id_map = {
            "backup": ("backup-display", "Backup"),
            "local": ("local-display", "Local"),
            "diff": ("diff-display", "Diff"),
            "info": ("info-display", "Info"),
        }

        if active_tab not in display_id_map:
            return None, ""

        widget_id, tab_name = display_id_map[active_tab]
        try:
            widget = self.query_one(f"#{widget_id}", Static)
            renderable = widget.renderable

            # Rich renderable からプレーンテキストを抽出
            if isinstance(renderable, str):
                return renderable, tab_name
            elif isinstance(renderable, Text):
                return renderable.plain, tab_name
            elif isinstance(renderable, Syntax):
                return renderable.code, tab_name
            else:
                # その他のRich renderableはstr変換を試みる
                return str(renderable), tab_name
        except Exception:
            return None, ""

    def add_future_tab(
        self, tab_id: str, title: str, initial_message: Optional[str] = None
    ) -> None:
        """将来のタブ追加用メソッド（拡張性対応）"""
        if initial_message is None:
            initial_message = f"Select a file to view {title.lower()} content"

        # 新しいTabPaneを動的に追加（実装時に調整が必要）
        # 注意: Textualでは動的なタブ追加は複雑なため、
        # 実際の5つ目のタブ実装時はcomposeメソッドを直接修正することを推奨
