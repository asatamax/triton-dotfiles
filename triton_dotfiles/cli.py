#!/usr/bin/env python3
"""
Dotfiles Management - Main CLI
"""

import os
import sys
import rich_click as click
from pathlib import Path
from colorama import Fore, Style
from .validation_display import ValidationDisplay

from .utils import import_class_from_module, get_triton_dir
from .__version__ import get_version_info

ConfigManager = import_class_from_module("config", "ConfigManager")
create_default_config = import_class_from_module("config", "create_default_config")
FileManager = import_class_from_module("managers.file_manager", "FileManager")
EncryptionManager = import_class_from_module("encryption", "get_encryption_manager")
create_encryption_key = import_class_from_module("encryption", "create_encryption_key")


def set_triton_dir(triton_dir: str) -> None:
    """Set TRITON_DIR environment variable for the current process.

    This ensures all subsequent calls to get_triton_dir() return the specified directory,
    keeping config.yml, master.key, and archives/ in the same location.
    """
    resolved_path = Path(triton_dir).expanduser().resolve()
    os.environ["TRITON_DIR"] = str(resolved_path)


def find_config_file() -> str:
    """Find config file from TRITON_DIR.

    Returns:
        Config file path if found, None otherwise.
    """
    triton_dir = get_triton_dir()
    config_path = triton_dir / "config.yml"

    if config_path.exists():
        return str(config_path)

    return None


@click.group(invoke_without_command=True)
@click.option(
    "--config",
    "-c",
    "triton_dir",
    default=None,
    help="Triton directory containing config.yml, master.key, and archives/",
)
@click.option("--version", is_flag=True, help="Show version information")
@click.option(
    "--skip-startup",
    "-S",
    is_flag=True,
    help="Skip auto git pull and hooks on TUI startup",
)
@click.pass_context
def cli(ctx, triton_dir, version, skip_startup):
    """Dotfiles management tool.

    Launches TUI by default. For CLI commands:
    triton backup, triton restore, triton diff, etc.

    \b
    For LLM/AI agents:
    Use --schema option to get machine-readable JSON documentation:
      triton config --schema   - Configuration management commands
      triton archive --schema  - Archive management commands
      triton init --schema     - Initialization commands
    """
    ctx.ensure_object(dict)
    ctx.obj["skip_startup"] = skip_startup

    # Set TRITON_DIR if --config option is specified
    if triton_dir:
        set_triton_dir(triton_dir)

    # Handle --version flag
    if version:
        version_info = get_version_info()
        click.echo(
            f"{Fore.CYAN}Triton Dotfiles {Fore.GREEN}{version_info['version']}{Style.RESET_ALL}"
        )

        if version_info["source"] == "git":
            click.echo(f"Version source: {Fore.GREEN}Git tag{Style.RESET_ALL}")
        else:
            click.echo(f"Version source: {Fore.YELLOW}Static fallback{Style.RESET_ALL}")

        if version_info["git_version"]:
            click.echo(f"Git version: {version_info['git_version']}")
        if version_info["static_version"]:
            click.echo(f"Static version: {version_info['static_version']}")

        return

    # Determine config file location (except when launching TUI)
    if ctx.invoked_subcommand is None:
        # Check config file before launching TUI
        config_path = find_config_file()
        if config_path is None:
            # First-time user: show friendly welcome message instead of error
            _show_welcome_message()
            sys.exit(0)

        # Launch TUI when config exists
        _launch_default_tui(skip_startup=skip_startup)
        return

    # Commands that don't require config.yml
    config_optional_commands = {"init"}

    if ctx.invoked_subcommand in config_optional_commands:
        # Skip config file check for init and similar commands
        ctx.obj["config_path"] = None
        return

    # Check config file when subcommand is specified
    config_path = find_config_file()

    # Error handling when config file is not found
    if config_path is None:
        current_triton_dir = get_triton_dir()
        click.echo(f"{Fore.RED}Error: Configuration file not found{Style.RESET_ALL}")
        click.echo(f"Expected at: {current_triton_dir / 'config.yml'}")
        click.echo(f"\n{Fore.YELLOW}To get started:{Style.RESET_ALL}")
        click.echo("  1. Run 'triton init' to start the setup wizard")
        click.echo("  2. Or run 'triton init config' to create a config template")
        click.echo(f"\n{Fore.CYAN}For help: triton --help{Style.RESET_ALL}")
        sys.exit(1)

    ctx.obj["config_path"] = config_path


def _show_welcome_message():
    """Show friendly welcome message for first-time users."""
    version_info = get_version_info()
    version = version_info["version"]

    click.echo()
    click.echo(f"  {Fore.CYAN}Welcome to Triton Dotfiles {version}{Style.RESET_ALL}")
    click.echo()
    click.echo("  Triton helps you manage and sync dotfiles across machines.")
    click.echo("  Let's get you set up!")
    click.echo()
    click.echo(f"  {Fore.YELLOW}Get started:{Style.RESET_ALL}")
    click.echo(
        f"    {Fore.GREEN}triton init{Style.RESET_ALL}  - Interactive setup wizard"
    )
    click.echo()
    click.echo(f"  {Fore.CYAN}Learn more:{Style.RESET_ALL}")
    click.echo("    triton --help")
    click.echo()


