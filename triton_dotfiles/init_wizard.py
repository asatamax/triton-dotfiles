#!/usr/bin/env python3
"""
Initialization Wizard for Triton Dotfiles.

Provides an interactive setup wizard for new users to configure triton.
"""

import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style

from .utils import get_triton_dir, import_class_from_module

create_default_config = import_class_from_module("config", "create_default_config")
create_encryption_key = import_class_from_module("encryption", "create_encryption_key")


@dataclass
class WizardResult:
    """Result of the wizard execution."""

    success: bool = False
    config_dir: Optional[Path] = None
    config_file: Optional[Path] = None
    key_file: Optional[Path] = None
    vault_path: Optional[Path] = None
    machine_name: Optional[str] = None
    backup_executed: bool = False
    needs_remote_setup: bool = False  # True if local vault was created without remote
    needs_master_key_placement: bool = False  # True if user chose to use existing key
    targets_added: list[str] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PresetTarget:
    """Preset backup target definition."""

    path: str
    description: str
    recursive: bool = False
    auto_encrypted: bool = False
    files: Optional[list[str]] = None


# Preset targets for initial setup
PRESET_TARGETS: list[PresetTarget] = [
    PresetTarget(
        path="~/.ssh",
        description="SSH keys and configs",
        recursive=True,
        auto_encrypted=True,
    ),
    PresetTarget(
        path="~/.aws",
        description="AWS credentials",
        recursive=True,
        auto_encrypted=True,
    ),
    PresetTarget(
        path="~/.config/nvim",
        description="Neovim config",
        recursive=True,
    ),
    PresetTarget(
        path="~/",
        description="Shell & editor configs",
        files=[
            ".zshrc",
            ".bashrc",
            ".bash_profile",
            ".zshenv",
            ".zprofile",
            ".vimrc",
            ".tmux.conf",
        ],
    ),
    PresetTarget(
        path="~/",
        description="Git config (.gitconfig)",
        files=[".gitconfig"],
    ),
    PresetTarget(
        path="~/.claude",
        description="Claude Code settings",
        recursive=True,
        files=[
            "CLAUDE.md",
            "settings.json",
            "agents/**/*",
            "commands/**/*",
            "hooks/**/*",
            "skills/**/*",
        ],
    ),
    PresetTarget(
        path="~/.codex",
        description="Codex CLI settings",
        files=["AGENTS.md"],
    ),
]


