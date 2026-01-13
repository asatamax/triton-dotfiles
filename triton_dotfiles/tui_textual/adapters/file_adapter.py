"""
File operations adapter for TUI
"""

import os
from pathlib import Path
from colorama import Fore, Style
from ...managers.file_comparison_manager import (
    FileComparisonManager,
    DuplicateDetectionMethod,
)


class TUIFileAdapter:
    """既存のFileManagerをTUI用にラップするアダプター"""

    def __init__(self):
        # 既存クラスを遅延インポート（循環インポート回避）
        from ...config import ConfigManager
        from ...managers.file_manager import FileManager
        from ...cli import find_config_file

        # CLIと同じ設定ファイル検索ロジックを使用
        config_path = find_config_file()
        if config_path is None:
            raise FileNotFoundError(
                "Config file not found. Run 'triton init config' to create one."
            )

        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load_config()
        self.file_manager = FileManager(self.config_manager)

        # 統一ファイル比較マネージャーを初期化
        self.file_comparison_manager = FileComparisonManager(
            self.file_manager.encryption_manager
        )

    def get_repository_path(self):
        """リポジトリパスを取得"""
        repo_path = getattr(self.config.repository, "path", "~/dotfiles")
        return os.path.expanduser(repo_path)

    def _should_exclude_from_ui(self, file_path: str) -> bool:
        """
        UI表示から除外すべきファイルかどうか判定。

        FileManagerの共通ロジックに委譲し、CLI/TUIで一貫したフィルタリングを実現。
        セキュリティ保護（master.key等）と見た目系システムファイル（.DS_Store等）
        の両方をチェックする。
        """
        return self.file_manager.should_exclude_from_ui(
            Path(file_path),
            self.config.tui.hide_system_files,
            self.config.tui.system_file_patterns,
        )

    def get_available_machines(self):
        """利用可能なマシン一覧を取得"""
        repo_path = self.get_repository_path()
        machines = []

        try:
            if not os.path.exists(repo_path):
                return []

            # リポジトリ内のディレクトリをスキャン
            for item in os.listdir(repo_path):
                machine_path = os.path.join(repo_path, item)
                if os.path.isdir(machine_path) and not item.startswith("."):
                    # ファイル数をカウント
                    file_count = len(
                        [
                            f
                            for f in os.listdir(machine_path)
                            if os.path.isfile(os.path.join(machine_path, f))
                        ]
                    )

                    machines.append(
                        {
                            "id": item,
                            "name": item,
                            "description": f"{file_count} files",
                            "path": machine_path,
                            "file_count": file_count,
                        }
                    )

            # ファイル数でソート
            machines.sort(key=lambda x: x["file_count"], reverse=True)

        except Exception as e:
            print(f"Error scanning machines: {e}")

        return machines

    def get_files_for_machine(self, machine_id, include_local_only=None):
        """指定マシンのファイル一覧を再帰的に取得（リモート + ローカル専用ファイル）"""
        repo_path = self.get_repository_path()
        machine_path = os.path.join(repo_path, machine_id)
        files = []

        # ローカル専用ファイルを含めるかの判定
        if include_local_only is None:
            include_local_only = self._is_current_machine(machine_id)

        try:
            if not os.path.exists(machine_path):
                return []

            # 1. リモートファイルベースの既存ロジック
            for root, dirs, filenames in os.walk(machine_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)

                    # machine_pathからの相対パスを計算
                    relative_path = os.path.relpath(file_path, machine_path)

                    # セキュリティ保護・システムファイルをフィルタリング
                    if self._should_exclude_from_ui(file_path):
                        continue

                    # 暗号化ファイルかチェック
                    is_encrypted = filename.endswith(".enc")
                    display_name = relative_path[:-4] if is_encrypted else relative_path

                    # ファイルサイズとタイムスタンプを取得
                    file_stat = os.stat(file_path)
                    file_size = file_stat.st_size
                    backup_mtime = file_stat.st_mtime

                    # ローカルファイルの存在確認とタイムスタンプ
                    local_path = os.path.expanduser(f"~/{display_name}")
                    local_exists = os.path.exists(local_path)
                    local_mtime = os.path.getmtime(local_path) if local_exists else None
                    local_size = os.path.getsize(local_path) if local_exists else 0

                    # 統一されたファイル状態分析を使用
                    status = self.file_comparison_manager.analyze_file_relationship(
                        Path(local_path),
                        Path(file_path),
                        local_mtime,
                        backup_mtime,
                        self.config_manager,
                    )
                    has_changes = status.changed
                    change_type = status.change_type

                    # ファイルが属するtargetを取得
                    target_name = self._get_target_for_file(local_path)

                    files.append(
                        {
                            "name": display_name,
                            "backup_name": filename,
                            "encrypted": is_encrypted,
                            "size": file_size,
                            "local_exists": local_exists,
                            "local_path": local_path,
                            "local_size": local_size,
                            "backup_path": file_path,
                            "backup_mtime": backup_mtime,
                            "local_mtime": local_mtime,
                            "relative_path": relative_path,
                            "is_directory": False,  # ファイルのみなのでFalse
                            "changed": has_changes,  # ハッシュベースの変更検知結果
                            "change_type": change_type,  # 'ahead', 'behind', None
                            "local_only": False,  # リモートに存在するファイル
                            "target": target_name,  # ファイルが属するtarget
                        }
                    )

            # 2. ローカル専用ファイルの検出（自分自身のマシンのみ）
            if include_local_only:
                local_only_files = self._get_local_only_files(files)
                files.extend(local_only_files)

            # パス名でソート（ディレクトリ/ファイル名の階層順）
            files.sort(key=lambda x: x["name"])

        except Exception as e:
            print(f"Error scanning files for {machine_id}: {e}")

        return files

    def _is_current_machine(self, machine_id):
        """指定されたマシンIDが現在のマシンかどうか判定"""
        try:
            current_machine_name = self.config_manager.get_machine_name()
            # マシンIDは通常マシン名と同じ
            return machine_id == current_machine_name
        except Exception:
            return False

    def _get_target_for_file(self, local_path: str) -> str:
        """ファイルパスに対応するtarget名を取得"""
        try:
            file_path = Path(local_path).expanduser().resolve()
            home_path = Path.home()

            best_match = None
            best_match_depth = -1

            for target in self.config.targets:
                target_path = Path(target.path).expanduser().resolve()

                # ファイルパスがtargetのpath以下にあるか確認
                try:
                    relative = file_path.relative_to(target_path)

                    # recursive: false の場合、直下のファイルのみマッチ
                    if not target.recursive:
                        # relative.partsが1つ（ファイル名のみ）の場合のみマッチ
                        if len(relative.parts) != 1:
                            continue

                    # より深いマッチ（より具体的なターゲット）を優先
                    depth = len(target_path.parts)
                    if depth > best_match_depth:
                        best_match_depth = depth
                        # target.pathを読みやすい形式で返す
                        try:
                            display_path = "~/" + str(
                                target_path.relative_to(home_path)
                            )
                        except ValueError:
                            display_path = str(target_path)
                        best_match = display_path
                except ValueError:
                    # このtargetには属さない
                    continue

            if best_match:
                return best_match

            # configにマッチしなかった場合、パスの先頭部分でグループ化
            # （リモートマシンのファイルなど）
            return self._infer_group_from_path(file_path, home_path)

        except Exception:
            return "other"

    def _infer_group_from_path(self, file_path: Path, home_path: Path) -> str:
        """パスの先頭部分からグループ名を推測"""
        try:
            relative_to_home = file_path.relative_to(home_path)
            parts = relative_to_home.parts

            if len(parts) == 0:
                return "~/"
            elif len(parts) == 1:
                # ホームディレクトリ直下のファイル（.zshrcなど）
                return "~/"
            else:
                # 最初のディレクトリをグループ名に
                first_dir = parts[0]
                return f"~/{first_dir}"
        except ValueError:
            # ホームディレクトリ外のファイル
            return "other"

    def clear_local_only_cache(self):
        """ローカル専用ファイル検出とハッシュキャッシュをクリア

        Restore後の正確なファイル比較のため、ハッシュキャッシュもクリアする。
        """
        if hasattr(self.file_comparison_manager, "_path_cache"):
            self.file_comparison_manager._path_cache.clear()
        if hasattr(self.file_comparison_manager, "_inode_cache"):
            self.file_comparison_manager._inode_cache.clear()
        if hasattr(self.file_comparison_manager, "_hash_cache"):
            self.file_comparison_manager._hash_cache.clear()

    def _get_local_only_files(self, existing_files):
        """ローカルにのみ存在するファイルを検出"""
        local_only_files = []

        try:
            # 既存ファイルのパスを収集
            existing_file_paths = []
            for file_info in existing_files:
                local_path = file_info.get("local_path")
                if local_path:
                    existing_file_paths.append(Path(local_path))

            # FileComparisonManagerで重複検知用のベースデータを構築
            if existing_file_paths:
                # detect_duplicatesを呼び出してキャッシュを初期化（戻り値は使用しない）
                self.file_comparison_manager.detect_duplicates(
                    existing_file_paths, DuplicateDetectionMethod.COMPREHENSIVE
                )
                # 既存ファイルの情報をキャッシュに登録
                for file_path in existing_file_paths:
                    duplicate_info = self.file_comparison_manager._analyze_duplicate(
                        file_path,
                        DuplicateDetectionMethod.COMPREHENSIVE,
                        self.file_comparison_manager._path_cache,
                        self.file_comparison_manager._inode_cache,
                    )
                    if not duplicate_info.is_duplicate:
                        self.file_comparison_manager._path_cache.add(
                            duplicate_info.normalized_path
                        )
                        if duplicate_info.inode:
                            self.file_comparison_manager._inode_cache.add(
                                duplicate_info.inode
                            )

            # 設定のtargetsからバックアップ対象ファイルを取得
            target_file_paths = self._get_target_file_paths_from_config()

            # targetsベースの検索を実行
            for target_path in target_file_paths:
                # すでに存在するファイルかチェック
                duplicate_info = self.file_comparison_manager._analyze_duplicate(
                    target_path,
                    DuplicateDetectionMethod.COMPREHENSIVE,
                    self.file_comparison_manager._path_cache,
                    self.file_comparison_manager._inode_cache,
                )

                # 重複している場合はスキップ
                if duplicate_info.is_duplicate:
                    continue

                # ディレクトリは除外
                if not target_path.is_file():
                    continue

                # ホームディレクトリからの相対パス
                try:
                    home_path = Path.home()
                    relative_path = os.path.relpath(target_path, home_path)

                    # セキュリティ保護・システムファイルをフィルタリング
                    if self._should_exclude_from_ui(str(target_path)):
                        continue

                    # ファイル情報を取得
                    file_stat = target_path.stat()
                    file_size = file_stat.st_size
                    local_mtime = file_stat.st_mtime

                    # ファイルが属するtargetを取得
                    target_name = self._get_target_for_file(str(target_path))

                    local_only_files.append(
                        {
                            "name": relative_path,
                            "backup_name": None,
                            "encrypted": False,
                            "size": file_size,
                            "local_exists": True,
                            "local_path": str(target_path),
                            "local_size": file_size,
                            "backup_path": None,
                            "backup_mtime": None,
                            "local_mtime": local_mtime,
                            "relative_path": relative_path,
                            "is_directory": False,
                            "changed": False,
                            "change_type": None,
                            "local_only": True,
                            "target": target_name,  # ファイルが属するtarget
                        }
                    )

                    # キャッシュに登録
                    self.file_comparison_manager._path_cache.add(
                        duplicate_info.normalized_path
                    )
                    if duplicate_info.inode:
                        self.file_comparison_manager._inode_cache.add(
                            duplicate_info.inode
                        )

                except (ValueError, OSError):
                    continue

        except Exception as e:
            print(f"Error scanning local-only files: {e}")

        return local_only_files

    def _get_target_file_paths_from_config(self):
        """設定のtargetsからローカル専用ファイルの候補パスを取得"""
        target_paths = []

        try:
            # file_managerのcollect_target_filesを利用
            for target in self.config.targets:
                for (
                    source_file,
                    relative_path,
                ) in self.file_manager.collect_target_files(target):
                    target_paths.append(source_file)
        except Exception as e:
            print(f"Error collecting target file paths: {e}")

        return target_paths

    def get_file_diff(self, machine_id, file_info):
        """ファイルの差分を取得"""
        try:
            backup_file_path = file_info["backup_path"]
            local_file_path = file_info["local_path"]

            # バックアップファイルが存在しない場合
            if not os.path.exists(backup_file_path):
                return {
                    "diff_lines": ["Backup file not found"],
                    "has_changes": True,
                    "local_exists": file_info["local_exists"],
                    "encrypted": file_info["encrypted"],
                    "line_count": 1,
                }

            # ローカルファイルが存在しない場合
            if not os.path.exists(local_file_path):
                return {
                    "diff_lines": ["Local file does not exist"],
                    "has_changes": True,
                    "local_exists": False,
                    "encrypted": file_info["encrypted"],
                    "line_count": 1,
                }

            # バックアップファイルの内容を取得
            if file_info["encrypted"]:
                # 暗号化ファイルの場合は復号化
                try:
                    backup_content = (
                        self.file_manager.encryption_manager.decrypt_file_content(
                            backup_file_path
                        )
                    )
                    backup_lines = backup_content.decode(
                        "utf-8", errors="replace"
                    ).splitlines()
                except Exception as e:
                    return {
                        "diff_lines": [f"Error decrypting backup file: {str(e)}"],
                        "has_changes": True,
                        "local_exists": file_info["local_exists"],
                        "encrypted": file_info["encrypted"],
                        "line_count": 1,
                    }
            else:
                # 通常ファイル
                try:
                    with open(
                        backup_file_path, "r", encoding="utf-8", errors="replace"
                    ) as f:
                        backup_lines = f.read().splitlines()
                except Exception as e:
                    return {
                        "diff_lines": [f"Error reading backup file: {str(e)}"],
                        "has_changes": True,
                        "local_exists": file_info["local_exists"],
                        "encrypted": file_info["encrypted"],
                        "line_count": 1,
                    }

            # ローカルファイルの内容を取得
            try:
                with open(
                    local_file_path, "r", encoding="utf-8", errors="replace"
                ) as f:
                    local_lines = f.read().splitlines()
            except Exception as e:
                return {
                    "diff_lines": [f"Error reading local file: {str(e)}"],
                    "has_changes": True,
                    "local_exists": file_info["local_exists"],
                    "encrypted": file_info["encrypted"],
                    "line_count": 1,
                }

            # 差分を生成
            import difflib

            diff_lines = list(
                difflib.unified_diff(
                    local_lines,
                    backup_lines,
                    fromfile=f"local/{file_info['name']}",
                    tofile=f"backup/{file_info['name']}",
                    lineterm="",
                )
            )

            has_changes = len(diff_lines) > 0

            return {
                "diff_lines": diff_lines if has_changes else ["No differences found"],
                "has_changes": has_changes,
                "local_exists": file_info["local_exists"],
                "encrypted": file_info["encrypted"],
                "line_count": len(diff_lines),
            }

        except Exception as e:
            return {
                "diff_lines": [f"Error getting diff: {str(e)}"],
                "has_changes": True,
                "local_exists": file_info["local_exists"],
                "encrypted": file_info["encrypted"],
                "line_count": 1,
            }

    def get_file_content_preview(self, machine_id, file_info, max_lines=20):
        """ファイル内容のプレビューを取得"""
        try:
            # backup_pathを直接使用（すでに正しいフルパスが設定されている）
            backup_file_path = file_info["backup_path"]

            if not os.path.exists(backup_file_path):
                return ["File not found in backup"]

            # 暗号化ファイルの場合は復号化して読み込み
            if file_info["encrypted"]:
                try:
                    # 既存の暗号化機能を使用
                    decrypted_content = (
                        self.file_manager.encryption_manager.decrypt_file_content(
                            backup_file_path
                        )
                    )
                    lines = decrypted_content.decode("utf-8", errors="replace").split(
                        "\n"
                    )
                except Exception as e:
                    return [f"Error decrypting file: {str(e)}"]
            else:
                # 通常ファイル
                try:
                    with open(
                        backup_file_path, "r", encoding="utf-8", errors="replace"
                    ) as f:
                        lines = f.read().split("\n")
                except Exception as e:
                    return [f"Error reading file: {str(e)}"]

            # 最大行数まで返す
            preview_lines = lines[:max_lines]
            if len(lines) > max_lines:
                preview_lines.append(f"... ({len(lines) - max_lines} more lines)")

            return preview_lines

        except Exception as e:
            return [f"Error getting preview: {str(e)}"]

    def restore_file(self, machine_id, file_info):
        """単一ファイルを復元"""
        try:
            # 既存のrestore機能を使用
            result = self.file_manager.restore_specific_files(
                machine_id, [file_info["name"]]
            )

            # 結果の解析
            restored_count = len(result.get("restored", []))
            unchanged_count = len(result.get("unchanged", []))
            error_count = len(result.get("errors", []))

            if error_count > 0:
                return {
                    "success": False,
                    "message": f"Error restoring {file_info['name']}: {'; '.join(result['errors'])}",
                }
            elif restored_count > 0:
                return {
                    "success": True,
                    "message": f"Successfully restored {file_info['name']}",
                }
            elif unchanged_count > 0:
                return {
                    "success": True,
                    "message": f"{file_info['name']} is already up to date",
                }
            else:
                return {
                    "success": False,
                    "message": f"No changes made to {file_info['name']}",
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error restoring {file_info['name']}: {str(e)}",
            }

    def restore_files(self, machine_id, file_infos):
        """複数ファイルを復元"""
        try:
            # ファイル名のリストを作成
            file_names = [file_info["name"] for file_info in file_infos]

            # 既存のrestore機能を使用
            result = self.file_manager.restore_specific_files(machine_id, file_names)

            # 結果をサマリー
            restored_count = len(result.get("restored", []))
            unchanged_count = len(result.get("unchanged", []))
            error_count = len(result.get("errors", []))

            # メッセージの構築
            message_parts = []
            if restored_count > 0:
                message_parts.append(f"{restored_count} files restored")
            if unchanged_count > 0:
                message_parts.append(f"{unchanged_count} files unchanged")
            if error_count > 0:
                message_parts.append(f"{error_count} errors")

            if error_count == 0:
                if restored_count == 0 and unchanged_count > 0:
                    # 全てのファイルがunchangedの場合
                    message = f"All {unchanged_count} files are already up to date"
                elif message_parts:
                    message = "Successfully completed: " + ", ".join(message_parts)
                else:
                    message = "No files to restore"

                return {"success": True, "message": message}
            else:
                message = "Completed with issues: " + ", ".join(message_parts)
                return {"success": False, "message": message}
        except Exception as e:
            return {"success": False, "message": f"Error restoring files: {str(e)}"}

    def export_file(self, machine_id, file_info, destination_path):
        """ファイルをエクスポート"""
        try:
            # 既存のexport機能を使用
            self.file_manager.export_file(
                machine_id, file_info["name"], destination_path
            )
            return {
                "success": True,
                "message": f"Successfully exported {file_info['name']} to {destination_path}",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error exporting {file_info['name']}: {str(e)}",
            }

    def validate_export_path(self, path):
        """エクスポートパスの妥当性をチェック（従来の単一ファイル用）"""
        try:
            expanded_path = os.path.expanduser(path)
            # 絶対パスに変換（相対パスの場合はカレントディレクトリを基準）
            absolute_path = os.path.abspath(expanded_path)
            parent_dir = os.path.dirname(absolute_path)

            # 親ディレクトリが存在するかチェック
            if not os.path.exists(parent_dir):
                return {
                    "valid": False,
                    "message": f"Parent directory does not exist: {parent_dir}",
                }

            # 書き込み権限をチェック
            if not os.access(parent_dir, os.W_OK):
                return {
                    "valid": False,
                    "message": f"No write permission to: {parent_dir}",
                }

            # ファイルが既に存在する場合は警告
            if os.path.exists(absolute_path):
                return {
                    "valid": True,
                    "warning": f"File already exists and will be overwritten: {absolute_path}",
                    "path": absolute_path,
                }

            return {"valid": True, "path": absolute_path}

        except Exception as e:
            return {"valid": False, "message": f"Invalid path: {str(e)}"}

    def validate_export_directory(self, dir_path):
        """エクスポートディレクトリの妥当性をチェック"""
        try:
            expanded_path = os.path.expanduser(dir_path)

            # 絶対パスでない場合（相対パス）は、カレントディレクトリ基準で絶対パスに変換
            if not os.path.isabs(expanded_path):
                absolute_path = os.path.abspath(expanded_path)
            else:
                absolute_path = expanded_path

            # 親ディレクトリの存在と書き込み権限をチェック
            parent_dir = os.path.dirname(absolute_path)

            # ルートディレクトリの場合は特別処理
            if parent_dir == absolute_path:
                # ルートディレクトリ自体への書き込み権限をチェック
                if not os.access(absolute_path, os.W_OK):
                    return {
                        "valid": False,
                        "message": f"No write permission to: {absolute_path}",
                    }
            else:
                # 親ディレクトリが存在するかチェック
                if not os.path.exists(parent_dir):
                    return {
                        "valid": False,
                        "message": f"Parent directory does not exist: {parent_dir}",
                    }

                # 親ディレクトリへの書き込み権限をチェック
                if not os.access(parent_dir, os.W_OK):
                    return {
                        "valid": False,
                        "message": f"No write permission to parent directory: {parent_dir}",
                    }

            return {"valid": True, "path": absolute_path}

        except Exception as e:
            return {"valid": False, "message": f"Invalid directory path: {str(e)}"}

    def check_export_file_conflicts(self, file_infos, destination_dir):
        """エクスポート時のファイル競合をチェック"""
        try:
            conflicts = []

            for file_info in file_infos:
                # ファイル名を取得（パス区切りを置換してフラットなファイル名にする）
                file_name = file_info["name"]
                safe_filename = file_name.replace("/", "_").replace("\\", "_")
                destination_file = os.path.join(destination_dir, safe_filename)

                if os.path.exists(destination_file):
                    conflicts.append(
                        {
                            "original_name": file_name,
                            "safe_filename": safe_filename,
                            "destination_path": destination_file,
                        }
                    )

            return {
                "has_conflicts": len(conflicts) > 0,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
            }

        except Exception as e:
            return {
                "has_conflicts": False,
                "conflict_count": 0,
                "conflicts": [],
                "error": f"Error checking conflicts: {str(e)}",
            }

    def export_files_to_directory(self, machine_id, file_infos, destination_dir):
        """複数ファイルをディレクトリにエクスポート"""
        try:
            # デバッグ情報
            # Export request logging - visible in app.log

            # ディレクトリを作成（相対パスの場合のみmkdir -p）
            os.makedirs(destination_dir, exist_ok=True)
            # Directory created - visible in app.log

            success_count = 0
            error_count = 0
            errors = []

            for file_info in file_infos:
                try:
                    # ファイル名を取得（パス区切りを置換してフラットなファイル名にする）
                    file_name = file_info["name"]
                    safe_filename = file_name.replace("/", "_").replace("\\", "_")
                    destination_file = os.path.join(destination_dir, safe_filename)

                    # 既存のexport機能を使用
                    self.file_manager.export_file(
                        machine_id, file_info["name"], destination_file, decrypt=True
                    )
                    success_count += 1

                except Exception as e:
                    # Export error - visible in app.log
                    error_count += 1
                    errors.append(f"{file_info['name']}: {str(e)}")

            if error_count == 0:
                return {
                    "success": True,
                    "message": f"Successfully exported {success_count} files to {destination_dir}",
                }
            else:
                return {
                    "success": False,
                    "message": f"Exported {success_count} files, {error_count} errors: {'; '.join(errors[:3])}",
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error exporting files to directory: {str(e)}",
            }

    def backup_files_to_repository(
        self, machine_name: str = None, dry_run: bool = False
    ):
        """現在のマシンのファイルをバックアップ"""
        import io
        import sys

        try:
            # マシン名が指定されていない場合は設定から取得
            if not machine_name:
                machine_name = self.config_manager.get_machine_name()

            # 標準出力をキャプチャ
            captured_output = io.StringIO()
            original_stdout = sys.stdout
            sys.stdout = captured_output

            try:
                # 既存のbackup機能を使用
                result = self.file_manager.backup_files(machine_name, dry_run=dry_run)
            finally:
                # 標準出力を元に戻す
                sys.stdout = original_stdout

            # キャプチャした出力を取得
            console_output = captured_output.getvalue()

            # 結果を統合
            success_count = len(result.get("copied", []))
            skip_count = len(result.get("skipped", []))
            error_count = len(result.get("errors", []))

            # メッセージを生成
            if dry_run:
                message = f"[DRY RUN] Would backup {success_count} files (skip {skip_count}, errors {error_count})"
            else:
                message = f"Backup completed: {success_count} files copied, {skip_count} skipped, {error_count} errors"

            # 詳細情報を追加（CLIの出力 + ファイルリスト）
            details = []

            # コンソール出力を追加（ANSIコードを保持 - RichLogで表示）
            if console_output.strip():
                details.append(console_output.strip())
                details.append("")

            # ファイルリストを詳細表示（colorama色付き）
            if result.get("copied"):
                header = "Files that would be copied:" if dry_run else "Files copied:"
                details.append(f"{Fore.CYAN}{header}{Style.RESET_ALL}")
                for file_path in result["copied"]:
                    details.append(f"  {Fore.GREEN}✓{Style.RESET_ALL} {file_path}")
                details.append("")

            if result.get("skipped"):
                details.append(f"{Fore.CYAN}Files skipped:{Style.RESET_ALL}")
                for file_path in result["skipped"]:
                    details.append(f"  {Fore.YELLOW}!{Style.RESET_ALL} {file_path}")
                details.append("")

            if result.get("errors"):
                details.append(f"{Fore.CYAN}Errors:{Style.RESET_ALL}")
                for error in result["errors"]:
                    details.append(f"  {Fore.RED}✗{Style.RESET_ALL} {error}")
                details.append("")

            # nextステップの提案（dry_runでないときのみ）
            if not dry_run and success_count > 0:
                details.append(f"{Fore.CYAN}Next steps:{Style.RESET_ALL}")
                details.append(f"  git add {machine_name}/")
                details.append(
                    f'  git commit -m "backup({machine_name}): $(date +%Y-%m-%d)"'
                )
                details.append("  git push")

            return {
                "success": error_count == 0,
                "message": message,
                "details": "\n".join(details) if details else "",
                "result": result,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Backup failed: {str(e)}",
                "details": "",
                "result": {},
            }

    def git_is_working_directory_clean(self) -> dict:
        """ワーキングディレクトリがクリーンかどうかを確認"""
        return self.file_manager.git_is_working_directory_clean()

    def git_pull_repository(self, dry_run: bool = False):
        """リポジトリでgit pullを実行"""
        try:
            # git pullを実行
            result = self.file_manager.git_pull_repository(dry_run=dry_run)

            # メッセージを生成
            if dry_run:
                message = "[DRY RUN] Would pull repository changes"
            else:
                if result["success"]:
                    message = "Repository updated successfully"
                else:
                    message = "Git pull failed"

            # 詳細情報を追加（colorama色付き）
            details = []

            # コマンド出力を表示
            if result.get("output"):
                details.append(f"{Fore.CYAN}Git Output:{Style.RESET_ALL}")
                details.append(result["output"])
                details.append("")

            # エラー情報を表示
            if result.get("error"):
                details.append(f"{Fore.RED}Errors/Warnings:{Style.RESET_ALL}")
                details.append(result["error"])
                details.append("")

            # 成功時の追加情報
            if result["success"] and not dry_run:
                details.append(
                    f"{Fore.GREEN}✓ Repository has been updated with latest changes.{Style.RESET_ALL}"
                )
                details.append("")

            # dry-run時の情報
            if dry_run:
                details.append(f"{Fore.CYAN}Planned Operations:{Style.RESET_ALL}")
                details.append("  1. git pull")
                details.append("")
                details.append(
                    f"{Fore.YELLOW}(dry-run) No actual changes will be made.{Style.RESET_ALL}"
                )

            return {
                "success": result["success"],
                "message": message,
                "details": "\n".join(details) if details else "",
                "result": result,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Git pull failed: {str(e)}",
                "details": f"Error: {str(e)}",
                "result": {},
            }

    def get_repository_path_info(self):
        """リポジトリパス情報を取得"""
        return {
            "path": str(self.file_manager.repo_root),
            "exists": self.file_manager.repo_root.exists(),
        }

    def git_commit_push_repository(
        self, machine_name: str = None, dry_run: bool = False
    ):
        """リポジトリでgit add, commit, pushを実行"""

        try:
            # マシン名が指定されていない場合は設定から取得
            if not machine_name:
                machine_name = self.config_manager.get_machine_name()

            # git_commit_push_repositoryを実行（このメソッドは直接printしないので標準出力キャプチャは不要）
            result = self.file_manager.git_commit_push_repository(
                machine_name, dry_run=dry_run
            )

            # メッセージを生成
            if dry_run:
                message = f"[DRY RUN] Would commit and push {machine_name}"
            else:
                if result["success"]:
                    message = f"Successfully committed and pushed {machine_name}"
                else:
                    message = f"Failed to commit and push {machine_name}"

            # 詳細情報を追加（colorama色付き）
            details = []

            # コマンド出力を表示
            if result.get("output"):
                details.append(f"{Fore.CYAN}Git Output:{Style.RESET_ALL}")
                details.append(result["output"])
                details.append("")

            # エラー情報を表示
            if result.get("error"):
                details.append(f"{Fore.RED}Errors/Warnings:{Style.RESET_ALL}")
                details.append(result["error"])
                details.append("")

            # 成功時の追加情報
            if result["success"] and not dry_run:
                commit_msg = result.get("commit_message", "N/A")
                details.append(f"{Fore.CYAN}Commit Information:{Style.RESET_ALL}")
                details.append(f"  Commit message: {commit_msg}")
                details.append(f"  Machine: {machine_name}")
                details.append("")
                details.append(
                    f"{Fore.GREEN}✓ Changes have been pushed to the remote repository.{Style.RESET_ALL}"
                )

            # dry-run時の情報
            if dry_run:
                details.append(f"{Fore.CYAN}Planned Operations:{Style.RESET_ALL}")
                details.append(f"  1. git add {machine_name}/")
                details.append(
                    f'  2. git commit -m "updated {machine_name} YYYY-MM-DD"'
                )
                details.append("  3. git push")
                details.append("")
                details.append(
                    f"{Fore.YELLOW}(dry-run) No actual changes will be made.{Style.RESET_ALL}"
                )

            return {
                "success": result["success"],
                "message": message,
                "details": "\n".join(details) if details else "",
                "result": result,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Git commit push failed: {str(e)}",
                "details": f"Error: {str(e)}",
                "result": {},
            }

    def get_local_file_content_preview(self, file_info, max_lines=1000):
        """ローカルファイル内容のプレビューを取得"""
        try:
            local_file_path = file_info["local_path"]

            if not os.path.exists(local_file_path):
                return ["Local file does not exist"]

            # ローカルファイルを直接読み込み
            with open(local_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()

            # 行数制限を適用
            if max_lines and len(lines) > max_lines:
                original_count = len(lines)
                lines = lines[:max_lines]
                lines.append(
                    f"... (showing first {max_lines} lines of {original_count} total)"
                )

            return lines

        except Exception as e:
            return [f"Error reading local file: {str(e)}"]

    def open_vscode_diff(self, file_info):
        """VSCodeでlocal vs databaseファイルの差分を表示"""
        import subprocess
        import tempfile
        import os
        import shutil

        try:
            # ローカル専用ファイルの場合は特別な処理
            if file_info.get("local_only", False):
                return {
                    "success": False,
                    "message": f"Cannot show diff for local-only file. Use 'Backup' to add {file_info['name']} to repository first.",
                }

            local_path = file_info["local_path"]

            # ローカルファイルの存在確認
            if not os.path.exists(local_path):
                return {
                    "success": False,
                    "message": f"Local file does not exist: {local_path}",
                }

            # VSCodeコマンドの存在確認
            vscode_commands = ["code", "code-insiders", "cursor", "windsurf"]
            vscode_cmd = None

            for cmd in vscode_commands:
                try:
                    subprocess.run(
                        [cmd, "--version"], capture_output=True, check=True, timeout=5
                    )
                    vscode_cmd = cmd
                    break
                except (
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                    FileNotFoundError,
                ):
                    continue

            if not vscode_cmd:
                return {
                    "success": False,
                    "message": "Code editor not found. Please install VS Code, VS Code Insiders, Cursor, or Windsurf and ensure the command is in PATH.",
                }

            # 一時ファイルを作成してdatabase版をエクスポート
            temp_dir = tempfile.mkdtemp(prefix="triton_diff_")

            # ファイル名から安全な一時ファイル名を作成
            safe_filename = (
                os.path.basename(file_info["name"]).replace("/", "_").replace("\\", "_")
            )
            temp_db_file = os.path.join(temp_dir, f"database_{safe_filename}")

            # データベースファイルを一時ファイルにエクスポート
            backup_file_path = file_info["backup_path"]

            if file_info["encrypted"]:
                # 暗号化ファイルの場合は復号化
                try:
                    decrypted_content = (
                        self.file_manager.encryption_manager.decrypt_file_content(
                            backup_file_path
                        )
                    )
                    with open(temp_db_file, "wb") as f:
                        f.write(decrypted_content)
                except Exception as e:
                    shutil.rmtree(temp_dir)
                    return {
                        "success": False,
                        "message": f"Error decrypting database file: {str(e)}",
                    }
            else:
                # 通常ファイルの場合はコピー
                try:
                    shutil.copy2(backup_file_path, temp_db_file)
                except Exception as e:
                    shutil.rmtree(temp_dir)
                    return {
                        "success": False,
                        "message": f"Error copying database file: {str(e)}",
                    }

            # VSCode diff起動
            try:
                subprocess.Popen(
                    [
                        vscode_cmd,
                        "--diff",
                        local_path,  # Local (左側)
                        temp_db_file,  # Database (右側)
                    ],
                    cwd=os.path.expanduser("~"),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # 注意: 一時ファイルはVSCodeが開いている間は削除しない
                # TODO: より良いクリーンアップ機構が必要

                return {
                    "success": True,
                    "message": f"Opened {file_info['name']} in VSCode diff view",
                    "temp_dir": temp_dir,  # クリーンアップ用
                    "vscode_cmd": vscode_cmd,
                }

            except Exception as e:
                shutil.rmtree(temp_dir)
                return {
                    "success": False,
                    "message": f"Error launching VSCode: {str(e)}",
                }

        except Exception as e:
            return {"success": False, "message": f"Error opening VSCode diff: {str(e)}"}

    def open_vscode_edit(self, file_info):
        """VSCodeでローカルファイルを直接編集"""
        import subprocess
        import os

        try:
            local_path = file_info["local_path"]

            # ローカルファイルの存在確認
            if not os.path.exists(local_path):
                return {
                    "success": False,
                    "message": f"Local file does not exist: {local_path}",
                }

            # VSCodeコマンドの存在確認（既存のロジックを再利用）
            vscode_commands = ["code", "code-insiders", "cursor", "windsurf"]
            vscode_cmd = None

            for cmd in vscode_commands:
                try:
                    subprocess.run(
                        [cmd, "--version"], capture_output=True, check=True, timeout=5
                    )
                    vscode_cmd = cmd
                    break
                except (
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                    FileNotFoundError,
                ):
                    continue

            if not vscode_cmd:
                return {
                    "success": False,
                    "message": "Code editor not found. Please install VS Code, VS Code Insiders, Cursor, or Windsurf and ensure the command is in PATH.",
                }

            # VSCodeでローカルファイルを直接開く
            try:
                subprocess.Popen(
                    [
                        vscode_cmd,
                        local_path,  # ローカルファイルを直接開く
                    ],
                    cwd=os.path.expanduser("~"),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                return {
                    "success": True,
                    "message": f"Opened {file_info['name']} for editing in {vscode_cmd}",
                    "vscode_cmd": vscode_cmd,
                }

            except Exception as e:
                return {
                    "success": False,
                    "message": f"Error launching {vscode_cmd}: {str(e)}",
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error opening file for editing: {str(e)}",
            }

    def cleanup_repository_files(self, machine_name: str, dry_run: bool = False):
        """リポジトリから孤立ファイルを削除（ローカルに存在しないファイル）"""
        try:
            # 既存のcleanup機能を使用
            result = self.file_manager.cleanup_repository_files(
                machine_name, dry_run=dry_run
            )

            # 結果を統合
            deleted_count = len(result.get("deleted", []))
            would_delete_count = len(result.get("would_delete", []))
            error_count = len(result.get("errors", []))

            # メッセージを生成
            if dry_run:
                message = f"[DRY RUN] Would delete {would_delete_count} orphaned files"
            else:
                message = f"Repository cleanup completed: {deleted_count} files deleted, {error_count} errors"

            return {"success": error_count == 0, "message": message, "result": result}

        except Exception as e:
            return {
                "success": False,
                "message": f"Repository cleanup failed: {str(e)}",
                "result": {},
            }

    # --- Hooks Methods ---

    def has_startup_hooks(self) -> bool:
        """起動時フックが設定されているか"""
        return bool(self.config.hooks.on_startup)

    def run_startup_hooks(self, dry_run: bool = False) -> dict:
        """
        起動時フックを実行。

        Args:
            dry_run: Trueの場合、実行せずに何が実行されるかを返す

        Returns:
            HookManager.run_startup_hooks() の戻り値
        """
        from ...managers.hook_manager import HookManager

        hook_manager = HookManager(self.config.hooks)
        return hook_manager.run_startup_hooks(dry_run=dry_run)

    def run_startup_hooks_with_progress(
        self,
        on_hook_start: callable = None,
        on_hook_complete: callable = None,
    ) -> dict:
        """
        進捗コールバック付きで起動時フックを実行。

        Args:
            on_hook_start: フック開始時のコールバック (index, command) -> None
            on_hook_complete: フック完了時のコールバック (index, command, success, skipped) -> None

        Returns:
            HookManager.run_startup_hooks_with_progress() の戻り値
        """
        from ...managers.hook_manager import HookManager

        hook_manager = HookManager(self.config.hooks)
        return hook_manager.run_startup_hooks_with_progress(
            dry_run=False,
            on_hook_start=on_hook_start,
            on_hook_complete=on_hook_complete,
        )
