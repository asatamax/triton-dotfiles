---
name: triton-config
description: Manage triton dotfiles backup targets and startup hooks via CLI. Use when user asks to add, remove, or list backup targets in triton configuration, manage startup hooks, or mentions "triton config", "dotfiles backup target", "triton hook", or wants to configure which files/directories to backup with triton.
---

# Triton Config Management

Manage backup targets, startup hooks, exclude/encrypt patterns, and settings in triton's config.yml without manual YAML editing.

**CRITICAL**: Never run `triton` without arguments - it launches an interactive TUI.

## Quick Reference

### Target Commands
| Task | Command |
|------|---------|
| List targets | `triton config target list --json` |
| List by path | `triton config target list --path <path> --json` |
| Check coverage | `triton config target check <path> --json` |
| Ensure backed up | `triton config target ensure <file> --json` |
| Add recursive | `triton config target add <path> --recursive` |
| Add specific files | `triton config target add <path> --files 'file1,file2'` |
| Modify: add files | `triton config target modify <path> --add-files 'file1,file2'` |
| Modify: remove files | `triton config target modify <path> --remove-files 'file1'` |
| Modify: add encrypt | `triton config target modify <path> --add-encrypt-files 'secret*'` |
| Modify: set recursive | `triton config target modify <path> --recursive` |
| Remove target | `triton config target remove <path> --yes` |

### Hook Commands
| Task | Command |
|------|---------|
| List hooks | `triton config hook list --json` |
| Add hook | `triton config hook add '<command>'` |
| Remove hook | `triton config hook remove '<command>'` |
| Set timeout | `triton config hook timeout <seconds>` |

### Exclude Commands (Global Blacklist)
| Task | Command |
|------|---------|
| List patterns | `triton config exclude list --json` |
| Add pattern | `triton config exclude add '<pattern>'` |
| Remove pattern | `triton config exclude remove '<pattern>'` |

### Encrypt Commands (Global Encryption)
| Task | Command |
|------|---------|
| List patterns | `triton config encrypt list --json` |
| Add pattern | `triton config encrypt add '<pattern>'` |
| Remove pattern | `triton config encrypt remove '<pattern>'` |

### Settings Commands
| Task | Command |
|------|---------|
| List all settings | `triton config settings list --json` |
| Get setting | `triton config settings get <key> --json` |
| Set setting | `triton config settings set <key> <value>` |
| Reset to default | `triton config settings unset <key>` |

### Validation
| Task | Command |
|------|---------|
| Validate config | `triton config validate` |

For full command schema, run `triton config --schema`.

## Workflow: Ensure File Backup (Recommended)

The simplest way to ensure a file is backed up. Idempotent and handles all logic automatically.

```bash
# Single command - checks, creates/modifies targets as needed
triton config target ensure ~/.claude/CLAUDE.md --json
```

**Behavior:**
- If already backed up: returns `action: "none"` (no changes)
- If parent target exists: adds file to that target (`action: "added_to_existing"`)
- If no target exists: creates new target for parent directory (`action: "created_target"`)
- Picks the **deepest (most specific) target** to prevent duplicates with nested targets

**JSON response:**
```json
{"success": true, "action": "none", "backed_up": true, "file": "CLAUDE.md", "target": "~/.claude", "matched_pattern": "CLAUDE.md"}
```

## Workflow: Check Backup Coverage

Check if a path is currently backed up before deciding what to do.

```bash
triton config target check ~/.claude/CLAUDE.md --json
```

**Key fields in response:**
- `backed_up`: Whether the path is currently backed up
- `matched_target`: Target that covers this path (`{"path": "~/.claude", "recursive": true}`)
- `matched_pattern`: Pattern that matched (e.g., `"CLAUDE.md"`, `"*.yml"`)
- `conflicts`, `warnings`, `suggestions`: For adding as new target

## Workflow: Add a New Target

### Step 1: Gather Requirements

Ask user for:
1. **Path**: Directory or file to backup (e.g., `~/.config/myapp`, `.` for current directory)
2. **Files**: Specific files to backup, or all files recursively
3. **Encryption**: Any files requiring encryption (optional)

### Step 2: Pre-flight Check

```bash
triton config target check <path> --json
```

Verify:
- `conflicts` array is empty
- `exists` is true
- Review `suggestions` for recommended command

### Step 3: Add Target

**For recursive backup (all files in directory):**
```bash
triton config target add <path> --recursive
```

**For specific files only:**
```bash
triton config target add <path> --files 'file1.md,file2.yml'
```

