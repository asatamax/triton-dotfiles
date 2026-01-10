#!/usr/bin/env python3
"""
Triton Dotfiles - Hook Manager

起動時フックの実行を管理するモジュール。
"""

import subprocess
import time
from typing import Any, Dict, List, Optional

from ..config import HooksConfig


class HookManager:
    """起動時フック実行マネージャー"""

    def __init__(self, hooks_config: HooksConfig):
        """
        HookManagerを初期化。

        Args:
            hooks_config: HooksConfig dataclass instance
        """
        self.hooks_config = hooks_config

    def run_startup_hooks(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        起動時フックを順次実行。

        全体のタイムアウトを各hookで消費していく方式。
        失敗しても続行し、結果を収集する。

        Args:
            dry_run: Trueの場合、実行せずに何が実行されるかを返す

        Returns:
            {
                "success": bool,      # 全て成功したか
                "total": int,         # 総フック数
                "succeeded": int,     # 成功数
                "failed": int,        # 失敗数
                "skipped": int,       # スキップ数（タイムアウト等）
                "results": List[Dict],# 各フックの結果
                "summary": str,       # サマリ文字列
                "dry_run": bool,      # dry_runモードかどうか
            }
        """
        return self.run_startup_hooks_with_progress(dry_run=dry_run)

    def run_startup_hooks_with_progress(
        self,
        dry_run: bool = False,
        on_hook_start: Optional[callable] = None,
        on_hook_complete: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        進捗コールバック付きで起動時フックを順次実行。

        全体のタイムアウトを各hookで消費していく方式。
        失敗しても続行し、結果を収集する。

        Args:
            dry_run: Trueの場合、実行せずに何が実行されるかを返す
            on_hook_start: フック開始時のコールバック (index, command) -> None
            on_hook_complete: フック完了時のコールバック (index, command, success, skipped) -> None

        Returns:
            {
                "success": bool,      # 全て成功したか
                "total": int,         # 総フック数
                "succeeded": int,     # 成功数
                "failed": int,        # 失敗数
                "skipped": int,       # スキップ数（タイムアウト等）
                "results": List[Dict],# 各フックの結果
                "summary": str,       # サマリ文字列
                "dry_run": bool,      # dry_runモードかどうか
            }
        """
        hooks = self.hooks_config.on_startup
        timeout = self.hooks_config.timeout

        if not hooks:
            return {
                "success": True,
                "total": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
                "summary": "No hooks configured",
                "dry_run": dry_run,
            }

        if dry_run:
            return self._dry_run_hooks(hooks, timeout)

        return self._execute_hooks(hooks, timeout, on_hook_start, on_hook_complete)

    def _dry_run_hooks(self, hooks: List[str], timeout: int) -> Dict[str, Any]:
        """Dry-run mode: 実行せずに何が実行されるかを返す"""
        results = []
        for i, command in enumerate(hooks):
            results.append(
                {
                    "index": i,
                    "command": command,
                    "would_execute": True,
                    "dry_run": True,
                }
            )

        return {
            "success": True,
            "total": len(hooks),
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "results": results,
            "summary": f"Would execute {len(hooks)} hook(s) with {timeout}s total timeout",
            "dry_run": True,
        }

    def _execute_hooks(
        self,
        hooks: List[str],
        total_timeout: int,
        on_hook_start: Optional[callable] = None,
        on_hook_complete: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """実際にフックを実行"""
        results = []
        succeeded = 0
        failed = 0
        skipped = 0
        remaining_timeout = float(total_timeout)
        start_time = time.time()

        for i, command in enumerate(hooks):
            # 残り時間チェック
            elapsed = time.time() - start_time
            remaining_timeout = total_timeout - elapsed

            if remaining_timeout <= 0:
                # タイムアウト超過でスキップ
                results.append(
                    {
                        "index": i,
                        "command": command,
                        "success": False,
                        "skipped": True,
                        "error": "Total timeout exceeded",
                        "duration_ms": 0,
                    }
                )
                skipped += 1
                # コールバック: スキップ
                if on_hook_complete:
                    on_hook_complete(i, command, False, True)
                continue

            # コールバック: 開始
            if on_hook_start:
                on_hook_start(i, command)

            result = self._run_single_hook(command, remaining_timeout)
            result["index"] = i
            results.append(result)

            if result.get("skipped"):
                skipped += 1
                # コールバック: スキップ
                if on_hook_complete:
                    on_hook_complete(i, command, False, True)
            elif result["success"]:
                succeeded += 1
                # コールバック: 成功
                if on_hook_complete:
                    on_hook_complete(i, command, True, False)
            else:
                failed += 1
                # コールバック: 失敗
                if on_hook_complete:
                    on_hook_complete(i, command, False, False)

        # サマリ生成
        total = len(hooks)
        if failed == 0 and skipped == 0:
            summary = f"Hooks: {succeeded}/{total}"
        elif skipped > 0:
            summary = f"Hooks: {succeeded}/{total} ({skipped} skipped)"
        else:
            # 失敗したコマンドの最初の1つを表示
            failed_cmd = None
            for r in results:
                if not r["success"] and not r.get("skipped"):
                    failed_cmd = r["command"]
                    # コマンドが長い場合は短縮
                    if len(failed_cmd) > 30:
                        failed_cmd = failed_cmd[:27] + "..."
                    break
            summary = f"Hooks: {succeeded}/{total} ({failed_cmd} failed)"

        return {
            "success": failed == 0 and skipped == 0,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "results": results,
            "summary": summary,
            "dry_run": False,
        }

    def _run_single_hook(
        self, command: str, remaining_timeout: float
    ) -> Dict[str, Any]:
        """
        単一フックを実行。

        Args:
            command: 実行するコマンド
            remaining_timeout: 残りタイムアウト（秒）

        Returns:
            {
                "command": str,
                "success": bool,
                "returncode": int,
                "stdout": str,
                "stderr": str,
                "duration_ms": float,
                "error": str | None,
                "skipped": bool,
            }
        """
        hook_start = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=remaining_timeout,
            )

            duration_ms = (time.time() - hook_start) * 1000

            return {
                "command": command,
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": duration_ms,
                "error": None
                if result.returncode == 0
                else f"Exit code {result.returncode}",
                "skipped": False,
            }

        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - hook_start) * 1000
            return {
                "command": command,
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "duration_ms": duration_ms,
                "error": f"Timeout after {remaining_timeout:.1f}s",
                "skipped": True,
            }

        except Exception as e:
            duration_ms = (time.time() - hook_start) * 1000
            return {
                "command": command,
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "duration_ms": duration_ms,
                "error": str(e),
                "skipped": False,
            }

    def has_hooks(self) -> bool:
        """起動時フックが設定されているか"""
        return bool(self.hooks_config.on_startup)

    def list_hooks(self) -> List[Dict[str, Any]]:
        """
        設定されているフックの一覧を返す。

        Returns:
            List of hook info dicts with 'index' and 'command'
        """
        return [
            {"index": i, "command": cmd}
            for i, cmd in enumerate(self.hooks_config.on_startup)
        ]

    def get_timeout(self) -> int:
        """タイムアウト設定を返す"""
        return self.hooks_config.timeout
