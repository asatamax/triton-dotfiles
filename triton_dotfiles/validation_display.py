"""
Validation結果表示用のヘルパーモジュール

将来のリファクタリング（ValidationResultクラス化）の準備として、
絵文字判定ロジックを1箇所に集約。
"""

import click
from colorama import Fore, Style
from typing import List, Tuple, Optional
from .config import ConfigManager


class ValidationDisplay:
    """バリデーション結果の表示を統一管理するクラス"""

    # 記号判定の集約（将来のリファクタリング時にここだけ変更）
    # CLI Design Guide: 設定系コマンドは記号ベース (✗, !, ✓)
    ERROR_PREFIX = "✗"
    WARNING_PREFIX = "!"
    INFO_PREFIX = "i"

    @classmethod
    def categorize_results(cls, results: List[str]) -> Tuple[List[str], List[str]]:
        """バリデーション結果を警告/情報とエラーに分類"""
        warnings_and_info = [
            r for r in results if r.startswith((cls.WARNING_PREFIX, cls.INFO_PREFIX))
        ]
        errors = [r for r in results if r.startswith(cls.ERROR_PREFIX)]
        return warnings_and_info, errors

    @classmethod
    def display_validation_results(
        cls,
        config_manager: ConfigManager,
        show_success_message: bool = True,
        ask_continue_on_error: bool = False,
    ) -> bool:
        """
        統一されたバリデーション結果表示

        Args:
            config_manager: 設定管理オブジェクト
            show_success_message: エラーがない場合の成功メッセージ表示フラグ
            ask_continue_on_error: エラー時に続行確認するフラグ

        Returns:
            bool: 続行可能かどうか（エラーなし or ユーザーが続行選択）
        """
        validation_results = config_manager.validate_config()
        actual_errors = config_manager.get_validation_errors()

        warnings_and_info, _ = cls.categorize_results(validation_results)

        # 警告・情報の表示
        if warnings_and_info:
            click.echo(f"{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for msg in warnings_and_info:
                click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {msg}")

        # エラーの表示
        if actual_errors:
            click.echo(f"\n{Fore.RED}Errors:{Style.RESET_ALL}")
            for error in actual_errors:
                click.echo(f"  {Fore.RED}✗{Style.RESET_ALL} {error}")

            if ask_continue_on_error:
                return click.confirm("Continue anyway?")
            return False

        # 成功メッセージ
        if show_success_message and not actual_errors:
            click.echo(f"\n{Fore.GREEN}✓ No configuration errors{Style.RESET_ALL}")

        return True

    @classmethod
    def display_detailed_validation(
        cls,
        config_manager: ConfigManager,
        additional_warnings: Optional[List[str]] = None,
    ):
        """詳細バリデーション表示（validate コマンド用）"""
        validation_results = config_manager.validate_config()
        actual_errors = config_manager.get_validation_errors()

        warnings_and_info, _ = cls.categorize_results(validation_results)

        # バリデーション結果を表示
        if warnings_and_info:
            click.echo(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for msg in warnings_and_info:
                click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {msg}")

        # 実際のエラーのみを表示
        if actual_errors:
            click.echo(f"\n{Fore.RED}Errors:{Style.RESET_ALL}")
            for error in actual_errors:
                click.echo(f"  {Fore.RED}✗{Style.RESET_ALL} {error}")

        # 追加の警告を表示（パス検証など）
        if additional_warnings:
            click.echo(f"\n{Fore.YELLOW}Path warnings:{Style.RESET_ALL}")
            for warning in additional_warnings:
                click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {warning}")

        # 完璧な場合の表示
        if not actual_errors and not additional_warnings:
            click.echo(f"\n{Fore.GREEN}✓ Configuration is valid{Style.RESET_ALL}")


# 将来のリファクタリング準備用の列挙型（コメントアウト）
"""
from enum import Enum
from dataclasses import dataclass

class ValidationLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationResult:
    level: ValidationLevel
    message: str
    context: Optional[str] = None  # どのターゲットやパスに関連するか

    def __str__(self) -> str:
        # CLI Design Guide: 設定系コマンドは記号ベース
        prefix_map = {
            ValidationLevel.ERROR: "✗",
            ValidationLevel.WARNING: "!",
            ValidationLevel.INFO: "i"
        }
        return f"{prefix_map[self.level]} {self.message}"
"""
