"""
Helper module for validation result display.

Centralizes symbol/prefix logic in preparation for future refactoring
(e.g., ValidationResult class).
"""

import click
from colorama import Fore, Style
from typing import List, Tuple, Optional
from .config import ConfigManager


class ValidationDisplay:
    """Unified validation result display manager."""

    # Centralized symbol definitions (change only here for future refactoring)
    # CLI Design Guide: config commands use symbol-based prefixes (✗, !, ✓)
    ERROR_PREFIX = "✗"
    WARNING_PREFIX = "!"
    INFO_PREFIX = "i"

    @classmethod
    def categorize_results(
        cls, results: List[str]
    ) -> Tuple[List[str], List[str], List[str]]:
        """Categorize validation results into warnings, info, and errors.

        Returns:
            Tuple of (warnings, info, errors).
            warnings: items starting with WARNING_PREFIX ('!')
            info: items starting with INFO_PREFIX ('i')
            errors: items starting with ERROR_PREFIX ('✗')
        """
        warnings = [r for r in results if r.startswith(cls.WARNING_PREFIX)]
        info = [r for r in results if r.startswith(cls.INFO_PREFIX)]
        errors = [r for r in results if r.startswith(cls.ERROR_PREFIX)]
        return warnings, info, errors

    @classmethod
    def display_validation_results(
        cls,
        config_manager: ConfigManager,
        show_success_message: bool = True,
        ask_continue_on_error: bool = False,
        verbose: bool = False,
    ) -> bool:
        """
        Display validation results in a unified format.

        Args:
            config_manager: Configuration manager object.
            show_success_message: Show success message when no errors.
            ask_continue_on_error: Prompt user to continue when errors exist.
            verbose: Show info-level messages (target mode descriptions, etc.).

        Returns:
            bool: Whether to proceed (no errors or user chose to continue).
        """
        validation_results = config_manager.validate_config()
        actual_errors = config_manager.get_validation_errors()

        warnings, info, _ = cls.categorize_results(validation_results)

        # 警告の表示
        if warnings:
            click.echo(f"{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for msg in warnings:
                click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {msg}")

        # info表示（verbose時のみ）
        if verbose and info:
            click.echo(f"{Fore.CYAN}Info:{Style.RESET_ALL}")
            for msg in info:
                click.echo(f"  {Fore.CYAN}i{Style.RESET_ALL} {msg}")

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
        """Display detailed validation results (for validate command).

        Always shows all messages including info (used by validate --verbose).
        """
        validation_results = config_manager.validate_config()
        actual_errors = config_manager.get_validation_errors()

        warnings, info, _ = cls.categorize_results(validation_results)

        # 警告の表示
        if warnings:
            click.echo(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for msg in warnings:
                click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {msg}")

        # info表示
        if info:
            click.echo(f"\n{Fore.CYAN}Info:{Style.RESET_ALL}")
            for msg in info:
                click.echo(f"  {Fore.CYAN}i{Style.RESET_ALL} {msg}")

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
