#!/usr/bin/env python3
"""
Schema definitions for triton CLI commands.

This module provides machine-readable documentation for LLM agents
to understand and correctly use triton commands.
"""

from typing import Any

# Config command schema
CONFIG_SCHEMA: dict[str, Any] = {
    "name": "triton config",
    "version": "1.1",
    "description": "Manage triton configuration file programmatically. "
    "Use these commands to manage backup targets and startup hooks without manually editing YAML.",
    "subgroups": ["target", "hook", "exclude", "encrypt", "settings"],
    "commands": {
        "view": {
            "description": "Display raw configuration file content (YAML)",
            "examples": ["triton config view"],
            "output": "Raw YAML content of config file",
        },
        "validate": {
            "description": "Validate configuration file and target paths",
            "options": {
                "--verbose, -v": {
                    "type": "flag",
                    "description": "Show detailed information including all targets",
                }
            },
            "examples": [
                "triton config validate",
                "triton config validate --verbose",
            ],
            "output": {
                "errors": "Configuration errors (if any)",
                "warnings": "Undefined environment variables",
                "missing_targets": "Target directories that don't exist",
                "missing_files": "Specific files that don't exist",
                "summary": "Count of errors and warnings",
            },
        },
        "target list": {
            "description": "List all configured backup targets with their settings",
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON array for programmatic parsing",
                },
                "--resolve": {
                    "type": "flag",
                    "description": "Resolve and show actual files for each target",
                },
                "--path": {
                    "type": "string",
                    "description": "Filter by target path (exact match after normalization)",
                    "examples": ["~/.claude", "~/.ssh"],
                },
            },
            "examples": [
                "triton config target list",
                "triton config target list --json",
                "triton config target list --resolve",
                "triton config target list --path ~/.claude --json",
            ],
            "output_fields": ["path", "files", "recursive", "encrypt_files"],
        },
        "target check": {
            "description": "Pre-flight check before adding a target. "
            "Returns conflicts, warnings, and suggested commands.",
            "use_before": "target add",
            "arguments": {
                "path": {
                    "required": True,
                    "type": "string",
                    "description": "Path to check (will be normalized to ~/ format)",
                }
            },
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                }
            },
            "examples": [
                "triton config target check ~/.docker",
                "triton config target check /Users/name/.config/app --json",
            ],
            "returns": {
                "path": "Normalized path (e.g., ~/.docker)",
                "expanded_path": "Full absolute path",
                "exists": "Whether path exists on filesystem",
                "is_directory": "True if path is a directory",
                "is_file": "True if path is a file",
                "file_count": "Number of files (if directory)",
                "conflicts": "List of reasons why target cannot be added",
                "warnings": "List of potential issues",
                "suggestions": "Recommended commands to add this target",
                "backed_up": "Whether this path is currently backed up by any target",
                "matched_target": "Target that covers this path ({path, recursive} or null)",
                "matched_pattern": "File pattern that matched (e.g., 'CLAUDE.md', '*.yml', or null)",
            },
        },
        "target add": {
            "description": "Add a new backup target to the configuration",
            "arguments": {
                "path": {
                    "required": True,
                    "type": "string",
                    "description": "Path to backup. Automatically normalized to ~/ format for portability.",
                }
            },
            "options": {
                "--files": {
                    "short": "-f",
                    "type": "string",
                    "description": "Comma-separated list of file patterns to backup",
                    "examples": ["*.md", "config.yml,settings.json", "**/*"],
                },
                "--recursive": {
                    "short": "-r",
                    "type": "flag",
                    "description": "Backup all files in directory recursively",
                },
                "--encrypt-files": {
                    "short": "-e",
                    "type": "string",
                    "description": "Comma-separated list of files to encrypt",
                },
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip creating config.yml backup before modifying",
                },
            },
            "examples": [
                "triton config target add ~/.docker --recursive",
                "triton config target add ~/project --files '*.md,*.yml'",
                "triton config target add ~/.secrets --recursive --encrypt-files 'api_key,token.json'",
            ],
            "constraints": [
                "Cannot add path that already exists as a target",
                "Cannot add path that is covered by an existing recursive target",
                "Cannot add recursive target that would cover existing targets",
                "Non-recursive targets MUST specify --files",
            ],
            "side_effects": [
                "Creates config.yml.bak.N backup (unless --no-backup)",
                "Modifies config.yml",
            ],
            "performance_tips": {
                "direct_path_optimization": {
                    "description": "File patterns with '/' (no glob chars) are direct paths",
                    "benefit": "Direct paths use stat() instead of scanning, much faster for large directories",
                    "example": {
                        "slow": "--files '**/*.env' --recursive (scans entire tree)",
                        "fast": "--files 'app/.env,config/settings.yml' (direct stat, no scan)",
                    },
                    "rule": "Use 'subdir/file.ext' format for specific files in large directories",
                },
            },
        },
        "target remove": {
            "description": "Remove a backup target from the configuration",
            "arguments": {
                "path": {
                    "required": True,
                    "type": "string",
                    "description": "Path of target to remove (will be normalized)",
                }
            },
            "options": {
                "--yes": {
                    "short": "-y",
                    "type": "flag",
                    "description": "Skip confirmation prompt",
                },
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip creating config.yml backup before modifying",
                },
            },
            "examples": [
                "triton config target remove ~/.docker",
                "triton config target remove ~/.old-config --yes",
            ],
            "side_effects": [
                "Creates config.yml.bak.N backup (unless --no-backup)",
                "Modifies config.yml",
            ],
        },
        "target modify": {
            "description": "Modify an existing backup target. Add or remove file patterns, "
            "encryption patterns, or change recursive mode without recreating the target.",
            "arguments": {
                "path": {
                    "required": True,
                    "type": "string",
                    "description": "Path of existing target to modify (will be normalized)",
                }
            },
            "options": {
                "--add-files": {
                    "type": "string",
                    "description": "Comma-separated list of file patterns to add",
                    "examples": [".gitconfig,.bashrc", "*.md,*.yml"],
                },
                "--remove-files": {
                    "type": "string",
                    "description": "Comma-separated list of file patterns to remove",
                    "examples": [".old-config", "*.bak"],
                },
                "--add-encrypt-files": {
                    "type": "string",
                    "description": "Comma-separated list of encryption patterns to add",
                    "examples": ["id_*", "*.pem,*.key"],
                },
                "--remove-encrypt-files": {
                    "type": "string",
                    "description": "Comma-separated list of encryption patterns to remove",
                },
                "--recursive": {
                    "type": "flag",
                    "description": "Enable recursive mode for target",
                },
                "--no-recursive": {
                    "type": "flag",
                    "description": "Disable recursive mode (requires files to exist)",
                },
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip creating config.yml backup before modifying",
                },
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                },
            },
            "examples": [
                "triton config target modify ~/ --add-files '.gitconfig,.gitignore_global'",
                "triton config target modify ~/ --remove-files '.old-bashrc'",
                "triton config target modify ~/.ssh --add-encrypt-files 'id_*'",
                "triton config target modify ~/.docker --recursive",
                "triton config target modify ~/project --no-recursive --add-files '*.md'",
            ],
            "constraints": [
                "Target must already exist",
                "Cannot use both --recursive and --no-recursive",
                "Disabling recursive requires at least one file pattern to remain",
                "Must specify at least one modification option",
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if patterns already exist or don't exist",
            "returns": {
                "success": "Whether operation succeeded",
                "message": "Description of what was changed",
                "changed": "Whether any actual changes were made",
                "changes": "List of specific changes made",
                "target": "Updated target configuration",
                "backup_path": "Path to config backup (if created)",
            },
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml targets section",
            ],
        },
        "target ensure": {
            "description": "Ensure a file is backed up. Idempotent: if already backed up, "
            "does nothing. Otherwise adds the file to the most specific existing target, "
            "or creates a new target.",
            "arguments": {
                "file_path": {
                    "required": True,
                    "type": "string",
                    "description": "File path to ensure is backed up (files only, not directories)",
                }
            },
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                },
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip creating config.yml backup before modifying",
                },
            },
            "examples": [
                "triton config target ensure ~/.claude/CLAUDE.md --json",
                "triton config target ensure ~/.ssh/config",
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns action='none' if file is already backed up",
            "returns": {
                "success": "Whether operation succeeded",
                "action": "One of: 'none', 'added_to_existing', 'created_target'",
                "backed_up": "Always true on success",
                "file": "Filename that was ensured",
                "target": "Target path that covers the file",
                "matched_pattern": "Pattern that matches the file (for action='none')",
                "backup_path": "Path to config backup (if config was modified)",
            },
            "constraints": [
                "Only accepts file paths, not directories",
                "Adds to the deepest (most specific) matching target to prevent duplicates",
            ],
            "side_effects": [
                "May modify an existing target's files list",
                "May create a new target",
                "Creates config backup when changes are made (unless --no-backup)",
            ],
        },
        # --- Hook commands ---
        "hook list": {
            "description": "List all configured startup hooks",
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                }
            },
            "examples": [
                "triton config hook list",
                "triton config hook list --json",
            ],
            "output_fields": ["on_startup", "timeout", "count"],
        },
        "hook add": {
            "description": "Add a new startup hook command",
            "arguments": {
                "command": {
                    "required": True,
                    "type": "string",
                    "description": "Shell command to execute on TUI startup",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                'triton config hook add "brew bundle dump --file=~/.config/triton/Brewfile --force"',
                'triton config hook add "echo Hello"',
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if command already exists",
            "constraints": [
                "Command cannot be empty",
            ],
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/",
                "Modifies config.yml hooks section",
            ],
        },
        "hook remove": {
            "description": "Remove a startup hook command",
            "arguments": {
                "command": {
                    "required": True,
                    "type": "string",
                    "description": "Exact command string to remove",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                'triton config hook remove "brew bundle dump --file=~/.config/triton/Brewfile --force"',
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if command doesn't exist",
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml hooks section",
            ],
        },
        "hook timeout": {
            "description": "Set the total timeout for all hooks",
            "arguments": {
                "seconds": {
                    "required": True,
                    "type": "integer",
                    "description": "Total time in seconds for all hooks to complete",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                "triton config hook timeout 60",
                "triton config hook timeout 10",
            ],
            "constraints": [
                "Timeout must be a positive integer",
            ],
            "default": 30,
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/",
                "Modifies config.yml hooks section",
            ],
        },
        # --- Exclude (Global Blacklist) commands ---
        "exclude list": {
            "description": "List global exclude patterns (blacklist)",
            "scope": "global",
            "config_field": "blacklist",
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON array for programmatic parsing",
                }
            },
            "examples": [
                "triton config exclude list",
                "triton config exclude list --json",
            ],
        },
        "exclude add": {
            "description": "Add a global exclude pattern",
            "scope": "global",
            "config_field": "blacklist",
            "arguments": {
                "pattern": {
                    "required": True,
                    "type": "string",
                    "description": "Glob pattern for files to exclude from backup",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                'triton config exclude add "*.log"',
                'triton config exclude add ".DS_Store"',
                'triton config exclude add "*.tmp"',
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if pattern already exists",
            "constraints": [
                "Pattern cannot be empty",
            ],
            "warnings": [
                "Pattern '*' will match everything",
                "Patterns with '//' may indicate typo",
            ],
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml blacklist section",
            ],
        },
        "exclude remove": {
            "description": "Remove a global exclude pattern",
            "scope": "global",
            "config_field": "blacklist",
            "arguments": {
                "pattern": {
                    "required": True,
                    "type": "string",
                    "description": "Exact pattern to remove",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                'triton config exclude remove "*.log"',
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if pattern doesn't exist",
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml blacklist section",
            ],
        },
        # --- Encrypt (Global Encryption Patterns) commands ---
        "encrypt list": {
            "description": "List global encryption patterns",
            "scope": "global",
            "config_field": "encrypt_list",
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON array for programmatic parsing",
                }
            },
            "examples": [
                "triton config encrypt list",
                "triton config encrypt list --json",
            ],
        },
        "encrypt add": {
            "description": "Add a global encryption pattern",
            "scope": "global",
            "config_field": "encrypt_list",
            "arguments": {
                "pattern": {
                    "required": True,
                    "type": "string",
                    "description": "Glob pattern for files to encrypt during backup",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                'triton config encrypt add "id_rsa*"',
                'triton config encrypt add "*.pem"',
                'triton config encrypt add "*secret*"',
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if pattern already exists",
            "constraints": [
                "Pattern cannot be empty",
            ],
            "warnings": [
                "Pattern '*' will match everything",
                "Patterns with '//' may indicate typo",
            ],
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml encrypt_list section",
            ],
            "note": "Target-specific encrypt_files take precedence over global encrypt_list",
        },
        "encrypt remove": {
            "description": "Remove a global encryption pattern",
            "scope": "global",
            "config_field": "encrypt_list",
            "arguments": {
                "pattern": {
                    "required": True,
                    "type": "string",
                    "description": "Exact pattern to remove",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                'triton config encrypt remove "id_rsa*"',
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if pattern doesn't exist",
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml encrypt_list section",
            ],
        },
        # --- Settings (Scalar Values) commands ---
        "settings list": {
            "description": "List all available settings with current values",
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON array for programmatic parsing",
                }
            },
            "examples": [
                "triton config settings list",
                "triton config settings list --json",
            ],
            "output_fields": [
                "key",
                "value",
                "default",
                "is_default",
                "type",
                "description",
                "required",
                "choices",
            ],
        },
        "settings get": {
            "description": "Get a setting value",
            "arguments": {
                "key": {
                    "required": True,
                    "type": "string",
                    "description": "Setting key (e.g., 'max_file_size_mb', 'repository.auto_pull')",
                }
            },
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                }
            },
            "examples": [
                "triton config settings get max_file_size_mb",
                "triton config settings get repository.auto_pull --json",
            ],
            "returns": {
                "key": "Setting key",
                "value": "Current value (or default if not set)",
                "default": "Default value",
                "type": "Value type (boolean, number, string, enum)",
                "description": "Setting description",
                "choices": "Available choices for enum types",
                "required": "Whether setting is required",
            },
        },
        "settings set": {
            "description": "Set a setting value",
            "arguments": {
                "key": {
                    "required": True,
                    "type": "string",
                    "description": "Setting key",
                },
                "value": {
                    "required": True,
                    "type": "string",
                    "description": "Value to set (parsed based on type)",
                },
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                "triton config settings set max_file_size_mb 10",
                "triton config settings set repository.auto_pull false",
                "triton config settings set tui.theme nord",
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if value already set",
            "value_parsing": {
                "boolean": "true/false, on/off, yes/no, 1/0",
                "number": "Numeric value (integer or float)",
                "string": "String value as-is",
                "enum": "Must be one of the allowed choices",
            },
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Modifies config.yml",
            ],
        },
        "settings unset": {
            "description": "Unset a setting (reset to default)",
            "arguments": {
                "key": {
                    "required": True,
                    "type": "string",
                    "description": "Setting key to unset",
                }
            },
            "options": {
                "--no-backup": {
                    "type": "flag",
                    "description": "Skip config backup before modifying",
                }
            },
            "examples": [
                "triton config settings unset tui.theme",
                "triton config settings unset max_file_size_mb",
            ],
            "idempotent": True,
            "idempotent_behavior": "Returns success with 'changed: false' if already unset",
            "constraints": [
                "Cannot unset required settings (e.g., repository.path)",
            ],
            "side_effects": [
                "Creates config backup in archives/config/{timestamp}/ (only when change is made)",
                "Removes setting from config.yml (uses default value)",
            ],
        },
    },
    "available_settings": {
        "description": "Scalar settings that can be managed via 'triton config settings'",
        "keys": {
            "max_file_size_mb": {
                "type": "number",
                "default": 5.0,
                "required": False,
                "description": "Maximum file size in MB (0 = no limit)",
            },
            "encryption.enabled": {
                "type": "boolean",
                "default": False,
                "required": False,
                "description": "Enable AES-256-GCM encryption for sensitive files",
            },
            "encryption.key_file": {
                "type": "string",
                "default": "${TRITON_DIR:-~/.config/triton}/master.key",
                "required": False,
                "description": "Path to encryption master key file",
            },
            "repository.path": {
                "type": "string",
                "default": None,
                "required": True,
                "description": "Backup destination directory path",
            },
            "repository.use_hostname": {
                "type": "boolean",
                "default": True,
                "required": False,
                "description": "Auto-detect machine name from hostname",
            },
            "repository.machine_name": {
                "type": "string",
                "default": None,
                "required": False,
                "description": "Override auto-detected machine name (null = use hostname)",
            },
            "repository.auto_pull": {
                "type": "boolean",
                "default": True,
                "required": False,
                "description": "Automatically run git pull when TUI starts",
            },
            "tui.theme": {
                "type": "enum",
                "default": None,
                "required": False,
                "description": "TUI color theme",
                "choices": ["nord", "gruvbox", "textual-dark"],
            },
            "tui.hide_system_files": {
                "type": "boolean",
                "default": True,
                "required": False,
                "description": "Hide system files in file list",
            },
        },
    },
    "workflows": {
        "target": {
            "description": "Recommended workflow for adding a new target",
            "steps": [
                {
                    "step": 1,
                    "command": "triton config target check <path> --json",
                    "purpose": "Check for conflicts and get suggested command",
                },
                {
                    "step": 2,
                    "action": "Review the 'conflicts' array - if empty, proceed",
                    "on_conflict": "Choose different path or remove conflicting target first",
                },
                {
                    "step": 3,
                    "command": "triton config target add <path> [options]",
                    "purpose": "Add the target using suggested options from step 1",
                },
                {
                    "step": 4,
                    "command": "triton config target list --json",
                    "purpose": "Verify the target was added correctly",
                },
            ],
        },
        "target_modify": {
            "description": "Workflow for modifying an existing target (add/remove files)",
            "use_case": "Add files to existing target without recreating",
            "steps": [
                {
                    "step": 1,
                    "command": "triton config target list --json",
                    "purpose": "Find target and review current configuration",
                },
                {
                    "step": 2,
                    "command": "triton config target modify <path> --add-files '<patterns>' --json",
                    "purpose": "Add file patterns to existing target (idempotent)",
                },
                {
                    "step": 3,
                    "command": "triton config target list --json",
                    "purpose": "Verify the target was modified correctly",
                },
            ],
            "examples": [
                {
                    "scenario": "Add dotfiles to home directory target",
                    "command": "triton config target modify ~/ --add-files '.gitconfig,.gitignore_global'",
                },
                {
                    "scenario": "Add encryption for SSH keys",
                    "command": "triton config target modify ~/.ssh --add-encrypt-files 'id_*'",
                },
                {
                    "scenario": "Convert to recursive mode",
                    "command": "triton config target modify ~/.config/app --recursive",
                },
            ],
        },
        "hook": {
            "description": "Recommended workflow for managing hooks",
            "steps": [
                {
                    "step": 1,
                    "command": "triton config hook list --json",
                    "purpose": "Check current hooks configuration",
                },
                {
                    "step": 2,
                    "command": 'triton config hook add "<command>"',
                    "purpose": "Add new hook command",
                },
                {
                    "step": 3,
                    "command": "triton hooks run --dry-run",
                    "purpose": "Verify hooks without executing",
                },
                {
                    "step": 4,
                    "command": "triton hooks run",
                    "purpose": "Test hook execution",
                },
            ],
        },
        "exclude": {
            "description": "Workflow for managing global exclude patterns",
            "scope": "global",
            "steps": [
                {
                    "step": 1,
                    "command": "triton config exclude list --json",
                    "purpose": "Check current exclude patterns",
                },
                {
                    "step": 2,
                    "command": 'triton config exclude add "<pattern>"',
                    "purpose": "Add new exclude pattern (idempotent)",
                },
                {
                    "step": 3,
                    "command": "triton config validate",
                    "purpose": "Verify configuration is valid",
                },
            ],
        },
        "encrypt": {
            "description": "Workflow for managing global encryption patterns",
            "scope": "global",
            "steps": [
                {
                    "step": 1,
                    "command": "triton config encrypt list --json",
                    "purpose": "Check current encryption patterns",
                },
                {
                    "step": 2,
                    "command": 'triton config encrypt add "<pattern>"',
                    "purpose": "Add new encryption pattern (idempotent)",
                },
                {
                    "step": 3,
                    "command": "triton config validate",
                    "purpose": "Verify configuration is valid",
                },
            ],
            "note": "Encryption must be enabled in config for patterns to take effect",
        },
        "settings": {
            "description": "Workflow for managing scalar settings",
            "steps": [
                {
                    "step": 1,
                    "command": "triton config settings list --json",
                    "purpose": "Check all available settings and current values",
                },
                {
                    "step": 2,
                    "command": "triton config settings set <key> <value>",
                    "purpose": "Set a setting value (idempotent)",
                },
                {
                    "step": 3,
                    "command": "triton config validate",
                    "purpose": "Verify configuration is valid",
                },
            ],
            "note": "Use 'settings unset' to reset a setting to its default value",
        },
    },
    "related_commands": {
        "triton hooks run": {
            "description": "Execute all configured startup hooks",
            "options": {"--dry-run": "Show what would be executed without running"},
            "note": "This is an action command, not a config command",
        },
        "triton hooks list": {
            "description": "Shortcut for 'triton config hook list'",
            "options": {"--json": "Output as JSON for programmatic parsing"},
        },
        "triton init config": {
            "description": "Generate default configuration file",
            "options": {
                "-o, --output": "Output file path",
                "--global-config": "Create in ~/.config/triton/config.yml",
            },
            "note": "Use this to create initial config.yml",
        },
        "triton init key": {
            "description": "Generate encryption key",
            "options": {
                "-o, --output": "Output file path (default: ~/.config/triton/master.key)",
                "-f, --force": "Force overwrite existing key (WARNING: data loss)",
            },
            "note": "Refuses to overwrite existing key without --force to prevent data loss",
        },
    },
    "path_normalization": {
        "description": "Paths are automatically normalized for cross-machine portability",
        "rules": [
            "/Users/username/.ssh -> ~/.ssh",
            "/home/username/.config -> ~/.config",
            "./relative/path -> ~/full/path/to/relative/path (if under home)",
            "/etc/hosts -> /etc/hosts (paths outside home unchanged)",
        ],
    },
    "backup_behavior": {
        "description": "Config modifications create automatic backups",
        "format": "archives/config/{timestamp}/config.yml",
        "timestamp_format": "YYYYmmdd_HHMMSS (e.g., 20251225_143025)",
        "location": "$TRITON_DIR/archives/config/ (default: ~/.config/triton/archives/config/)",
        "disable": "Use --no-backup flag",
        "manage_with": "triton archive list/show/clean commands",
    },
}

