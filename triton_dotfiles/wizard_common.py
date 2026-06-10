#!/usr/bin/env python3
"""
Shared helpers for interactive setup wizards (init / join).
"""

import os
import re
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style


def prompt_valid_path(prompt_text: str, default: Optional[str] = None) -> Path:
    """Prompt for a valid file path with validation.

    Validates that the input looks like a path (contains / or ~)
    to prevent accidental numeric input from being used as a path.

    Args:
        prompt_text: Prompt label shown to the user.
        default: Default value offered to the user.

    Returns:
        Expanded Path entered by the user.
    """
    while True:
        if default:
            path_str = click.prompt(prompt_text, default=default)
        else:
            path_str = click.prompt(prompt_text)

        path_str = path_str.strip()
        if not path_str:
            click.echo(f"  {Fore.YELLOW}Please enter a valid path.{Style.RESET_ALL}")
            continue

        # Reject pure numeric input (likely accidental from previous prompt)
        if path_str.isdigit():
            click.echo(
                f"  {Fore.YELLOW}Invalid path: '{path_str}'. Please enter a directory path.{Style.RESET_ALL}"
            )
            continue

        # Path should contain / or start with ~
        if "/" not in path_str and not path_str.startswith("~"):
            click.echo(
                f"  {Fore.YELLOW}Invalid path format. Use absolute path (/) or home-relative path (~/).{Style.RESET_ALL}"
            )
            continue

        return Path(path_str).expanduser()


def update_config_repository_settings(
    config_path: Path,
    vault_path: Optional[Path] = None,
    machine_name: Optional[str] = None,
) -> None:
    """Update repository settings in a template-generated config.yml.

    Rewrites the template vault path and, when a custom machine name was
    chosen, inserts a ``machine_name`` entry in the repository section.
    Failures are non-critical (the user can edit the file manually).

    Args:
        config_path: Path to the config.yml to update.
        vault_path: Vault path to set as repository.path.
        machine_name: Machine name; only written when it differs from the
            auto-detected name.
    """
    try:
        content = config_path.read_text()
        home = str(Path.home())

        if vault_path:
            vault_path_str = str(vault_path)
            if vault_path_str.startswith(home):
                vault_path_str = "~" + vault_path_str[len(home) :]
            content = content.replace(
                "path: ~/dotfiles-repo",
                f"path: {vault_path_str}",
            )

        if machine_name:
            from .config import get_machine_name_unified

            auto_name = get_machine_name_unified(use_hostname=True)
            if machine_name != auto_name:
                # Custom name was set - add machine_name after use_hostname
                pattern = r"(repository:\s*\n(?:.*\n)*?\s*use_hostname:\s*true)"
                replacement = r"\1\n    machine_name: " + machine_name
                content = re.sub(pattern, replacement, content)

        config_path.write_text(content)
    except Exception:
        pass  # Non-critical, user can edit manually


def read_repository_path_from_config(config_path: Path) -> Optional[Path]:
    """Read repository.path from a config.yml without full validation.

    Used by wizards before a working setup exists, where strict config
    validation would get in the way.

    Args:
        config_path: Path to the config.yml.

    Returns:
        Expanded repository path, or None if unavailable.
    """
    try:
        import yaml

        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        if config_data and "config" in config_data:
            repo_path = config_data["config"].get("repository", {}).get("path")
            if repo_path:
                return Path(os.path.expandvars(str(repo_path))).expanduser()
    except Exception:
        pass

    return None


def read_machine_name_from_config(config_path: Path) -> Optional[str]:
    """Read repository.machine_name from a config.yml if explicitly set.

    Args:
        config_path: Path to the config.yml.

    Returns:
        Configured machine name, or None when not set / unreadable.
    """
    try:
        import yaml

        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        if config_data and "config" in config_data:
            name = config_data["config"].get("repository", {}).get("machine_name")
            if name:
                return str(name)
    except Exception:
        pass

    return None


def scan_vault_machines(vault_path: Path) -> list[dict]:
    """Scan a vault directory for machine folders.

    Lightweight scan for wizard display, usable before a valid
    ConfigManager exists.

    Args:
        vault_path: Vault repository root.

    Returns:
        List of {"name": str, "file_count": int} sorted by name.
    """
    machines = []
    try:
        for item in sorted(vault_path.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                file_count = sum(1 for f in item.rglob("*") if f.is_file())
                machines.append({"name": item.name, "file_count": file_count})
    except OSError:
        pass

    return machines
