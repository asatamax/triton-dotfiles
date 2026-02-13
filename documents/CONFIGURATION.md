# Triton Configuration Reference

Configuration reference for Triton Dotfiles.

## Overview

Triton stores its configuration in `~/.config/triton/` (or `$TRITON_DIR`):

```
~/.config/triton/
├── config.yml    # Backup targets and settings
├── master.key    # Encryption key (KEEP THIS SAFE!)
└── archives/     # Safety backups before restore
    ├── config/   # Config file backups
    └── restore/  # Pre-restore file backups
```

> **For AI agents**: Use `triton config --schema` to get machine-readable command specifications.

---

## Configuration File (config.yml)

### repository (Required)

Backup destination settings.

```yaml
config:
  repository:
    path: ~/dotfiles-backup          # Backup destination (required)
    use_hostname: true               # Auto-detect machine name (default: true)
    # machine_name: "MyMachine"      # Override machine name
    auto_pull: true                  # Auto git pull on TUI start (default: true)
    # excluded_directories:          # Exclude from machine detection
    #   - "docs"
    #   - "backup"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `path` | string | - | **Required.** Backup destination directory |
| `use_hostname` | boolean | `true` | Auto-detect machine name from hostname |
| `machine_name` | string | - | Override auto-detected machine name |
| `auto_pull` | boolean | `true` | Run `git pull` when TUI starts |
| `excluded_directories` | list | - | Directories to exclude from machine detection |

### targets (Required)

Define what to backup. Each target specifies a path and file patterns.

```yaml
config:
  targets:
    # All files in directory (recursive)
    - path: ~/.ssh
      files: ["**/*"]
      recursive: true

    # Specific files only (non-recursive)
    - path: ~/
      files: [".zshrc", ".bashrc", ".gitconfig"]

    # Pattern with exclusions
    - path: ~/projects
      files:
        - "**/*.md"              # Include all markdown
        - "!**/node_modules/**"  # Exclude node_modules
      recursive: true

    # Target-specific encryption
    - path: ~/.m2
      files: ["settings.xml", "toolchains.xml"]
      encrypt_files: ["settings.xml"]  # Override global encrypt_list
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `path` | string | - | **Required.** Directory to backup |
| `files` | list | `[]` | File patterns to include/exclude |
| `recursive` | boolean | `false` | Search subdirectories |
| `encrypt_files` | list | - | Target-specific encryption patterns (overrides global) |

**Rules:**
- Non-recursive targets **must** specify `files`
- Recursive targets without `files` collect all files
- Recursive targets with `files` filter by pattern

### blacklist

Global exclusion patterns. Files matching blacklist are **never** collected.

```yaml
config:
  blacklist:
    - ".DS_Store"
    - "*.log"
    - "*.tmp"
    - "*.bak"
    - "*~"
    - ".*.swp"
```

### encryption / encrypt_list

Encryption settings for sensitive files (AES-256-GCM).

```yaml
config:
  encryption:
    enabled: true
    key_file: ~/.config/triton/master.key

  encrypt_list:
    - "id_rsa*"
    - "id_ed25519*"
    - "*.pem"
    - "credentials"
    - "*secret*"
```

**Encryption priority:**
1. `target.encrypt_files` (if specified for a target)
2. Global `encrypt_list`

**File transformation:**
```
Backup:  ~/.ssh/id_rsa  →  repo/Machine/.ssh/id_rsa.enc  (encrypted)
Restore: repo/Machine/.ssh/id_rsa.enc  →  ~/.ssh/id_rsa  (decrypted)
```

### startup_hooks

Commands to execute when TUI starts.

```yaml
config:
  hooks:
    on_startup:
      - "brew bundle dump --file=${TRITON_DIR}/Brewfile --force"
      - "code --list-extensions > ${TRITON_DIR}/vscode-extensions.txt"
    timeout: 30  # Total timeout for all hooks (seconds)
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `on_startup` | list | `[]` | Commands to execute on TUI startup |
| `timeout` | integer | `30` | Total timeout for all hooks (seconds) |

**Manage hooks via CLI:**
```bash
triton config hook list
triton config hook add "brew bundle dump --force"
triton config hook remove "brew bundle dump --force"
triton config hook timeout 60
```

**Test hooks:**
```bash
triton hooks run --dry-run  # Preview
triton hooks run            # Execute
```

### tui

TUI display settings.

```yaml
config:
  tui:
    theme: "nord"              # nord, gruvbox, textual-dark
    hide_system_files: true    # Hide .DS_Store etc. in file list
    system_file_patterns:      # Custom patterns (optional)
      - ".DS_Store"
      - "._*"
      - "Thumbs.db"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `theme` | enum | - | UI theme: `nord`, `gruvbox`, `textual-dark` |
| `hide_system_files` | boolean | `true` | Hide system files in file list |
| `system_file_patterns` | list | (see below) | Patterns for system files to hide |

**Default system_file_patterns:**
`.DS_Store`, `._*`, `Thumbs.db`, `desktop.ini`, `.Spotlight-V100`, `.Trashes`, `ehthumbs.db`

### max_file_size_mb

Skip files larger than this size.

```yaml
config:
  max_file_size_mb: 5.0  # Skip files > 5MB (0 = no limit)
```

---

## Pattern Matching

Triton uses gitignore-like pattern syntax.

### Basic Patterns

