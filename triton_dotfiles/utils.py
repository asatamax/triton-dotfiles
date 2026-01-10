#!/usr/bin/env python3
"""
Utility functions for triton-dotfiles
"""

import os
import re
import sys
import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Type, List


def safe_import(
    module_name: str, package: str = None, fallback_path: str = None
) -> Any:
    """
    Safe import handling.

    Args:
        module_name: Name of the module to import.
        package: Package name (for relative imports).
        fallback_path: Path to add to sys.path as fallback.

    Returns:
        Imported module.

    Raises:
        ImportError: If import fails.
    """
    try:
        # 相対インポートを試す
        if package:
            return __import__(module_name, fromlist=[package])
        else:
            return __import__(module_name)
    except ImportError:
        # フォールバック: 絶対パスでインポート
        if fallback_path:
            if fallback_path not in sys.path:
                sys.path.append(fallback_path)
            return __import__(module_name)
        raise


def get_package_root() -> Path:
    """Get the package root directory."""
    return Path(__file__).parent


def import_from_package(module_name: str) -> Any:
    """
    Import a module from the package uniformly.

    Args:
        module_name: Name of the module to import (e.g., 'config', 'file_manager').

    Returns:
        Imported module.
    """
    package_root = get_package_root()

    try:
        # 相対インポートを試す
        return __import__(
            f"triton_dotfiles.{module_name}", fromlist=["triton_dotfiles"]
        )
    except ImportError:
        # フォールバック: パッケージルートを追加して絶対インポート
        if str(package_root) not in sys.path:
            sys.path.append(str(package_root))
        return __import__(module_name)


def import_class_from_module(module_name: str, class_name: str) -> Type:
    """
    Import a specific class from a module.

    Args:
        module_name: Module name.
        class_name: Class name.

    Returns:
        Imported class.
    """
    module = import_from_package(module_name)
    return getattr(module, class_name)


def get_triton_dir() -> Path:
    """Get the Triton directory path (with environment variable support).

    Returns:
        Path: Triton directory path (absolute, resolved).

    Note:
        Uses TRITON_DIR environment variable if set,
        otherwise defaults to ~/.config/triton.
    """
    return Path(os.getenv("TRITON_DIR", "~/.config/triton")).expanduser().resolve()


def matches_glob_pattern(path: Path, pattern: str) -> bool:
    """
    Check if a path matches a glob pattern.

    Supports:
    - Basic wildcards: *.txt, config.*
    - Globstar: **/*.md, **/node_modules/**
    - Path matching: packages/*/src

    Args:
        path: Path to check (relative path).
        pattern: Glob pattern.

    Returns:
        True if matched.
    """
    # パスをPOSIX形式に正規化
    path_str = str(PurePosixPath(path))

    # globstarパターン（**）の処理
    if "**" in pattern:
        # **を正規表現に変換
        # ** は任意のパス部分にマッチ（0個以上のディレクトリ）
        regex_pattern = pattern
        # エスケープが必要な文字を処理
        regex_pattern = regex_pattern.replace(".", r"\.")
        regex_pattern = regex_pattern.replace("?", ".")
        # ** を一時的なプレースホルダに置換
        regex_pattern = regex_pattern.replace("**/", "__GLOBSTAR_SLASH__")
        regex_pattern = regex_pattern.replace("**", "__GLOBSTAR__")
        # 通常の * を処理
        regex_pattern = regex_pattern.replace("*", "[^/]*")
        # globstarを復元
        regex_pattern = regex_pattern.replace("__GLOBSTAR_SLASH__", "(?:.*/)?")
        regex_pattern = regex_pattern.replace("__GLOBSTAR__", ".*")
        # 完全マッチ
        regex_pattern = f"^{regex_pattern}$"

        try:
            return bool(re.match(regex_pattern, path_str))
        except re.error:
            return False
    else:
        # 標準のfnmatchを使用
        # パス全体とファイル名の両方でマッチを試みる
        if fnmatch.fnmatch(path_str, pattern):
            return True
        # ファイル名のみでもマッチを試みる
        if fnmatch.fnmatch(path.name, pattern):
            return True
        return False


def matches_any_pattern(file_path: Path, patterns: List[str]) -> bool:
    """
    Check if a file matches any pattern in the list (OR evaluation).

    Used for priority rules like blacklist or encrypt_list.
    Returns True if any pattern matches.

    Args:
        file_path: File path to check.
        patterns: List of patterns.

    Returns:
        True if any pattern matched.
    """
    for pattern in patterns:
        if matches_glob_pattern(file_path, pattern):
            return True
    return False