class InitWizard:
    """Interactive initialization wizard for triton."""

    def __init__(self, non_interactive: bool = False, vault_path: Optional[str] = None):
        """
        Initialize the wizard.

        Args:
            non_interactive: If True, use defaults without prompting.
            vault_path: Pre-specified vault path for non-interactive mode.
        """
        self.non_interactive = non_interactive
        self.vault_path = vault_path
        self.result = WizardResult()

    def run(self) -> WizardResult:
        """Run the initialization wizard."""
        self._print_welcome()

        # Check for existing setup
        existing = self._detect_existing_setup()
        if existing and not self.non_interactive:
            if not self._handle_existing_setup(existing):
                self.result.success = False
                return self.result

        # Step 1: Configuration Directory
        if not self._step_config_directory():
            return self.result

        # Step 2: Vault Setup (required - triton cannot work without it)
        if not self._step_vault_setup(existing):
            return self.result

        # Step 3: Machine Name
        if not self._step_machine_name():
            return self.result

        # Step 4: Encryption Key (required for security)
        if not self._step_encryption_key():
            return self.result

        # Step 5: Initial Backup Targets
        self._step_backup_targets()

        # Step 6: Create config.yml
        if not self._create_config_file():
            return self.result

        # Final Summary
        self._print_summary()

        # Step 7: Initial Backup (optional)
        self._step_initial_backup()

        # Show remote repository reminder if needed
        self._show_remote_reminder()

        # Show master.key placement reminder if user chose to use existing key
        self._show_master_key_reminder()

        self.result.success = True
        return self.result

    def _print_welcome(self) -> None:
        """Print welcome message."""
        click.echo()
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}  Welcome to Triton Dotfiles Manager{Style.RESET_ALL}")
        click.echo(
            f"{Fore.CYAN}  Secure backup for your dotfiles across machines{Style.RESET_ALL}"
        )
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo()

        if not self.non_interactive:
            click.echo("This wizard will help you set up:")
            click.echo(
                f"  1. Configuration directory ({Fore.CYAN}~/.config/triton{Style.RESET_ALL})"
            )
            click.echo(
                f"  2. Vault location ({Fore.CYAN}Git repository for your backups{Style.RESET_ALL})"
            )
            click.echo(
                f"  3. Machine name ({Fore.CYAN}identifier for this computer{Style.RESET_ALL})"
            )
            click.echo(
                f"  4. Encryption key ({Fore.CYAN}for sensitive files like SSH keys{Style.RESET_ALL})"
            )
            click.echo("  5. Initial backup targets")
            click.echo("  6. First backup (optional)")
            click.echo()

    def _detect_existing_setup(self) -> dict[str, Path]:
        """Detect existing triton setup files."""
        existing = {}
        triton_dir = get_triton_dir()

        config_file = triton_dir / "config.yml"
        if config_file.exists():
            existing["config"] = config_file

        key_file = triton_dir / "master.key"
        if key_file.exists():
            existing["key"] = key_file

        return existing

    def _get_existing_vault_path(self, existing: Optional[dict]) -> Optional[Path]:
        """Get vault path from existing config if available."""
        if not existing or "config" not in existing:
            return None

        try:
            import yaml

            config_path = existing["config"]
            with open(config_path) as f:
                config_data = yaml.safe_load(f)

            if config_data and "config" in config_data:
                repo_path = config_data["config"].get("repository", {}).get("path")
                if repo_path:
                    expanded = Path(repo_path).expanduser()
                    if expanded.exists():
                        return expanded
        except Exception:
            pass

        return None

    def _handle_existing_setup(self, existing: dict[str, Path]) -> bool:
        """Handle existing setup detection."""
        click.echo(f"{Fore.YELLOW}[Existing Setup Detected]{Style.RESET_ALL}")

        for item, path in existing.items():
            click.echo(f"  Found: {Fore.CYAN}{path}{Style.RESET_ALL}")

        click.echo()
        return click.confirm(
            "Re-run setup? (existing files will be preserved unless you choose to overwrite)"
        )

    def _step_config_directory(self) -> bool:
        """Step 1: Create configuration directory."""
        click.echo(f"{Fore.GREEN}[Step 1/6] Configuration Directory{Style.RESET_ALL}")

        triton_dir = get_triton_dir()
        self.result.config_dir = triton_dir

        if triton_dir.exists():
            click.echo(f"  Directory exists: {Fore.CYAN}{triton_dir}{Style.RESET_ALL}")
        else:
            try:
                triton_dir.mkdir(parents=True, exist_ok=True)
                click.echo(
                    f"  Created: {Fore.CYAN}{triton_dir}{Style.RESET_ALL} {Fore.GREEN}Done{Style.RESET_ALL}"
                )
            except OSError as e:
                click.echo(
                    f"  {Fore.RED}Error: Failed to create directory: {e}{Style.RESET_ALL}"
                )
                self.result.errors.append(f"Failed to create config directory: {e}")
                return False

        click.echo()
        return True

    def _step_encryption_key(self) -> bool:
        """Step 4: Generate encryption key (required)."""
        click.echo(f"{Fore.GREEN}[Step 4/6] Encryption Key{Style.RESET_ALL}")
        click.echo(
            f"  {Fore.CYAN}Encryption protects sensitive files like SSH keys and credentials.{Style.RESET_ALL}"
        )
        click.echo()

        triton_dir = get_triton_dir()
        key_path = triton_dir / "master.key"

        if key_path.exists():
            # Key already exists - use it (no skip option)
            click.echo(f"  Key exists: {Fore.CYAN}{key_path}{Style.RESET_ALL}")
            self.result.key_file = key_path

            if not self.non_interactive:
                click.echo()
                if click.confirm(
                    "  Generate a NEW key? (WARNING: existing encrypted files will become unreadable)",
                    default=False,
                ):
                    # User wants to regenerate - continue to key generation below
                    pass
                else:
                    # Use existing key
                    click.echo(
                        f"  Using existing key {Fore.GREEN}Done{Style.RESET_ALL}"
                    )
                    self._show_key_importance_warning(key_path, is_new=False)
                    click.echo()
                    return True
            else:
                # Non-interactive: use existing key
                click.echo()
                return True
        else:
            # Key does not exist - ask user what to do
            if not self.non_interactive:
                click.echo("  No encryption key found. Choose an option:")
                click.echo()
                click.echo(
                    f"    {Fore.CYAN}[1]{Style.RESET_ALL} Create new master.key (first machine setup)"
                )
                click.echo(
                    f"    {Fore.CYAN}[2]{Style.RESET_ALL} Use existing master.key (setting up additional machine)"
                )
                click.echo()

                choice = click.prompt(
                    "  Choice",
                    type=click.IntRange(1, 2),
                    default=1,
                )

                if choice == 2:
                    # User will copy key from another machine
                    self.result.needs_master_key_placement = True
                    self.result.skipped_steps.append("encryption_key_generation")
                    click.echo()
                    click.echo(
                        f"  {Fore.YELLOW}Skipping key generation.{Style.RESET_ALL}"
                    )
                    click.echo(
                        f"  {Fore.CYAN}You will need to copy your master.key from another machine.{Style.RESET_ALL}"
                    )
                    click.echo()
                    return True
                # choice == 1: continue to generate new key below

        try:
            # Generate new key
            force = key_path.exists()
            create_encryption_key(key_path, force=force)
            self.result.key_file = key_path

            click.echo(
                f"  Generated: {Fore.CYAN}{key_path}{Style.RESET_ALL} {Fore.GREEN}Done{Style.RESET_ALL}"
            )
            self._show_key_importance_warning(key_path, is_new=True)

        except Exception as e:
            click.echo(f"  {Fore.RED}Error: {e}{Style.RESET_ALL}")
            self.result.errors.append(f"Failed to create encryption key: {e}")
            return False

        click.echo()
        return True

    def _show_key_importance_warning(self, key_path: Path, is_new: bool = True) -> None:
        """Show warning about encryption key importance."""
        click.echo()
        click.echo(f"  {Fore.RED}{'=' * 55}{Style.RESET_ALL}")
        click.echo(f"  {Fore.RED}CRITICAL: About your encryption key{Style.RESET_ALL}")
        click.echo(f"  {Fore.RED}{'=' * 55}{Style.RESET_ALL}")
        click.echo()
        click.echo(
            f"  {Fore.YELLOW}Your master.key encrypts sensitive files (SSH keys, credentials).{Style.RESET_ALL}"
        )
        click.echo()
        click.echo(f"  {Fore.WHITE}You MUST:{Style.RESET_ALL}")
        click.echo(
            f"    {Fore.GREEN}1.{Style.RESET_ALL} Back up this key separately (password manager, USB, etc.)"
        )
        click.echo(
            f"    {Fore.GREEN}2.{Style.RESET_ALL} NEVER commit it to your vault or any Git repository"
        )
        click.echo(
            f"    {Fore.GREEN}3.{Style.RESET_ALL} Keep it safe - triton automatically excludes it from backups"
        )
        click.echo()
        click.echo(
            f"  {Fore.RED}WARNING: If you lose this key, encrypted files CANNOT be recovered.{Style.RESET_ALL}"
        )
        click.echo(f"  {Fore.RED}{'=' * 55}{Style.RESET_ALL}")

        # Require explicit acknowledgment (skip in non-interactive mode)
        if not self.non_interactive:
            click.echo()
            click.prompt(
                f"  {Fore.YELLOW}Press Enter to confirm you understand{Style.RESET_ALL}",
                default="",
                show_default=False,
            )

    def _step_vault_setup(self, existing: Optional[dict] = None) -> bool:
        """Step 2: Configure vault (repository) location. Required."""
        click.echo(f"{Fore.GREEN}[Step 2/6] Vault Setup{Style.RESET_ALL}")
        click.echo(
            f"  {Fore.CYAN}Your vault is a Git repository where backups are stored.{Style.RESET_ALL}"
        )
        click.echo()

        if self.non_interactive:
            # Use provided vault path or default
            vault_path = (
                Path(self.vault_path).expanduser()
                if self.vault_path
                else Path.home() / "dotfiles-vault"
            )
            return self._setup_vault_directory(vault_path)

        # Interactive mode: show options
        click.echo("  Where would you like to store your backups?")
        click.echo()
        click.echo(
            f"    {Fore.CYAN}[1]{Style.RESET_ALL} Create new local directory (~/dotfiles-vault)"
        )
        click.echo(f"    {Fore.CYAN}[2]{Style.RESET_ALL} Use existing Git repository")
        click.echo(
            f"    {Fore.CYAN}[3]{Style.RESET_ALL} Skip for now (configure manually later)"
        )

        # Check for gh CLI
        gh_available = self._check_gh_cli()
        if gh_available:
            click.echo(
                f"    {Fore.CYAN}[4]{Style.RESET_ALL} GitHub repository setup guide (gh CLI detected)"
            )

        click.echo()

        max_choice = 4 if gh_available else 3
        choice = click.prompt(
            "  Choice",
            type=click.IntRange(1, max_choice),
            default=1,
        )

        if choice == 1:
            # Create new local directory
            default_path = Path.home() / "dotfiles-vault"
            vault_path = self._prompt_valid_path(
                "  Vault path",
                default=str(default_path),
            )
            return self._setup_vault_directory(vault_path)

        elif choice == 2:
            # Use existing repository
            vault_path = self._prompt_valid_path("  Path to existing Git repository")

            if not vault_path.exists():
                click.echo(
                    f"  {Fore.RED}Error: Path does not exist: {vault_path}{Style.RESET_ALL}"
                )
                return False

            if not (vault_path / ".git").exists():
                click.echo(
                    f"  {Fore.YELLOW}Warning: Not a Git repository (no .git directory){Style.RESET_ALL}"
                )
                if not click.confirm("  Continue anyway?"):
                    return False

            self.result.vault_path = vault_path
            click.echo(
                f"  Using: {Fore.CYAN}{vault_path}{Style.RESET_ALL} {Fore.GREEN}Done{Style.RESET_ALL}"
            )

        elif choice == 3:
            # Skip - only allowed if existing vault is configured
            existing_vault_path = self._get_existing_vault_path(existing)
            if existing_vault_path:
                self.result.vault_path = existing_vault_path
                self.result.skipped_steps.append("vault_setup")
                click.echo(
                    f"  Using existing vault: {Fore.CYAN}{existing_vault_path}{Style.RESET_ALL}"
                )
            else:
                click.echo()
                click.echo(
                    f"  {Fore.RED}Vault is required for triton to work.{Style.RESET_ALL}"
                )
                click.echo(
                    f"  {Fore.YELLOW}Please select option [1] or [2] to configure a vault.{Style.RESET_ALL}"
                )
                click.echo()
                return self._step_vault_setup(existing)  # Re-run this step

        elif choice == 4 and gh_available:
            # GitHub setup guide
            self._show_github_guide()
            return self._step_vault_setup(existing)  # Re-run this step

        click.echo()
        return True

    def _prompt_valid_path(
        self, prompt_text: str, default: Optional[str] = None
    ) -> Path:
        """Prompt for a valid file path with validation.

        Validates that the input looks like a path (contains / or ~)
        to prevent accidental numeric input from being used as a path.
        """
        while True:
            if default:
                path_str = click.prompt(prompt_text, default=default)
            else:
                path_str = click.prompt(prompt_text)

            # Check if input looks like a valid path
            path_str = path_str.strip()
            if not path_str:
                click.echo(
                    f"  {Fore.YELLOW}Please enter a valid path.{Style.RESET_ALL}"
                )
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

    def _setup_vault_directory(self, vault_path: Path) -> bool:
        """Set up vault directory with Git initialization."""
        try:
            if vault_path.exists():
                if (vault_path / ".git").exists():
                    click.echo(
                        f"  Using existing repository: {Fore.CYAN}{vault_path}{Style.RESET_ALL}"
                    )
                else:
                    click.echo(
                        f"  Directory exists (not a Git repo): {Fore.CYAN}{vault_path}{Style.RESET_ALL}"
                    )
                    if not self.non_interactive:
                        if click.confirm(
                            "  Initialize as Git repository?", default=True
                        ):
                            self._git_init(vault_path)
            else:
                vault_path.mkdir(parents=True, exist_ok=True)
                click.echo(f"  Created: {Fore.CYAN}{vault_path}{Style.RESET_ALL}")
                self._git_init(vault_path)

            self.result.vault_path = vault_path
            self.result.needs_remote_setup = True  # Mark for reminder at the end
            click.echo(f"  {Fore.GREEN}Done{Style.RESET_ALL}")

            # Show next step hint
            if not self.non_interactive:
                click.echo()
                click.echo(
                    f"  {Fore.CYAN}Tip: Add a remote repository when ready:{Style.RESET_ALL}"
                )
                click.echo(f"    cd {vault_path}")
                click.echo("    git remote add origin <your-private-repo-url>")

            return True

        except OSError as e:
            click.echo(f"  {Fore.RED}Error: {e}{Style.RESET_ALL}")
            self.result.errors.append(f"Failed to setup vault: {e}")
            return False

    def _git_init(self, path: Path) -> None:
        """Initialize Git repository."""
        try:
            subprocess.run(
                ["git", "init"],
                cwd=path,
                capture_output=True,
                check=True,
            )
            click.echo("  Initialized Git repository")
        except subprocess.CalledProcessError as e:
            click.echo(f"  {Fore.YELLOW}Warning: git init failed: {e}{Style.RESET_ALL}")

    def _check_gh_cli(self) -> bool:
        """Check if GitHub CLI is available."""
        return shutil.which("gh") is not None

    def _show_github_guide(self) -> None:
        """Show GitHub repository setup guide."""
        click.echo()
        click.echo(f"  {Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        click.echo(f"  {Fore.CYAN}GitHub Repository Setup Guide{Style.RESET_ALL}")
        click.echo(f"  {Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        click.echo()
        click.echo(f"  {Fore.YELLOW}SECURITY RECOMMENDATION:{Style.RESET_ALL}")
        click.echo("  Your vault contains encrypted sensitive files.")
        click.echo(
            f"  A {Fore.RED}PRIVATE{Style.RESET_ALL} repository is {Fore.RED}STRONGLY{Style.RESET_ALL} recommended."
        )
        click.echo()
        click.echo("  Create a private repository with gh CLI:")
        click.echo()
        click.echo(f"    {Fore.GREEN}# Create private repository{Style.RESET_ALL}")
        click.echo("    gh repo create dotfiles-vault --private --clone")
        click.echo()
        click.echo(
            f"    {Fore.GREEN}# Or if you have an existing local directory:{Style.RESET_ALL}"
        )
        click.echo("    cd ~/dotfiles-vault")
        click.echo("    git init")
        click.echo("    gh repo create dotfiles-vault --private --source=. --push")
        click.echo()
        click.echo(f"  {Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        click.echo()
        click.echo("  After creating your repository, run the wizard again")
        click.echo("  and select option [2] to use the existing repository.")
        click.echo()
        click.prompt("  Press Enter to continue", default="", show_default=False)

    def _step_machine_name(self) -> bool:
        """Step 3: Configure machine name."""
        from .config import get_machine_name_unified

        click.echo(f"{Fore.GREEN}[Step 3/6] Machine Name{Style.RESET_ALL}")
        click.echo(
            f"  {Fore.CYAN}Your machine name identifies this computer in backups.{Style.RESET_ALL}"
        )
        click.echo()

        # Get auto-detected name
        auto_name = get_machine_name_unified(use_hostname=True)

        if self.non_interactive:
            self.result.machine_name = auto_name
            click.echo(
                f"  Using auto-detected name: {Fore.CYAN}{auto_name}{Style.RESET_ALL}"
            )
            click.echo()
            return True

        click.echo(f"  Auto-detected: {Fore.CYAN}{auto_name}{Style.RESET_ALL}")
        click.echo()
        click.echo("  Options:")
        click.echo(
            f"    {Fore.CYAN}[1]{Style.RESET_ALL} Use auto-detected name (recommended)"
        )
        click.echo(f"    {Fore.CYAN}[2]{Style.RESET_ALL} Enter a custom name")
        click.echo()

        choice = click.prompt(
            "  Choice",
            type=click.IntRange(1, 2),
            default=1,
        )

        if choice == 1:
            self.result.machine_name = auto_name
            click.echo(
                f"  Using: {Fore.CYAN}{auto_name}{Style.RESET_ALL} {Fore.GREEN}Done{Style.RESET_ALL}"
            )
        else:
            custom_name = click.prompt("  Enter machine name")
            # Validate: no spaces, no special characters except - and _
            if (
                not custom_name
                or not custom_name.replace("-", "").replace("_", "").isalnum()
            ):
                click.echo(
                    f"  {Fore.YELLOW}Warning: Name should contain only letters, numbers, - and _{Style.RESET_ALL}"
                )
                if not click.confirm("  Use this name anyway?", default=False):
                    return self._step_machine_name()  # Retry
            self.result.machine_name = custom_name
            click.echo(
                f"  Using: {Fore.CYAN}{custom_name}{Style.RESET_ALL} {Fore.GREEN}Done{Style.RESET_ALL}"
            )

        click.echo()
        return True

    def _step_backup_targets(self) -> None:
        """Step 5: Configure initial backup targets."""
        click.echo(f"{Fore.GREEN}[Step 5/6] Initial Backup Targets{Style.RESET_ALL}")

        if self.non_interactive:
            # In non-interactive mode, add default targets
            self.result.targets_added = ["~/.ssh", "~/.aws", "~/.zshrc"]
            click.echo("  Using default targets: ~/.ssh, ~/.aws, ~/.zshrc")
            click.echo()
            return

        # Find targets that exist on this machine
        available_targets: list[tuple[int, PresetTarget]] = []
        for i, target in enumerate(PRESET_TARGETS):
            expanded_path = Path(target.path).expanduser()
            if expanded_path.exists():
                available_targets.append((i, target))

        # If no targets exist, auto-skip
        if not available_targets:
            click.echo(
                f"  {Fore.YELLOW}No suggested targets found on this machine.{Style.RESET_ALL}"
            )
            click.echo("  Add targets later with 'triton config target add'")
            self.result.skipped_steps.append("backup_targets")
            click.echo()
            return

        click.echo(
            f"  {Fore.CYAN}Found {len(available_targets)} directories to backup:{Style.RESET_ALL}"
        )
        click.echo()

        selected_targets: list[PresetTarget] = []

        for i, target in available_targets:
            encrypted = (
                f" {Fore.CYAN}(encrypted){Style.RESET_ALL}"
                if target.auto_encrypted
                else ""
            )
            click.echo(f"    [{i + 1}] {target.path} - {target.description}{encrypted}")

        click.echo()

        choices = click.prompt(
            "  Press Enter for all, or type numbers/none",
            default="all",
        )

        choice_stripped = choices.strip().lower()
        if choice_stripped == "none":
            self.result.skipped_steps.append("backup_targets")
            click.echo(
                f"  {Fore.YELLOW}Skipped. Add targets later with 'triton config target add'{Style.RESET_ALL}"
            )
        elif choice_stripped == "all":
            # Select all targets
            selected_targets = list(PRESET_TARGETS)
            self.result.targets_added = [t.path for t in selected_targets]
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choices.split(",") if x.strip()]
                for idx in indices:
                    if 0 <= idx < len(PRESET_TARGETS):
                        selected_targets.append(PRESET_TARGETS[idx])
                        self.result.targets_added.append(PRESET_TARGETS[idx].path)
            except ValueError:
                click.echo(
                    f"  {Fore.YELLOW}Invalid input. Using defaults.{Style.RESET_ALL}"
                )
                selected_targets = PRESET_TARGETS[:2]  # ~/.ssh and ~/.aws
                self.result.targets_added = [t.path for t in selected_targets]

        # Store for config creation
        self._selected_targets = selected_targets

        click.echo()

    def _create_config_file(self) -> bool:
        """Create the config.yml file."""
        triton_dir = get_triton_dir()
        config_path = triton_dir / "config.yml"

        if config_path.exists() and not self.non_interactive:
            if not click.confirm(
                f"  Config file exists at {config_path}. Overwrite?", default=False
            ):
                self.result.skipped_steps.append("config_file")
                self.result.config_file = config_path
                return True

        try:
            # Create config from template
            create_default_config(str(config_path))

            # Update config with wizard results
            self._update_config_settings(config_path)

            self.result.config_file = config_path
            return True

        except Exception as e:
            click.echo(f"  {Fore.RED}Error creating config: {e}{Style.RESET_ALL}")
            self.result.errors.append(f"Failed to create config file: {e}")
            return False

    def _update_config_settings(self, config_path: Path) -> None:
        """Update config.yml with wizard results (vault path, machine name)."""
        try:
            content = config_path.read_text()
            home = str(Path.home())

            # Update vault path if set
            if self.result.vault_path:
                vault_path_str = str(self.result.vault_path)
                if vault_path_str.startswith(home):
                    vault_path_str = "~" + vault_path_str[len(home) :]
                content = content.replace(
                    "path: ~/dotfiles-repo",
                    f"path: {vault_path_str}",
                )

            # Update machine name if custom name was set
            if self.result.machine_name:
                from .config import get_machine_name_unified

                auto_name = get_machine_name_unified(use_hostname=True)
                if self.result.machine_name != auto_name:
                    # Custom name was set - add machine_name to config
                    # Find the repository section and add machine_name after use_hostname
                    import re

                    # Pattern to find use_hostname line in repository section
                    pattern = r"(repository:\s*\n(?:.*\n)*?\s*use_hostname:\s*true)"
                    replacement = r"\1\n    machine_name: " + self.result.machine_name
                    content = re.sub(pattern, replacement, content)

            # Add selected targets that are not in template
            content = self._add_selected_targets_to_config(content)

            config_path.write_text(content)
        except Exception:
            pass  # Non-critical, user can edit manually

    def _add_selected_targets_to_config(self, content: str) -> str:
        """Add wizard-selected targets that are not already in the config template."""
        if not hasattr(self, "_selected_targets") or not self._selected_targets:
            return content

        # Paths that are already in the template (no need to add again)
        template_paths = {
            "~/",
            "~/.ssh",
            "~/.aws",
            "~/.config/git",
            "~/.config/triton",
        }

        # Find targets that need to be added
        targets_to_add = [
            t for t in self._selected_targets if t.path not in template_paths
        ]

        if not targets_to_add:
            return content

        # Generate YAML for new targets
        yaml_lines = ["\n    # --- Wizard-added targets ---"]
        for target in targets_to_add:
            yaml_lines.append(f"    - path: {target.path}")
            if target.files:
                if len(target.files) == 1:
                    yaml_lines.append(f'      files: ["{target.files[0]}"]')
                else:
                    yaml_lines.append("      files:")
                    for f in target.files:
                        yaml_lines.append(f'        - "{f}"')
            if target.recursive:
                yaml_lines.append("      recursive: true")
            yaml_lines.append("")

        yaml_block = "\n".join(yaml_lines)

        # Insert before "# Global Exclude Patterns" section
        marker = "  # ============================================================\n  # Global Exclude Patterns"
        if marker in content:
            content = content.replace(marker, yaml_block + "\n" + marker)
        else:
            # Fallback: append to targets section
            # Find end of targets section and insert there
            pass  # Just append if marker not found

        return content

    def _print_summary(self) -> None:
        """Print final summary and next steps."""
        click.echo()
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}  Setup Complete!{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}{'=' * 55}{Style.RESET_ALL}")
        click.echo()

        # Created files
        click.echo(f"{Fore.GREEN}Created:{Style.RESET_ALL}")
        if self.result.config_file:
            click.echo(f"  {Fore.GREEN}Done{Style.RESET_ALL} {self.result.config_file}")
        if self.result.key_file and "encryption_key" not in self.result.skipped_steps:
            click.echo(
                f"  {Fore.GREEN}Done{Style.RESET_ALL} {self.result.key_file} {Fore.YELLOW}(KEEP THIS SAFE!){Style.RESET_ALL}"
            )
        if self.result.vault_path and "vault_setup" not in self.result.skipped_steps:
            click.echo(
                f"  {Fore.GREEN}Done{Style.RESET_ALL} {self.result.vault_path} (vault)"
            )

        # Machine name
        if self.result.machine_name:
            click.echo()
            click.echo(
                f"Your machine name: {Fore.CYAN}{self.result.machine_name}{Style.RESET_ALL}"
            )

        # Skipped steps
        if self.result.skipped_steps:
            click.echo()
            click.echo(f"{Fore.YELLOW}Skipped:{Style.RESET_ALL}")
            for step in self.result.skipped_steps:
                click.echo(f"  - {step.replace('_', ' ').title()}")

        # Next steps
        click.echo()
        click.echo(f"{Fore.CYAN}{'─' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}Quick Start:{Style.RESET_ALL}")
        click.echo(
            f"  {Fore.GREEN}triton{Style.RESET_ALL}               Launch TUI (recommended for browsing)"
        )
        click.echo(
            f"  {Fore.GREEN}triton backup{Style.RESET_ALL}        Backup your dotfiles now"
        )
        click.echo(
            f"  {Fore.GREEN}triton status{Style.RESET_ALL}        Check current backup status"
        )
        click.echo()
        click.echo(f"{Fore.CYAN}Add backup targets:{Style.RESET_ALL}")
        click.echo(
            f"  {Fore.GREEN}triton config target add ~/.ssh -r{Style.RESET_ALL}      # SSH keys (auto-encrypted)"
        )
        click.echo(
            f'  {Fore.GREEN}triton config target add ~/ -f ".zshrc,.bashrc"{Style.RESET_ALL}'
        )
        click.echo()
        click.echo(f"{Fore.CYAN}For AI/LLM agents:{Style.RESET_ALL}")
        click.echo(
            f"  {Fore.GREEN}triton config --schema{Style.RESET_ALL}  # Get command schema for automation"
        )
        click.echo('  Example: "Please add ~/.aws to my encrypted backup list"')
        click.echo()
        click.echo(f"{Fore.CYAN}{'─' * 55}{Style.RESET_ALL}")

    def _step_initial_backup(self) -> None:
        """Step 6: Optionally run first backup."""
        # Skip if vault was not set up
        if "vault_setup" in self.result.skipped_steps:
            return

        click.echo()
        click.echo(f"{Fore.GREEN}[Step 6/6] First Backup{Style.RESET_ALL}")

        if self.non_interactive:
            # In non-interactive mode, skip backup (user can run separately)
            click.echo("  Skipping backup in non-interactive mode.")
            click.echo("  Run 'triton backup' to create your first backup.")
            return

        click.echo(
            f"  {Fore.CYAN}Create your first backup now to start using TUI immediately.{Style.RESET_ALL}"
        )
        click.echo()

        if not click.confirm("  Run first backup now?", default=True):
            self.result.skipped_steps.append("initial_backup")
            click.echo()
            click.echo(
                "  You can run 'triton backup' later to create your first backup."
            )
            return

        click.echo()
        click.echo(f"  {Fore.CYAN}Running backup...{Style.RESET_ALL}")
        click.echo()

        try:
            # Import and run backup
            ConfigManager = import_class_from_module("config", "ConfigManager")
            FileManager = import_class_from_module(
                "managers.file_manager", "FileManager"
            )

            config_manager = ConfigManager(str(self.result.config_file))
            file_manager = FileManager(config_manager)

            # Use the machine name from wizard result
            machine_name = self.result.machine_name or config_manager.get_machine_name()

            # Run backup
            results = file_manager.backup_files(machine_name, dry_run=False)

            # Count results - backup_files returns Dict[str, List[str]]
            # with keys: "copied", "skipped", "unchanged", "errors"
            copied = len(results.get("copied", []))
            unchanged = len(results.get("unchanged", []))
            errors = len(results.get("errors", []))

            click.echo()
            click.echo(f"  {Fore.GREEN}Backup complete!{Style.RESET_ALL}")
            click.echo(f"    Files copied: {Fore.GREEN}{copied}{Style.RESET_ALL}")
            if unchanged:
                click.echo(f"    Unchanged: {unchanged}")
            if errors:
                click.echo(f"    Errors: {Fore.RED}{errors}{Style.RESET_ALL}")

            self.result.backup_executed = True

            click.echo()
            click.echo(
                f"  {Fore.CYAN}You can now launch TUI with 'triton'{Style.RESET_ALL}"
            )

        except Exception as e:
            click.echo(f"  {Fore.RED}Backup failed: {e}{Style.RESET_ALL}")
            click.echo("  You can try again later with 'triton backup'")

    def _show_remote_reminder(self) -> None:
        """Show reminder to set up remote repository if needed."""
        if not self.result.needs_remote_setup:
            return

        vault_path = self.result.vault_path
        if not vault_path:
            return

        click.echo()
        click.echo(f"{Fore.YELLOW}{'─' * 55}{Style.RESET_ALL}")
        click.echo(
            f"{Fore.YELLOW}  Don't forget: Connect to a remote repository{Style.RESET_ALL}"
        )
        click.echo(f"{Fore.YELLOW}{'─' * 55}{Style.RESET_ALL}")
        click.echo()
        click.echo("  Your backups are currently stored locally at:")
        click.echo(f"    {Fore.CYAN}{vault_path}{Style.RESET_ALL}")
        click.echo()
        click.echo(
            f"  {Fore.WHITE}To sync across machines and keep backups safe:{Style.RESET_ALL}"
        )
        click.echo()
        click.echo(f"    cd {vault_path}")
        click.echo(
            f"    git remote add origin {Fore.CYAN}<your-private-repo-url>{Style.RESET_ALL}"
        )
        click.echo("    git push -u origin main")
        click.echo()
        click.echo(
            f"  {Fore.YELLOW}Tip: Use a PRIVATE repository to keep your dotfiles secure.{Style.RESET_ALL}"
        )
        click.echo()

    def _show_master_key_reminder(self) -> None:
        """Show reminder to place master.key if user chose to use existing key."""
        if not self.result.needs_master_key_placement:
            return

        triton_dir = get_triton_dir()
        key_path = triton_dir / "master.key"

        click.echo()
        click.echo(f"{Fore.RED}{'─' * 55}{Style.RESET_ALL}")
        click.echo(f"{Fore.RED}  REQUIRED: Place your master.key file{Style.RESET_ALL}")
        click.echo(f"{Fore.RED}{'─' * 55}{Style.RESET_ALL}")
        click.echo()
        click.echo(
            f"  {Fore.WHITE}You chose to use an existing encryption key.{Style.RESET_ALL}"
        )
        click.echo(
            f"  {Fore.WHITE}Copy your master.key from another machine to:{Style.RESET_ALL}"
        )
        click.echo()
        click.echo(f"    {Fore.CYAN}{key_path}{Style.RESET_ALL}")
        click.echo()
        click.echo(f"  {Fore.YELLOW}Example (from another machine):{Style.RESET_ALL}")
        click.echo(
            f"    scp ~/.config/triton/master.key {Fore.CYAN}this-machine:{key_path}{Style.RESET_ALL}"
        )
        click.echo()
        click.echo(
            f"  {Fore.RED}WARNING: triton will not work until master.key is in place.{Style.RESET_ALL}"
        )
        click.echo(
            f"  {Fore.RED}         Encrypted files cannot be read without the correct key.{Style.RESET_ALL}"
        )
        click.echo()


def run_wizard(
    non_interactive: bool = False,
    vault_path: Optional[str] = None,
) -> WizardResult:
    """
    Run the initialization wizard.

    Args:
        non_interactive: If True, use defaults without prompting.
        vault_path: Pre-specified vault path for non-interactive mode.

    Returns:
        WizardResult with details of what was created.
    """
    wizard = InitWizard(non_interactive=non_interactive, vault_path=vault_path)
    return wizard.run()
