"""
Main screen for the Textual TUI
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from ..adapters.file_adapter import TUIFileAdapter
from ..widgets.file_list import FileList, FileSelected
from ..widgets.content_viewer import ContentViewer, ViewModeChanged
from ..widgets.status_bar import StatusBar
from ..widgets.dialogs import (
    BackupSuccessDialog,
    ConfirmationDialog,
    InputDialog,
    MessageDialog,
    ProgressDialog,
    MachineSelectDialog,
    ScrollableMessageDialog,
    ThreeChoiceDialog,
)


class MainScreen(Static):
    """Main screen (2-pane layout)."""

    def __init__(self, skip_startup: bool = True, **kwargs):
        """
        Initialize MainScreen.

        Args:
            skip_startup: Whether to skip startup processing (always True when using StartupScreen).
        """
        super().__init__(**kwargs)
        # skip_startupは互換性のため残すが、StartupScreen導入後は常にTrueで使用
        self._skip_startup = skip_startup

    def compose(self) -> ComposeResult:
        """Compose the 2-pane layout."""
        with Horizontal():
            # 左ペイン（ファイル一覧）
            self.left_pane = Vertical(classes="left-pane")
            with self.left_pane:
                self.file_list = FileList()
                yield self.file_list

            # 右ペイン（コンテンツ表示）
            self.right_pane = Vertical(classes="right-pane")
            with self.right_pane:
                self.content_viewer = ContentViewer()
                yield self.content_viewer

    def on_mount(self) -> None:
        """Handle screen initialization."""
        # file_adapterを初期化
        try:
            self.file_adapter = TUIFileAdapter()
            self.content_viewer.set_file_adapter(self.file_adapter)
            self.file_list.file_adapter = self.file_adapter

            # 設定からテーマを読み込み、Appに設定
            # 注: StartupScreenで既にテーマが適用されている場合は再適用
            theme_name = self.file_adapter.config.tui.theme
            if theme_name:
                try:
                    self.app.theme = theme_name
                except ValueError:
                    # 無効なテーマ名の場合は警告のみ
                    self.app.notify(
                        f"Unknown theme '{theme_name}', using default",
                        severity="warning",
                    )

            # 起動時処理はStartupScreenで実行済みなので、直接データを読み込む
            self._load_initial_data()
        except FileNotFoundError as e:
            # 設定ファイルが見つからない場合
            self.file_list.load_files("Error", [])
            self.content_viewer._show_error_in_tab(
                "preview", f"Config file not found: {e}"
            )
        except Exception as e:
            # その他のエラー
            self.file_list.load_files("Error", [])
            self.content_viewer._show_error_in_tab(
                "preview", f"Failed to initialize: {e}"
            )

    def _load_initial_data(self) -> None:
        """Load initial data."""
        # マシン一覧を取得
        self.machines = self.file_adapter.get_available_machines()

        if not self.machines:
            # マシンが見つからない場合
            self.file_list.load_files("No Machines", [])
            welcome_text = (
                "[$warning bold]No backup data found in repository.[/]\n\n"
                "Please create a backup with:\n"
                "1. Exit TUI with [bold]q[/bold]\n"
                "2. Create backup with [bold]triton backup[/bold]\n"
                "3. Launch again with [bold]triton[/bold]"
            )
            self.content_viewer.query_one("#preview-display").update(welcome_text)

            return

        # 自分自身のマシンがあればそれを優先選択、なければ最初のマシンを選択
        self.current_machine_index = 0  # デフォルト

        try:
            # 現在のマシン名を取得
            current_machine_name = self.file_adapter.config_manager.get_machine_name()

            # 自分自身のマシンを探す
            for i, machine in enumerate(self.machines):
                if machine["name"] == current_machine_name:
                    self.current_machine_index = i
                    break
        except Exception:
            # マシン名取得に失敗した場合はデフォルト（0）のまま
            pass

        self.current_machine = self.machines[self.current_machine_index]
        self._load_files_for_current_machine()

    def _refresh_data_preserve_machine(self) -> None:
        """マシン選択を維持しながらデータを再読み込み"""
        # 現在選択中のマシンIDを保存
        preserved_machine_id = (
            self.current_machine["id"] if self.current_machine else None
        )

        # マシン一覧を再取得
        self.machines = self.file_adapter.get_available_machines()

        if not self.machines:
            self.file_list.load_files("No Machines", [])
            return

        # 保存したマシンIDで選択を復元
        self.current_machine_index = 0  # デフォルト
        if preserved_machine_id:
            for i, machine in enumerate(self.machines):
                if machine["id"] == preserved_machine_id:
                    self.current_machine_index = i
                    break

        self.current_machine = self.machines[self.current_machine_index]
        self._load_files_for_current_machine()

    def _load_files_for_current_machine(self):
        """現在のマシンのファイル一覧を読み込み"""
        if not self.current_machine:
            return

        # マシン切り替え時はキャッシュをクリア（新規ファイル検出のため）
        self.file_adapter.clear_local_only_cache()

        # ファイル一覧を取得
        files = self.file_adapter.get_files_for_machine(self.current_machine["id"])

        # ファイル一覧ウィジェットに読み込み
        self.file_list.load_files(self.current_machine["name"], files)

        # ウェルカムメッセージを表示
        if files:
            welcome_text = (
                "Welcome to Triton TUI!\n\n"
                "Available features:\n"
                "• File browsing\n"
                "• Diff view (d)\n"
                "• Preview (v)\n"
                "• File restore (r)\n"
                "• File export (e)\n\n"
                "Use arrow keys to navigate\n"
                "Press Space to select files\n"
                "Press '?' for help"
            )
        else:
            welcome_text = (
                f"No files found for machine '{self.current_machine['name']}'"
            )

        self.content_viewer.query_one("#preview-display").update(welcome_text)

        # 初期フォーカスをファイルリストのListViewに設定
        self.file_list.list_view.focus()

    def on_file_selected(self, message: FileSelected) -> None:
        """ファイル選択時の処理"""
        if self.current_machine:
            self.content_viewer.update_content(
                message.file_info, self.current_machine["id"]
            )
            # ステータスバーを更新
            self._update_status_bar(message.file_info)

    def on_view_mode_changed(self, message: ViewModeChanged) -> None:
        """表示モード変更時の処理"""
        # 現在は特に何もしない
        pass

    def _update_status_bar(self, file_info: dict | None) -> None:
        """ステータスバーを更新"""
        try:
            status_bar = self.app.query_one(StatusBar)
        except Exception:
            # StatusBarが見つからない場合は何もしない
            return

        if not file_info:
            status_bar.clear()
            return

        # 現在のマシンかどうかを判定
        try:
            current_machine_name = self.file_adapter.config_manager.get_machine_name()
            selected_machine_name = (
                self.current_machine["name"] if self.current_machine else ""
            )
            is_current_machine = current_machine_name == selected_machine_name
        except Exception:
            is_current_machine = False

        if is_current_machine:
            # 現在のマシン: ローカルのフルパスを表示
            path = file_info.get("local_path", file_info.get("name", ""))
        else:
            # 他のマシン: repo内の相対パスを表示
            path = file_info.get("name", "")

        status_bar.update_path(path, is_current_machine)

    def toggle_file_selection(self) -> None:
        """現在のファイルの選択状態をトグル"""
        self.file_list.toggle_file_selection()

    def set_view_mode(self, mode: str) -> None:
        """表示モードを設定"""
        self.content_viewer.set_view_mode(mode)

    def toggle_left_pane(self) -> None:
        """左ペインの表示/非表示を切り替え"""
        try:
            if self.left_pane.has_class("hidden"):
                # 非表示から表示へ
                self.left_pane.remove_class("hidden")
                self.right_pane.remove_class("full-width")
            else:
                # 表示から非表示へ
                self.left_pane.add_class("hidden")
                self.right_pane.add_class("full-width")
        except Exception:
            # エラーが発生した場合は無視
            pass

    async def show_machine_select_dialog(self):
        """マシン選択ダイアログを表示"""
        if not hasattr(self, "machines") or not self.machines:
            await self.app.push_screen(
                MessageDialog("Error", "No machines available", "error")
            )
            return

        current_machine_id = self.current_machine["id"] if self.current_machine else ""

        # callbackパターンでダイアログを表示
        self.app.push_screen(
            MachineSelectDialog(self.machines, current_machine_id, self.file_adapter),
            self._handle_machine_selection,
        )

    async def _handle_machine_selection(self, selected_machine: dict) -> None:
        """マシン選択ダイアログからのcallback処理"""
        if not selected_machine:
            return

        if selected_machine != self.current_machine:
            # マシンを変更
            self.current_machine = selected_machine
            self.current_machine_index = next(
                (
                    i
                    for i, m in enumerate(self.machines)
                    if m["id"] == selected_machine["id"]
                ),
                0,
            )
            self._load_files_for_current_machine()

    async def restore_files(self):
        """ファイル復元を実行"""
        if not hasattr(self, "current_machine") or not self.current_machine:
            await self.app.push_screen(
                MessageDialog("Error", "No machine selected", "error")
            )
            return

        # 選択されたファイルを取得
        selected_files = self.file_list.get_selected_files()
        current_file = self.file_list.get_current_file()

        if selected_files:
            # 複数ファイル復元
            file_count = len(selected_files)
            if file_count == 1:
                title = "Restore Confirmation"
                message = f"Restore '{selected_files[0]['name']}'"
            else:
                title = "Restore Confirmation"
                message = f"Restore {file_count} selected files"

            submessage = "Local files will be overwritten. Continue?"

            # callbackパターンでダイアログを表示
            self._pending_restore_files = selected_files
            self.app.push_screen(
                ConfirmationDialog(title, message, submessage),
                self._handle_restore_confirmation,
            )

        elif current_file:
            # 単一ファイル復元
            title = "Restore Confirmation"
            message = f"Restore '{current_file['name']}'"
            submessage = "Local file will be overwritten. Continue?"

            # callbackパターンでダイアログを表示
            self._pending_restore_files = [current_file]
            self.app.push_screen(
                ConfirmationDialog(title, message, submessage),
                self._handle_restore_confirmation,
            )
        else:
            await self.app.push_screen(
                MessageDialog("Error", "No file selected", "error")
            )

    async def _handle_restore_confirmation(self, confirmed: bool) -> None:
        """復元確認ダイアログからのcallback処理"""
        if not confirmed:
            return

        files = self._pending_restore_files
        await self._perform_restore(files)

    async def export_files(self):
        """ファイルエクスポートを実行"""

        if not hasattr(self, "current_machine") or not self.current_machine:
            self.app.notify("No machine selected")
            await self.app.push_screen(
                MessageDialog("Error", "No machine selected", "error")
            )
            return

        # 選択されたファイルを取得
        selected_files = self.file_list.get_selected_files()
        current_file = self.file_list.get_current_file()

        target_files = (
            selected_files
            if selected_files
            else ([current_file] if current_file else [])
        )

        if not target_files:
            await self.app.push_screen(
                MessageDialog("Error", "No file selected", "error")
            )
            return

        # エクスポート先ディレクトリを入力
        file_count = len(target_files)
        if file_count == 1:
            prompt = f"Please enter export directory for '{target_files[0]['name']}':"
        else:
            prompt = f"Please enter export directory for {file_count} selected files:"

        # Callbackパターンでダイアログを表示
        self.app.push_screen(
            InputDialog("Export Directory", prompt, "exported_files"),
            self._handle_export_directory_input,
        )

        # target_filesを一時保存（callbackで使用）
        self._pending_export_files = target_files
        self._pending_export_file_count = file_count

    async def _perform_restore(self, files):
        """復元を実行"""
        progress_dialog = ProgressDialog(
            "Restoring", f"Restoring {len(files)} files..."
        )

        async def show_progress():
            self.app.push_screen(progress_dialog)

        # プログレスダイアログを表示
        await show_progress()

        try:
            if len(files) == 1:
                result = self.file_adapter.restore_file(
                    self.current_machine["id"], files[0]
                )
            else:
                result = self.file_adapter.restore_files(
                    self.current_machine["id"], files
                )

            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # 結果を表示
            if result["success"]:
                await self.app.push_screen(
                    MessageDialog("Success", result["message"], "success")
                )
                # ファイルリストを更新してカラーリングをリフレッシュ
                self._load_files_for_current_machine()
            else:
                await self.app.push_screen(
                    MessageDialog("Error", result["message"], "error")
                )

        except Exception as e:
            progress_dialog.dismiss()
            await self.app.push_screen(
                MessageDialog("Error", f"Restore failed: {str(e)}", "error")
            )

    async def _handle_export_directory_input(self, export_dir: str | None) -> None:
        """InputDialogからのcallback処理"""

        if export_dir is None:
            return

        if not export_dir.strip():
            return

        # 一時保存したファイル情報を取得
        target_files = self._pending_export_files
        file_count = self._pending_export_file_count

        # ディレクトリパスの妥当性をチェック
        validation = self.file_adapter.validate_export_directory(export_dir)

        if not validation["valid"]:
            await self.app.push_screen(
                MessageDialog("Error", validation["message"], "error")
            )
            return

        # ファイル競合をチェック
        conflict_check = self.file_adapter.check_export_file_conflicts(
            target_files, validation["path"]
        )

        # 確認ダイアログ
        title = "Export Confirmation"
        if file_count == 1:
            message = f"Export '{target_files[0]['name']}' to '{validation['path']}'"
        else:
            message = f"Export {file_count} selected files to '{validation['path']}'"

        # 上書き警告を統合
        if conflict_check["has_conflicts"]:
            conflict_count = conflict_check["conflict_count"]
            if conflict_count == 1:
                warning = "Warning: 1 file will be overwritten"
            else:
                warning = f"Warning: {conflict_count} files will be overwritten"
            submessage = f"{warning}\nFiles will be decrypted if encrypted. Continue?"
        else:
            submessage = "Files will be decrypted if encrypted. Continue?"

        # ダイアログの結果に必要な情報を一時保存
        self._pending_export_path = validation["path"]

        self.app.push_screen(
            ConfirmationDialog(title, message, submessage),
            self._handle_export_confirmation,
        )

    async def _handle_export_confirmation(self, confirmed: bool) -> None:
        """確認ダイアログからのcallback処理"""
        if confirmed:
            target_files = self._pending_export_files
            destination_path = self._pending_export_path
            await self._perform_export(target_files, destination_path)

    async def _perform_export(self, files, destination_path):
        """エクスポートを実行"""
        progress_dialog = ProgressDialog(
            "Exporting", f"Exporting {len(files)} files..."
        )

        # プログレスダイアログを表示
        self.app.push_screen(progress_dialog)

        try:
            # デバッグ情報
            self.app.log.info(
                f"Starting export: machine_id={self.current_machine['id']}, files={[f['name'] for f in files]}, destination={destination_path}"
            )

            # 実際のエクスポート処理
            result = self.file_adapter.export_files_to_directory(
                self.current_machine["id"], files, destination_path
            )

            # デバッグ情報
            self.app.log.info(f"Export result: {result}")

            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # 結果を表示
            if result.get("success", False):
                message = result.get(
                    "message",
                    f"Successfully exported {len(files)} files to {destination_path}",
                )
                await self.app.push_screen(
                    MessageDialog("Export Success", message, "success")
                )
            else:
                error_message = result.get(
                    "message", f"Export failed: {result.get('errors', 'Unknown error')}"
                )
                await self.app.push_screen(
                    MessageDialog("Export Error", error_message, "error")
                )

        except Exception as e:
            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # エラーメッセージを表示
            await self.app.push_screen(
                MessageDialog("Export Error", f"Export failed: {str(e)}", "error")
            )

    async def git_pull_repository(self):
        """Git pullを実行"""
        try:
            # 確認ダイアログを表示
            repo_info = self.file_adapter.get_repository_path_info()
            title = "Git Pull Confirmation"
            message = "Pull latest changes from repository"
            submessage = f"Repository: {repo_info['path']}\nThis will update your local dotfiles database."

            # callbackパターンでダイアログを表示
            self.app.push_screen(
                ConfirmationDialog(title, message, submessage),
                self._handle_git_pull_confirmation,
            )

        except Exception as e:
            # 予期しないエラー
            await self.app.push_screen(
                MessageDialog("Error", f"Unexpected error: {str(e)}", "error")
            )

    async def _handle_git_pull_confirmation(self, confirmed: bool) -> None:
        """Git pull確認ダイアログからのcallback処理"""
        if not confirmed:
            return

        await self._perform_git_pull()

    async def _perform_git_pull(self):
        """実際のgit pullを実行"""
        # プログレスダイアログを表示
        progress_dialog = ProgressDialog("Git Pull", "Pulling latest changes...")
        self.app.push_screen(progress_dialog)

        try:
            # git pullを実行
            result = self.file_adapter.git_pull_repository(dry_run=False)

            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # 結果を表示
            if result["success"]:
                # 成功時はスクロール可能ダイアログを使用（詳細情報があるため）
                await self.app.push_screen(
                    ScrollableMessageDialog(
                        "Git Pull Success",
                        result["message"],
                        result.get("details", ""),
                        "success",
                    )
                )

                # データを再読み込み（マシン選択を維持）
                self._refresh_data_preserve_machine()
            else:
                # エラー時もスクロール可能ダイアログを使用
                await self.app.push_screen(
                    ScrollableMessageDialog(
                        "Git Pull Failed",
                        result["message"],
                        result.get("details", ""),
                        "error",
                    )
                )

        except Exception as e:
            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # エラーメッセージを表示
            await self.app.push_screen(
                MessageDialog("Git Pull Error", f"Git pull failed: {str(e)}", "error")
            )

    def show_in_finder(self):
        """現在のファイルをFinderで表示"""
        # 現在選択されているファイルを取得
        current_file = self.file_list.get_current_file()

        if not current_file:
            self.app.notify("No file selected", severity="warning")
            return

        # ローカルファイルが存在しない場合はエラー
        if not current_file.get("local_exists", False):
            self.app.notify("Local file does not exist", severity="error")
            return

        # macOS以外では使用不可
        import platform

        if platform.system() != "Darwin":
            self.app.notify(
                "Show in Finder is only available on macOS", severity="error"
            )
            return

        # ローカルパスを取得
        local_path = current_file.get("local_path")
        if not local_path:
            self.app.notify("Local path not available", severity="error")
            return

        # Finderで表示
        try:
            import subprocess

            # open -R コマンドでFinderでファイルを選択状態で開く
            subprocess.run(["open", "-R", local_path], check=True)
            self.app.notify(
                f"Opened in Finder: {current_file['name']}", severity="information"
            )
        except subprocess.CalledProcessError as e:
            self.app.notify(f"Failed to open in Finder: {str(e)}", severity="error")
        except Exception as e:
            self.app.notify(f"Error: {str(e)}", severity="error")

    def show_config_in_finder(self):
        """現在使用中のconfig.ymlファイルをFinderで表示"""
        # macOS以外では使用不可
        import platform

        if platform.system() != "Darwin":
            self.app.notify(
                "Show in Finder is only available on macOS", severity="error"
            )
            return

        # 現在使用中のconfig.ymlパスを取得
        try:
            config_path = self.file_adapter.config_manager.config_path
            if not config_path.exists():
                self.app.notify("Config file not found", severity="error")
                return

            # Finderで表示
            import subprocess

            subprocess.run(["open", "-R", str(config_path)], check=True)
            self.app.notify(
                f"Opened config in Finder: {config_path.name}", severity="information"
            )
        except subprocess.CalledProcessError as e:
            self.app.notify(
                f"Failed to open config in Finder: {str(e)}", severity="error"
            )
        except Exception as e:
            self.app.notify(f"Error: {str(e)}", severity="error")

    def show_repository_in_finder(self):
        """現在使用中のリポジトリフォルダをFinderで表示"""
        # macOS以外では使用不可
        import platform

        if platform.system() != "Darwin":
            self.app.notify(
                "Show in Finder is only available on macOS", severity="error"
            )
            return

        # 現在使用中のリポジトリパスを取得
        try:
            repo_info = self.file_adapter.get_repository_path_info()
            if not repo_info["exists"]:
                self.app.notify("Repository directory not found", severity="error")
                return

            # Finderで表示
            import subprocess
            from pathlib import Path

            repo_path = Path(repo_info["path"])
            subprocess.run(["open", str(repo_path)], check=True)
            self.app.notify(
                f"Opened repository in Finder: {repo_path.name}", severity="information"
            )
        except subprocess.CalledProcessError as e:
            self.app.notify(
                f"Failed to open repository in Finder: {str(e)}", severity="error"
            )
        except Exception as e:
            self.app.notify(f"Error: {str(e)}", severity="error")

    def show_archive_in_finder(self):
        """アーカイブフォルダをFinderで表示"""
        # macOS以外では使用不可
        import platform

        if platform.system() != "Darwin":
            self.app.notify(
                "Show in Finder is only available on macOS", severity="error"
            )
            return

        # アーカイブフォルダのパスを取得
        try:
            from triton_dotfiles.utils import get_triton_dir

            archive_path = get_triton_dir() / "archives"

            # アーカイブフォルダが存在しない場合は作成
            if not archive_path.exists():
                archive_path.mkdir(parents=True, exist_ok=True)
                self.app.notify(
                    f"Created archives folder: {archive_path}", severity="information"
                )

            # Finderで表示
            import subprocess

            subprocess.run(["open", str(archive_path)], check=True)
            self.app.notify(
                f"Opened archives in Finder: {archive_path.name}",
                severity="information",
            )
        except subprocess.CalledProcessError as e:
            self.app.notify(
                f"Failed to open archives in Finder: {str(e)}", severity="error"
            )
        except Exception as e:
            self.app.notify(f"Error: {str(e)}", severity="error")

    async def backup_current_machine(self):
        """現在のマシンのファイルをバックアップ"""
        try:
            # 確認ダイアログを表示
            machine_name = self.file_adapter.config_manager.get_machine_name()
            title = "Backup Confirmation"
            message = "Backup current machine settings"
            submessage = f"Machine: {machine_name}\nThis will backup your current dotfiles to the repository."

            # 3択ダイアログを使用（Yes/No/Dry Run）
            self.app.push_screen(
                ThreeChoiceDialog(title, message, submessage),
                self._handle_backup_choice,
            )

        except Exception as e:
            # 予期しないエラー
            await self.app.push_screen(
                MessageDialog("Error", f"Unexpected error: {str(e)}", "error")
            )

    async def _handle_backup_choice(self, choice: str) -> None:
        """バックアップ選択ダイアログからのcallback処理"""
        if choice == "yes":
            await self._perform_backup(dry_run=False)
        elif choice == "dry":
            await self._perform_backup(dry_run=True)
        # choice == "no" の場合は何もしない

    async def _handle_backup_success_choice(self, choice: str) -> None:
        """バックアップ成功ダイアログからのcallback処理"""
        if choice == "commit":
            # 直接Commit & Pushを実行（確認ダイアログをバイパス）
            await self._perform_git_commit_push(dry_run=False)
        elif choice == "dry":
            # Dry RunでCommit & Pushを実行
            await self._perform_git_commit_push(dry_run=True)
        # choice == "close" の場合は何もしない

    async def _perform_backup(self, dry_run: bool = False):
        """実際のバックアップを実行"""
        # プログレスダイアログを表示
        operation = "Dry Run Backup" if dry_run else "Backup"
        progress_dialog = ProgressDialog(
            operation, "Backing up current machine files..."
        )
        self.app.push_screen(progress_dialog)

        try:
            # バックアップを実行
            result = self.file_adapter.backup_files_to_repository(dry_run=dry_run)

            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # 結果を表示
            if result["success"]:
                # ファイルリストを更新（バックアップ後に状態が変わるため）
                # マシン選択を維持するため _load_files_for_current_machine を使用
                if not dry_run:
                    self._load_files_for_current_machine()

                if dry_run:
                    # Dry runの場合は従来通りスクロール可能ダイアログを使用
                    await self.app.push_screen(
                        ScrollableMessageDialog(
                            f"{operation} Success",
                            result["message"],
                            result.get("details", ""),
                            "success",
                        )
                    )
                else:
                    # 実行時はCommit&Push遷移オプション付きダイアログ
                    self.app.push_screen(
                        BackupSuccessDialog(
                            f"{operation} Success",
                            result["message"],
                            result.get("details", ""),
                        ),
                        self._handle_backup_success_choice,
                    )
            else:
                # エラー時もスクロール可能ダイアログを使用
                await self.app.push_screen(
                    ScrollableMessageDialog(
                        f"{operation} Failed",
                        result["message"],
                        result.get("details", ""),
                        "error",
                    )
                )

        except Exception as e:
            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # エラーメッセージを表示
            await self.app.push_screen(
                MessageDialog(f"{operation} Error", f"Backup failed: {str(e)}", "error")
            )

    async def git_commit_push_repository(self):
        """現在のマシンの変更をgit commit & pushする"""
        try:
            # 確認ダイアログを表示（破壊的操作なので慎重に）
            machine_name = self.file_adapter.config_manager.get_machine_name()
            title = "Git Commit & Push Confirmation"
            message = "Commit and push changes to remote repository"
            submessage = f"Machine: {machine_name}\nThis will permanently commit and push your changes to the remote repository.\nThis action cannot be easily undone."

            # 3択ダイアログを使用（Yes/No/Dry Run）
            self.app.push_screen(
                ThreeChoiceDialog(title, message, submessage),
                self._handle_git_commit_push_choice,
            )

        except Exception as e:
            # 予期しないエラー
            await self.app.push_screen(
                MessageDialog("Error", f"Unexpected error: {str(e)}", "error")
            )

    async def _handle_git_commit_push_choice(self, choice: str) -> None:
        """Git commit push選択ダイアログからのcallback処理"""
        if choice == "yes":
            await self._perform_git_commit_push(dry_run=False)
        elif choice == "dry":
            await self._perform_git_commit_push(dry_run=True)
        # choice == "no" の場合は何もしない

    async def _perform_git_commit_push(self, dry_run: bool = False):
        """実際のgit commit pushを実行"""
        # プログレスダイアログを表示
        operation = "Dry Run Git Commit Push" if dry_run else "Git Commit Push"
        progress_dialog = ProgressDialog(operation, "Processing git operations...")
        self.app.push_screen(progress_dialog)

        try:
            # git commit pushを実行
            result = self.file_adapter.git_commit_push_repository(dry_run=dry_run)

            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # 結果を表示
            if result["success"]:
                # 成功時はスクロール可能ダイアログを使用（詳細情報があるため）
                await self.app.push_screen(
                    ScrollableMessageDialog(
                        f"{operation} Success",
                        result["message"],
                        result.get("details", ""),
                        "success",
                    )
                )

                # データを再読み込み（commitした後なので最新の状態に更新、マシン選択を維持）
                if not dry_run:
                    self._refresh_data_preserve_machine()
            else:
                # Pull required の場合は特別な処理
                if result.get("need_pull", False):
                    # Pull requiredの場合、専用のconfirmationダイアログを表示
                    title = "Pull Required"
                    message = result["message"]
                    submessage = "The remote repository has newer changes.\nWould you like to pull them now?\n\nAfter pulling, you may need to run the commit & push operation again."

                    self.app.push_screen(
                        ConfirmationDialog(title, message, submessage),
                        self._handle_pull_confirmation,
                    )
                else:
                    # 通常のエラー時はスクロール可能ダイアログを使用
                    await self.app.push_screen(
                        ScrollableMessageDialog(
                            f"{operation} Failed",
                            result["message"],
                            result.get("details", ""),
                            "error",
                        )
                    )

        except Exception as e:
            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # エラーメッセージを表示
            await self.app.push_screen(
                MessageDialog(
                    f"{operation} Error", f"Git commit push failed: {str(e)}", "error"
                )
            )

    async def _handle_pull_confirmation(self, result: bool) -> None:
        """Pull確認ダイアログからのcallback処理"""
        if result:
            # ユーザーがPullを選択した場合、Git Pullを実行
            await self.git_pull_repository()
        # result が False の場合は何もしない（ユーザーがキャンセル）

    async def cleanup_repository(self):
        """リポジトリから孤立ファイルを削除（現在のマシンのみ）"""
        try:
            # 安全性チェック: 現在のマシンかどうか確認
            current_machine = self.file_adapter.config_manager.get_machine_name()
            selected_machine = (
                self.current_machine["name"] if self.current_machine else "unknown"
            )

            if selected_machine != current_machine:
                await self.app.push_screen(
                    MessageDialog(
                        "Cleanup Not Allowed",
                        f"Repository cleanup is only allowed for current machine.\n\n"
                        f"Current machine: {current_machine}\n"
                        f"Selected machine: {selected_machine}\n\n"
                        f"This safety measure prevents accidental deletion of files "
                        f"from other machines that might be temporarily offline.",
                        "error",
                    )
                )
                return

            # 確認ダイアログを表示（破壊的操作なので慎重に）
            title = "Repository Cleanup Confirmation"
            message = "Delete orphaned files from repository"
            submessage = (
                f"Machine: {current_machine}\n\n"
                f"This will PERMANENTLY delete files that exist in the repository "
                f"but not on your local system.\n\n"
                f"Use 'Dry Run' to preview which files would be deleted first."
            )

            # 3択ダイアログを使用（Yes/No/Dry Run）
            self.app.push_screen(
                ThreeChoiceDialog(title, message, submessage),
                self._handle_cleanup_choice,
            )

        except Exception as e:
            # 予期しないエラー
            await self.app.push_screen(
                MessageDialog("Error", f"Unexpected error: {str(e)}", "error")
            )

    async def _handle_cleanup_choice(self, choice: str) -> None:
        """Cleanup選択ダイアログからのcallback処理"""
        if choice == "yes":
            await self._perform_repository_cleanup(dry_run=False)
        elif choice == "dry":
            await self._perform_repository_cleanup(dry_run=True)
        # choice == "no" の場合は何もしない

    async def _perform_repository_cleanup(self, dry_run: bool = False):
        """実際のリポジトリクリーンアップを実行"""
        # プログレスダイアログを表示
        operation = "Dry Run Repository Cleanup" if dry_run else "Repository Cleanup"
        progress_dialog = ProgressDialog(operation, "Scanning for orphaned files...")
        self.app.push_screen(progress_dialog)

        try:
            # cleanup実行
            current_machine = self.file_adapter.config_manager.get_machine_name()
            result = self.file_adapter.cleanup_repository_files(
                current_machine, dry_run=dry_run
            )

            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # 結果メッセージを構築
            cleanup_result = result.get("result", {})
            if dry_run:
                # Dry runの場合
                would_delete = len(cleanup_result.get("would_delete", []))
                if would_delete > 0:
                    files_list = "\n".join(
                        f"• {file}" for file in cleanup_result["would_delete"][:10]
                    )
                    if len(cleanup_result["would_delete"]) > 10:
                        files_list += f"\n... and {len(cleanup_result['would_delete']) - 10} more files"

                    details = (
                        f"Files that would be deleted:\n\n{files_list}\n\n"
                        f"Run the actual cleanup (not dry run) to delete these files permanently."
                    )

                    await self.app.push_screen(
                        ScrollableMessageDialog(
                            "Dry Run Results",
                            f"Found {would_delete} orphaned file(s) that would be deleted.",
                            details,
                            "warning",
                        )
                    )
                else:
                    await self.app.push_screen(
                        MessageDialog(
                            "Dry Run Results",
                            "No orphaned files found in repository.",
                            "success",
                        )
                    )
            else:
                # 実際の削除の場合
                deleted = len(cleanup_result.get("deleted", []))
                errors = len(cleanup_result.get("errors", []))

                if deleted > 0 or errors > 0:
                    details = ""
                    if deleted > 0:
                        deleted_list = "\n".join(
                            f"• {file}" for file in cleanup_result["deleted"][:10]
                        )
                        if len(cleanup_result["deleted"]) > 10:
                            deleted_list += f"\n... and {len(cleanup_result['deleted']) - 10} more files"
                        details += f"Deleted files:\n\n{deleted_list}\n\n"

                    if errors > 0:
                        error_list = "\n".join(
                            f"✗ {error}" for error in cleanup_result["errors"][:5]
                        )
                        if len(cleanup_result["errors"]) > 5:
                            error_list += f"\n... and {len(cleanup_result['errors']) - 5} more errors"
                        details += f"Errors:\n\n{error_list}\n\n"

                    details += "Consider running 'Git Commit Push' to save these changes to the remote repository."

                    await self.app.push_screen(
                        ScrollableMessageDialog(
                            "Repository Cleanup Complete",
                            f"Deleted {deleted} file(s), {errors} error(s) occurred.",
                            details,
                            "success" if errors == 0 else "warning",
                        )
                    )

                    # データを再読み込み（ファイルが削除されたので更新、マシン選択を維持）
                    self._refresh_data_preserve_machine()
                else:
                    await self.app.push_screen(
                        MessageDialog(
                            "Repository Cleanup Complete",
                            "No orphaned files found in repository.",
                            "success",
                        )
                    )

        except Exception as e:
            # プログレスダイアログを閉じる
            progress_dialog.dismiss()

            # エラーメッセージを表示
            await self.app.push_screen(
                MessageDialog(
                    f"{operation} Error",
                    f"Repository cleanup failed: {str(e)}",
                    "error",
                )
            )

    async def open_vscode_diff(self):
        """現在選択されたファイルをVSCodeで差分表示"""
        try:
            # 現在選択されたファイルを取得
            current_file = self.file_list.get_current_file()

            if not current_file:
                self.app.notify("No file selected")
                return

            # プログレスダイアログを表示
            progress_dialog = ProgressDialog(
                "Opening VSCode...", "Preparing diff view..."
            )
            self.app.push_screen(progress_dialog)

            try:
                # VSCode diff を開く
                result = self.file_adapter.open_vscode_diff(current_file)

                # プログレスダイアログを閉じる
                self.app.pop_screen()

                if result["success"]:
                    # 成功通知
                    self.app.notify(result["message"])
                else:
                    # ローカルファイル不存在の場合は軽い通知で済ます
                    if "Local file does not exist" in result["message"]:
                        self.app.notify(
                            "Local file does not exist - cannot open diff",
                            severity="warning",
                        )
                    else:
                        # その他のエラー（VSCode未インストールなど）はモーダルで表示
                        await self.app.push_screen_wait(
                            MessageDialog(
                                "VSCode Diff Error", result["message"], "error"
                            )
                        )
            except Exception as e:
                # プログレスダイアログを閉じる
                self.app.pop_screen()
                raise e

        except Exception as e:
            await self.app.push_screen_wait(
                MessageDialog(
                    "VSCode Diff Error", f"Unexpected error: {str(e)}", "error"
                )
            )

    async def open_vscode_edit(self):
        """現在選択されたファイルをVSCodeで直接編集"""
        try:
            # 現在選択されたファイルを取得
            current_file = self.file_list.get_current_file()

            if not current_file:
                self.app.notify("No file selected")
                return

            # プログレスダイアログを表示
            progress_dialog = ProgressDialog(
                "Opening VSCode...", "Preparing file for editing..."
            )
            self.app.push_screen(progress_dialog)

            try:
                # VSCodeでローカルファイルを編集
                result = self.file_adapter.open_vscode_edit(current_file)

                # プログレスダイアログを閉じる
                self.app.pop_screen()

                if result["success"]:
                    # 成功通知
                    self.app.notify(result["message"])
                else:
                    # ローカルファイル不存在の場合は軽い通知で済ます
                    if "Local file does not exist" in result["message"]:
                        self.app.notify(
                            "Local file does not exist - cannot open for editing",
                            severity="warning",
                        )
                    else:
                        # その他のエラー（VSCode未インストールなど）はモーダルで表示
                        await self.app.push_screen_wait(
                            MessageDialog(
                                "VSCode Edit Error", result["message"], "error"
                            )
                        )
            except Exception as e:
                # プログレスダイアログを閉じる
                self.app.pop_screen()
                raise e

        except Exception as e:
            await self.app.push_screen_wait(
                MessageDialog(
                    "VSCode Edit Error", f"Unexpected error: {str(e)}", "error"
                )
            )
