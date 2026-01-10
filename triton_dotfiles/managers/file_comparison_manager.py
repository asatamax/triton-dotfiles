#!/usr/bin/env python3
"""
Unified file comparison and duplicate detection manager.
"""

import os
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum


class ComparisonMethod(Enum):
    """File comparison methods."""

    BINARY = "binary"  # Binary exact match
    HASH = "hash"  # SHA256 hash comparison
    COMPREHENSIVE = "comprehensive"  # Hash + encryption support


class DuplicateDetectionMethod(Enum):
    """Duplicate detection methods."""

    PATH_ONLY = "path_only"  # Path normalization only
    INODE_ONLY = "inode_only"  # Inode information only
    COMPREHENSIVE = (
        "comprehensive"  # Path normalization + inode + post-add registration
    )


@dataclass
class FileComparisonResult:
    """File comparison result."""

    identical: bool
    method_used: ComparisonMethod
    error: Optional[str] = None
    hash1: Optional[str] = None
    hash2: Optional[str] = None


@dataclass
class DuplicateInfo:
    """Duplicate file information."""

    normalized_path: str
    original_path: str
    inode: Optional[Tuple[int, int]] = None  # (device, inode)
    is_duplicate: bool = False
    duplicate_reason: Optional[str] = None


@dataclass
class FileRelationshipAnalysis:
    """File relationship analysis result."""

    exists: bool
    changed: bool
    change_type: Optional[str]  # 'ahead', 'behind', None
    time_diff: float
    local_mtime: Optional[float]
    backup_mtime: Optional[float]
    comparison_result: Optional[FileComparisonResult] = None


