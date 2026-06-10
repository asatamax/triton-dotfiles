#!/usr/bin/env python3
"""
Join Wizard for Triton Dotfiles.

Connects an additional machine to an existing vault: clones the repository,
verifies the encryption key, and registers the machine. The wizard does NOT
run restore or backup - selective restore is done in the TUI where the user
can see file lists and diffs before deciding.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style

from .utils import get_triton_dir, import_class_from_module
from .wizard_common import (
    prompt_valid_path,
    read_machine_name_from_config,
    read_repository_path_from_config,
    scan_vault_machines,
    update_config_repository_settings,
)
from .managers.git_manager import GitManager

create_default_config = import_class_from_module("config", "create_default_config")
verify_key_against_repository = import_class_from_module(
    "encryption", "verify_key_against_repository"
)

DEFAULT_VAULT_PATH = Path.home() / "dotfiles-vault"


@dataclass
class JoinResult:
    """Result of the join wizard execution."""

    success: bool = False
    config_file: Optional[Path] = None
    config_created: bool = False
    vault_path: Optional[Path] = None
    remote_url: str = ""
    cloned: bool = False
    key_verified: bool = False
    key_verification_skipped: bool = False
    needs_master_key_placement: bool = False
    machine_name: Optional[str] = None
    machine_dir: Optional[Path] = None
    existing_machines: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class JoinWizard:
    """Interactive wizard to join an existing triton vault."""

    def __init__(
        self,
        repo_url: Optional[str] = None,
        vault_path: Optional[str] = None,
        non_interactive: bool = False,
    ):
        """
        Initialize the wizard.

        Args:
            repo_url: Remote repository URL to clone (skips the URL prompt).
            vault_path: Local vault path override (default: from config.yml).
            non_interactive: If True, use defaults and fail instead of prompting.
        """
        self.repo_url = repo_url
        self.vault_path_override = vault_path
        self.non_interactive = non_interactive
        self.result = JoinResult()

    def run(self) -> JoinResult:
        """Run the join wizard."""
        self._print_welcome()

        # Step 1: Prerequisites (config.yml / master.key)
        config_exists, key_exists = self._step_prerequisites()

        # Step 2: Clone or adopt the vault repository
        if not self._step_vault_repository(config_exists):
            return self.result

        # Step 3: Verify encryption key against the vault
        if not self._step_verify_key(key_exists):
            return self.result

        # Step 4: Machine name and folder registration
        if not self._step_register_machine(config_exists):
            return self.result

        # Create minimal config when none was placed by the user
        if not config_exists:
            if not self._create_minimal_config():
                return self.result

        self._print_summary(key_exists)
        self.result.success = True
        return self.result

    def _print_welcome(self) -> None:
        """Print welcome message."""
        click.echo()
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}  Join an Existing Triton Vault{Style.RESET_ALL}")
        click.echo(
            f"{Fore.CYAN}  Connect this machine to your dotfiles vault{Style.RESET_ALL}"
        )
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo()
        click.echo("This wizard will:")
        click.echo("  1. Check your config and encryption key")
        click.echo("  2. Clone your vault repository")
        click.echo("  3. Verify your encryption key against the vault")
        click.echo("  4. Register this machine")
        click.echo()

    def _step_prerequisites(self) -> tuple[bool, bool]:
        """Step 1: Detect manually placed config.yml / master.key."""
        click.echo(f"{Fore.GREEN}[Step 1/4] Checking prerequisites{Style.RESET_ALL}")

        triton_dir = get_triton_dir()
        config_path = triton_dir / "config.yml"
        key_path = triton_dir / "master.key"

        config_exists = config_path.exists()
        key_exists = key_path.exists()

        if config_exists:
            click.echo(f"  ✓ Config found: {Fore.CYAN}{config_path}{Style.RESET_ALL}")
            self.result.config_file = config_path
        else:
            click.echo(
                f"  {Fore.YELLOW}✗ Config not found: {config_path}{Style.RESET_ALL}"
            )

        if key_exists:
            click.echo(
                f"  ✓ Encryption key found: {Fore.CYAN}{key_path}{Style.RESET_ALL}"
            )
        else:
            click.echo(
                f"  {Fore.YELLOW}✗ Encryption key not found: {key_path}{Style.RESET_ALL}"
            )
            self.result.needs_master_key_placement = True

        if not config_exists:
            click.echo()
            click.echo("  No config found. A minimal config will be created.")
            click.echo(
                f"  {Fore.CYAN}Tip: if your old machine backs up ~/.config/triton, you can{Style.RESET_ALL}"
            )
            click.echo(
                f"  {Fore.CYAN}     restore the full config from the vault after joining.{Style.RESET_ALL}"
            )

        click.echo()
        return config_exists, key_exists

    def _resolve_vault_path(self, config_exists: bool) -> Optional[Path]:
        """Determine the local vault path from override, config, or prompt."""
        if self.vault_path_override:
            return Path(self.vault_path_override).expanduser()

        if config_exists and self.result.config_file:
            config_vault = read_repository_path_from_config(self.result.config_file)
            if config_vault:
                click.echo(
                    f"  Your config expects the vault at: {Fore.CYAN}{config_vault}{Style.RESET_ALL}"
                )
                return config_vault

        if self.non_interactive:
            return DEFAULT_VAULT_PATH

        return prompt_valid_path("  Vault location", default=str(DEFAULT_VAULT_PATH))

    def _step_vault_repository(self, config_exists: bool) -> bool:
        """Step 2: Clone the vault repository (idempotent)."""
        click.echo(f"{Fore.GREEN}[Step 2/4] Clone vault repository{Style.RESET_ALL}")

        vault_path = self._resolve_vault_path(config_exists)
        if vault_path is None:
            self.result.errors.append("Could not determine vault path")
            return False

        self.result.vault_path = vault_path
        git_manager = GitManager(vault_path)

        # Re-running join is safe: adopt an existing clone as-is
        if git_manager.is_git_repository():
            self.result.remote_url = git_manager.get_remote_url()
            machines = scan_vault_machines(vault_path)
            total_files = sum(m["file_count"] for m in machines)
            click.echo(
                f"  ✓ Using existing clone: {Fore.CYAN}{vault_path}{Style.RESET_ALL}"
                f" ({len(machines)} machines, {total_files} files)"
            )
            click.echo()
            return True

        if vault_path.exists() and any(vault_path.iterdir()):
            click.echo(
                f"  {Fore.RED}Error: Directory exists and is not a git repository: {vault_path}{Style.RESET_ALL}"
            )
            click.echo(
                "  Move it away, or point your config.yml repository.path elsewhere."
            )
            self.result.errors.append(f"Vault path is not empty: {vault_path}")
            return False

        # Need to clone: resolve the remote URL
        url = self.repo_url
        if not url:
            if self.non_interactive:
                click.echo(
                    f"  {Fore.RED}Error: Repository URL is required in non-interactive mode.{Style.RESET_ALL}"
                )
                self.result.errors.append("Repository URL not provided")
                return False
            click.echo()
            url = click.prompt(
                "  Repository URL (e.g. git@github.com:you/dotfiles-vault.git)"
            ).strip()

        if not url:
            self.result.errors.append("Repository URL not provided")
            return False

        click.echo(f"  Cloning into {Fore.CYAN}{vault_path}{Style.RESET_ALL} ...")
        clone_result = GitManager.clone_repository(url, vault_path)

        if not clone_result["success"]:
            click.echo(f"  {Fore.RED}Error: {clone_result['message']}{Style.RESET_ALL}")
            if clone_result.get("error"):
                click.echo(f"  {clone_result['error'].strip()}")
            self.result.errors.append(clone_result["message"])
            return False

        self.result.cloned = True
        self.result.remote_url = url

        machines = scan_vault_machines(vault_path)
        total_files = sum(m["file_count"] for m in machines)
        click.echo(f"  ✓ Cloned: {len(machines)} machines, {total_files} files")
        click.echo()
        return True

    def _step_verify_key(self, key_exists: bool) -> bool:
        """Step 3: Test-decrypt an encrypted file to verify the key."""
        click.echo(f"{Fore.GREEN}[Step 3/4] Verify encryption key{Style.RESET_ALL}")

        if not key_exists:
            self.result.key_verification_skipped = True
            click.echo(
                f"  {Fore.YELLOW}! Skipped: no master.key in place yet.{Style.RESET_ALL}"
            )
            click.echo("  Encrypted files cannot be restored until the key is copied.")
            click.echo()
            return True

        key_path = get_triton_dir() / "master.key"
        verification = verify_key_against_repository(key_path, self.result.vault_path)

        if verification["verified"]:
            tested = Path(verification["tested_file"])
            try:
                tested_display = tested.relative_to(self.result.vault_path)
            except ValueError:
                tested_display = tested
            click.echo(
                f"  Testing master.key against {Fore.CYAN}{tested_display}{Style.RESET_ALL} ..."
            )
            click.echo("  ✓ Key verified: encrypted files can be decrypted")
            self.result.key_verified = True
            click.echo()
            return True

        if verification["skipped"]:
            self.result.key_verification_skipped = True
            click.echo(
                f"  {Fore.YELLOW}! Skipped: {verification['error']}{Style.RESET_ALL}"
            )
            click.echo()
            return True

        # Key mismatch detected before any restore is attempted
        click.echo(
            f"  {Fore.RED}✗ Decryption failed: this master.key does not match the vault{Style.RESET_ALL}"
        )
        click.echo()
        click.echo("  Your master.key cannot decrypt files in this vault.")
        click.echo("  Possible causes:")
        click.echo("    - The key belongs to a different vault")
        click.echo("    - The key file was corrupted during transfer")
        click.echo()
        click.echo("  Copy the correct key from another machine:")
        click.echo(
            f"    {Fore.CYAN}scp other-machine:~/.config/triton/master.key {key_path}{Style.RESET_ALL}"
        )
        click.echo()

        if self.non_interactive:
            self.result.errors.append("Encryption key does not match the vault")
            return False

        if not click.confirm(
            "  Continue without encryption support? (encrypted files will be\n"
            "  unreadable until the correct key is in place)",
            default=False,
        ):
            self.result.errors.append("Encryption key does not match the vault")
            return False

        click.echo()
        return True

    def _step_register_machine(self, config_exists: bool) -> bool:
        """Step 4: Decide machine name and create this machine's folder."""
        from .config import get_machine_name_unified

        click.echo(f"{Fore.GREEN}[Step 4/4] Machine name{Style.RESET_ALL}")

        configured_name = None
        if config_exists and self.result.config_file:
            configured_name = read_machine_name_from_config(self.result.config_file)

        machine_name = configured_name or get_machine_name_unified(use_hostname=True)
        source = "configured" if configured_name else "Auto-detected"
        click.echo(f"  {source}: {Fore.CYAN}{machine_name}{Style.RESET_ALL}")

        machines = scan_vault_machines(self.result.vault_path)
        self.result.existing_machines = machines

        if machines:
            click.echo()
            click.echo("  Existing machines in vault:")
            for i, machine in enumerate(machines):
                click.echo(
                    f"    {Fore.GREEN}[{i}]{Style.RESET_ALL} {machine['name']}"
                    f" ({machine['file_count']} files)"
                )
            click.echo()

        existing_names = {m["name"] for m in machines}

        if machine_name in existing_names:
            machine_name = self._resolve_name_conflict(machine_name)
            if machine_name is None:
                return False
        elif not self.non_interactive:
            click.echo("  No conflict with existing machines.")
            if not click.confirm(
                f'  Use "{machine_name}" for this machine?', default=True
            ):
                machine_name = click.prompt("  Enter machine name").strip()
                if not machine_name:
                    self.result.errors.append("Machine name not provided")
                    return False

        self.result.machine_name = machine_name

        # Ensure this machine appears in the TUI machine list immediately.
        # Git does not track empty directories, so nothing reaches the
        # remote until the first backup is pushed - which is intended.
        machine_dir = self.result.vault_path / machine_name
        try:
            machine_dir.mkdir(exist_ok=True)
        except OSError as e:
            click.echo(
                f"  {Fore.RED}Error: Failed to create machine folder: {e}{Style.RESET_ALL}"
            )
            self.result.errors.append(f"Failed to create machine folder: {e}")
            return False

        self.result.machine_dir = machine_dir
        click.echo(
            f"  ✓ Registered: {Fore.CYAN}{machine_dir}/{Style.RESET_ALL}"
            " (empty until first backup)"
        )
        click.echo()
        return True

    def _resolve_name_conflict(self, machine_name: str) -> Optional[str]:
        """Handle a machine name that already exists in the vault."""
        click.echo(
            f'  {Fore.YELLOW}! A machine named "{machine_name}" already exists in the vault.{Style.RESET_ALL}'
        )

        if self.non_interactive:
            # Joining writes nothing into the folder (writes happen at backup
            # time), so reusing it keeps re-runs of 'join -y' idempotent.
            click.echo("  Reusing the existing folder (re-setup of the same machine).")
            return machine_name

        click.echo()
        click.echo(
            f"    {Fore.CYAN}[1]{Style.RESET_ALL} This is the same machine"
            " (re-setup / clean install) - use the existing folder"
        )
        click.echo(
            f"    {Fore.CYAN}[2]{Style.RESET_ALL} This is a different machine"
            " - enter a new name"
        )
        click.echo()

        choice = click.prompt("  Choice", type=click.IntRange(1, 2), default=1)
        if choice == 1:
            return machine_name

        new_name = click.prompt("  Enter machine name").strip()
        if not new_name:
            self.result.errors.append("Machine name not provided")
            return None
        if new_name in {m["name"] for m in self.result.existing_machines}:
            click.echo(
                f"  {Fore.YELLOW}That name also exists. Choose another.{Style.RESET_ALL}"
            )
            return self._resolve_name_conflict(new_name)
        return new_name

    def _create_minimal_config(self) -> bool:
        """Create a minimal config.yml pointing at the joined vault."""
        triton_dir = get_triton_dir()
        config_path = triton_dir / "config.yml"

        try:
            triton_dir.mkdir(parents=True, exist_ok=True)
            create_default_config(str(config_path))
            update_config_repository_settings(
                config_path,
                vault_path=self.result.vault_path,
                machine_name=self.result.machine_name,
            )
            self.result.config_file = config_path
            self.result.config_created = True
            click.echo(f"  ✓ Created config: {Fore.CYAN}{config_path}{Style.RESET_ALL}")
            click.echo()
            return True
        except Exception as e:
            click.echo(f"  {Fore.RED}Error creating config: {e}{Style.RESET_ALL}")
            self.result.errors.append(f"Failed to create config file: {e}")
            return False

    def _print_summary(self, key_exists: bool) -> None:
        """Print final summary directing the user to the TUI."""
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}  Join Complete!{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo()

        click.echo(
            f"This machine:  {Fore.CYAN}{self.result.machine_name}{Style.RESET_ALL}"
        )
        vault_line = str(self.result.vault_path)
        if self.result.remote_url:
            vault_line += f" (origin: {self.result.remote_url})"
        click.echo(f"Vault:         {Fore.CYAN}{vault_line}{Style.RESET_ALL}")

        if self.result.key_verified:
            click.echo(f"Encryption:    {Fore.GREEN}✓ key verified{Style.RESET_ALL}")
        elif self.result.needs_master_key_placement:
            click.echo(
                f"Encryption:    {Fore.RED}✗ master.key missing - copy it from another machine{Style.RESET_ALL}"
            )
        elif self.result.key_verification_skipped:
            click.echo(
                f"Encryption:    {Fore.YELLOW}! not verified (no encrypted files in vault){Style.RESET_ALL}"
            )
        else:
            click.echo(
                f"Encryption:    {Fore.YELLOW}! key does not match the vault{Style.RESET_ALL}"
            )

        if self.result.existing_machines:
            machines_str = ", ".join(
                f"{m['name']} ({m['file_count']} files)"
                for m in self.result.existing_machines
            )
            click.echo(f"Machines:      {machines_str}")

        click.echo()
        click.echo(f"{Fore.CYAN}{'─' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}Next step: launch the TUI{Style.RESET_ALL}")
        click.echo()
        click.echo(f"  {Fore.GREEN}triton{Style.RESET_ALL}")
        click.echo()
        click.echo("In the TUI you can:")
        click.echo("  - Browse other machines and restore only the files")
        click.echo("    you need (e.g. .ssh, .zshrc) -- selective restore")
        click.echo("    is safer than restoring everything at once")
        click.echo("  - Press B to create this machine's first backup")
        click.echo("    once you are happy with your setup")
        click.echo(f"{Fore.CYAN}{'─' * 55}{Style.RESET_ALL}")

        if self.result.needs_master_key_placement:
            key_path = get_triton_dir() / "master.key"
            click.echo()
            click.echo(f"{Fore.RED}{'─' * 55}{Style.RESET_ALL}")
            click.echo(
                f"{Fore.RED}  REQUIRED: Place your master.key file{Style.RESET_ALL}"
            )
            click.echo(f"{Fore.RED}{'─' * 55}{Style.RESET_ALL}")
            click.echo()
            click.echo("  Copy your master.key from another machine to:")
            click.echo(f"    {Fore.CYAN}{key_path}{Style.RESET_ALL}")
            click.echo()
            click.echo(
                f"  {Fore.RED}WARNING: Encrypted files cannot be restored without it.{Style.RESET_ALL}"
            )
        click.echo()


def run_join_wizard(
    repo_url: Optional[str] = None,
    vault_path: Optional[str] = None,
    non_interactive: bool = False,
) -> JoinResult:
    """
    Run the join wizard.

    Args:
        repo_url: Remote repository URL to clone.
        vault_path: Local vault path override.
        non_interactive: If True, use defaults and fail instead of prompting.

    Returns:
        JoinResult with details of what was done.
    """
    wizard = JoinWizard(
        repo_url=repo_url,
        vault_path=vault_path,
        non_interactive=non_interactive,
    )
    return wizard.run()
