"""
External editor (VSCode-compatible) integration.

Handles editor discovery, diff/edit launching, and secure lifecycle
management of decrypted temp files used for diff views.
"""

import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# VSCode diff用一時ディレクトリの管理
# 復号済みコンテンツ（SSH鍵等）を含むため、確実に削除する必要がある
_TEMP_DIFF_PREFIX = "triton_diff_"
_temp_diff_dirs: list[str] = []


def _cleanup_temp_diff_dirs() -> None:
    """このプロセスが作成した復号済み一時ディレクトリを削除"""
    while _temp_diff_dirs:
        shutil.rmtree(_temp_diff_dirs.pop(), ignore_errors=True)


atexit.register(_cleanup_temp_diff_dirs)


def sweep_stale_diff_dirs() -> None:
    """過去セッションの一時ディレクトリ残骸を掃除

    異常終了等でatexitが走らなかった場合、復号済み秘密情報が
    /tmpに残り続けるため、起動時に必ず一掃する。
    """
    tmp_root = Path(tempfile.gettempdir())
    for stale_dir in tmp_root.glob(f"{_TEMP_DIFF_PREFIX}*"):
        if stale_dir.is_dir() and str(stale_dir) not in _temp_diff_dirs:
            shutil.rmtree(stale_dir, ignore_errors=True)


class EditorManager:
    """VSCode系エディタの検出・起動を管理する。

    Args:
        encryption_manager: 暗号化ファイルのdiff表示時に復号へ使用。
            Noneの場合、暗号化ファイルのdiffはエラーを返す。
    """

    # 検出候補（優先順）
    EDITOR_COMMANDS = ("code", "code-insiders", "cursor", "windsurf")

    EDITOR_NOT_FOUND_MESSAGE = (
        "Code editor not found. Please install VS Code, VS Code Insiders, "
        "Cursor, or Windsurf and ensure the command is in PATH."
    )

    def __init__(self, encryption_manager=None):
        self.encryption_manager = encryption_manager
        sweep_stale_diff_dirs()

    def find_editor_command(self) -> Optional[str]:
        """PATHから利用可能なVSCode系エディタコマンドを探す

        `--version`の実行（1コマンドあたり最大数秒かかる）は行わず、
        whichベースの存在チェックのみで判定する。
        """
        for cmd in self.EDITOR_COMMANDS:
            if shutil.which(cmd):
                return cmd
        return None

    def open_diff(
        self,
        local_path: str,
        backup_path: str,
        encrypted: bool,
        display_name: str,
    ) -> Dict[str, Any]:
        """ローカル vs バックアップの差分をエディタで開く

        バックアップ側は一時ディレクトリにエクスポート（暗号化ファイルは
        復号）してから開く。一時ファイルはatexitと起動時sweepで削除される。

        Returns:
            success / message（+ 成功時は temp_dir, editor_cmd）
        """
        if not os.path.exists(local_path):
            return {
                "success": False,
                "message": f"Local file does not exist: {local_path}",
            }

        editor_cmd = self.find_editor_command()
        if not editor_cmd:
            return {"success": False, "message": self.EDITOR_NOT_FOUND_MESSAGE}

        temp_dir = tempfile.mkdtemp(prefix=_TEMP_DIFF_PREFIX)
        _temp_diff_dirs.append(temp_dir)

        safe_filename = (
            os.path.basename(display_name).replace("/", "_").replace("\\", "_")
        )
        temp_db_file = os.path.join(temp_dir, f"database_{safe_filename}")

        if encrypted:
            try:
                if not self.encryption_manager:
                    raise RuntimeError("Encryption manager not available")
                decrypted_content = self.encryption_manager.decrypt_file_content(
                    backup_path
                )
                with open(temp_db_file, "wb") as f:
                    f.write(decrypted_content)
            except Exception as e:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {
                    "success": False,
                    "message": f"Error decrypting database file: {str(e)}",
                }
        else:
            try:
                shutil.copy2(backup_path, temp_db_file)
            except Exception as e:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {
                    "success": False,
                    "message": f"Error copying database file: {str(e)}",
                }

        # 復号済みコンテンツを含み得るため所有者のみ読み書き可に制限
        os.chmod(temp_db_file, 0o600)

        try:
            subprocess.Popen(
                [
                    editor_cmd,
                    "--diff",
                    local_path,  # Local (左側)
                    temp_db_file,  # Database (右側)
                ],
                cwd=os.path.expanduser("~"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "message": f"Opened {display_name} in {editor_cmd} diff view",
                "temp_dir": temp_dir,
                "editor_cmd": editor_cmd,
            }
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "success": False,
                "message": f"Error launching {editor_cmd}: {str(e)}",
            }

    def open_edit(self, local_path: str, display_name: str) -> Dict[str, Any]:
        """ローカルファイルをエディタで直接開く"""
        if not os.path.exists(local_path):
            return {
                "success": False,
                "message": f"Local file does not exist: {local_path}",
            }

        editor_cmd = self.find_editor_command()
        if not editor_cmd:
            return {"success": False, "message": self.EDITOR_NOT_FOUND_MESSAGE}

        try:
            subprocess.Popen(
                [editor_cmd, local_path],
                cwd=os.path.expanduser("~"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "success": True,
                "message": f"Opened {display_name} for editing in {editor_cmd}",
                "editor_cmd": editor_cmd,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error launching {editor_cmd}: {str(e)}",
            }
