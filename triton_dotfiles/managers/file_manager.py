#!/usr/bin/env python3
"""
Dotfiles管理 - ファイル操作モジュール
"""

import shutil
import difflib
import hashlib
import fnmatch
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Generator, Any
from datetime import datetime
from dataclasses import dataclass, field
from colorama import Fore, Style, init

# システム保護パス設定
# 注意: 実際の保護は is_system_protected_path() メソッドで TRITON_DIR を使用して動的に行われます
# 以下のパスは ${TRITON_DIR} 内で保護される相対パス:
# - master.key        # 暗号化キー（セキュリティクリティカル）
# - archives/         # アーカイブフォルダ（無限再帰防止）
# - archives/**       # アーカイブフォルダ内容
#
# 注意: config.yml は意図的に保護対象外（ユーザーがバックアップしたい場合があるため）

# 暗号化モジュール、Gitマネージャー、ファイル比較マネージャーのインポート
from ..utils import (
    import_class_from_module,
    get_triton_dir,
    matches_glob_pattern,
)
from .file_comparison_manager import FileComparisonManager, ComparisonMethod

get_encryption_manager = import_class_from_module(
    "encryption", "get_encryption_manager"
)
GitManager = import_class_from_module("managers.git_manager", "GitManager")

# coloramaの初期化
init(autoreset=True)


@dataclass
class FileInfo:
    """ファイル情報"""

    path: Path
    relative_path: str
    exists: bool
    size: Optional[int] = None
    mtime: Optional[float] = None

    def __post_init__(self):
        if self.exists:
            stat = self.path.stat()
            self.size = stat.st_size
            self.mtime = stat.st_mtime


@dataclass
class PatternMatchResult:
    """パターンマッチング結果（dry-run出力用）"""

    total_scanned: int = 0
    blacklist_blocked: List[Tuple[str, str]] = field(
        default_factory=list
    )  # (file_path, matched_pattern)
    pattern_matched: List[Tuple[str, str]] = field(
        default_factory=list
    )  # (file_path, matched_pattern)
    pattern_excluded: List[Tuple[str, str]] = field(
        default_factory=list
    )  # (file_path, matched_pattern)
    would_backup: int = 0


def separate_patterns(patterns: List[str]) -> Tuple[List[str], List[str]]:
    """
    パターンリストをinclusionとexclusionに分離

    Args:
        patterns: パターンリスト（!プレフィックスで除外）

    Returns:
        (inclusion_patterns, exclusion_patterns)のタプル
    """
    include_patterns = []
    exclude_patterns = []

    for pattern in patterns:
        if pattern.startswith("!"):
            # !を除去してexclusionリストに追加
            exclude_patterns.append(pattern[1:])
        else:
            include_patterns.append(pattern)

    return include_patterns, exclude_patterns