def _launch_default_tui(skip_startup: bool = False):
    """Launch TUI by default."""
    try:
        from .tui_textual.app import run_textual_tui

        run_textual_tui(skip_startup=skip_startup)
    except ImportError as e:
        click.echo(f"{Fore.RED}Error: Textual TUI not available: {e}{Style.RESET_ALL}")
        click.echo("Install textual dependencies with: uv sync --extra tui")
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: Textual TUI: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.option("--dry-run", "-n", is_flag=True, help="Dry run - show what would be done")
@click.option("--machine", "-m", help="Override machine name")
@click.pass_context
def backup(ctx, dry_run, machine):
    """Backup current machine's configuration."""
    try:
        # Display config file in use
        config_path = Path(ctx.obj["config_path"]).resolve()
        click.echo(f"Using config: {Fore.CYAN}{config_path}{Style.RESET_ALL}")

        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Validate configuration
        if not ValidationDisplay.display_validation_results(
            config_manager, show_success_message=False, ask_continue_on_error=True
        ):
            return

        machine_name = machine or config_manager.get_machine_name()
        results = file_manager.backup_files(machine_name, dry_run=dry_run)

        # Display results
        click.echo(
            f"\nBackup complete: {len(results['copied'])} files copied, "
            f"{len(results['unchanged'])} unchanged"
        )
        if results["skipped"]:
            click.echo(
                f"{Fore.YELLOW}Warning: {len(results['skipped'])} files skipped{Style.RESET_ALL}"
            )
        if results["errors"]:
            click.echo(f"{Fore.RED}Errors: {len(results['errors'])}{Style.RESET_ALL}")

        if results["errors"]:
            click.echo(f"\n{Fore.RED}Errors:{Style.RESET_ALL}")
            for error in results["errors"]:
                click.echo(f"  - {error}")

        if not dry_run:
            repo_path = file_manager.repo_root
            click.echo(f"\n{Fore.CYAN}Next steps:{Style.RESET_ALL}")
            click.echo(f"  pushd {repo_path}")
            click.echo(f"  git add {machine_name}/")
            click.echo(f'  git commit -m "backup({machine_name}): $(date +%Y-%m-%d)"')
            click.echo("  git push")
            click.echo("  popd")
            click.echo(f"\n{Fore.YELLOW}Or as one-liner:{Style.RESET_ALL}")
            click.echo(
                f'  (pushd {repo_path} && git add {machine_name}/ && git commit -m "backup({machine_name}): $(date +%Y-%m-%d)" && git push && popd)'
            )

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.argument("source_machine")
@click.option("--target", "-t", help="Target machine name (default: current machine)")
@click.option(
    "--file",
    "-f",
    "files",
    multiple=True,
    help="Specific files to restore (can be used multiple times)",
)
@click.option("--dry-run", "-n", is_flag=True, help="Dry run - show what would be done")
@click.pass_context
def restore(ctx, source_machine, target, files, dry_run):
    """Restore configuration from specified machine."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Check available machines
        available_machines = [m["name"] for m in file_manager.get_available_machines()]

        if source_machine not in available_machines:
            click.echo(
                f"{Fore.RED}Error: Machine '{source_machine}' not found{Style.RESET_ALL}"
            )
            click.echo(f"Available machines: {', '.join(available_machines)}")
            return

        if not dry_run:
            current_machine = target or config_manager.get_machine_name()
            if files:
                click.echo(
                    f"This will restore specific files from {Fore.CYAN}{source_machine}{Style.RESET_ALL} "
                    f"to {Fore.CYAN}{current_machine}{Style.RESET_ALL}"
                )
                click.echo(f"Files to restore: {', '.join(files)}")
            else:
                click.echo(
                    f"This will restore {Fore.CYAN}{source_machine}{Style.RESET_ALL} "
                    f"settings to {Fore.CYAN}{current_machine}{Style.RESET_ALL}"
                )
            click.echo("Existing files will be archived with timestamp suffix.")
            if not click.confirm("Continue?"):
                return

        # Selective restore or full restore
        if files:
            results = file_manager.restore_specific_files(
                source_machine, list(files), target, dry_run=dry_run
            )
        else:
            results = file_manager.restore_files(
                source_machine, target, dry_run=dry_run
            )

        # Display results
        click.echo(f"\n{Fore.GREEN}Restore completed!{Style.RESET_ALL}")
        click.echo(f"Files restored: {len(results['restored'])}")
        click.echo(f"Files unchanged: {len(results['unchanged'])}")
        click.echo(f"Files archived: {len(results['backed_up'])}")
        click.echo(f"Errors: {len(results['errors'])}")

        if results["errors"]:
            click.echo(f"\n{Fore.RED}Errors:{Style.RESET_ALL}")
            for error in results["errors"]:
                click.echo(f"  - {error}")

        if not dry_run and results["restored"]:
            click.echo(
                f"\n{Fore.YELLOW}Note: If you restored SSH config, you may need to:{Style.RESET_ALL}"
            )
            click.echo("  chmod 600 ~/.ssh/config")
            click.echo("  chmod 700 ~/.ssh")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.argument("source_machine")
@click.argument("file_pattern")
@click.argument("output_path")
@click.option(
    "--no-decrypt", is_flag=True, help="Export encrypted file as-is without decryption"
)
@click.option("--dry-run", "-n", is_flag=True, help="Dry run - show what would be done")
@click.pass_context
def export(ctx, source_machine, file_pattern, output_path, no_decrypt, dry_run):
    """Export file (decrypt and save to any location like Desktop).

    Examples:
      triton export B4F .ssh/id_rsa ~/Desktop/id_rsa_b4f
      triton export B4F .aws/credentials ~/temp/aws_creds.txt
      triton export B4F "*secret*" ~/Desktop/secret_file
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Check available machines
        available_machines = [m["name"] for m in file_manager.get_available_machines()]

        if source_machine not in available_machines:
            click.echo(
                f"{Fore.RED}Error: Machine '{source_machine}' not found{Style.RESET_ALL}"
            )
            click.echo(f"Available machines: {', '.join(available_machines)}")
            return

        # Execute export
        decrypt = not no_decrypt
        result = file_manager.export_file(
            source_machine, file_pattern, output_path, decrypt=decrypt, dry_run=dry_run
        )

        # Display results
        if not dry_run:
            click.echo(f"\n{Fore.GREEN}Export completed!{Style.RESET_ALL}")
            click.echo(f"Source: {result['source']}")
            click.echo(f"Destination: {result['destination']}")
            if result["encrypted"]:
                if result["decrypted"]:
                    click.echo("File was decrypted during export")
                else:
                    click.echo(
                        "File exported as encrypted (use --no-decrypt was specified)"
                    )

            # Suggest file permission settings
            output_file = Path(output_path)
            if output_file.name.startswith("id_") or "key" in output_file.name.lower():
                click.echo(
                    f"\n{Fore.YELLOW}Security tip: Consider setting restrictive permissions:{Style.RESET_ALL}"
                )
                click.echo(f"  chmod 600 {output_path}")

    except FileNotFoundError as e:
        click.echo(f"{Fore.RED}Error:{e}{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.argument("machine1")
@click.argument("machine2")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed diff output")
@click.pass_context
def diff(ctx, machine1, machine2, verbose):
    """Compare configuration between two machines."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Check available machines
        available_machines = [m["name"] for m in file_manager.get_available_machines()]

        for machine in [machine1, machine2]:
            if machine not in available_machines:
                click.echo(f"{Fore.RED}Machine '{machine}' not found{Style.RESET_ALL}")
                click.echo(f"Available machines: {', '.join(available_machines)}")
                return

        diffs = file_manager.compare_files(machine1, machine2)
        file_manager.print_diff_summary(diffs, machine1, machine2)

        if verbose:
            click.echo(f"\n{Fore.CYAN}Detailed differences:{Style.RESET_ALL}")
            for diff in diffs:
                if diff.status != "unchanged" and diff.diff_lines:
                    click.echo(f"\n{Fore.YELLOW}=== {diff.path} ==={Style.RESET_ALL}")
                    for line in diff.diff_lines:
                        if line.startswith("+"):
                            click.echo(f"{Fore.GREEN}{line}{Style.RESET_ALL}")
                        elif line.startswith("-"):
                            click.echo(f"{Fore.RED}{line}{Style.RESET_ALL}")
                        elif line.startswith("@@"):
                            click.echo(f"{Fore.CYAN}{line}{Style.RESET_ALL}")
                        else:
                            click.echo(line)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Display current system status."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)
        machine_name = config_manager.get_machine_name()

        # Machine & Config
        click.echo(f"{Fore.CYAN}Machine:{Style.RESET_ALL} {machine_name}")
        click.echo(f"{Fore.CYAN}Config:{Style.RESET_ALL} {ctx.obj['config_path']}")

        # Repository & Git status
        repo_path = config_manager.config.repository.path
        git_status_str = _get_git_status_string(file_manager)
        click.echo(
            f"{Fore.CYAN}Repository:{Style.RESET_ALL} {repo_path} ({git_status_str})"
        )

        # Encryption status
        encryption_status = _get_encryption_status_string(config_manager)
        click.echo(f"{Fore.CYAN}Encryption:{Style.RESET_ALL} {encryption_status}")

        # Backup status
        backup_dir = file_manager.get_backup_dir(machine_name)
        if backup_dir.exists():
            file_count = sum(1 for f in backup_dir.rglob("*") if f.is_file())
            last_modified = _get_last_backup_time(backup_dir)
            if last_modified:
                click.echo(
                    f"{Fore.CYAN}Backup:{Style.RESET_ALL} {file_count} files "
                    f"(last: {last_modified})"
                )
            else:
                click.echo(f"{Fore.CYAN}Backup:{Style.RESET_ALL} {file_count} files")
        else:
            click.echo(
                f"{Fore.CYAN}Backup:{Style.RESET_ALL} "
                f"{Fore.YELLOW}no backup found{Style.RESET_ALL}"
            )

        # Available machines
        try:
            available_machines = file_manager.get_available_machines()

            if available_machines:
                click.echo(f"\n{Fore.GREEN}Available machines:{Style.RESET_ALL}")
                for machine in sorted(available_machines, key=lambda x: x["name"]):
                    status_icon = "⚫" if machine["name"] == machine_name else "⚪"
                    click.echo(
                        f"  {status_icon} {machine['name']} ({machine['file_count']} files)"
                    )
            else:
                click.echo(
                    f"\n{Fore.YELLOW}No machine backups found in repository{Style.RESET_ALL}"
                )
        except Exception as e:
            click.echo(
                f"\n{Fore.YELLOW}Could not scan repository: {e}{Style.RESET_ALL}"
            )

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


def _get_git_status_string(file_manager: FileManager) -> str:
    """Get a concise Git status string."""
    try:
        git_manager = file_manager.git_manager
        if not git_manager.is_git_repository():
            return f"{Fore.YELLOW}not a git repo{Style.RESET_ALL}"

        # Check working directory status
        wd_result = git_manager.is_working_directory_clean()
        is_clean = wd_result.get("is_clean", False)

        # Check remote status
        remote_result = git_manager.check_remote_status()
        ahead = remote_result.get("ahead", 0)
        behind = remote_result.get("behind", 0)

        # Build status string
        parts = []
        if is_clean:
            parts.append(f"{Fore.GREEN}clean{Style.RESET_ALL}")
        else:
            parts.append(f"{Fore.YELLOW}dirty{Style.RESET_ALL}")

        if ahead > 0 and behind > 0:
            parts.append(f"{Fore.YELLOW}↑{ahead} ↓{behind}{Style.RESET_ALL}")
        elif ahead > 0:
            parts.append(f"{Fore.YELLOW}↑{ahead} unpushed{Style.RESET_ALL}")
        elif behind > 0:
            parts.append(f"{Fore.YELLOW}↓{behind} behind{Style.RESET_ALL}")
        else:
            parts.append(f"{Fore.GREEN}up-to-date{Style.RESET_ALL}")

        return ", ".join(parts)
    except Exception:
        return f"{Fore.YELLOW}unknown{Style.RESET_ALL}"


def _get_encryption_status_string(config_manager: ConfigManager) -> str:
    """Get encryption status string."""
    if not config_manager.config.encryption.enabled:
        return f"{Fore.YELLOW}disabled{Style.RESET_ALL}"

    key_file = config_manager.config.encryption.key_file
    if key_file:
        key_path = Path(key_file).expanduser()
        if key_path.exists():
            return f"{Fore.GREEN}enabled{Style.RESET_ALL} (key exists)"
        else:
            return f"{Fore.YELLOW}enabled{Style.RESET_ALL} (key missing)"
    return f"{Fore.YELLOW}enabled{Style.RESET_ALL} (no key configured)"


def _get_last_backup_time(backup_dir: Path) -> str:
    """Get the last modification time of files in backup directory."""
    try:
        from datetime import datetime

        latest_mtime = 0
        for f in backup_dir.rglob("*"):
            if f.is_file():
                mtime = f.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime

        if latest_mtime > 0:
            dt = datetime.fromtimestamp(latest_mtime)
            return dt.strftime("%Y-%m-%d %H:%M")
        return ""
    except Exception:
        return ""


# =============================================================================
# Init Commands
# =============================================================================


@cli.group("init", invoke_without_command=True)
@click.option(
    "--non-interactive",
    "-y",
    is_flag=True,
    help="Run setup with defaults, no prompts",
)
@click.option(
    "--vault-path",
    "-v",
    help="Vault (repository) path for non-interactive mode",
)
@click.option(
    "--schema",
    "show_schema",
    is_flag=True,
    help="Output command schema as JSON for LLM agents",
)
@click.pass_context
def init_cmd(ctx, non_interactive, vault_path, show_schema):
    """Initialize triton with interactive setup wizard.

    \b
    Run 'triton init' to start the interactive setup wizard.
    The wizard will guide you through:
      1. Creating configuration directory (~/.config/triton)
      2. Generating encryption key for sensitive files
      3. Setting up your vault (backup repository)
      4. Selecting initial backup targets

    \b
    For advanced users, subcommands are available:
      triton init config  - Generate config file only
      triton init key     - Generate encryption key only

    \b
    Non-interactive mode (for scripting):
      triton init -y --vault-path ~/my-vault
    """
    # Output schema if requested
    if show_schema:
        import json
        from .schema import get_init_schema

        click.echo(json.dumps(get_init_schema(), indent=2))
        ctx.exit(0)

    # Only run wizard if no subcommand is specified
    if ctx.invoked_subcommand is None:
        from .init_wizard import run_wizard

        result = run_wizard(
            non_interactive=non_interactive,
            vault_path=vault_path,
        )

        if not result.success:
            if result.errors:
                for error in result.errors:
                    click.echo(f"{Fore.RED}Error: {error}{Style.RESET_ALL}")
            sys.exit(1)


@init_cmd.command("config")
@click.option(
    "--output", "-o", help="Output file path (default: auto-detect best location)"
)
@click.option(
    "--global-config", "use_global", is_flag=True, help="Create in ~/.triton/config.yml"
)
def init_config(output, use_global):
    """Generate default configuration file."""
    try:
        # Determine output destination
        if output:
            config_path = Path(output)
        elif use_global:
            config_path = Path.home() / ".config" / "triton" / "config.yml"
        else:
            # Default: create in current directory
            config_path = Path.cwd() / "config-template.yml"

        # Create directory
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if config_path.exists():
            if not click.confirm(f"File '{config_path}' exists. Overwrite?"):
                return

        create_default_config(str(config_path))
        click.echo(
            f"{Fore.GREEN}Configuration file created: {config_path}{Style.RESET_ALL}"
        )

        # Explain recommended setup
        click.echo(f"\n{Fore.CYAN}Recommended workflow:{Style.RESET_ALL}")
        if not use_global and not output:
            click.echo(
                "  1. git init  # Initialize git repository in current directory"
            )
            click.echo("  2. Edit config.yml to add your targets")
            click.echo("  3. triton backup  # Create first backup")
            click.echo("  4. git add . && git commit -m 'Initial dotfiles'")
            click.echo(
                "\n  Others can copy your config.yml to ~/.triton/ and customize!"
            )

        click.echo(f"\n{Fore.CYAN}Next steps:{Style.RESET_ALL}")
        click.echo(f"  1. Edit {config_path} to customize your settings")
        click.echo("  2. Run 'triton config validate' to check your config")
        click.echo("  3. Run 'triton backup' to create your first backup")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@init_cmd.command("key")
@click.option(
    "--output", "-o", help="Output file path (default: ~/.config/triton/master.key)"
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force overwrite existing key (WARNING: encrypted data will be lost)",
)
def init_key(output, force):
    """Generate new encryption key."""
    try:
        key_path = None
        if output:
            key_path = Path(output).expanduser()

        create_encryption_key(key_path, force=force)

        manager = EncryptionManager(key_path)
        click.echo(
            f"{Fore.GREEN}Encryption key created: {manager.key_file}{Style.RESET_ALL}"
        )
        click.echo(f"{Fore.YELLOW}Key file created. Keep it secure!{Style.RESET_ALL}")

        click.echo(f"\n{Fore.CYAN}Next steps:{Style.RESET_ALL}")
        click.echo("  1. Enable encryption in your config.yml")
        click.echo("  2. Run 'triton backup' to create encrypted backups")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command("git-pull")
@click.option("--dry-run", "-n", is_flag=True, help="Dry run - show what would be done")
@click.pass_context
def git_pull(ctx, dry_run):
    """Execute git pull in dotfiles repository."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Display repository path
        repo_path = file_manager.repo_root
        click.echo(f"Repository: {Fore.CYAN}{repo_path}{Style.RESET_ALL}")

        if not dry_run:
            click.echo("Pulling latest changes...")

        # Execute git pull
        result = file_manager.git_pull_repository(dry_run=dry_run)

        if result["success"]:
            click.echo(f"{Fore.GREEN}{result['message']}{Style.RESET_ALL}")
            if result["output"]:
                click.echo(f"{Fore.CYAN}Output:{Style.RESET_ALL}")
                for line in result["output"].strip().split("\n"):
                    if line.strip():
                        click.echo(f"  {line}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            if result["error"]:
                click.echo(f"{Fore.RED}Error:{Style.RESET_ALL}")
                for line in result["error"].strip().split("\n"):
                    if line.strip():
                        click.echo(f"  {line}")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command("git-commit-push")
@click.option("--machine", "-m", help="Override machine name")
@click.option("--dry-run", "-n", is_flag=True, help="Dry run - show what would be done")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def git_commit_push(ctx, machine, dry_run, yes):
    """Commit and push current machine's changes."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Display repository path
        repo_path = file_manager.repo_root
        click.echo(f"Repository: {Fore.CYAN}{repo_path}{Style.RESET_ALL}")

        # Determine machine name
        machine_name = machine or config_manager.get_machine_name()
        click.echo(f"Machine: {Fore.CYAN}{machine_name}{Style.RESET_ALL}")

        if not dry_run and not yes:
            click.echo(
                f"{Fore.YELLOW}Warning: This will commit and push changes to the remote repository.{Style.RESET_ALL}"
            )
            click.echo("This action cannot be easily undone.")
            if not click.confirm("Continue?"):
                return

        if not dry_run:
            click.echo("Committing and pushing changes...")

        # Execute git commit push
        result = file_manager.git_commit_push_repository(machine_name, dry_run=dry_run)

        if result["success"]:
            click.echo(f"{Fore.GREEN}{result['message']}{Style.RESET_ALL}")
            if result["output"]:
                click.echo(f"{Fore.CYAN}Output:{Style.RESET_ALL}")
                for line in result["output"].strip().split("\n"):
                    if line.strip():
                        click.echo(f"  {line}")

            if not dry_run and result.get("commit_message"):
                click.echo(
                    f"\n{Fore.GREEN}Commit message: {result['commit_message']}{Style.RESET_ALL}"
                )
                click.echo(
                    f"{Fore.GREEN}Your changes have been successfully pushed to the remote repository!{Style.RESET_ALL}"
                )
        else:
            # Special handling when pull is required
            if result.get("need_pull", False):
                click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
                click.echo(
                    f"{Fore.YELLOW}Warning: The remote repository has newer changes.{Style.RESET_ALL}"
                )
                click.echo("Please run 'triton pull' first to get the latest changes.")
                if result.get("commits_behind", 0) > 0:
                    click.echo(
                        f"Remote is ahead by {result['commits_behind']} commit(s)."
                    )
            else:
                click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
                if result["output"]:
                    click.echo(f"{Fore.CYAN}Output:{Style.RESET_ALL}")
                    for line in result["output"].strip().split("\n"):
                        if line.strip():
                            click.echo(f"  {line}")
            if result["error"]:
                click.echo(f"{Fore.RED}Error:{Style.RESET_ALL}")
                for line in result["error"].strip().split("\n"):
                    if line.strip():
                        click.echo(f"  {line}")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.option(
    "--skip-startup",
    "-S",
    is_flag=True,
    help="Skip auto git pull and hooks on startup",
)
@click.pass_context
def tui(ctx, skip_startup):
    """Launch TUI browser."""
    try:
        from .tui_textual.app import run_textual_tui

        run_textual_tui(skip_startup=skip_startup)
    except ImportError as e:
        click.echo(f"{Fore.RED}Error: Textual TUI not available: {e}{Style.RESET_ALL}")
        click.echo("Install textual dependencies with: uv sync --extra tui")
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: TUI Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command("cleanup-repository")
@click.option("--machine", "-m", help="Target machine name (must be current machine)")
@click.option(
    "--dry-run", "-n", is_flag=True, help="Dry run - show what would be deleted"
)
@click.pass_context
def cleanup_repository(ctx, machine, dry_run):
    """Remove orphaned files from repository (current machine only).

    This command deletes files that exist in the repository but not
    on the local system. Only executable for the current machine.

    Examples:
      triton cleanup-repository --dry-run  # Check files to be deleted
      triton cleanup-repository             # Actually delete files
    """
    try:
        # Display config file in use
        config_path = Path(ctx.obj["config_path"]).resolve()
        click.echo(f"Using config: {Fore.CYAN}{config_path}{Style.RESET_ALL}")

        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager)

        # Validate configuration
        if not ValidationDisplay.display_validation_results(
            config_manager, show_success_message=False, ask_continue_on_error=True
        ):
            return

        # Get current machine name
        current_machine = config_manager.get_machine_name()
        target_machine = machine or current_machine

        # Safety check: only allow current machine
        if target_machine != current_machine:
            click.echo(
                f"{Fore.RED}Error: Cleanup is only allowed for current machine{Style.RESET_ALL}"
            )
            click.echo(
                f"Current machine: {Fore.CYAN}{current_machine}{Style.RESET_ALL}"
            )
            click.echo(
                f"Requested machine: {Fore.YELLOW}{target_machine}{Style.RESET_ALL}"
            )
            click.echo(
                f"\n{Fore.YELLOW}This safety measure prevents accidental deletion of files{Style.RESET_ALL}"
            )
            click.echo("from other machines that might be temporarily offline.")
            sys.exit(1)

        # Confirmation prompt (not needed for dry-run)
        if not dry_run:
            click.echo(
                f"\n{Fore.YELLOW}Warning: This will delete orphaned files from repository{Style.RESET_ALL}"
            )
            click.echo(f"Machine: {Fore.CYAN}{target_machine}{Style.RESET_ALL}")
            click.echo(
                f"Repository: {Fore.CYAN}{file_manager.repo_root}{Style.RESET_ALL}"
            )
            click.echo(
                f"\n{Fore.RED}Files that exist in repository but not locally will be PERMANENTLY deleted.{Style.RESET_ALL}"
            )

            if not click.confirm("Continue with cleanup?"):
                click.echo("Cleanup cancelled.")
                return

        # Execute cleanup
        results = file_manager.cleanup_repository_files(target_machine, dry_run=dry_run)

        # Display results
        if dry_run:
            click.echo(f"\n{Fore.CYAN}Dry run results:{Style.RESET_ALL}")
            click.echo(f"Would delete: {len(results['would_delete'])} files")

            if results["would_delete"]:
                click.echo(
                    f"\n{Fore.YELLOW}Files that would be deleted:{Style.RESET_ALL}"
                )
                for file_path in results["would_delete"]:
                    click.echo(f"  - {file_path}")

                click.echo(
                    f"\n{Fore.GREEN}Run without --dry-run to actually delete these files{Style.RESET_ALL}"
                )
            else:
                click.echo(f"{Fore.GREEN}No orphaned files found{Style.RESET_ALL}")
        else:
            click.echo(f"\n{Fore.GREEN}Repository cleanup completed!{Style.RESET_ALL}")
            click.echo(f"Files deleted: {len(results['deleted'])}")
            click.echo(f"Errors: {len(results['errors'])}")

            if results["errors"]:
                click.echo(f"\n{Fore.RED}Errors:{Style.RESET_ALL}")
                for error in results["errors"]:
                    click.echo(f"  - {error}")

            if results["deleted"]:
                click.echo(f"\n{Fore.CYAN}Next steps:{Style.RESET_ALL}")
                repo_path = file_manager.repo_root
                click.echo(f"  git -C {repo_path} add .")
                click.echo(
                    f'  git -C {repo_path} commit -m "cleanup({target_machine}): remove orphaned files"'
                )
                click.echo(f"  git -C {repo_path} push")
                click.echo(f"\n{Fore.YELLOW}Or as one-liner:{Style.RESET_ALL}")
                click.echo(
                    f'  (cd {repo_path} && git add . && git commit -m "cleanup({target_machine}): remove orphaned files" && git push)'
                )

    except ValueError as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: Unexpected error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# --- Hooks Commands ---


@cli.group("hooks")
@click.pass_context
def hooks_cmd(ctx):
    """Execute startup hooks.

    Run configured hooks manually. Hooks are commands that execute
    automatically when TUI starts.

    To manage hook configuration (add/remove/list), use:
      triton config hook <command>
    """
    pass


@hooks_cmd.command("run")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be executed")
@click.pass_context
def hooks_run(ctx, dry_run):
    """Manually run startup hooks.

    Executes all configured startup hooks in order.
    Use --dry-run to see what would be executed without running.

    To manage hooks configuration, use 'triton config hook' commands.
    """
    from .managers.hook_manager import HookManager

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        hook_manager = HookManager(config_manager.config.hooks)

        if not hook_manager.has_hooks():
            click.echo(f"{Fore.YELLOW}No startup hooks configured{Style.RESET_ALL}")
            click.echo("Use 'triton config hook add <command>' to add hooks")
            return

        if dry_run:
            click.echo(f"{Fore.CYAN}Dry run - would execute:{Style.RESET_ALL}")

        result = hook_manager.run_startup_hooks(dry_run=dry_run)

        if dry_run:
            for r in result["results"]:
                click.echo(f"  {r['index'] + 1}. {r['command']}")
            click.echo(f"\nTotal timeout: {hook_manager.get_timeout()}s")
        else:
            for r in result["results"]:
                if r.get("skipped"):
                    status = f"{Fore.YELLOW}SKIPPED{Style.RESET_ALL}"
                elif r["success"]:
                    status = f"{Fore.GREEN}✓{Style.RESET_ALL}"
                else:
                    status = f"{Fore.RED}✗{Style.RESET_ALL}"

                click.echo(f"{status} {r['command']}")
                if r.get("error"):
                    click.echo(f"   Error: {r['error']}")
                if r.get("duration_ms"):
                    click.echo(f"   Duration: {r['duration_ms']:.0f}ms")

            click.echo(f"\n{result['summary']}")

    except FileNotFoundError:
        click.echo(f"{Fore.RED}Error: Config file not found{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@hooks_cmd.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def hooks_list(ctx, as_json):
    """List configured startup hooks.

    Shortcut for 'triton config hook list'.
    """
    import json as json_module

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        hooks = config_manager.config.hooks

        if as_json:
            output = {
                "on_startup": hooks.on_startup,
                "timeout": hooks.timeout,
                "count": len(hooks.on_startup),
            }
            click.echo(json_module.dumps(output, indent=2))
        else:
            if not hooks.on_startup:
                click.echo(f"{Fore.YELLOW}No startup hooks configured{Style.RESET_ALL}")
                click.echo("Use 'triton config hook add <command>' to add hooks")
                return

            click.echo(f"{Fore.CYAN}Startup Hooks:{Style.RESET_ALL}")
            for i, cmd in enumerate(hooks.on_startup):
                click.echo(f"  {i + 1}. {cmd}")
            click.echo(f"\nTimeout: {hooks.timeout}s (total)")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# --- Config Management Commands ---


@cli.group("config", invoke_without_command=True)
@click.option(
    "--schema",
    "show_schema",
    is_flag=True,
    help="Output command schema as JSON for LLM agents",
)
@click.pass_context
def config_cmd(ctx, show_schema):
    """Configuration management commands."""
    if show_schema:
        import json
        from .schema import get_config_schema

        click.echo(json.dumps(get_config_schema(), indent=2))
        ctx.exit(0)


@config_cmd.command("view")
@click.pass_context
def config_view(ctx):
    """Display raw configuration file content."""
    try:
        config_path = Path(ctx.obj["config_path"])

        if not config_path.exists():
            click.echo(
                f"{Fore.RED}Error: Config file not found: {config_path}{Style.RESET_ALL}"
            )
            sys.exit(1)

        content = config_path.read_text(encoding="utf-8")
        click.echo(content)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_cmd.command("validate")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
@click.pass_context
def config_validate(ctx, verbose):
    """Validate configuration file and target paths."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])

        click.echo(f"{Fore.CYAN}Validating configuration...{Style.RESET_ALL}\n")

        issues = _collect_validation_issues(config_manager)

        # Display issues grouped by type
        if issues["errors"]:
            click.echo(f"{Fore.RED}Errors:{Style.RESET_ALL}")
            for error in issues["errors"]:
                click.echo(f"  {Fore.RED}✗{Style.RESET_ALL} {error}")

        if issues["warnings"]:
            click.echo(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for warning in issues["warnings"]:
                click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {warning}")

        if issues["missing_targets"]:
            click.echo(f"\n{Fore.YELLOW}Missing targets:{Style.RESET_ALL}")
            for idx, path in issues["missing_targets"]:
                click.echo(
                    f"  {Fore.YELLOW}!{Style.RESET_ALL} "
                    f"{Fore.GREEN}[{idx}]{Style.RESET_ALL} {path}"
                )

        if issues["missing_files"]:
            click.echo(f"\n{Fore.YELLOW}Missing files:{Style.RESET_ALL}")
            for idx, path in issues["missing_files"]:
                click.echo(
                    f"  {Fore.YELLOW}!{Style.RESET_ALL} "
                    f"{Fore.GREEN}[{idx}]{Style.RESET_ALL} {path}"
                )

        # Summary
        total_issues = (
            len(issues["errors"])
            + len(issues["warnings"])
            + len(issues["missing_targets"])
            + len(issues["missing_files"])
        )

        if total_issues == 0:
            click.echo(f"{Fore.GREEN}✓ Configuration is valid{Style.RESET_ALL}")
        else:
            warning_count = (
                len(issues["warnings"])
                + len(issues["missing_targets"])
                + len(issues["missing_files"])
            )
            click.echo(
                f"\n{Fore.CYAN}Summary:{Style.RESET_ALL} "
                f"{len(issues['errors'])} errors, {warning_count} warnings"
            )

        # Verbose: show all targets
        if verbose:
            click.echo(
                f"\n{Fore.CYAN}Targets ({len(config_manager.config.targets)}):{Style.RESET_ALL}"
            )
            for i, target in enumerate(config_manager.config.targets):
                mode = "recursive" if target.recursive else "files"
                click.echo(f"  [{i}] {target.path} ({mode})")

    except Exception as e:
        click.echo(f"{Fore.RED}✗ Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


def _collect_validation_issues(config_manager: ConfigManager) -> dict:
    """Collect all validation issues."""
    issues = {
        "errors": [],
        "warnings": [],
        "missing_targets": [],  # (index, path) tuples
        "missing_files": [],  # (index, path) tuples
    }

    # Check for undefined environment variables
    for var in config_manager.missing_env_vars:
        issues["warnings"].append(f"Environment variable '{var}' is not defined")

    # Check actual errors
    for error in config_manager.get_validation_errors():
        issues["errors"].append(error)

    # Check paths
    for i, target in enumerate(config_manager.config.targets):
        try:
            expanded_path = config_manager.expand_path(target.path)
        except Exception:
            continue

        if "${" in str(expanded_path):
            # Path contains unresolved env var
            continue

        if not expanded_path.exists():
            issues["missing_targets"].append((i, target.path))
        elif target.files and not target.recursive:
            # Check specific files (non-glob patterns only)
            for file_pattern in target.files:
                if file_pattern.startswith("!"):
                    continue
                if "*" in file_pattern or "**" in file_pattern:
                    continue
                file_path = expanded_path / file_pattern
                if not file_path.exists():
                    # Construct display path without double slashes
                    base_path = target.path.rstrip("/")
                    issues["missing_files"].append((i, f"{base_path}/{file_pattern}"))

    return issues


# --- Config Hook Management ---


@config_cmd.group(
    "hook",
    epilog="See also: triton config schema - Machine-readable command schema for LLM agents",
)
def config_hook():
    """Startup hook management commands.

    Manage hooks that run automatically when TUI starts.
    """
    pass


@config_hook.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def hook_list(ctx, as_json):
    """List configured startup hooks."""
    import json as json_module

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        hooks = config_manager.config.hooks

        if as_json:
            output = {
                "on_startup": hooks.on_startup,
                "timeout": hooks.timeout,
                "count": len(hooks.on_startup),
            }
            click.echo(json_module.dumps(output, indent=2))
        else:
            if not hooks.on_startup:
                click.echo(f"{Fore.YELLOW}No startup hooks configured{Style.RESET_ALL}")
                return

            click.echo(f"{Fore.CYAN}Startup Hooks:{Style.RESET_ALL}")
            for i, cmd in enumerate(hooks.on_startup):
                click.echo(f"  {i + 1}. {cmd}")
            click.echo(f"\nTimeout: {hooks.timeout}s (total)")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_hook.command("add")
@click.argument("command")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def hook_add(ctx, command, no_backup):
    """Add a startup hook command.

    COMMAND is the shell command to run on TUI startup.
    Commands are executed in order with a shared timeout.

    Examples:
        triton config hook add "brew bundle dump --file=~/.config/triton/Brewfile"
        triton config hook add "echo Hello"
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.add_startup_hook(command, backup=not no_backup)

        if result["success"]:
            # Idempotent: show different message based on whether change was made
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_hook.command("remove")
@click.argument("command")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def hook_remove(ctx, command, no_backup):
    """Remove a startup hook command.

    COMMAND must match exactly the hook to remove.
    Use 'triton config hook list' to see current hooks.
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.remove_startup_hook(command, backup=not no_backup)

        if result["success"]:
            # Idempotent: show different message based on whether change was made
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_hook.command("timeout")
@click.argument("seconds", type=int)
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def hook_timeout(ctx, seconds, no_backup):
    """Set the total timeout for all hooks.

    SECONDS is the total time allowed for all hooks to complete.
    If time runs out, remaining hooks are skipped.

    Default: 30 seconds
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.set_hooks_timeout(seconds, backup=not no_backup)

        if result["success"]:
            click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
            if result.get("backup_path"):
                click.echo(f"  Config backup: {result['backup_path']}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# --- Config Exclude (Global Blacklist) Management ---


@config_cmd.group(
    "exclude",
    epilog="See also: triton config schema - Machine-readable command schema for LLM agents",
)
def config_exclude():
    """Global exclude pattern management.

    Manage patterns for files to exclude from backup (global blacklist).
    These patterns apply to all targets.
    """
    pass


@config_exclude.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def exclude_list(ctx, as_json):
    """List global exclude patterns."""
    import json as json_module

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        patterns = config_manager.config.blacklist

        if as_json:
            click.echo(json_module.dumps(patterns, indent=2))
        else:
            if not patterns:
                click.echo(
                    f"{Fore.YELLOW}No exclude patterns configured{Style.RESET_ALL}"
                )
                return

            click.echo(f"{Fore.CYAN}Global Exclude Patterns:{Style.RESET_ALL}")
            for pattern in patterns:
                click.echo(f"  - {pattern}")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_exclude.command("add")
@click.argument("pattern")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def exclude_add(ctx, pattern, no_backup):
    """Add a global exclude pattern.

    PATTERN is a glob pattern for files to exclude from backup.
    Patterns apply to all targets.

    Examples:
        triton config exclude add "*.log"
        triton config exclude add ".DS_Store"
        triton config exclude add "*.tmp"
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.add_exclude_pattern(pattern, backup=not no_backup)

        if result["success"]:
            # Show warnings if any
            for warning in result.get("warnings", []):
                click.echo(f"{Fore.YELLOW}! {warning}{Style.RESET_ALL}")

            # Idempotent: show different message based on whether change was made
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_exclude.command("remove")
@click.argument("pattern")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def exclude_remove(ctx, pattern, no_backup):
    """Remove a global exclude pattern.

    PATTERN must match exactly the pattern to remove.
    Use 'triton config exclude list' to see current patterns.
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.remove_exclude_pattern(pattern, backup=not no_backup)

        if result["success"]:
            # Idempotent: show different message based on whether change was made
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# --- Config Encrypt (Global Encryption Patterns) Management ---


@config_cmd.group(
    "encrypt",
    epilog="See also: triton config schema - Machine-readable command schema for LLM agents",
)
def config_encrypt():
    """Global encryption pattern management.

    Manage patterns for files to encrypt during backup.
    These patterns apply to all targets (target-specific patterns take precedence).
    """
    pass


@config_encrypt.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def encrypt_list(ctx, as_json):
    """List global encryption patterns."""
    import json as json_module

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        patterns = config_manager.config.encrypt_list

        if as_json:
            click.echo(json_module.dumps(patterns, indent=2))
        else:
            if not patterns:
                click.echo(
                    f"{Fore.YELLOW}No encryption patterns configured{Style.RESET_ALL}"
                )
                return

            click.echo(f"{Fore.CYAN}Global Encryption Patterns:{Style.RESET_ALL}")
            for pattern in patterns:
                click.echo(f"  - {pattern}")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_encrypt.command("add")
@click.argument("pattern")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def encrypt_add(ctx, pattern, no_backup):
    """Add a global encryption pattern.

    PATTERN is a glob pattern for files to encrypt during backup.
    Matching files will be stored with .enc extension.

    Examples:
        triton config encrypt add "id_rsa*"
        triton config encrypt add "*.pem"
        triton config encrypt add "*secret*"
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.add_encrypt_pattern(pattern, backup=not no_backup)

        if result["success"]:
            # Show warnings if any
            for warning in result.get("warnings", []):
                click.echo(f"{Fore.YELLOW}! {warning}{Style.RESET_ALL}")

            # Idempotent: show different message based on whether change was made
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_encrypt.command("remove")
@click.argument("pattern")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def encrypt_remove(ctx, pattern, no_backup):
    """Remove a global encryption pattern.

    PATTERN must match exactly the pattern to remove.
    Use 'triton config encrypt list' to see current patterns.
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.remove_encrypt_pattern(pattern, backup=not no_backup)

        if result["success"]:
            # Idempotent: show different message based on whether change was made
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# --- Config Settings (Scalar Values) Management ---


@config_cmd.group(
    "settings",
    epilog="See also: triton config schema - Machine-readable command schema for LLM agents",
)
def config_settings():
    """Scalar settings management.

    Manage individual configuration values (non-array settings).
    Use 'triton config settings list' to see all available keys.
    """
    pass


@config_settings.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def settings_list(ctx, as_json):
    """List all available settings with current values."""
    import json as json_module

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.list_settings()

        if as_json:
            click.echo(json_module.dumps(result["settings"], indent=2))
        else:
            click.echo(f"{Fore.CYAN}Available Settings:{Style.RESET_ALL}\n")
            for setting in result["settings"]:
                key = setting["key"]
                value = setting["value"]
                is_default = setting["is_default"]
                setting_type = setting["type"]
                required = setting["required"]

                # Format value display
                if value is None:
                    value_str = f"{Fore.YELLOW}null{Style.RESET_ALL}"
                elif isinstance(value, bool):
                    value_str = f"{Fore.GREEN}{str(value).lower()}{Style.RESET_ALL}"
                else:
                    value_str = str(value)

                # Build status indicator
                status = ""
                if required:
                    status = f" {Fore.RED}(required){Style.RESET_ALL}"
                elif is_default:
                    status = f" {Fore.BLUE}(default){Style.RESET_ALL}"

                # Show choices for enum types
                choices_str = ""
                if setting.get("choices"):
                    choices_str = f" [{', '.join(setting['choices'])}]"

                click.echo(
                    f"  {Fore.WHITE}{key}{Style.RESET_ALL} = {value_str}{status}"
                )
                click.echo(f"    Type: {setting_type}{choices_str}")
                click.echo(f"    {setting['description']}")
                click.echo()

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_settings.command("get")
@click.argument("key")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def settings_get(ctx, key, as_json):
    """Get a setting value.

    KEY is the setting key (e.g., 'max_file_size_mb', 'repository.auto_pull').
    Use 'triton config settings list' to see available keys.
    """
    import json as json_module

    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.get_setting(key)

        if not result["success"]:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            if result.get("available_keys"):
                click.echo(f"\nAvailable keys: {', '.join(result['available_keys'])}")
            sys.exit(1)

        if as_json:
            click.echo(json_module.dumps(result, indent=2))
        else:
            value = result["value"]
            if value is None:
                value_str = "null"
            elif isinstance(value, bool):
                value_str = str(value).lower()
            else:
                value_str = str(value)

            click.echo(f"{result['key']} = {value_str}")
            click.echo(f"  Type: {result['type']}")
            click.echo(f"  Default: {result['default']}")
            if result.get("choices"):
                click.echo(f"  Choices: {', '.join(result['choices'])}")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_settings.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def settings_set(ctx, key, value, no_backup):
    """Set a setting value.

    KEY is the setting key.
    VALUE is the value to set (parsed based on type).

    Boolean values: true/false, on/off, yes/no, 1/0
    Enum values: must be one of the allowed choices

    Examples:
        triton config settings set max_file_size_mb 10
        triton config settings set repository.auto_pull false
        triton config settings set tui.theme nord
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.set_setting(key, value, backup=not no_backup)

        if result["success"]:
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            if result.get("available_keys"):
                click.echo(f"\nAvailable keys: {', '.join(result['available_keys'])}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_settings.command("unset")
@click.argument("key")
@click.option("--no-backup", is_flag=True, help="Skip config backup before modifying")
@click.pass_context
def settings_unset(ctx, key, no_backup):
    """Unset a setting (reset to default).

    KEY is the setting key to unset.
    The setting will be removed from config.yml and use its default value.

    Note: Required settings cannot be unset.

    Examples:
        triton config settings unset tui.theme
        triton config settings unset max_file_size_mb
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.unset_setting(key, backup=not no_backup)

        if result["success"]:
            if result.get("changed", True):
                click.echo(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                if result.get("backup_path"):
                    click.echo(f"  Config backup: {result['backup_path']}")
            else:
                click.echo(f"{Fore.YELLOW}✓ {result['message']}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            if result.get("available_keys"):
                click.echo(f"\nAvailable keys: {', '.join(result['available_keys'])}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# --- Config Target Management ---


@config_cmd.group(
    "target",
    epilog="See also: triton config schema - Machine-readable command schema for LLM agents",
)
def config_target():
    """Target management commands."""
    pass


@config_target.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--resolve", is_flag=True, help="Resolve and show actual files for each target"
)
@click.pass_context
def target_list(ctx, as_json, resolve):
    """List all configured targets."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        file_manager = FileManager(config_manager) if resolve else None

        if as_json:
            import json

            targets = []
            for i, target in enumerate(config_manager.config.targets):
                target_data = {
                    "index": i,
                    "path": target.path,
                    "files": target.files,
                    "recursive": target.recursive,
                    "encrypt_files": target.encrypt_files,
                }
                if resolve:
                    resolved = _resolve_target_files(
                        file_manager, config_manager, target, i
                    )
                    target_data["resolved_files"] = resolved
                targets.append(target_data)
            click.echo(json.dumps(targets, indent=2))
        else:
            click.echo(f"{Fore.CYAN}Configured targets:{Style.RESET_ALL}\n")
            for i, target in enumerate(config_manager.config.targets):
                mode = "recursive" if target.recursive else "files"

                click.echo(f"  {Fore.GREEN}[{i}]{Style.RESET_ALL} {target.path}")
                click.echo(f"      Mode: {mode}")
                if target.files:
                    click.echo(f"      Pattern: {target.files}")
                if target.encrypt_files:
                    click.echo(f"      Encrypt: {target.encrypt_files}")

                if resolve:
                    resolved = _resolve_target_files(
                        file_manager, config_manager, target, i
                    )
                    _display_resolved_files(resolved, config_manager)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


def _resolve_target_files(
    file_manager: FileManager, config_manager: ConfigManager, target, index: int
) -> dict:
    """Resolve actual files for a target."""
    from triton_dotfiles.config import expand_env_vars

    result = {
        "found": [],
        "not_found": [],
        "skipped_env": False,
        "error": None,
    }

    try:
        # Check for undefined environment variables
        expanded_path = expand_env_vars(target.path)
        if "${" in expanded_path:
            result["skipped_env"] = True
            result["error"] = f"Undefined environment variable in path: {target.path}"
            return result

        target_path = Path(expanded_path).expanduser()

        if not target_path.exists():
            result["error"] = f"Path does not exist: {target_path}"
            return result

        # Collect files using file_manager
        for file_path, relative_path in file_manager.collect_target_files(target):
            is_encrypted = config_manager.should_encrypt_file(
                file_path, target, Path(relative_path)
            )
            result["found"].append(
                {
                    "path": str(file_path),
                    "encrypted": is_encrypted,
                }
            )

        # Check for not found files (non-recursive mode with specific files)
        if not target.recursive and target.files:
            for pattern in target.files:
                if pattern.startswith("!"):
                    continue
                if "*" not in pattern and "**" not in pattern:
                    file_path = target_path / pattern
                    if not file_path.exists():
                        result["not_found"].append(str(file_path))

    except Exception as e:
        result["error"] = str(e)

    return result


def _display_resolved_files(resolved: dict, config_manager: ConfigManager):
    """Display resolved files for a target."""
    if resolved.get("skipped_env"):
        click.echo(
            f"      {Fore.YELLOW}! Skipped: {resolved['error']}{Style.RESET_ALL}"
        )
        return

    if resolved.get("error") and not resolved["found"]:
        click.echo(f"      {Fore.YELLOW}! {resolved['error']}{Style.RESET_ALL}")
        return

    found = resolved.get("found", [])
    not_found = resolved.get("not_found", [])

    if found:
        click.echo(f"      {Fore.CYAN}Resolved ({len(found)} files):{Style.RESET_ALL}")
        for f in found[:10]:  # Show first 10 files
            path = f["path"]
            # Shorten home directory
            display_path = path.replace(str(Path.home()), "~")
            if f.get("encrypted"):
                click.echo(
                    f"        {Fore.GREEN}✓{Style.RESET_ALL} {display_path} "
                    f"{Fore.MAGENTA}(encrypted){Style.RESET_ALL}"
                )
            else:
                click.echo(f"        {Fore.GREEN}✓{Style.RESET_ALL} {display_path}")
        if len(found) > 10:
            click.echo(
                f"        {Fore.CYAN}... and {len(found) - 10} more{Style.RESET_ALL}"
            )
    else:
        click.echo(f"      {Fore.YELLOW}No files found{Style.RESET_ALL}")

    for path in not_found:
        display_path = path.replace(str(Path.home()), "~")
        click.echo(
            f"        {Fore.RED}✗{Style.RESET_ALL} {display_path} "
            f"{Fore.RED}(not found){Style.RESET_ALL}"
        )


@config_target.command("add")
@click.argument("path")
@click.option("--files", "-f", help="Comma-separated list of file patterns")
@click.option("--recursive", "-r", is_flag=True, help="Backup directory recursively")
@click.option("--encrypt-files", "-e", help="Comma-separated list of files to encrypt")
@click.option("--no-backup", is_flag=True, help="Don't backup config before modifying")
@click.pass_context
def target_add(ctx, path, files, recursive, encrypt_files, no_backup):
    """Add a new target to the configuration."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])

        # Parse comma-separated lists
        files_list = [f.strip() for f in files.split(",")] if files else None
        encrypt_list = (
            [f.strip() for f in encrypt_files.split(",")] if encrypt_files else None
        )

        result = config_manager.add_target(
            path=path,
            files=files_list,
            recursive=recursive,
            encrypt_files=encrypt_list,
            backup=not no_backup,
        )

        if result["success"]:
            click.echo(f"{Fore.GREEN}{result['message']}{Style.RESET_ALL}")
            if result.get("backup_path"):
                click.echo(f"   Config backed up to: {result['backup_path']}")

            # Show added target details
            target = result["target"]
            click.echo(f"\n   Path: {target.path}")
            click.echo(f"   Recursive: {target.recursive}")
            if target.files:
                click.echo(f"   Files: {target.files}")
            if target.encrypt_files:
                click.echo(f"   Encrypt files: {target.encrypt_files}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_target.command("remove")
@click.argument("path")
@click.option("--no-backup", is_flag=True, help="Don't backup config before modifying")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def target_remove(ctx, path, no_backup, yes):
    """Remove a target from the configuration."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        normalized = config_manager.normalize_path(path)

        # Check if target exists
        target = config_manager.find_target_by_path(normalized)
        if not target:
            click.echo(
                f"{Fore.RED}Error: Target {normalized} not found{Style.RESET_ALL}"
            )
            sys.exit(1)

        # Confirm removal
        if not yes:
            click.echo(f"Target to remove: {normalized}")
            if target.recursive:
                click.echo("  Mode: recursive")
            if target.files:
                click.echo(f"  Files: {target.files}")
            if not click.confirm("Remove this target?"):
                click.echo("Cancelled.")
                return

        result = config_manager.remove_target(path, backup=not no_backup)

        if result["success"]:
            click.echo(f"{Fore.GREEN}{result['message']}{Style.RESET_ALL}")
            if result.get("backup_path"):
                click.echo(f"   Config backed up to: {result['backup_path']}")
        else:
            click.echo(f"{Fore.RED}Error:{result['message']}{Style.RESET_ALL}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_target.command("check")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def target_check(ctx, path, as_json):
    """Check a path before adding as target."""
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])
        result = config_manager.check_target_path(path)

        if as_json:
            import json

            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"{Fore.CYAN}Path check results:{Style.RESET_ALL}\n")
            click.echo(f"  Normalized path: {result['path']}")
            click.echo(f"  Expanded path:   {result['expanded_path']}")
            click.echo(f"  Exists: {result['exists']}")

            if result["exists"]:
                if result["is_directory"]:
                    click.echo("  Type: Directory")
                    if "file_count" in result:
                        click.echo(f"  Files: {result['file_count']}")
                elif result["is_file"]:
                    click.echo("  Type: File")

            if result["conflicts"]:
                click.echo(f"\n{Fore.RED}Conflicts:{Style.RESET_ALL}")
                for conflict in result["conflicts"]:
                    click.echo(f"  {Fore.RED}✗{Style.RESET_ALL} {conflict}")

            if result["warnings"]:
                click.echo(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
                for warning in result["warnings"]:
                    click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} {warning}")

            if result["suggestions"] and not result["conflicts"]:
                click.echo(f"\n{Fore.GREEN}Suggested commands:{Style.RESET_ALL}")
                for suggestion in result["suggestions"]:
                    click.echo(f"  $ {suggestion}")

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@config_target.command("modify")
@click.argument("path")
@click.option("--add-files", help="Comma-separated list of file patterns to add")
@click.option("--remove-files", help="Comma-separated list of file patterns to remove")
@click.option(
    "--add-encrypt-files", help="Comma-separated list of encrypt patterns to add"
)
@click.option(
    "--remove-encrypt-files", help="Comma-separated list of encrypt patterns to remove"
)
@click.option("--recursive", is_flag=True, default=None, help="Enable recursive mode")
@click.option(
    "--no-recursive", is_flag=True, default=None, help="Disable recursive mode"
)
@click.option("--no-backup", is_flag=True, help="Don't backup config before modifying")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def target_modify(
    ctx,
    path,
    add_files,
    remove_files,
    add_encrypt_files,
    remove_encrypt_files,
    recursive,
    no_recursive,
    no_backup,
    as_json,
):
    """Modify an existing target's configuration.

    Examples:
        triton config target modify ~/ --add-files '.gitconfig,.bashrc'
        triton config target modify ~/.ssh --add-encrypt-files 'id_*'
        triton config target modify ~/.docker --recursive
        triton config target modify ~/project --no-recursive --add-files '*.md'
    """
    try:
        config_manager = ConfigManager(ctx.obj["config_path"])

        # Parse comma-separated lists
        add_files_list = (
            [f.strip() for f in add_files.split(",")] if add_files else None
        )
        remove_files_list = (
            [f.strip() for f in remove_files.split(",")] if remove_files else None
        )
        add_encrypt_list = (
            [f.strip() for f in add_encrypt_files.split(",")]
            if add_encrypt_files
            else None
        )
        remove_encrypt_list = (
            [f.strip() for f in remove_encrypt_files.split(",")]
            if remove_encrypt_files
            else None
        )

        # Handle recursive flag
        # recursive=True means --recursive was passed
        # no_recursive=True means --no-recursive was passed
        # Both False means no change
        recursive_value = None
        if recursive and no_recursive:
            click.echo(
                f"{Fore.RED}Error: Cannot specify both --recursive and --no-recursive{Style.RESET_ALL}"
            )
            sys.exit(1)
        elif recursive:
            recursive_value = True
        elif no_recursive:
            recursive_value = False

        result = config_manager.modify_target(
            path=path,
            add_files=add_files_list,
            remove_files=remove_files_list,
            add_encrypt_files=add_encrypt_list,
            remove_encrypt_files=remove_encrypt_list,
            recursive=recursive_value,
            backup=not no_backup,
        )

        if as_json:
            import json

            output = {
                "success": result["success"],
                "message": result["message"],
                "changed": result.get("changed", False),
            }
            if result.get("changes"):
                output["changes"] = result["changes"]
            if result.get("target"):
                target = result["target"]
                output["target"] = {
                    "path": target.path,
                    "files": target.files,
                    "recursive": target.recursive,
                    "encrypt_files": target.encrypt_files,
                }
            if result.get("backup_path"):
                output["backup_path"] = str(result["backup_path"])
            click.echo(json.dumps(output, indent=2))
            if not result["success"]:
                sys.exit(1)
        else:
            if result["success"]:
                if result.get("changed"):
                    click.echo(f"{Fore.GREEN}{result['message']}{Style.RESET_ALL}")
                    if result.get("backup_path"):
                        click.echo(f"   Config backed up to: {result['backup_path']}")

                    # Show updated target details
                    target = result["target"]
                    click.echo(f"\n   Path: {target.path}")
                    click.echo(f"   Recursive: {target.recursive}")
                    if target.files:
                        click.echo(f"   Files: {target.files}")
                    if target.encrypt_files:
                        click.echo(f"   Encrypt files: {target.encrypt_files}")
                else:
                    click.echo(f"{Fore.YELLOW}{result['message']}{Style.RESET_ALL}")
            else:
                click.echo(f"{Fore.RED}Error: {result['message']}{Style.RESET_ALL}")
                sys.exit(1)

    except Exception as e:
        click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


# =============================================================================
# Archive Commands
# =============================================================================


@cli.group("archive", invoke_without_command=True)
@click.option(
    "--schema",
    "show_schema",
    is_flag=True,
    help="Output command schema as JSON for LLM agents",
)
@click.pass_context
def archive_cmd(ctx, show_schema):
    """Archive management commands."""
    if show_schema:
        import json
        from .schema import get_archive_schema

        click.echo(json.dumps(get_archive_schema(), indent=2))
        ctx.exit(0)


def _get_archive_info(archive_path: Path) -> dict:
    """Get information about an archive directory."""
    from datetime import datetime

    # Determine archive type based on path structure
    # archives/config/{timestamp}/ -> config
    # archives/{timestamp}/ -> restore
    timestamp_str = archive_path.name
    if archive_path.parent.name == "config":
        archive_type = "config"
    else:
        archive_type = "restore"

    # Parse timestamp
    try:
        created = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
    except ValueError:
        created = None

    # Count files
    files = list(archive_path.rglob("*"))
    file_count = sum(1 for f in files if f.is_file())
    total_size = sum(f.stat().st_size for f in files if f.is_file())

    return {
        "path": archive_path,
        "type": archive_type,
        "timestamp": timestamp_str,
        "created": created,
        "file_count": file_count,
        "total_size": total_size,
    }


def _get_all_archives(archives_root: Path) -> list[dict]:
    """Get all archives sorted by creation time (newest first)."""
    from datetime import datetime

    archives = []

    if not archives_root.exists():
        return archives

    # Find restore archives (direct timestamp directories)
    for entry in archives_root.iterdir():
        if entry.is_dir() and entry.name != "config":
            # Check if it looks like a timestamp directory
            if len(entry.name) == 15 and "_" in entry.name:
                archives.append(_get_archive_info(entry))

    # Find config archives
    config_dir = archives_root / "config"
    if config_dir.exists():
        for entry in config_dir.iterdir():
            if entry.is_dir():
                archives.append(_get_archive_info(entry))

    # Sort by creation time (newest first)
    archives.sort(key=lambda x: x["created"] or datetime.min, reverse=True)
    return archives


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


@archive_cmd.command("list")
@click.option(
    "--type",
    "archive_type",
    type=click.Choice(["config", "restore", "all"]),
    default="all",
    help="Filter by archive type",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def archive_list(archive_type, as_json):
    """List all archives."""
    from .utils import get_triton_dir

    archives_root = get_triton_dir() / "archives"
    archives = _get_all_archives(archives_root)

    # Filter by type
    if archive_type != "all":
        archives = [a for a in archives if a["type"] == archive_type]

    if as_json:
        import json

        output = []
        for archive in archives:
            output.append(
                {
                    "path": str(archive["path"]),
                    "type": archive["type"],
                    "timestamp": archive["timestamp"],
                    "created": archive["created"].isoformat()
                    if archive["created"]
                    else None,
                    "file_count": archive["file_count"],
                    "total_size": archive["total_size"],
                }
            )
        click.echo(json.dumps(output, indent=2))
    else:
        if not archives:
            click.echo(f"{Fore.YELLOW}No archives found.{Style.RESET_ALL}")
            return

        click.echo(f"{Fore.CYAN}Archives:{Style.RESET_ALL}")
        click.echo()

        for archive in archives:
            type_color = Fore.BLUE if archive["type"] == "config" else Fore.GREEN
            type_label = f"[{archive['type']}]"
            date_str = (
                archive["created"].strftime("%Y-%m-%d %H:%M:%S")
                if archive["created"]
                else "Unknown"
            )
            size_str = _format_size(archive["total_size"])

            click.echo(
                f"  {type_color}{type_label:10}{Style.RESET_ALL} "
                f"{date_str}  {archive['timestamp']}  "
                f"({archive['file_count']} files, {size_str})"
            )


@archive_cmd.command("show")
@click.argument("timestamp")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def archive_show(timestamp, as_json):
    """Show contents of a specific archive."""
    from .utils import get_triton_dir

    archives_root = get_triton_dir() / "archives"

    # Find the archive (could be in archives/ or archives/config/)
    archive_path = None
    archive_type = None

    # Check config archives first
    config_path = archives_root / "config" / timestamp
    if config_path.exists():
        archive_path = config_path
        archive_type = "config"
    else:
        # Check restore archives
        restore_path = archives_root / timestamp
        if restore_path.exists():
            archive_path = restore_path
            archive_type = "restore"

    if not archive_path:
        click.echo(f"{Fore.RED}Error: Archive not found: {timestamp}{Style.RESET_ALL}")
        click.echo("Use 'triton archive list' to see available archives.")
        sys.exit(1)

    # Get archive info
    info = _get_archive_info(archive_path)

    # List files
    files = []
    for f in sorted(archive_path.rglob("*")):
        if f.is_file():
            rel_path = f.relative_to(archive_path)
            files.append(
                {
                    "path": str(rel_path),
                    "size": f.stat().st_size,
                }
            )

    if as_json:
        import json

        output = {
            "path": str(archive_path),
            "type": archive_type,
            "timestamp": timestamp,
            "created": info["created"].isoformat() if info["created"] else None,
            "file_count": info["file_count"],
            "total_size": info["total_size"],
            "files": files,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        date_str = (
            info["created"].strftime("%Y-%m-%d %H:%M:%S")
            if info["created"]
            else "Unknown"
        )
        type_color = Fore.BLUE if archive_type == "config" else Fore.GREEN

        click.echo(f"{Fore.CYAN}Archive: {timestamp}{Style.RESET_ALL}")
        click.echo(f"  Type: {type_color}{archive_type}{Style.RESET_ALL}")
        click.echo(f"  Created: {date_str}")
        click.echo(f"  Location: {archive_path}")
        click.echo(f"  Total size: {_format_size(info['total_size'])}")
        click.echo()
        click.echo(f"{Fore.GREEN}Files ({info['file_count']}):{Style.RESET_ALL}")

        for file_info in files:
            size_str = _format_size(file_info["size"])
            click.echo(f"  {file_info['path']} ({size_str})")


@archive_cmd.command("clean")
@click.option("--keep", type=int, default=None, help="Keep the most recent N archives")
@click.option(
    "--older-than",
    "older_than_days",
    type=int,
    default=None,
    help="Delete archives older than N days",
)
@click.option(
    "--type",
    "archive_type",
    type=click.Choice(["config", "restore", "all"]),
    default="all",
    help="Filter by archive type",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deleted without actually deleting",
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def archive_clean(keep, older_than_days, archive_type, dry_run, force):
    """Clean up old archives."""
    import shutil
    from datetime import datetime, timedelta

    from .utils import get_triton_dir

    if keep is None and older_than_days is None:
        click.echo(
            f"{Fore.RED}Error: Please specify --keep or --older-than{Style.RESET_ALL}"
        )
        click.echo("Examples:")
        click.echo("  triton archive clean --keep 5          # Keep 5 most recent")
        click.echo(
            "  triton archive clean --older-than 30   # Delete older than 30 days"
        )
        sys.exit(1)

    archives_root = get_triton_dir() / "archives"
    archives = _get_all_archives(archives_root)

    # Filter by type
    if archive_type != "all":
        archives = [a for a in archives if a["type"] == archive_type]

    if not archives:
        click.echo(f"{Fore.YELLOW}No archives found.{Style.RESET_ALL}")
        return

    # Determine which archives to delete
    to_delete = []

    if keep is not None:
        # Keep the most recent N, delete the rest
        if archive_type == "all":
            # Keep N of each type
            config_archives = [a for a in archives if a["type"] == "config"]
            restore_archives = [a for a in archives if a["type"] == "restore"]
            to_delete.extend(config_archives[keep:])
            to_delete.extend(restore_archives[keep:])
        else:
            to_delete = archives[keep:]

    if older_than_days is not None:
        cutoff = datetime.now() - timedelta(days=older_than_days)
        for archive in archives:
            if archive["created"] and archive["created"] < cutoff:
                if archive not in to_delete:
                    to_delete.append(archive)

    if not to_delete:
        click.echo(f"{Fore.GREEN}✓ No archives to clean up.{Style.RESET_ALL}")
        return

    # Calculate total size
    total_size = sum(a["total_size"] for a in to_delete)

    # Show what will be deleted
    click.echo(f"{Fore.CYAN}Archives to delete ({len(to_delete)}):{Style.RESET_ALL}")
    for archive in to_delete:
        type_color = Fore.BLUE if archive["type"] == "config" else Fore.GREEN
        date_str = (
            archive["created"].strftime("%Y-%m-%d %H:%M:%S")
            if archive["created"]
            else "Unknown"
        )
        click.echo(
            f"  {type_color}[{archive['type']}]{Style.RESET_ALL} "
            f"{date_str}  {archive['timestamp']}"
        )

    click.echo()
    click.echo(
        f"Total space to free: {Fore.YELLOW}{_format_size(total_size)}{Style.RESET_ALL}"
    )

    if dry_run:
        click.echo(f"\n{Fore.YELLOW}Dry run - no files were deleted.{Style.RESET_ALL}")
        return

    # Confirm deletion
    if not force:
        click.confirm(f"\nDelete {len(to_delete)} archives?", abort=True)

    # Delete archives
    deleted_count = 0
    for archive in to_delete:
        try:
            shutil.rmtree(archive["path"])
            deleted_count += 1
        except Exception as e:
            click.echo(
                f"{Fore.RED}Error: Failed to delete {archive['timestamp']}: {e}{Style.RESET_ALL}"
            )

    click.echo(
        f"\n{Fore.GREEN}✓ Deleted {deleted_count} archives, freed {_format_size(total_size)}{Style.RESET_ALL}"
    )


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        click.echo(
            f"\n{Fore.YELLOW}Warning: Operation cancelled by user{Style.RESET_ALL}"
        )
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: Unexpected error: {e}{Style.RESET_ALL}")
        sys.exit(1)