class FileComparisonManager:
    """Unified file comparison and duplicate detection manager."""

    def __init__(self, encryption_manager=None):
        """
        Args:
            encryption_manager: Encryption manager (for encrypted file comparison).
        """
        self.encryption_manager = encryption_manager
        self._hash_cache: Dict[str, str] = {}  # パス -> ハッシュのキャッシュ
        self._inode_cache: Set[Tuple[int, int]] = set()  # inode情報のキャッシュ
        self._path_cache: Set[str] = set()  # 正規化パスのキャッシュ

    def clear_caches(self) -> None:
        """Clear all caches."""
        self._hash_cache.clear()
        self._inode_cache.clear()
        self._path_cache.clear()

    def are_files_identical(
        self,
        file1: Path,
        file2: Path,
        comparison_type: ComparisonMethod = ComparisonMethod.HASH,
        config_manager=None,
    ) -> FileComparisonResult:
        """
        Unified file comparison.

        Args:
            file1: First file to compare.
            file2: Second file to compare.
            comparison_type: Comparison method.
            config_manager: Config manager (for encryption detection).

        Returns:
            FileComparisonResult: Comparison result.
        """
        try:
            # ファイル存在チェック
            if not file1.exists() or not file2.exists():
                return FileComparisonResult(
                    identical=False,
                    method_used=comparison_type,
                    error="One or both files do not exist",
                )

            # 両方のファイルサイズが0の場合は同一とみなす
            if file1.stat().st_size == 0 and file2.stat().st_size == 0:
                return FileComparisonResult(identical=True, method_used=comparison_type)

            if comparison_type == ComparisonMethod.BINARY:
                return self._compare_binary(file1, file2)
            elif comparison_type == ComparisonMethod.HASH:
                return self._compare_hash(file1, file2)
            elif comparison_type == ComparisonMethod.COMPREHENSIVE:
                return self._compare_comprehensive(file1, file2, config_manager)
            else:
                return FileComparisonResult(
                    identical=False,
                    method_used=comparison_type,
                    error=f"Unknown comparison method: {comparison_type}",
                )

        except Exception as e:
            return FileComparisonResult(
                identical=False,
                method_used=comparison_type,
                error=f"Comparison failed: {str(e)}",
            )

    def _compare_binary(self, file1: Path, file2: Path) -> FileComparisonResult:
        """Binary exact match comparison."""
        try:
            with open(file1, "rb") as f1, open(file2, "rb") as f2:
                identical = f1.read() == f2.read()
            return FileComparisonResult(
                identical=identical, method_used=ComparisonMethod.BINARY
            )
        except Exception as e:
            return FileComparisonResult(
                identical=False, method_used=ComparisonMethod.BINARY, error=str(e)
            )

    def _compare_hash(self, file1: Path, file2: Path) -> FileComparisonResult:
        """SHA256 hash comparison."""
        try:
            hash1 = self._calculate_file_hash(file1)
            hash2 = self._calculate_file_hash(file2)

            if hash1 is None or hash2 is None:
                return FileComparisonResult(
                    identical=False,
                    method_used=ComparisonMethod.HASH,
                    error="Failed to calculate hash for one or both files",
                    hash1=hash1,
                    hash2=hash2,
                )

            return FileComparisonResult(
                identical=hash1 == hash2,
                method_used=ComparisonMethod.HASH,
                hash1=hash1,
                hash2=hash2,
            )
        except Exception as e:
            return FileComparisonResult(
                identical=False, method_used=ComparisonMethod.HASH, error=str(e)
            )

    def _compare_comprehensive(
        self, file1: Path, file2: Path, config_manager=None
    ) -> FileComparisonResult:
        """Comprehensive comparison (with encrypted file support)."""
        try:
            # 通常ファイル同士の比較
            if not file2.name.endswith(".enc"):
                return self._compare_hash(file1, file2)

            # 暗号化ファイルの場合は復号化して比較
            # Note: file2が.encで終わっている時点で、呼び出し側で暗号化対象と判定済み
            if self.encryption_manager:
                try:
                    # 既存の暗号化ファイルを復号化
                    with open(file2, "rb") as f:
                        encrypted_data = f.read()
                    decrypted_data = self.encryption_manager.decrypt_data(
                        encrypted_data
                    )

                    # 元ファイルと復号化したデータを比較
                    with open(file1, "rb") as f:
                        source_data = f.read()

                    identical = source_data == decrypted_data
                    return FileComparisonResult(
                        identical=identical, method_used=ComparisonMethod.COMPREHENSIVE
                    )
                except Exception as e:
                    # 復号化に失敗した場合は異なるファイルとみなす
                    return FileComparisonResult(
                        identical=False,
                        method_used=ComparisonMethod.COMPREHENSIVE,
                        error=f"Decryption failed: {str(e)}",
                    )

            return FileComparisonResult(
                identical=False,
                method_used=ComparisonMethod.COMPREHENSIVE,
                error="Encryption manager not available or file not encrypted",
            )

        except Exception as e:
            return FileComparisonResult(
                identical=False,
                method_used=ComparisonMethod.COMPREHENSIVE,
                error=str(e),
            )

    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """Calculate SHA256 hash of a file (with caching)."""
        file_path_str = str(file_path)

        # キャッシュチェック
        if file_path_str in self._hash_cache:
            return self._hash_cache[file_path_str]

        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_sha256.update(chunk)

            file_hash = hash_sha256.hexdigest()
            self._hash_cache[file_path_str] = file_hash
            return file_hash
        except Exception:
            return None

    def detect_duplicates(
        self,
        file_paths: List[Path],
        method: DuplicateDetectionMethod = DuplicateDetectionMethod.COMPREHENSIVE,
    ) -> Dict[str, List[DuplicateInfo]]:
        """
        Advanced duplicate detection.

        Args:
            file_paths: List of file paths to check.
            method: Duplicate detection method.

        Returns:
            Dict: Duplicate groups {group_key: [DuplicateInfo, ...]}.
        """
        duplicates = {}
        seen_paths = set()
        seen_inodes = set()

        for file_path in file_paths:
            try:
                duplicate_info = self._analyze_duplicate(
                    file_path, method, seen_paths, seen_inodes
                )

                if duplicate_info.is_duplicate:
                    # 重複グループのキーを決定
                    if duplicate_info.inode:
                        group_key = (
                            f"inode_{duplicate_info.inode[0]}_{duplicate_info.inode[1]}"
                        )
                    else:
                        group_key = f"path_{duplicate_info.normalized_path}"

                    if group_key not in duplicates:
                        duplicates[group_key] = []
                    duplicates[group_key].append(duplicate_info)
                else:
                    # 見つかったファイルを記録
                    seen_paths.add(duplicate_info.normalized_path)
                    if duplicate_info.inode:
                        seen_inodes.add(duplicate_info.inode)

            except Exception as e:
                # エラーが発生したファイルは警告として記録
                error_info = DuplicateInfo(
                    normalized_path=str(file_path),
                    original_path=str(file_path),
                    is_duplicate=False,
                    duplicate_reason=f"Analysis error: {str(e)}",
                )
                duplicates.setdefault("errors", []).append(error_info)

        return duplicates

    def _analyze_duplicate(
        self,
        file_path: Path,
        method: DuplicateDetectionMethod,
        seen_paths: Set[str],
        seen_inodes: Set[Tuple[int, int]],
    ) -> DuplicateInfo:
        """Analyze single file for duplicates."""

        # パスを正規化
        try:
            normalized_path = os.path.normpath(str(file_path))
            # Windowsでのパス区切り文字統一
            normalized_path = normalized_path.replace("\\", "/")
        except Exception:
            # 正規化に失敗した場合は元のパスを使用
            normalized_path = str(file_path)

        # inode情報取得（Unix系のみ）
        file_inode = None
        try:
            if file_path.exists():
                stat_info = file_path.stat()
                file_inode = (stat_info.st_dev, stat_info.st_ino)
        except (OSError, AttributeError):
            # Windows や権限エラーの場合は無視
            pass

        duplicate_info = DuplicateInfo(
            normalized_path=normalized_path,
            original_path=str(file_path),
            inode=file_inode,
        )

        # 重複チェック
        if method == DuplicateDetectionMethod.PATH_ONLY:
            if normalized_path in seen_paths:
                duplicate_info.is_duplicate = True
                duplicate_info.duplicate_reason = "Path normalization match"

        elif method == DuplicateDetectionMethod.INODE_ONLY:
            if file_inode and file_inode in seen_inodes:
                duplicate_info.is_duplicate = True
                duplicate_info.duplicate_reason = "Inode match"

        elif method == DuplicateDetectionMethod.COMPREHENSIVE:
            # パス正規化チェック
            if normalized_path in seen_paths:
                duplicate_info.is_duplicate = True
                duplicate_info.duplicate_reason = "Path normalization match"
            # inode チェック（シンボリックリンク・ハードリンク対応）
            elif file_inode and file_inode in seen_inodes:
                duplicate_info.is_duplicate = True
                duplicate_info.duplicate_reason = "Inode match (symlink/hardlink)"

        return duplicate_info

    def analyze_file_relationship(
        self,
        local_path: Path,
        backup_path: Path,
        local_mtime: Optional[float] = None,
        backup_mtime: Optional[float] = None,
        config_manager=None,
    ) -> FileRelationshipAnalysis:
        """
        Comprehensive file relationship analysis.

        Args:
            local_path: Path to the local file.
            backup_path: Path to the backup file.
            local_mtime: Local file modification time (auto-fetched if omitted).
            backup_mtime: Backup file modification time (auto-fetched if omitted).
            config_manager: Config manager (for encryption detection).

        Returns:
            FileRelationshipAnalysis: Analysis result.
        """
        result = FileRelationshipAnalysis(
            exists=local_path.exists(),
            changed=False,
            change_type=None,
            time_diff=0,
            local_mtime=local_mtime,
            backup_mtime=backup_mtime,
        )

        if not result.exists:
            return result

        # mtimeの取得（引数で渡されていない場合）
        if local_mtime is None:
            result.local_mtime = local_path.stat().st_mtime
        if backup_mtime is None and backup_path.exists():
            result.backup_mtime = backup_path.stat().st_mtime

        # ファイル比較
        comparison_result = self.are_files_identical(
            local_path, backup_path, ComparisonMethod.COMPREHENSIVE, config_manager
        )
        result.comparison_result = comparison_result
        result.changed = not comparison_result.identical

        # ahead/behind判定（変更がある場合のみ）
        if result.changed and result.local_mtime and result.backup_mtime:
            result.time_diff = result.local_mtime - result.backup_mtime

            if abs(result.time_diff) < 2:  # 2秒以内は同期済み
                result.changed = False  # ハッシュが違っても時間が同じなら同期済み扱い
                result.change_type = None
            elif result.time_diff > 0:  # ローカルが新しい
                result.change_type = "ahead"
            else:  # バックアップが新しい
                result.change_type = "behind"

        return result

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "hash_cache_size": len(self._hash_cache),
            "inode_cache_size": len(self._inode_cache),
            "path_cache_size": len(self._path_cache),
        }
