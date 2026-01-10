#!/usr/bin/env python3
"""
Git操作を管理するモジュール
"""

import subprocess
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


class GitManager:
    """Git操作を管理するクラス"""

    def __init__(self, repo_root: Path):
        """
        GitManagerを初期化

        Args:
            repo_root: gitリポジトリのルートパス
        """
        self.repo_root = Path(repo_root)

    def is_git_repository(self) -> bool:
        """gitリポジトリかどうかを確認"""
        return (self.repo_root / ".git").exists()

    def is_working_directory_clean(self) -> Dict[str, Any]:
        """
        ワーキングディレクトリがクリーンかどうかを確認

        Returns:
            チェック結果の辞書:
            - success: チェックが成功したかどうか
            - is_clean: ワーキングディレクトリがクリーンかどうか
            - has_staged: ステージされた変更があるかどうか
            - has_unstaged: ステージされていない変更があるかどうか
            - has_untracked: 未追跡ファイルがあるかどうか
            - message: 状態の説明メッセージ
        """
        if not self.repo_root.exists():
            return {
                "success": False,
                "is_clean": False,
                "message": f"Repository directory does not exist: {self.repo_root}",
                "error": f"Path not found: {self.repo_root}",
            }

        if not self.is_git_repository():
            return {
                "success": False,
                "is_clean": False,
                "message": f"Not a git repository: {self.repo_root}",
                "error": f"No .git directory found in {self.repo_root}",
            }

        try:
            # git status --porcelain で変更を確認
            result = self._run_git_command(["status", "--porcelain"], timeout=10)

            if result.returncode != 0:
                return {
                    "success": False,
                    "is_clean": False,
                    "message": f"Git status failed: {result.stderr}",
                    "error": result.stderr,
                }

            status_output = result.stdout.strip()

            # 出力が空ならクリーン
            if not status_output:
                return {
                    "success": True,
                    "is_clean": True,
                    "has_staged": False,
                    "has_unstaged": False,
                    "has_untracked": False,
                    "message": "Working directory is clean",
                }

            # 各種変更を分類
            has_staged = False
            has_unstaged = False
            has_untracked = False

            for line in status_output.split("\n"):
                if len(line) < 2:
                    continue
                index_status = line[0]
                worktree_status = line[1]

                # ステージされた変更（インデックス列がスペース/? 以外）
                if index_status not in (" ", "?"):
                    has_staged = True

                # ステージされていない変更（ワークツリー列がスペース 以外）
                if worktree_status not in (" ",):
                    if index_status == "?":
                        has_untracked = True
                    else:
                        has_unstaged = True

            # メッセージを構築
            changes = []
            if has_staged:
                changes.append("staged changes")
            if has_unstaged:
                changes.append("unstaged changes")
            if has_untracked:
                changes.append("untracked files")

            message = f"Working directory has: {', '.join(changes)}"

            return {
                "success": True,
                "is_clean": False,
                "has_staged": has_staged,
                "has_unstaged": has_unstaged,
                "has_untracked": has_untracked,
                "message": message,
                "status_output": status_output,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "is_clean": False,
                "message": "Git status check timed out",
                "error": "Command timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "is_clean": False,
                "message": f"Failed to check working directory: {str(e)}",
                "error": str(e),
            }

    def pull_repository(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        リポジトリでgit pullを実行

        Args:
            dry_run: ドライランモード

        Returns:
            実行結果の辞書
        """
        if not self.repo_root.exists():
            return {
                "success": False,
                "message": f"Repository directory does not exist: {self.repo_root}",
                "output": "",
                "error": f"Path not found: {self.repo_root}",
            }

        if not self.is_git_repository():
            return {
                "success": False,
                "message": f"Not a git repository: {self.repo_root}",
                "output": "",
                "error": f"No .git directory found in {self.repo_root}",
            }

        if dry_run:
            return {
                "success": True,
                "message": f"Would execute git pull in {self.repo_root}",
                "output": f"[DRY RUN] git pull in {self.repo_root}",
                "error": "",
            }

        try:
            result = self._run_git_command(["pull"], timeout=30)

            success = result.returncode == 0
            message = (
                "Repository updated successfully" if success else "Git pull failed"
            )

            return {
                "success": success,
                "message": message,
                "output": result.stdout,
                "error": result.stderr,
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Git pull timed out after 30 seconds",
                "output": "",
                "error": "Command timed out",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "message": "Git command not found. Please install git.",
                "output": "",
                "error": "git command not found in PATH",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Git pull failed: {str(e)}",
                "output": "",
                "error": str(e),
            }

    def check_remote_status(self) -> Dict[str, Any]:
        """
        リモートリポジトリの状態をチェック

        Returns:
            チェック結果の辞書
        """
        if not self.repo_root.exists():
            return {
                "success": False,
                "message": f"Repository directory does not exist: {self.repo_root}",
                "need_pull": False,
                "error": f"Path not found: {self.repo_root}",
            }

        if not self.is_git_repository():
            return {
                "success": False,
                "message": f"Not a git repository: {self.repo_root}",
                "need_pull": False,
                "error": f"No .git directory found in {self.repo_root}",
            }

        try:
            # Step 1: git fetch to get latest remote information
            fetch_result = self._run_git_command(["fetch"], timeout=30)
            if fetch_result.returncode != 0:
                return {
                    "success": False,
                    "message": f"Git fetch failed: {fetch_result.stderr}",
                    "need_pull": False,
                    "error": fetch_result.stderr,
                }

            # Step 2: Check if remote is ahead
            # git status --porcelain=v1 --branch で状態をチェック
            status_result = self._run_git_command(
                ["status", "--porcelain=v1", "--branch"]
            )
            if status_result.returncode != 0:
                return {
                    "success": False,
                    "message": f"Git status check failed: {status_result.stderr}",
                    "need_pull": False,
                    "error": status_result.stderr,
                }

            status_output = status_result.stdout
            need_pull = (
                "[behind" in status_output
                or "[ahead" in status_output
                and "[behind" in status_output
            )

            # より詳細なチェック: git log --oneline HEAD..@{u}
            try:
                ahead_check = self._run_git_command(
                    ["rev-list", "--count", "HEAD..@{u}"], timeout=10
                )
                if ahead_check.returncode == 0:
                    commits_behind = (
                        int(ahead_check.stdout.strip())
                        if ahead_check.stdout.strip()
                        else 0
                    )
                    need_pull = commits_behind > 0
                else:
                    # upstream が設定されていない可能性
                    need_pull = False
            except (ValueError, subprocess.TimeoutExpired):
                # フォールバック: status出力から判断
                need_pull = "[behind" in status_output

            return {
                "success": True,
                "message": "Remote status checked successfully",
                "need_pull": need_pull,
                "status_output": status_output,
                "commits_behind": commits_behind if "commits_behind" in locals() else 0,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Git fetch/status check timed out",
                "need_pull": False,
                "error": "Command timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Remote status check failed: {str(e)}",
                "need_pull": False,
                "error": str(e),
            }

    def commit_and_push_machine(
        self, machine_name: str, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        指定されたマシンの変更をcommit & pushする

        Args:
            machine_name: マシン名
            dry_run: ドライランモード

        Returns:
            実行結果の辞書
        """
        if not self.repo_root.exists():
            return {
                "success": False,
                "message": f"Repository directory does not exist: {self.repo_root}",
                "output": "",
                "error": f"Path not found: {self.repo_root}",
            }

        if not self.is_git_repository():
            return {
                "success": False,
                "message": f"Not a git repository: {self.repo_root}",
                "output": "",
                "error": f"No .git directory found in {self.repo_root}",
            }

        # マシンディレクトリが存在するかチェック
        machine_dir = self.repo_root / machine_name
        if not machine_dir.exists():
            return {
                "success": False,
                "message": f"Machine directory does not exist: {machine_name}",
                "output": "",
                "error": f"Directory not found: {machine_dir}",
            }

        if dry_run:
            today = datetime.now().strftime("%Y-%m-%d")
            return {
                "success": True,
                "message": f"Would execute git add, commit, and push for {machine_name}",
                "output": f'[DRY RUN] git add {machine_name}/ && git commit -m "updated {machine_name} {today}" && git push',
                "error": "",
            }

        try:
            # Step 0: Check remote status BEFORE making any changes
            remote_status = self.check_remote_status()
            if not remote_status["success"]:
                return {
                    "success": False,
                    "message": f"Failed to check remote status: {remote_status['message']}",
                    "output": "",
                    "error": remote_status.get("error", ""),
                    "need_pull": False,
                }

            # If remote is ahead, stop and require pull first
            if remote_status["need_pull"]:
                commits_behind = remote_status.get("commits_behind", 0)
                return {
                    "success": False,
                    "message": f"Remote repository is ahead by {commits_behind} commit(s). Please pull changes first.",
                    "output": f"Remote status: {remote_status.get('status_output', '')}",
                    "error": "PULL_REQUIRED",
                    "need_pull": True,
                    "commits_behind": commits_behind,
                }

            today = datetime.now().strftime("%Y-%m-%d")
            commit_message = f"updated {machine_name} {today}"

            # Step 1: git add
            add_result = self._add_machine_files(machine_name)
            if not add_result["success"]:
                return add_result

            # Step 1.5: Check if there are staged changes
            staged_check = self._has_staged_changes()
            if staged_check["success"] and not staged_check["has_staged"]:
                # No changes to commit - this is a success, not an error
                return {
                    "success": True,
                    "message": "No changes to commit - repository is already up to date",
                    "output": add_result["output"],
                    "error": "",
                    "skipped": True,
                }

            # Step 2: git commit
            commit_result = self._commit_changes(commit_message)
            if not commit_result["success"]:
                return commit_result

            # Step 3: git push
            push_result = self._push_changes()
            if not push_result["success"]:
                return push_result

            # 全て成功
            all_output = [
                add_result["output"],
                commit_result["output"],
                push_result["output"],
            ]

            return {
                "success": True,
                "message": f"Successfully committed and pushed {machine_name}",
                "output": "\n".join(filter(None, all_output)),
                "error": "",
                "commit_message": commit_message,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Git commit push failed: {str(e)}",
                "output": "",
                "error": str(e),
            }

    def _run_git_command(
        self, args: list, timeout: int = 30
    ) -> subprocess.CompletedProcess:
        """
        gitコマンドを実行

        Args:
            args: gitコマンドの引数リスト
            timeout: タイムアウト秒数

        Returns:
            実行結果
        """
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _has_staged_changes(self) -> Dict[str, Any]:
        """ステージされた変更があるかチェック

        Returns:
            チェック結果の辞書:
            - success: チェックが成功したかどうか
            - has_staged: ステージされた変更があるかどうか
        """
        try:
            result = self._run_git_command(["diff", "--cached", "--quiet"], timeout=10)
            # returncode 0 = no diff (staging area is clean)
            # returncode 1 = has diff (there are staged changes)
            return {
                "success": True,
                "has_staged": result.returncode != 0,
            }
        except Exception as e:
            return {
                "success": False,
                "has_staged": False,
                "error": str(e),
            }

    def _add_machine_files(self, machine_name: str) -> Dict[str, Any]:
        """マシンファイルをgit addする"""
        try:
            result = self._run_git_command(["add", f"{machine_name}/"])

            output = f"=== git add {machine_name}/ ==="
            if result.stdout:
                output += f"\n{result.stdout.strip()}"

            if result.returncode != 0:
                error_msg = (
                    f"git add stderr: {result.stderr.strip()}"
                    if result.stderr
                    else "git add failed"
                )
                return {
                    "success": False,
                    "message": f"git add failed for {machine_name}",
                    "output": output,
                    "error": error_msg,
                    "returncode": result.returncode,
                }

            return {
                "success": True,
                "output": output,
                "error": result.stderr.strip() if result.stderr else "",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"git add failed: {str(e)}",
                "output": "",
                "error": str(e),
            }

    def _commit_changes(self, commit_message: str) -> Dict[str, Any]:
        """変更をcommitする"""
        try:
            result = self._run_git_command(["commit", "-m", commit_message])

            output = f'=== git commit -m "{commit_message}" ==='
            if result.stdout:
                output += f"\n{result.stdout.strip()}"

            if result.returncode != 0:
                error_msg = (
                    f"git commit stderr: {result.stderr.strip()}"
                    if result.stderr
                    else "git commit failed"
                )
                return {
                    "success": False,
                    "message": "git commit failed",
                    "output": output,
                    "error": error_msg
                    + '\n\nYou may want to run "git reset HEAD" to unstage the changes.',
                    "returncode": result.returncode,
                }

            return {
                "success": True,
                "output": output,
                "error": result.stderr.strip() if result.stderr else "",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"git commit failed: {str(e)}",
                "output": "",
                "error": str(e),
            }

    def _push_changes(self) -> Dict[str, Any]:
        """変更をpushする"""
        try:
            result = self._run_git_command(
                ["push"], timeout=60
            )  # pushは時間がかかる可能性があるので長めに

            output = "=== git push ==="
            if result.stdout:
                output += f"\n{result.stdout.strip()}"

            if result.returncode != 0:
                error_msg = (
                    f"git push stderr: {result.stderr.strip()}"
                    if result.stderr
                    else "git push failed"
                )
                return {
                    "success": False,
                    "message": "git push failed",
                    "output": output,
                    "error": error_msg
                    + "\n\nCommit was successful but push failed. Your changes are committed locally.",
                    "returncode": result.returncode,
                }

            return {
                "success": True,
                "output": output,
                "error": result.stderr.strip() if result.stderr else "",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"git push failed: {str(e)}",
                "output": "",
                "error": str(e),
            }