# Init command schema
INIT_SCHEMA: dict[str, Any] = {
    "name": "triton init",
    "version": "1.0",
    "description": "Initialize triton with interactive setup wizard. "
    "Creates configuration directory, encryption key, vault, and initial targets.",
    "commands": {
        "wizard": {
            "description": "Interactive setup wizard (default when running 'triton init')",
            "options": {
                "--non-interactive, -y": {
                    "type": "flag",
                    "description": "Run setup with defaults, no prompts",
                },
                "--vault-path, -v": {
                    "type": "string",
                    "description": "Vault (repository) path for non-interactive mode",
                },
            },
            "examples": [
                "triton init",
                "triton init -y",
                "triton init -y --vault-path ~/my-vault",
            ],
            "wizard_steps": [
                {
                    "step": 1,
                    "name": "Configuration Directory",
                    "description": "Creates ~/.config/triton directory",
                    "auto": True,
                },
                {
                    "step": 2,
                    "name": "Encryption Key",
                    "description": "Generates master.key for AES-256-GCM encryption",
                    "warning": "Key must be backed up separately - if lost, encrypted files cannot be recovered",
                    "location": "~/.config/triton/master.key",
                },
                {
                    "step": 3,
                    "name": "Vault Setup",
                    "description": "Configure backup repository location",
                    "options": [
                        "Create new local directory",
                        "Use existing Git repository",
                        "Skip for now",
                    ],
                    "recommendation": "Use a PRIVATE Git repository",
                },
                {
                    "step": 4,
                    "name": "Backup Targets",
                    "description": "Select initial files/directories to backup",
                    "presets": [
                        {
                            "path": "~/.ssh",
                            "description": "SSH keys and configs (auto-encrypted)",
                        },
                        {
                            "path": "~/.aws",
                            "description": "AWS credentials (auto-encrypted)",
                        },
                        {"path": "~/.config", "description": "Application configs"},
                        {"path": "~/.zshrc", "description": "Shell configuration"},
                        {"path": "~/.gitconfig", "description": "Git configuration"},
                    ],
                },
            ],
            "output": {
                "created_files": [
                    "~/.config/triton/config.yml",
                    "~/.config/triton/master.key",
                ],
                "vault_directory": "User-specified location",
            },
        },
        "config": {
            "description": "Generate default configuration file only",
            "options": {
                "--output, -o": {
                    "type": "string",
                    "description": "Output file path (default: ./config-template.yml)",
                },
                "--global-config": {
                    "type": "flag",
                    "description": "Create in ~/.config/triton/config.yml",
                },
            },
            "examples": [
                "triton init config",
                "triton init config --global-config",
                "triton init config -o ~/custom-config.yml",
            ],
        },
        "key": {
            "description": "Generate encryption key only",
            "options": {
                "--output, -o": {
                    "type": "string",
                    "description": "Output file path (default: ~/.config/triton/master.key)",
                },
                "--force, -f": {
                    "type": "flag",
                    "description": "Force overwrite existing key (WARNING: encrypted data will be lost)",
                },
            },
            "examples": [
                "triton init key",
                "triton init key -o ~/backup.key",
                "triton init key --force",
            ],
            "warning": "Overwriting an existing key will make all previously encrypted files unrecoverable",
        },
    },
    "workflows": {
        "new_user_setup": {
            "description": "Recommended workflow for first-time setup",
            "steps": [
                {
                    "step": 1,
                    "command": "triton init",
                    "purpose": "Run interactive wizard to set up everything",
                },
                {
                    "step": 2,
                    "command": "triton backup --dry-run",
                    "purpose": "Preview what will be backed up",
                },
                {
                    "step": 3,
                    "command": "triton backup",
                    "purpose": "Create your first backup",
                },
                {
                    "step": 4,
                    "command": "triton git-commit-push",
                    "purpose": "Commit and push to remote repository",
                },
            ],
        },
        "scripted_setup": {
            "description": "Non-interactive setup for automation",
            "steps": [
                {
                    "step": 1,
                    "command": "triton init -y --vault-path ~/dotfiles-vault",
                    "purpose": "Run wizard with defaults",
                },
                {
                    "step": 2,
                    "command": "triton config target add ~/.ssh -r",
                    "purpose": "Add SSH directory (already in defaults, but example)",
                },
                {
                    "step": 3,
                    "command": "triton backup",
                    "purpose": "Create backup",
                },
            ],
        },
    },
    "security_notes": {
        "encryption_key": {
            "location": "~/.config/triton/master.key",
            "algorithm": "AES-256-GCM with HKDF key derivation",
            "permissions": "0600 (owner read/write only)",
            "backup_recommendation": "Store in password manager or secure USB drive",
            "warning": "Never commit master.key to your vault repository",
        },
        "vault_repository": {
            "recommendation": "Use a PRIVATE repository",
            "reason": "Vault contains encrypted sensitive files",
            "note": "Even encrypted, private repos add an extra layer of security",
        },
    },
}