| Pattern | Description |
|---------|-------------|
| `*.py` | All `.py` files in current directory |
| `**/*.py` | All `.py` files recursively |
| `config.*` | Files starting with `config.` |
| `.zshrc` | Exact filename match |

### Exclusion Patterns

Prefix with `!` to exclude:

```yaml
files:
  - "**/*.xml"                    # Include all XML
  - "!**/generated/**"            # Exclude generated directory
  - "**/generated/important.xml"  # Re-include this specific file
```

**Evaluation order:**
1. **Global blacklist** - Always excluded (cannot override)
2. **Inclusion patterns** - Define what to collect
3. **Exclusion patterns** (`!`) - Refine collection

Patterns are evaluated sequentially. **Last match wins** (re-inclusion supported).

### Examples

```yaml
# Collect all files except logs
files:
  - "**/*"
  - "!**/*.log"

# Collect specific extensions
files:
  - "**/*.yml"
  - "**/*.yaml"
  - "**/*.json"

# Collect everything, exclude temp, but include important temp
files:
  - "**/*"
  - "!**/temp/**"
  - "**/temp/keep.txt"
```

---

## Environment Variables

### Syntax

```yaml
# Basic substitution
path: "${TRITON_REPO_PATH}"

# With default value
path: "${TRITON_REPO_PATH:-~/default-repo}"
```

### Common Variables

| Variable | Description |
|----------|-------------|
| `TRITON_DIR` | Config directory (default: `~/.config/triton`) |
| `TRITON_REPO_PATH` | Repository path |

**Usage:**
```bash
export TRITON_DIR=~/my-triton
export TRITON_REPO_PATH=~/dotfiles
triton backup
```

---

## CLI Configuration Commands

Triton provides CLI commands to manage configuration programmatically. These commands are designed for both human use and AI agent automation.

### Schema Output

```bash
triton config --schema  # JSON output of all commands, options, and workflows
```

### Validation

```bash
triton config validate           # Check configuration
triton config validate --verbose # Show detailed information
triton config view               # Display raw YAML
```

### Target Management

```bash
# List targets
triton config target list
triton config target list --json
triton config target list --resolve  # Show actual files
triton config target list --path ~/.docker --json  # Filter by path

# Check backup coverage
triton config target check ~/.docker
triton config target check ~/.config/app --json  # Includes backed_up field

# Ensure a file is backed up (idempotent, recommended for automation)
triton config target ensure ~/.zshrc --json

# Add targets
triton config target add ~/.docker --recursive
triton config target add ~/ --files '.zshrc,.gitconfig'
triton config target add ~/.secrets -r --encrypt-files 'api_key,token.json'

# Modify existing targets
triton config target modify ~/ --add-files '.gitconfig,.gitignore_global'
triton config target modify ~/.ssh --add-encrypt-files 'id_*'
triton config target modify ~/.docker --recursive

# Remove targets
triton config target remove ~/.docker
triton config target remove ~/.old-config --yes  # Skip confirmation
```

### Exclude Pattern Management (Blacklist)

```bash
triton config exclude list
triton config exclude list --json
triton config exclude add "*.log"
triton config exclude remove "*.log"
```

### Encryption Pattern Management

```bash
triton config encrypt list
triton config encrypt list --json
triton config encrypt add "id_rsa*"
triton config encrypt remove "id_rsa*"
```

### Hook Management

```bash
triton config hook list
triton config hook list --json
triton config hook add "brew bundle dump --force"
triton config hook remove "brew bundle dump --force"
triton config hook timeout 60
```

### Settings Management

```bash
# List all settings
triton config settings list
triton config settings list --json

# Get/set individual settings
triton config settings get max_file_size_mb
triton config settings set max_file_size_mb 10
triton config settings set repository.auto_pull false
triton config settings set tui.theme nord
triton config settings unset tui.theme  # Reset to default
```

**Available settings:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_file_size_mb` | number | `5.0` | Maximum file size in MB |
| `encryption.enabled` | boolean | `false` | Enable encryption |
| `encryption.key_file` | string | `~/.config/triton/master.key` | Key file path |
| `repository.path` | string | - | Backup destination (required) |
| `repository.use_hostname` | boolean | `true` | Auto-detect machine name |
| `repository.machine_name` | string | - | Override machine name |
| `repository.auto_pull` | boolean | `true` | Auto git pull on TUI start |
| `tui.theme` | enum | - | TUI theme |
| `tui.hide_system_files` | boolean | `true` | Hide system files |

### Automatic Backups

Config modifications automatically create backups:

```
~/.config/triton/archives/config/20251225_143025/config.yml
```

Use `--no-backup` to skip:
```bash
triton config target add ~/.docker --recursive --no-backup
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Config file not found` | Run `triton init` or create `~/.config/triton/config.yml` |
| `Repository path is required` | Set `repository.path` in config |
| `non-recursive without files` | Add `files: [...]` or `recursive: true` |
| Files not collected | Check blacklist, use `triton backup --dry-run` |
| Pattern not working | Ensure `recursive: true` for `**` patterns |
| Environment variable not expanded | Check variable is defined: `echo $VAR_NAME` |

**Debug commands:**
```bash
triton config validate --verbose  # Check configuration
triton backup --dry-run           # Preview backup operation
triton config target list --resolve  # See actual files per target
```

---

## Related Documentation

- [README.md](README.md) - Quick start and overview
- [TUI.md](TUI.md) - Interactive interface guide