def evaluate_patterns_sequential(
    path: Path, patterns: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    パターンを順番に評価し、最後にマッチしたパターンの種類で判定（re-inclusion対応）

    gitignore風の挙動: パターンは順番に評価され、最後にマッチしたパターンが勝つ

    Example:
        patterns = ["**/*.xml", "!**/confs/*.xml", "**/confs/my-settings.xml"]
        - **/*.xml にマッチ → included = True
        - !**/confs/*.xml にマッチ → included = False
        - **/confs/my-settings.xml にマッチ → included = True (re-inclusion)

    Args:
        path: チェック対象のパス（相対パス）
        patterns: パターンリスト（!プレフィックスで除外）

    Returns:
        (included, matched_pattern): 含めるべきかと、最後にマッチしたパターン
    """
    included = False
    matched_pattern = None

    for pattern in patterns:
        if pattern.startswith("!"):
            # 除外パターン
            excl_pattern = pattern[1:]
            if matches_glob_pattern(path, excl_pattern):
                included = False
                matched_pattern = pattern
        else:
            # 包含パターン
            if matches_glob_pattern(path, pattern):
                included = True
                matched_pattern = pattern

    return included, matched_pattern


@dataclass
class FileDiff:
    """ファイル差分情報"""

    path: str
    status: str  # 'added', 'modified', 'deleted', 'unchanged'
    source_file: Optional[FileInfo] = None
    target_file: Optional[FileInfo] = None
    diff_lines: Optional[List[str]] = None


class FileManager:
    """ファイル操作を管理するクラス"""

    def __init__(self, config_manager):
        self.config_manager = config_manager

        # Tritonディレクトリを統一的に取得
        self.triton_dir = get_triton_dir()

        # リポジトリルートを決定
        if config_manager.config.repository.path:
            # config.ymlでrepository.pathが指定されている場合
            self.repo_root = Path(
                config_manager.expand_path(config_manager.config.repository.path)
            )
        else:
            # 未指定の場合はconfig.ymlと同じディレクトリ
            self.repo_root = Path(config_manager.config_path).parent
        self.encryption_manager = None
        self.git_manager = GitManager(self.repo_root)

        # 暗号化が有効な場合、EncryptionManagerを初期化
        if config_manager.config.encryption.enabled:
            key_file = None
            if config_manager.config.encryption.key_file:
                key_file = config_manager.expand_path(
                    config_manager.config.encryption.key_file
                )
            self.encryption_manager = get_encryption_manager(key_file)

        # 統一ファイル比較マネージャーを初期化
        self.file_comparison_manager = FileComparisonManager(self.encryption_manager)

    def is_system_protected_path(self, file_path: Path) -> bool:
        """システム保護パスかどうかをチェック（TRITON_DIR対応）"""
        # ファイルパスを絶対パスに正規化
        file_abs = Path(file_path).expanduser().resolve()

        # Tritonディレクトリ内かチェック
        try:
            if file_abs.is_relative_to(self.triton_dir):
                # Tritonディレクトリからの相対パスを取得
                relative_to_triton = file_abs.relative_to(self.triton_dir)
                relative_str = str(relative_to_triton)

                # master.keyファイルの保護（暗号化キー）
                if relative_str == "master.key":
                    return True

                # archives/フォルダとその中身の保護（無限再帰防止）
                if relative_str == "archives" or relative_str.startswith("archives/"):
                    return True

                # config.ymlは保護しない（バックアップ可能）
                # ユーザーが設定をバックアップしたい場合があるため

            return False

        except ValueError:
            # is_relative_to や relative_to でエラーが発生した場合
            return False

    def get_backup_dir(self, machine_name: str) -> Path:
        """バックアップディレクトリのパスを取得"""
        return self.repo_root / machine_name

    def is_machine_directory(self, directory: Path) -> bool:
        """ディレクトリがマシンディレクトリかどうかを判定"""
        # ドットで始まる = システムディレクトリ
        if directory.name.startswith("."):
            return False

        # ディレクトリでない場合は除外
        if not directory.is_dir():
            return False

        # 設定ファイルの除外リストをチェック
        excluded_dirs = self.config_manager.get_excluded_directories()
        if directory.name in excluded_dirs:
            return False

        # ファイルが存在する = マシンディレクトリ（空のディレクトリは除外）
        return any(f.is_file() for f in directory.rglob("*"))

    def get_available_machines(self) -> List[Dict[str, Any]]:
        """利用可能なマシン一覧を取得"""
        machines = []

        if not self.repo_root.exists():
            return machines

        for item in self.repo_root.iterdir():
            if self.is_machine_directory(item):
                # ファイル数をカウント
                file_count = sum(1 for f in item.rglob("*") if f.is_file())
                machines.append({"name": item.name, "file_count": file_count})

        return machines

    def create_restore_archive(self, timestamp: str = None) -> Path:
        """復元時の既存ファイルアーカイブディレクトリを作成（TRITON_DIR対応）"""
        if not timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        archive_root = self.triton_dir / "archives" / timestamp
        archive_root.mkdir(parents=True, exist_ok=True)

        return archive_root

    def _ensure_restore_archive_root(
        self, restore_archive_root: Optional[Path]
    ) -> Path:
        """必要に応じてアーカイブルートを作成"""
        if restore_archive_root is None:
            restore_archive_root = self.create_restore_archive()
        return restore_archive_root

    def _is_file_unchanged_for_restore(
        self, backup_file: Path, actual_dest_file: Path, relative_path: Path
    ) -> bool:
        """復元時のファイル比較：bit-perfect比較でファイルが同一かチェック

        Args:
            backup_file: バックアップファイルのパス
            actual_dest_file: 実際の復元先ファイルのパス
            relative_path: 表示用の相対パス

        Returns:
            bool: ファイルが同一の場合True、異なる場合False
        """
        try:
            if backup_file.suffix == ".enc":
                # 暗号化ファイルの場合は復号化して比較
                if self.encryption_manager and actual_dest_file.exists():
                    try:
                        with open(backup_file, "rb") as src:
                            encrypted_data = src.read()
                        decrypted_data = self.encryption_manager.decrypt_data(
                            encrypted_data
                        )

                        with open(actual_dest_file, "rb") as local_file:
                            local_data = local_file.read()

                        if decrypted_data == local_data:
                            print(f"Unchanged (skipped): {relative_path}")
                            return True
                    except Exception:
                        # 復号化や比較に失敗した場合は復元処理を続行
                        return False
            else:
                # 通常ファイルのハッシュ比較
                comparison_result = self.file_comparison_manager.are_files_identical(
                    backup_file, actual_dest_file, ComparisonMethod.HASH
                )
                if comparison_result.identical:
                    print(f"Unchanged (skipped): {relative_path}")
                    return True

            return False
        except Exception:
            return False

    def archive_existing_file(
        self, file_path: Path, archive_root: Path
    ) -> Optional[Path]:
        """既存ファイルを集中アーカイブディレクトリに保存"""
        if not file_path.exists():
            return None

        # ホームディレクトリからの相対パスを取得
        home = Path.home()
        try:
            if file_path.is_relative_to(home):
                relative_path = file_path.relative_to(home)
            else:
                # ホーム外のファイルの場合は絶対パスを使用（安全な形に変換）
                relative_path = str(file_path).lstrip("/").replace("/", "_")
        except Exception:
            # fallback: ファイル名のみ使用
            relative_path = file_path.name

        archive_file = archive_root / relative_path
        archive_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(file_path, archive_file)
            return archive_file
        except Exception as e:
            print(f"  Warning: Failed to archive {file_path}: {e}")
            return None

    def collect_target_files(
        self, target, match_result: Optional[PatternMatchResult] = None
    ) -> Generator[Tuple[Path, str], None, None]:
        """
        対象ファイルを収集（negation pattern + re-inclusion対応）

        パターンは順番に評価され、最後にマッチしたパターンの種類で判定。
        これによりre-inclusion（一度除外したものを再度含める）が可能。

        Args:
            target: バックアップ対象の設定
            match_result: パターンマッチング結果を記録（dry-run出力用、省略可）

        Yields:
            (file_path, relative_path)のタプル
        """
        expanded_path = self.config_manager.expand_path(target.path)

        if not expanded_path.exists():
            print(f"Warning: Skipping non-existent path: {expanded_path}")
            return

        patterns = target.files or []
        has_patterns = bool(patterns)

        if target.recursive:
            # 再帰的にファイルを収集
            for file_path in expanded_path.rglob("*"):
                if not file_path.is_file():
                    continue

                if match_result:
                    match_result.total_scanned += 1

                relative_path = file_path.relative_to(expanded_path)

                # Priority 1: Global blacklist (absolute rule - cannot override)
                blacklist_match = self._check_blacklist_match(file_path)
                if blacklist_match:
                    if match_result:
                        match_result.blacklist_blocked.append(
                            (str(relative_path), blacklist_match)
                        )
                    continue

                # Priority 2 & 3: Sequential pattern evaluation (re-inclusion対応)
                if has_patterns:
                    included, matched_pattern = evaluate_patterns_sequential(
                        relative_path, patterns
                    )

                    if not included:
                        if matched_pattern and match_result:
                            # 除外パターンにマッチした場合のみ記録
                            match_result.pattern_excluded.append(
                                (str(relative_path), matched_pattern)
                            )
                        continue

                    # File passed all filters
                    if match_result:
                        match_result.pattern_matched.append(
                            (str(relative_path), matched_pattern or "**/*")
                        )
                        match_result.would_backup += 1
                else:
                    # パターンが空の場合は全ファイルを収集
                    if match_result:
                        match_result.pattern_matched.append(
                            (str(relative_path), "**/*")
                        )
                        match_result.would_backup += 1

                yield file_path, str(relative_path)
        else:
            # 非再帰モード: 指定されたディレクトリ直下のファイルのみ
            # 直下のファイルを取得して順序評価を適用
            for file_path in expanded_path.iterdir():
                if not file_path.is_file():
                    continue

                if match_result:
                    match_result.total_scanned += 1

                relative_path = file_path.relative_to(expanded_path)

                # Global blacklist check
                blacklist_match = self._check_blacklist_match(file_path)
                if blacklist_match:
                    if match_result:
                        match_result.blacklist_blocked.append(
                            (str(relative_path), blacklist_match)
                        )
                    continue

                # Sequential pattern evaluation (re-inclusion対応)
                if has_patterns:
                    included, matched_pattern = evaluate_patterns_sequential(
                        relative_path, patterns
                    )

                    if not included:
                        if matched_pattern and match_result:
                            match_result.pattern_excluded.append(
                                (str(relative_path), matched_pattern)
                            )
                        continue

                    if match_result:
                        match_result.pattern_matched.append(
                            (str(relative_path), matched_pattern or "*")
                        )
                        match_result.would_backup += 1

                    yield file_path, str(relative_path)

    def _check_blacklist_match(self, file_path: Path) -> Optional[str]:
        """
        ファイルがblacklistにマッチするかチェック

        Args:
            file_path: チェック対象のファイルパス

        Returns:
            マッチしたパターン、マッチしない場合はNone
        """
        if self.config_manager.should_exclude(file_path):
            # マッチしたパターンを特定
            file_name = file_path.name
            for pattern in self.config_manager.config.blacklist:
                if "*" in pattern or "?" in pattern:
                    if fnmatch.fnmatch(file_name, pattern):
                        return pattern
                else:
                    if pattern == file_name:
                        return pattern
            return "blacklist"
        return None

    def backup_files(
        self, machine_name: str, dry_run: bool = False
    ) -> Dict[str, List[str]]:
        """ファイルをバックアップ"""
        backup_dir = self.get_backup_dir(machine_name)
        results = {"copied": [], "skipped": [], "unchanged": [], "errors": []}

        print(
            f"Starting backup for machine: {Fore.CYAN}{machine_name}{Style.RESET_ALL}"
        )
        if dry_run:
            print(
                f"{Fore.YELLOW}DRY RUN MODE - No files will be copied{Style.RESET_ALL}"
            )

        if not dry_run:
            backup_dir.mkdir(exist_ok=True)

        for target in self.config_manager.config.targets:
            expanded_path = self.config_manager.expand_path(target.path)

            # パターン情報の表示
            include_patterns, exclude_patterns = separate_patterns(target.files or [])
            print(f"\nProcessing: {Fore.GREEN}{expanded_path}{Style.RESET_ALL}")
            if dry_run and (include_patterns or exclude_patterns):
                print(
                    f"   Patterns: {len(include_patterns)} inclusion, {len(exclude_patterns)} exclusion"
                )

            # バックアップ先のベースディレクトリを決定
            if str(expanded_path) == str(Path.home()):
                base_backup_dir = backup_dir
            else:
                # ~/.ssh → .ssh のように変換
                home_str = str(Path.home())
                if str(expanded_path).startswith(home_str):
                    relative_path = str(expanded_path)[len(home_str) :].lstrip("/")
                else:
                    relative_path = expanded_path.name
                base_backup_dir = backup_dir / relative_path

            # dry-run時はパターンマッチング結果を収集
            match_result = PatternMatchResult() if dry_run else None

            # ファイルをコピー
            for source_file, relative_path in self.collect_target_files(
                target, match_result
            ):
                dest_file = base_backup_dir / relative_path

                # システム保護ファイルチェック
                if self.is_system_protected_path(source_file):
                    print(f"  System protected (skipped): {relative_path}")
                    results["skipped"].append(f"System protected: {relative_path}")
                    continue

                # ファイルが暗号化対象かどうかを判定（target.encrypt_filesを優先）
                will_encrypt = self.config_manager.should_encrypt_file(
                    source_file, target, Path(relative_path)
                )
                if will_encrypt:
                    dest_file = dest_file.with_suffix(dest_file.suffix + ".enc")

                # 既存ファイルとの比較
                comparison_result = self.file_comparison_manager.are_files_identical(
                    source_file,
                    dest_file,
                    ComparisonMethod.COMPREHENSIVE,
                    self.config_manager,
                )
                files_identical = comparison_result.identical

                if files_identical:
                    print(f"Unchanged (skipped): {relative_path}")
                    results["unchanged"].append(str(relative_path))
                    continue

                try:
                    if not dry_run:
                        dest_file.parent.mkdir(parents=True, exist_ok=True)

                        # 暗号化チェック
                        if will_encrypt:
                            if self.encryption_manager:
                                # 暗号化してコピー
                                with open(source_file, "rb") as src:
                                    data = src.read()
                                encrypted_data = self.encryption_manager.encrypt_data(
                                    data
                                )
                                with open(dest_file, "wb") as dst:
                                    dst.write(encrypted_data)
                                print(f"  Encrypted: {relative_path}")
                            else:
                                error_msg = f"Encryption enabled but no key available for {source_file}"
                                print(f"  Error:{error_msg}")
                                results["errors"].append(error_msg)
                                continue
                        else:
                            # 通常のコピー
                            shutil.copy2(source_file, dest_file)
                            print(f"Copied: {relative_path}")
                    else:
                        # dry-run時の表示
                        if will_encrypt:
                            print(f"  Would encrypt: {relative_path}")
                        else:
                            print(f"Would copy: {relative_path}")

                    results["copied"].append(str(relative_path))

                except Exception as e:
                    error_msg = f"Error processing {source_file}: {e}"
                    print(f"  Error:{error_msg}")
                    results["errors"].append(error_msg)

            # dry-run時にパターンマッチング結果のサマリーを表示
            if dry_run and match_result:
                self._print_pattern_match_summary(match_result)

        return results

    def _print_pattern_match_summary(self, match_result: PatternMatchResult) -> None:
        """パターンマッチング結果のサマリーを表示（dry-run用）"""
        # Blacklist blocked
        if match_result.blacklist_blocked:
            print(f"\n   {Fore.RED}Blacklist blocked:{Style.RESET_ALL}")
            for file_path, pattern in match_result.blacklist_blocked[:5]:
                print(f"      • {file_path} (matched: {pattern})")
            if len(match_result.blacklist_blocked) > 5:
                print(f"      ... and {len(match_result.blacklist_blocked) - 5} more")

        # Pattern excluded
        if match_result.pattern_excluded:
            print(f"\n   Error:{Fore.YELLOW}Excluded by pattern:{Style.RESET_ALL}")
            for file_path, pattern in match_result.pattern_excluded[:5]:
                print(f"      • {file_path} (matched: {pattern})")
            if len(match_result.pattern_excluded) > 5:
                print(f"      ... and {len(match_result.pattern_excluded) - 5} more")

        # Summary statistics
        print(f"\n   {Fore.CYAN}Summary:{Style.RESET_ALL}")
        print(f"      • Total files scanned: {match_result.total_scanned}")
        print(f"      • Blacklist blocked: {len(match_result.blacklist_blocked)}")
        print(f"      • Pattern matched: {len(match_result.pattern_matched)}")
        print(f"      • Pattern excluded: {len(match_result.pattern_excluded)}")
        print(f"      • Would backup: {match_result.would_backup}")

    def restore_files(
        self,
        machine_name: str,
        target_machine: Optional[str] = None,
        dry_run: bool = False,
        file_patterns: Optional[List[str]] = None,
    ) -> Dict[str, List[str]]:
        """ファイルを復元

        Args:
            machine_name: 復元元のマシン名
            target_machine: 復元先のマシン名（省略時は現在のマシン）
            dry_run: ドライランモード
            file_patterns: 特定ファイルのみ復元する場合のパターンリスト
                          Noneの場合は全ファイルを復元
        """
        backup_dir = self.get_backup_dir(machine_name)
        current_machine = target_machine or self.config_manager.get_machine_name()

        results = {"restored": [], "backed_up": [], "unchanged": [], "errors": []}

        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

        # 復元モードの判定と表示
        if file_patterns:
            print(
                f"Selectively restoring from {Fore.CYAN}{machine_name}{Style.RESET_ALL} → {Fore.CYAN}{current_machine}{Style.RESET_ALL}"
            )
        else:
            print(
                f"Restoring {Fore.CYAN}{machine_name}{Style.RESET_ALL} → {Fore.CYAN}{current_machine}{Style.RESET_ALL}"
            )

        if dry_run:
            print(
                f"{Fore.YELLOW}DRY RUN MODE - No files will be restored{Style.RESET_ALL}"
            )

        # アーカイブルートは必要になった時に作成（遅延作成）
        restore_archive_root = None

        if file_patterns:
            # 特定ファイル復元モード
            restore_archive_root = self._restore_specific_files_impl(
                backup_dir, file_patterns, restore_archive_root, dry_run, results
            )
        else:
            # 全ファイル復元モード
            restore_archive_root = self._restore_all_files_impl(
                backup_dir, restore_archive_root, dry_run, results
            )

        # アーカイブが実際に作成された場合のみメッセージ表示
        if restore_archive_root and not dry_run:
            print(
                f"Existing files were archived to: {Fore.YELLOW}{restore_archive_root}{Style.RESET_ALL}"
            )

        return results

    def _restore_all_files_impl(
        self,
        backup_dir: Path,
        restore_archive_root: Optional[Path],
        dry_run: bool,
        results: Dict[str, List[str]],
    ) -> Optional[Path]:
        """全ファイル復元の実装"""
        for target in self.config_manager.config.targets:
            expanded_path = self.config_manager.expand_path(target.path)

            # バックアップ元のベースディレクトリを決定
            if str(expanded_path) == str(Path.home()):
                base_backup_dir = backup_dir
            else:
                home_str = str(Path.home())
                if str(expanded_path).startswith(home_str):
                    relative_path = str(expanded_path)[len(home_str) :].lstrip("/")
                else:
                    relative_path = expanded_path.name
                base_backup_dir = backup_dir / relative_path

            if not base_backup_dir.exists():
                continue

            print(f"\nRestoring to: {Fore.GREEN}{expanded_path}{Style.RESET_ALL}")

            # ファイルを復元
            for backup_file in base_backup_dir.rglob("*"):
                if not backup_file.is_file():
                    continue

                relative_path = backup_file.relative_to(base_backup_dir)
                dest_file = expanded_path / relative_path

                # 暗号化ファイルの場合は .enc を除いた実際の復元先パスを取得
                actual_dest_file = (
                    dest_file.with_suffix("")
                    if backup_file.suffix == ".enc"
                    else dest_file
                )

                # bit-perfect比較でファイルが同一かチェック
                if self._is_file_unchanged_for_restore(
                    backup_file, actual_dest_file, relative_path
                ):
                    results["unchanged"].append(str(relative_path))
                    continue

                try:
                    if not dry_run:
                        # 既存ファイルのアーカイブ（必要な時にアーカイブルート作成）
                        if dest_file.exists():
                            restore_archive_root = self._ensure_restore_archive_root(
                                restore_archive_root
                            )
                            archived_file = self.archive_existing_file(
                                dest_file, restore_archive_root
                            )
                            if archived_file:
                                print(f"Archived existing: {dest_file.name}")
                                results["backed_up"].append(str(archived_file))

                        # ディレクトリ作成
                        dest_file.parent.mkdir(parents=True, exist_ok=True)

                        # 暗号化ファイルの復号化チェック
                        if backup_file.suffix == ".enc":
                            if self.encryption_manager:
                                # 復号化して復元
                                try:
                                    with open(backup_file, "rb") as src:
                                        encrypted_data = src.read()
                                    decrypted_data = (
                                        self.encryption_manager.decrypt_data(
                                            encrypted_data
                                        )
                                    )

                                    # .encを除いた元のファイル名で保存
                                    actual_dest = dest_file.with_suffix("")
                                    with open(actual_dest, "wb") as dst:
                                        dst.write(decrypted_data)
                                    print(
                                        f"  {'Would decrypt' if dry_run else 'Decrypted'}: {relative_path}"
                                    )
                                except Exception as e:
                                    error_msg = f"Error decrypting {backup_file}: {e}"
                                    print(f"  Error:{error_msg}")
                                    results["errors"].append(error_msg)
                                    continue
                            else:
                                error_msg = f"Encrypted file found but no decryption key for {backup_file}"
                                print(f"  Error:{error_msg}")
                                results["errors"].append(error_msg)
                                continue
                        else:
                            # 通常のコピー
                            shutil.copy2(backup_file, dest_file)
                            print(
                                f"{'Would restore' if dry_run else 'Restored'}: {relative_path}"
                            )
                    else:
                        # dry-run時の表示
                        if backup_file.suffix == ".enc":
                            print(f"  Would decrypt: {relative_path}")
                        else:
                            print(f"Would restore: {relative_path}")

                    results["restored"].append(str(relative_path))

                except Exception as e:
                    error_msg = f"Error restoring {backup_file}: {e}"
                    print(f"  Error:{error_msg}")
                    results["errors"].append(error_msg)

        return restore_archive_root

    def _restore_specific_files_impl(
        self,
        backup_dir: Path,
        file_patterns: List[str],
        restore_archive_root: Optional[Path],
        dry_run: bool,
        results: Dict[str, List[str]],
    ) -> Optional[Path]:
        """特定ファイル復元の実装"""
        # ファイルパターンにマッチするバックアップファイルを検索
        matching_files = []
        for pattern in file_patterns:
            # パターンを正規化（先頭の./や/を除去）
            clean_pattern = pattern.lstrip("./")

            # バックアップディレクトリ内でマッチするファイルを検索
            for backup_file in backup_dir.rglob("*"):
                if not backup_file.is_file():
                    continue

                relative_path = backup_file.relative_to(backup_dir)
                file_path_str = str(relative_path)

                # パターンマッチング（完全一致、部分一致、ワイルドカード）
                if (
                    file_path_str == clean_pattern
                    or file_path_str.endswith(clean_pattern)
                    or clean_pattern in file_path_str
                ):
                    matching_files.append((backup_file, relative_path))
                elif "*" in clean_pattern:
                    if fnmatch.fnmatch(file_path_str, clean_pattern):
                        matching_files.append((backup_file, relative_path))

        if not matching_files:
            print(
                f"{Fore.YELLOW}Warning: No files found matching patterns: {', '.join(file_patterns)}{Style.RESET_ALL}"
            )
            return

        print(f"Found {len(matching_files)} matching files:")
        for _, rel_path in matching_files:
            print(f"  • {rel_path}")

        # マッチしたファイルを復元
        for backup_file, relative_path in matching_files:
            try:
                # 復元先のパスを決定
                home_path = Path.home()

                # 相対パスから実際の復元先パスを構築
                if str(relative_path).startswith("."):
                    # ドットファイル（ホームディレクトリ直下）
                    dest_file = home_path / relative_path
                else:
                    # 設定ディレクトリ内のファイル
                    dest_file = home_path / relative_path

                # 暗号化ファイルの場合は .enc を除いた実際の復元先パスを取得
                actual_dest_file = (
                    dest_file.with_suffix("")
                    if backup_file.suffix == ".enc"
                    else dest_file
                )

                # bit-perfect比較でファイルが同一かチェック
                if self._is_file_unchanged_for_restore(
                    backup_file, actual_dest_file, relative_path
                ):
                    results["unchanged"].append(str(relative_path))
                    continue

                if not dry_run:
                    # 既存ファイルのアーカイブ（必要な時にアーカイブルート作成）
                    if dest_file.exists():
                        restore_archive_root = self._ensure_restore_archive_root(
                            restore_archive_root
                        )
                        archived_file = self.archive_existing_file(
                            dest_file, restore_archive_root
                        )
                        if archived_file:
                            print(f"Archived existing: {dest_file.name}")
                            results["backed_up"].append(str(archived_file))

                    # ディレクトリ作成
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    # 暗号化ファイルの復号化チェック
                    if backup_file.suffix == ".enc":
                        if self.encryption_manager:
                            try:
                                with open(backup_file, "rb") as src:
                                    encrypted_data = src.read()
                                decrypted_data = self.encryption_manager.decrypt_data(
                                    encrypted_data
                                )

                                # .encを除いた元のファイル名で保存
                                with open(actual_dest_file, "wb") as dst:
                                    dst.write(decrypted_data)
                                print(f"  Decrypted and restored: {relative_path}")
                            except Exception as e:
                                error_msg = f"Error decrypting {backup_file}: {e}"
                                print(f"  Error:{error_msg}")
                                results["errors"].append(error_msg)
                                continue
                        else:
                            error_msg = f"Encrypted file found but no decryption key for {backup_file}"
                            print(f"  Error:{error_msg}")
                            results["errors"].append(error_msg)
                            continue
                    else:
                        # 通常のコピー
                        shutil.copy2(backup_file, dest_file)
                        print(f"Restored: {relative_path}")
                else:
                    # dry-run時の表示
                    if backup_file.suffix == ".enc":
                        print(f"  Would decrypt and restore: {relative_path}")
                    else:
                        print(f"Would restore: {relative_path}")

                results["restored"].append(str(relative_path))

            except Exception as e:
                error_msg = f"Error restoring {backup_file}: {e}"
                print(f"  Error:{error_msg}")
                results["errors"].append(error_msg)

        return restore_archive_root

    def restore_specific_files(
        self,
        machine_name: str,
        file_patterns: List[str],
        target_machine: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, List[str]]:
        """特定のファイルのみを復元（後方互換性のため維持）

        Note: このメソッドは後方互換性のために残されています。
        新しいコードでは restore_files(file_patterns=patterns) を使用してください。
        """
        # 新しい統一されたrestore_filesメソッドを呼び出し
        return self.restore_files(
            machine_name=machine_name,
            target_machine=target_machine,
            dry_run=dry_run,
            file_patterns=file_patterns,
        )

    def export_file(
        self,
        machine_name: str,
        file_pattern: str,
        output_path: str,
        decrypt: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, str]:
        """ファイルをエクスポート（復号化してデスクトップなど任意の場所に保存）"""
        backup_dir = self.get_backup_dir(machine_name)

        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

        # パターンにマッチするファイルを検索
        clean_pattern = file_pattern.lstrip("./")
        matching_file = None

        for backup_file in backup_dir.rglob("*"):
            if not backup_file.is_file():
                continue

            relative_path = backup_file.relative_to(backup_dir)
            file_path_str = str(relative_path)

            if (
                file_path_str == clean_pattern
                or file_path_str.endswith(clean_pattern)
                or clean_pattern in file_path_str
            ):
                matching_file = backup_file
                break
            elif "*" in clean_pattern:
                if fnmatch.fnmatch(file_path_str, clean_pattern):
                    matching_file = backup_file
                    break

        if not matching_file:
            raise FileNotFoundError(f"No file found matching pattern: {file_pattern}")

        output_file = Path(output_path)
        result = {
            "source": str(matching_file.relative_to(backup_dir)),
            "destination": str(output_file),
            "encrypted": matching_file.suffix == ".enc",
            "decrypted": False,
        }

        print(
            f"Exporting {Fore.CYAN}{result['source']}{Style.RESET_ALL} → {Fore.GREEN}{output_file}{Style.RESET_ALL}"
        )

        if dry_run:
            print(
                f"{Fore.YELLOW}DRY RUN MODE - File will not be exported{Style.RESET_ALL}"
            )
            if result["encrypted"] and decrypt:
                print(f"Would decrypt: {result['source']}")
            return result

        try:
            # 出力ディレクトリを作成
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if result["encrypted"] and decrypt:
                # 暗号化ファイルを復号化してエクスポート
                if self.encryption_manager:
                    with open(matching_file, "rb") as src:
                        encrypted_data = src.read()
                    decrypted_data = self.encryption_manager.decrypt_data(
                        encrypted_data
                    )

                    with open(output_file, "wb") as dst:
                        dst.write(decrypted_data)

                    result["decrypted"] = True
                    print(f"  Decrypted and exported: {output_file}")
                else:
                    raise ValueError(
                        "Encrypted file found but no decryption key available"
                    )
            else:
                # 通常のコピー（暗号化ファイルもそのまま）
                shutil.copy2(matching_file, output_file)
                print(f"Exported: {output_file}")

            return result

        except Exception as e:
            raise RuntimeError(f"Failed to export file: {e}")

    def compare_files(self, machine1: str, machine2: str) -> List[FileDiff]:
        """2つのマシンの設定ファイルを比較"""
        backup_dir1 = self.get_backup_dir(machine1)
        backup_dir2 = self.get_backup_dir(machine2)

        if not backup_dir1.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir1}")
        if not backup_dir2.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir2}")

        # 全ファイルのリストを作成
        files1 = {
            str(f.relative_to(backup_dir1)): f
            for f in backup_dir1.rglob("*")
            if f.is_file()
        }
        files2 = {
            str(f.relative_to(backup_dir2)): f
            for f in backup_dir2.rglob("*")
            if f.is_file()
        }

        all_files = set(files1.keys()) | set(files2.keys())
        diffs = []

        for file_path in sorted(all_files):
            file1 = files1.get(file_path)
            file2 = files2.get(file_path)

            if file1 and file2:
                # 両方に存在 - 内容比較
                comparison_result = self.file_comparison_manager.are_files_identical(
                    file1, file2, ComparisonMethod.BINARY
                )
                if comparison_result.identical:
                    status = "unchanged"
                    diff_lines = None
                else:
                    status = "modified"
                    diff_lines = self._generate_diff(file1, file2, file_path)
            elif file1:
                # machine1のみに存在
                status = "deleted"
                diff_lines = None
            else:
                # machine2のみに存在
                status = "added"
                diff_lines = None

            diffs.append(
                FileDiff(
                    path=file_path,
                    status=status,
                    source_file=FileInfo(file1, file_path, file1 is not None)
                    if file1
                    else None,
                    target_file=FileInfo(file2, file_path, file2 is not None)
                    if file2
                    else None,
                    diff_lines=diff_lines,
                )
            )

        return diffs

    def _files_identical(self, file1: Path, file2: Path) -> bool:
        """2つのファイルが同一かチェック"""
        try:
            with open(file1, "rb") as f1, open(file2, "rb") as f2:
                return f1.read() == f2.read()
        except Exception:
            return False

    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """ファイルのSHA256ハッシュを計算"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception:
            return None

    def analyze_file_status(
        self,
        local_path: Path,
        backup_path: Path,
        local_mtime: float = None,
        backup_mtime: float = None,
    ) -> Dict[str, Any]:
        """ファイルの状態を包括的に分析

        Args:
            local_path: ローカルファイルのパス
            backup_path: バックアップファイルのパス
            local_mtime: ローカルファイルの変更時刻（省略時は自動取得）
            backup_mtime: バックアップファイルの変更時刻（省略時は自動取得）

        Returns:
            Dict containing:
                - exists: ローカルファイルが存在するか
                - changed: ファイルに変更があるか（ハッシュベース）
                - change_type: 'ahead', 'behind', None
                - time_diff: 時刻差分（秒）
                - local_mtime: ローカルファイルの変更時刻
                - backup_mtime: バックアップファイルの変更時刻
        """
        result = {
            "exists": local_path.exists(),
            "changed": False,
            "change_type": None,
            "time_diff": 0,
            "local_mtime": local_mtime,
            "backup_mtime": backup_mtime,
        }

        if not result["exists"]:
            return result

        # mtimeの取得（引数で渡されていない場合）
        if local_mtime is None:
            result["local_mtime"] = local_path.stat().st_mtime
        if backup_mtime is None and backup_path.exists():
            result["backup_mtime"] = backup_path.stat().st_mtime

        # ファイル関係分析を使用
        relationship_analysis = self.file_comparison_manager.analyze_file_relationship(
            local_path,
            backup_path,
            result["local_mtime"],
            result["backup_mtime"],
            self.config_manager,
        )
        result["changed"] = relationship_analysis.changed

        # relationship_analysisから追加情報を取得
        result["change_type"] = relationship_analysis.change_type
        result["time_diff"] = relationship_analysis.time_diff

        return result

    def _are_files_identical_by_hash(self, source_file: Path, dest_file: Path) -> bool:
        """ハッシュベースでファイルが同一かチェック（暗号化ファイル対応）"""
        if not dest_file.exists():
            return False

        try:
            # 両方のファイルサイズが0の場合は同一とみなす
            if source_file.stat().st_size == 0 and dest_file.stat().st_size == 0:
                return True

            # 通常ファイル同士の比較
            if not dest_file.name.endswith(".enc"):
                source_hash = self._calculate_file_hash(source_file)
                dest_hash = self._calculate_file_hash(dest_file)
                return source_hash is not None and source_hash == dest_hash

            # 暗号化ファイルの場合は元ファイルと暗号化後のファイルを比較
            # 暗号化されたファイルのハッシュは毎回変わるため、復号化して比較
            if self.encryption_manager and self.config_manager.should_encrypt(
                source_file
            ):
                try:
                    # 既存の暗号化ファイルを復号化
                    with open(dest_file, "rb") as f:
                        encrypted_data = f.read()
                    decrypted_data = self.encryption_manager.decrypt_data(
                        encrypted_data
                    )

                    # 元ファイルと復号化したデータを比較
                    with open(source_file, "rb") as f:
                        source_data = f.read()

                    return source_data == decrypted_data
                except Exception:
                    # 復号化に失敗した場合は異なるファイルとみなす
                    return False

            return False

        except Exception:
            return False

    def _generate_diff(self, file1: Path, file2: Path, filename: str) -> List[str]:
        """ファイルの差分を生成"""
        try:
            with open(file1, "r", encoding="utf-8") as f1:
                lines1 = f1.readlines()
            with open(file2, "r", encoding="utf-8") as f2:
                lines2 = f2.readlines()

            diff = difflib.unified_diff(
                lines1,
                lines2,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
                lineterm="",
            )

            return list(diff)
        except Exception as e:
            return [f"Error generating diff: {e}"]

    def print_diff_summary(self, diffs: List[FileDiff], machine1: str, machine2: str):
        """差分のサマリーを表示"""
        print(
            f"\n{Fore.CYAN}{machine1}{Style.RESET_ALL} -> "
            f"{Fore.CYAN}{machine2}{Style.RESET_ALL}"
        )

        added = [d for d in diffs if d.status == "added"]
        modified = [d for d in diffs if d.status == "modified"]
        deleted = [d for d in diffs if d.status == "deleted"]
        unchanged = [d for d in diffs if d.status == "unchanged"]

        print(
            f"  {len(unchanged)} unchanged, "
            f"{Fore.YELLOW}{len(modified)} modified{Style.RESET_ALL}, "
            f"{Fore.GREEN}+{len(added)}{Style.RESET_ALL}, "
            f"{Fore.RED}-{len(deleted)}{Style.RESET_ALL}"
        )

        # 詳細表示
        for diff in diffs:
            if diff.status == "unchanged":
                continue

            if diff.status == "added":
                print(f"\n{Fore.GREEN}+ {diff.path}{Style.RESET_ALL}")
            elif diff.status == "deleted":
                print(f"\n{Fore.RED}- {diff.path}{Style.RESET_ALL}")
            elif diff.status == "modified":
                print(f"\n{Fore.YELLOW}M {diff.path}{Style.RESET_ALL}")
                if diff.diff_lines:
                    for line in diff.diff_lines[:10]:  # 最初の10行のみ表示
                        if line.startswith("+"):
                            print(f"  {Fore.GREEN}{line}{Style.RESET_ALL}")
                        elif line.startswith("-"):
                            print(f"  {Fore.RED}{line}{Style.RESET_ALL}")
                        elif line.startswith("@@"):
                            print(f"  {Fore.CYAN}{line}{Style.RESET_ALL}")

                    if len(diff.diff_lines) > 10:
                        print(f"  ... ({len(diff.diff_lines) - 10} more lines)")

    def git_pull_repository(self, dry_run: bool = False) -> Dict[str, any]:
        """リポジトリでgit pullを実行"""
        return self.git_manager.pull_repository(dry_run=dry_run)

    def git_is_working_directory_clean(self) -> Dict[str, any]:
        """ワーキングディレクトリがクリーンかどうかを確認"""
        return self.git_manager.is_working_directory_clean()

    def git_commit_push_repository(
        self, machine_name: str = None, dry_run: bool = False
    ) -> Dict[str, any]:
        """リポジトリでgit add <machine>, commit, pushを実行"""
        # マシン名が指定されていない場合は設定から取得
        if not machine_name:
            machine_name = self.config_manager.get_machine_name()

        return self.git_manager.commit_and_push_machine(machine_name, dry_run=dry_run)

    def cleanup_repository_files(
        self, machine_name: str, dry_run: bool = False
    ) -> Dict[str, List[str]]:
        """リポジトリから孤立ファイルを削除（ローカルに存在しないファイル）

        Args:
            machine_name: 対象のマシン名
            dry_run: ドライランモード

        Returns:
            Dict: 削除されたファイルの情報

        Raises:
            ValueError: 指定されたマシンが現在のマシンではない場合
        """
        current_machine = self.config_manager.get_machine_name()
        if machine_name != current_machine:
            raise ValueError(
                f"Cleanup is only allowed for current machine. Current: {current_machine}, Requested: {machine_name}"
            )

        backup_dir = self.get_backup_dir(machine_name)
        results = {
            "deleted": [],
            "errors": [],
            "would_delete": [],  # dry-run時に使用
        }

        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

        # 設定が空でないことを確認
        if not self.config_manager.config.targets:
            raise ValueError(
                "No targets configured. Cannot determine local file paths."
            )

        print(
            f"Cleaning up repository for machine: {Fore.CYAN}{machine_name}{Style.RESET_ALL}"
        )
        if dry_run:
            print(
                f"{Fore.YELLOW}DRY RUN MODE - No files will be deleted{Style.RESET_ALL}"
            )

        # リポジトリ内のファイルを確認
        orphaned_files = []

        # パフォーマンス最適化: targetのマッピングを事前に構築
        target_mappings = self._build_target_mappings()

        for repo_file in backup_dir.rglob("*"):
            if not repo_file.is_file():
                continue

            # リポジトリ内の相対パス
            relative_path = repo_file.relative_to(backup_dir)

            # ローカルの対応するパスを構築
            local_file_path = self._construct_local_path_fast(
                relative_path, target_mappings
            )

            # 暗号化ファイルの場合は実際のファイル名を取得（.encを除去）
            actual_local_path = (
                local_file_path.with_suffix("")
                if repo_file.suffix == ".enc" and local_file_path.suffix == ".enc"
                else local_file_path.with_suffix("")
                if repo_file.suffix == ".enc"
                else local_file_path
            )

            # ローカルファイルが存在しない場合は孤立ファイル
            if not actual_local_path.exists():
                orphaned_files.append((repo_file, relative_path, actual_local_path))
                encrypted_info = " [encrypted]" if repo_file.suffix == ".enc" else ""
                print(
                    f"  Orphaned: {relative_path}{encrypted_info} (local: {actual_local_path})"
                )
            else:
                # デバッグ用: 存在するファイルも表示（dry-runでのみ）
                if dry_run:
                    encrypted_info = (
                        " [encrypted]" if repo_file.suffix == ".enc" else ""
                    )
                    print(
                        f"Exists: {relative_path}{encrypted_info} (local: {actual_local_path})"
                    )

        if not orphaned_files:
            print(f"{Fore.GREEN}No orphaned files found in repository{Style.RESET_ALL}")
            print(
                f"Scanned {sum(1 for _ in backup_dir.rglob('*') if _.is_file())} files in total"
            )
            return results

        print(
            f"\n{Fore.YELLOW}Found {len(orphaned_files)} orphaned file(s){Style.RESET_ALL}"
        )

        if dry_run:
            for repo_file, relative_path, local_path in orphaned_files:
                results["would_delete"].append(str(relative_path))
            print(
                f"{Fore.YELLOW}DRY RUN: Would delete {len(orphaned_files)} files{Style.RESET_ALL}"
            )
            return results

        # 実際の削除処理
        for repo_file, relative_path, local_path in orphaned_files:
            try:
                repo_file.unlink()
                print(f"Deleted: {relative_path}")
                results["deleted"].append(str(relative_path))
            except Exception as e:
                error_msg = f"Error deleting {relative_path}: {e}"
                print(f"  Error:{error_msg}")
                results["errors"].append(error_msg)

        # 空のディレクトリも削除
        self._cleanup_empty_directories(backup_dir)

        return results

    def _construct_local_path(self, relative_path: Path, backup_dir: Path) -> Path:
        """リポジトリの相対パスから対応するローカルパスを構築

        バックアップ時のロジックを逆算して、正確なローカルパスを復元する
        """
        home = Path.home()
        path_parts = relative_path.parts

        if not path_parts:
            return home

        # 設定からtargetを探して、バックアップ時のロジックを再現
        for target in self.config_manager.config.targets:
            expanded_path = self.config_manager.expand_path(target.path)

            # バックアップ時のbase_backup_dir決定ロジックを再現
            if str(expanded_path) == str(home):
                # ホームディレクトリ直下の場合
                # backup_dir直下にファイルが保存される
                return home / relative_path
            else:
                # ホーム以外のディレクトリの場合
                home_str = str(home)
                if str(expanded_path).startswith(home_str):
                    # ~/.ssh -> .ssh のような変換が行われる
                    backup_relative_path = str(expanded_path)[len(home_str) :].lstrip(
                        "/"
                    )
                else:
                    # ホーム外のパスの場合はディレクトリ名のみ
                    backup_relative_path = expanded_path.name

                # relative_pathがこのbackup_relative_pathで始まるかチェック
                if str(relative_path).startswith(backup_relative_path):
                    # マッチした場合、元のtarget pathを復元
                    remaining_parts = relative_path.parts[
                        len(Path(backup_relative_path).parts) :
                    ]
                    if remaining_parts:
                        return expanded_path / Path(*remaining_parts)
                    else:
                        return expanded_path

        # どのtargetにもマッチしない場合、ホームディレクトリ直下と仮定
        # （ドットファイルなど）
        return home / relative_path

    def _cleanup_empty_directories(self, base_dir: Path):
        """空のディレクトリを削除"""
        try:
            # 深い階層から順に削除（ボトムアップ）
            for dir_path in sorted(
                base_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True
            ):
                if dir_path.is_dir() and not any(dir_path.iterdir()):
                    try:
                        dir_path.rmdir()
                        print(
                            f"Removed empty directory: {dir_path.relative_to(base_dir)}"
                        )
                    except OSError:
                        # ディレクトリが空でない場合はスキップ
                        pass
        except Exception as e:
            print(f"  Warning: Could not cleanup empty directories: {e}")

    def _build_target_mappings(self) -> Dict[str, Path]:
        """targetのマッピングを事前に構築（パフォーマンス最適化）"""
        mappings = {}
        home = Path.home()
        home_str = str(home)

        for target in self.config_manager.config.targets:
            expanded_path = self.config_manager.expand_path(target.path)

            if str(expanded_path) == str(home):
                # ホームディレクトリ直下の場合は特別なキー
                mappings["HOME_DIRECT"] = home
            else:
                if str(expanded_path).startswith(home_str):
                    # ~/.ssh -> .ssh のような変換
                    backup_relative_path = str(expanded_path)[len(home_str) :].lstrip(
                        "/"
                    )
                else:
                    # ホーム外のパスの場合はディレクトリ名のみ
                    backup_relative_path = expanded_path.name

                mappings[backup_relative_path] = expanded_path

        return mappings

    def _construct_local_path_fast(
        self, relative_path: Path, target_mappings: Dict[str, Path]
    ) -> Path:
        """高速化されたローカルパス構築"""
        home = Path.home()
        path_parts = relative_path.parts

        if not path_parts:
            return home

        first_part = path_parts[0]

        # 事前に構築されたマッピングから検索
        if first_part in target_mappings:
            target_path = target_mappings[first_part]
            remaining_parts = path_parts[1:] if len(path_parts) > 1 else []
            if remaining_parts:
                return target_path / Path(*remaining_parts)
            else:
                return target_path

        # ホームディレクトリ直下（ドットファイルなど）
        if "HOME_DIRECT" in target_mappings:
            return home / relative_path

        # フォールバック: ホームディレクトリ直下
        return home / relative_path