**With encryption:**
```bash
triton config target add <path> --recursive --encrypt-files 'secret.key,credentials.json'
```

### Step 4: Verify

```bash
triton config target list --json
```

Confirm the new target appears with correct settings.

## Workflow: Modify Existing Target

Use `target modify` to add/remove files from an existing target without recreating it.

### Add Files to Existing Target

```bash
# Add dotfiles to home directory target
triton config target modify ~/ --add-files '.gitconfig,.gitignore_global' --json
```

### Remove Files from Target

```bash
# Remove old config files
triton config target modify ~/ --remove-files '.old-bashrc,.deprecated-config'
```

### Add Encryption Patterns

```bash
# Add encryption for sensitive files
triton config target modify ~/.ssh --add-encrypt-files 'id_*,*.pem'
```

### Change Recursive Mode

```bash
# Enable recursive mode
triton config target modify ~/.config/myapp --recursive

# Disable recursive mode (requires files to exist)
triton config target modify ~/.config/myapp --no-recursive --add-files 'config.yml'
```

### Combined Operations

```bash
# Add files and enable recursive in one command
triton config target modify ~/.docker --add-files 'config.json' --recursive --json
```

**Note**: All modify operations are idempotent - adding existing patterns returns `changed: false`.

## Workflow: Manage Exclude Patterns

Exclude patterns define files to skip globally during backup (blacklist).

```bash
# List current patterns
triton config exclude list --json

# Add pattern (idempotent)
triton config exclude add '*.log'
triton config exclude add '.DS_Store'

# Verify
triton config validate
```

## Workflow: Manage Encrypt Patterns

Encrypt patterns define files to encrypt globally during backup.

```bash
# List current patterns
triton config encrypt list --json

# Add pattern (idempotent)
triton config encrypt add 'id_rsa*'
triton config encrypt add '*.pem'

# Note: Encryption must be enabled for patterns to take effect
triton config settings get encryption.enabled
```

## Workflow: Manage Settings

Settings are scalar configuration values.

```bash
# List all settings with current/default values
triton config settings list --json

# Get specific setting
triton config settings get max_file_size_mb --json

# Set value (idempotent)
triton config settings set max_file_size_mb 10
triton config settings set repository.auto_pull false
triton config settings set tui.theme nord

# Reset to default
triton config settings unset tui.theme
```

### Available Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_file_size_mb` | number | 5.0 | Maximum file size in MB |
| `encryption.enabled` | boolean | false | Enable AES-256-GCM encryption |
| `encryption.key_file` | string | `${TRITON_DIR}/master.key` | Encryption key file path |
| `repository.path` | string | (required) | Backup destination directory |
| `repository.auto_pull` | boolean | true | Auto git pull on TUI start |
| `repository.use_hostname` | boolean | true | Auto-detect machine name |
| `repository.machine_name` | string | null | Override machine name |
| `tui.theme` | enum | null | Theme: nord, gruvbox, textual-dark |
| `tui.hide_system_files` | boolean | true | Hide system files in TUI |

## Common Patterns

### Ensure a Single File is Backed Up
```bash
# Simplest approach - handles everything automatically
triton config target ensure ~/.claude/CLAUDE.md --json
```

### Current Directory with Specific Files
```bash
triton config target check . --json
triton config target add . --files 'CLAUDE.md,AGENTS.md'
```

### Config Directory (Recursive)
```bash
triton config target check ~/.config/myapp --json
triton config target add ~/.config/myapp --recursive
```

### Sensitive Files with Encryption
```bash
triton config target add ~/.myapp --files 'config.yml,secrets.json' --encrypt-files 'secrets.json'
```

### Filter Target List
```bash
# Get details of a specific target
triton config target list --path ~/.claude --json
```

### Global Log Exclusion
```bash
triton config exclude add '*.log'
triton config exclude add '*.tmp'
```

## Constraints

- Non-recursive targets **must** specify `--files`
- Cannot add duplicate paths
- Cannot add path already covered by recursive parent target
- Paths auto-normalize to `~/` format for portability
- All add/remove/modify/ensure commands are idempotent
- Required settings (e.g., `repository.path`) cannot be unset
- `target modify`: Cannot use `--recursive` and `--no-recursive` together
- `target modify`: Disabling recursive requires at least one file pattern to remain
- `target ensure`: Only accepts file paths, not directories

## Backup Behavior

Config modifications create automatic backups:
- Format: `archives/config/{timestamp}/config.yml`
- Location: `$TRITON_DIR/archives/config/`
- Disable: Use `--no-backup` flag