# Archive command schema
ARCHIVE_SCHEMA: dict[str, Any] = {
    "name": "triton archive",
    "version": "1.0",
    "description": "Manage backup archives created by triton. "
    "Archives are created when config is modified (config backups) or when restore overwrites existing files (restore archives).",
    "archive_types": {
        "config": {
            "description": "Backups of config.yml created during target add/remove operations",
            "location": "$TRITON_DIR/archives/config/{timestamp}/",
            "created_by": ["triton config target add", "triton config target remove"],
        },
        "restore": {
            "description": "Backups of existing files that were overwritten during restore",
            "location": "$TRITON_DIR/archives/{timestamp}/",
            "created_by": ["triton restore"],
        },
    },
    "commands": {
        "list": {
            "description": "List all archives sorted by creation time (newest first)",
            "options": {
                "--type": {
                    "type": "choice",
                    "choices": ["config", "restore", "all"],
                    "default": "all",
                    "description": "Filter archives by type",
                },
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                },
            },
            "examples": [
                "triton archive list",
                "triton archive list --type config",
                "triton archive list --json",
            ],
            "output_fields": [
                "type (config or restore)",
                "created (datetime)",
                "timestamp (directory name)",
                "file_count",
                "total_size",
            ],
        },
        "show": {
            "description": "Show detailed contents of a specific archive",
            "arguments": {
                "timestamp": {
                    "required": True,
                    "type": "string",
                    "description": "Archive timestamp (e.g., 20251225_143025). Get from 'triton archive list'.",
                }
            },
            "options": {
                "--json": {
                    "type": "flag",
                    "description": "Output as JSON for programmatic parsing",
                },
            },
            "examples": [
                "triton archive show 20251225_143025",
                "triton archive show 20251225_143025 --json",
            ],
            "returns": {
                "path": "Full path to archive directory",
                "type": "Archive type (config or restore)",
                "timestamp": "Archive timestamp",
                "created": "Creation datetime",
                "file_count": "Number of files in archive",
                "total_size": "Total size of archived files",
                "files": "List of archived files with sizes",
            },
        },
        "clean": {
            "description": "Delete old archives to free disk space",
            "options": {
                "--keep": {
                    "type": "integer",
                    "description": "Keep the N most recent archives (per type when --type=all)",
                },
                "--older-than": {
                    "type": "integer",
                    "description": "Delete archives older than N days",
                },
                "--type": {
                    "type": "choice",
                    "choices": ["config", "restore", "all"],
                    "default": "all",
                    "description": "Filter archives by type",
                },
                "--dry-run": {
                    "type": "flag",
                    "description": "Show what would be deleted without actually deleting",
                },
                "--force": {
                    "short": "-f",
                    "type": "flag",
                    "description": "Skip confirmation prompt",
                },
            },
            "examples": [
                "triton archive clean --keep 5",
                "triton archive clean --older-than 30",
                "triton archive clean --type config --keep 3",
                "triton archive clean --keep 5 --dry-run",
                "triton archive clean --older-than 7 --force",
            ],
            "constraints": [
                "Must specify either --keep or --older-than (or both)",
                "When --type=all and --keep=N, keeps N of each type separately",
            ],
            "side_effects": [
                "Permanently deletes archive directories",
                "Frees disk space",
            ],
        },
    },
    "workflow": {
        "description": "Recommended workflow for archive management",
        "steps": [
            {
                "step": 1,
                "command": "triton archive list",
                "purpose": "View all archives and their sizes",
            },
            {
                "step": 2,
                "command": "triton archive show <timestamp>",
                "purpose": "Inspect specific archive contents before cleanup",
            },
            {
                "step": 3,
                "command": "triton archive clean --keep 5 --dry-run",
                "purpose": "Preview what would be deleted",
            },
            {
                "step": 4,
                "command": "triton archive clean --keep 5",
                "purpose": "Actually delete old archives",
            },
        ],
    },
    "timestamp_format": {
        "description": "All archives use consistent timestamp format",
        "format": "YYYYmmdd_HHMMSS",
        "example": "20251225_143025 represents 2025-12-25 14:30:25",
    },
}

