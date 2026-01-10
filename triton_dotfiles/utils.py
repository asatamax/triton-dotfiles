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
    安全なインポート処理

    Args:
        module_name: インポートするモジュール名
        package: パッケージ名（相対インポート用）
        fallback_path: フォールバック時にsys.pathに追加するパス

    Returns:
        インポートしたモジュール

    Raises:
        ImportError: インポートに失敗した場合
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
    """パッケージルートディレクトリを取得"""
    return Path(__file__).parent


def import_from_package(module_name: str) -> Any:
    """
    パッケージから統一的にモジュールをインポート

    Args:
        module_name: インポートするモジュール名（例: 'config', 'file_manager'）

    Returns:
        インポートしたモジュール
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
    モジュールから特定のクラスをインポート

    Args:
        module_name: モジュール名
        class_name: クラス名

    Returns:
        インポートしたクラス
    """
    module = import_from_package(module_name)
    return getattr(module, class_name)


def get_triton_dir() -> Path:
    """Tritonディレクトリのパスを取得（環境変数対応）

    Returns:
        Path: Tritonディレクトリのパス（絶対パス・解決済み）

    Note:
        TRITON_DIR環境変数が設定されている場合はそれを使用、
        未設定の場合は~/.config/tritonを使用
    """
    return Path(os.getenv("TRITON_DIR", "~/.config/triton")).expanduser().resolve()


def matches_glob_pattern(path: Path, pattern: str) -> bool:
    """
    パスがglobパターンにマッチするかチェック

    Supports:
    - Basic wildcards: *.txt, config.*
    - Globstar: **/*.md, **/node_modules/**
    - Path matching: packages/*/src

    Args:
        path: チェック対象のパス（相対パス）
        pattern: globパターン

    Returns:
        マッチした場合True
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
    ファイルがパターンリストのいずれかにマッチするかチェック（OR評価）

    blacklistやencrypt_listのような最優先ルールに使用。
    いずれかのパターンにマッチすれば True を返す。

    Args:
        file_path: チェック対象のファイルパス
        patterns: パターンリスト

    Returns:
        いずれかのパターンにマッチした場合True
    """
    for pattern in patterns:
        if matches_glob_pattern(file_path, pattern):
            return True
    return False