# Config file (config.yml) schema - documents all configuration options
CONFIG_FILE_SCHEMA: dict[str, Any] = {
    "name": "config.yml",
    "version": "1.0",
    "description": "Schema for triton configuration file (~/.config/triton/config.yml)",
    "root_key": "config",
    "sections": {
        "repository": {
            "description": "Repository and machine settings",
            "required": True,
            "fields": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Backup destination directory path",
                    "supports_env_vars": True,
                    "example": "~/dotfiles-backup or ${TRITON_REPO_PATH}",
                },
                "use_hostname": {
                    "type": "boolean",
                    "default": True,
                    "description": "Auto-detect machine name from hostname",
                },
                "machine_name": {
                    "type": "string",
                    "required": False,
                    "description": "Override auto-detected machine name",
                },
                "excluded_directories": {
                    "type": "array[string]",
                    "required": False,
                    "description": "Directories to exclude from machine detection in repository",
                    "example": ["docs", "backup", "temp"],
                },
                "auto_pull": {
                    "type": "boolean",
                    "default": True,
                    "description": "Automatically run git pull when TUI starts",
                },
            },
        },
        "targets": {
            "description": "List of backup targets",
            "required": True,
            "type": "array",
            "item_fields": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Directory or file path to backup",
                },
                "files": {
                    "type": "array[string]",
                    "required": False,
                    "description": "File patterns to include (gitignore-like syntax)",
                    "example": ["**/*", ".zshrc", "!*.log"],
                },
                "recursive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable recursive file collection",
                },
                "encrypt_files": {
                    "type": "array[string]",
                    "required": False,
                    "description": "File patterns to encrypt (overrides global encrypt_list)",
                },
            },
            "performance_optimization": {
                "description": "Direct path optimization for large directories",
                "rule": "Files patterns containing '/' (without glob chars) are treated as direct paths",
                "benefit": "Direct paths skip directory scanning, using stat() instead of rglob()",
                "examples": {
                    "direct_path": {
                        "pattern": "app/config/.env",
                        "behavior": "Checks path/app/config/.env directly (no scan)",
                    },
                    "glob_pattern": {
                        "pattern": "*.yml",
                        "behavior": "Scans directory and matches files",
                    },
                },
                "best_practice": [
                    "For large directories, prefer direct paths over glob patterns",
                    "Use 'subdir/file.ext' instead of '**/*.ext' when targeting specific files",
                    "Direct paths work without 'recursive: true'",
                    "Mixing direct paths and patterns: direct paths processed first, then patterns",
                ],
                "example_config": {
                    "inefficient": {
                        "path": "~/large-repo",
                        "files": ["**/*.env"],
                        "recursive": True,
                        "note": "Scans entire directory tree",
                    },
                    "optimized": {
                        "path": "~/large-repo",
                        "files": ["app/.env", "config/settings.yml"],
                        "note": "Direct stat() for each file, no scanning",
                    },
                },
            },
        },
        "encryption": {
            "description": "Encryption settings for sensitive files",
            "required": False,
            "fields": {
                "enabled": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable AES-256-GCM encryption",
                },
                "key_file": {
                    "type": "string",
                    "required": False,
                    "description": "Path to encryption key file",
                    "default": "~/.config/triton/master.key",
                },
            },
        },
        "blacklist": {
            "description": "Global file patterns to always exclude",
            "required": False,
            "type": "array[string]",
            "example": [".DS_Store", "*.log", "*.tmp"],
        },
        "encrypt_list": {
            "description": "Global file patterns to encrypt",
            "required": False,
            "type": "array[string]",
            "example": ["id_rsa*", "*.pem", "*secret*"],
        },
        "max_file_size_mb": {
            "description": "Skip files larger than this size (0 = no limit)",
            "required": False,
            "type": "number",
            "default": 5.0,
        },
        "tui": {
            "description": "TUI (Terminal User Interface) settings",
            "required": False,
            "fields": {
                "hide_system_files": {
                    "type": "boolean",
                    "default": True,
                    "description": "Hide system files in file list",
                },
                "system_file_patterns": {
                    "type": "array[string]",
                    "required": False,
                    "description": "Patterns for system files to hide",
                    "default": [".DS_Store", "._*", "Thumbs.db", "desktop.ini"],
                },
                "theme": {
                    "type": "string",
                    "required": False,
                    "description": "TUI color theme",
                    "choices": ["nord", "gruvbox", "textual-dark"],
                },
            },
        },
        "hooks": {
            "description": "Startup hooks configuration",
            "required": False,
            "fields": {
                "on_startup": {
                    "type": "array[string]",
                    "required": False,
                    "description": "Shell commands to execute when TUI starts",
                    "example": [
                        "brew bundle dump --file=${TRITON_DIR}/Brewfile --force",
                        "echo 'Hooks executed'",
                    ],
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "Total timeout in seconds for all hooks (shared)",
                },
            },
            "behavior": {
                "execution_order": "Hooks execute sequentially in list order",
                "timeout": "Total timeout shared across all hooks. If time runs out, remaining hooks are skipped.",
                "failure_handling": "Failed hooks are logged but do not block TUI startup",
                "skip_option": "Use 'triton -S' or 'triton --skip-startup' to skip hooks and auto-pull",
            },
        },
    },
    "environment_variables": {
        "description": "Supported environment variable syntax",
        "patterns": {
            "${VAR}": "Substitute with environment variable value",
            "${VAR:-default}": "Use default if VAR is not set",
        },
        "common_vars": {
            "TRITON_DIR": "Custom config directory (default: ~/.config/triton)",
            "TRITON_REPO_PATH": "Repository path for backup destination",
        },
    },
}


def get_config_schema() -> dict[str, Any]:
    """Get the config command schema (includes target and hook subcommands)."""
    return CONFIG_SCHEMA


def get_archive_schema() -> dict[str, Any]:
    """Get the archive command schema."""
    return ARCHIVE_SCHEMA


def get_init_schema() -> dict[str, Any]:
    """Get the init command schema."""
    return INIT_SCHEMA


def get_config_file_schema() -> dict[str, Any]:
    """Get the config.yml file schema."""
    return CONFIG_FILE_SCHEMA


def get_full_schema() -> dict[str, Any]:
    """Get the full triton CLI schema."""
    return {
        "name": "triton",
        "description": "Dotfiles management tool with TUI and CLI interfaces",
        "schema_hint": "Use 'triton <command> --schema' for detailed command documentation",
        "available_schemas": [
            "triton init --schema",
            "triton config --schema",
            "triton archive --schema",
        ],
        "init": INIT_SCHEMA,
        "config": CONFIG_SCHEMA,
        "archive": ARCHIVE_SCHEMA,
        "config_file": CONFIG_FILE_SCHEMA,
    }
