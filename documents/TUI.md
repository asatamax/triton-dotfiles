# Triton TUI Guide

Interactive terminal browser for managing dotfiles across machines.

![Triton TUI](triton-tui.png)

## Getting Started

### Launch

```bash
triton          # Launch TUI (default)
triton tui      # Explicit command
triton -S       # Skip startup hooks and auto-pull
```

### Startup Behavior

When TUI starts, two things happen automatically:

1. **Hooks execution** - Configured startup commands run (e.g., `brew bundle dump`)
2. **Auto-pull** - `git pull` fetches latest changes from remote

Use `-S` or `--skip-startup` to skip both. Configure in `config.yml`:

```yaml
config:
  repository:
    auto_pull: false  # Disable auto-pull only
  hooks:
    on_startup:
      - "brew bundle dump --force"
    timeout: 30
```

---

## Workflow Examples

### Example 1: Backup Local Changes (Self Machine)

When viewing your own machine, files with local changes are highlighted in color.

1. **Launch** - `triton`
2. **Check changes** - Colored files indicate local modifications
3. **Backup** - `B` to save local changes to repository
4. **Commit & Push** - `C` to commit and push to remote

```
[When your machine is selected]
Colored files in the list = local changes exist
  ↓
B (Backup) → C (Commit & Push)
```

### Example 2: Restore from Another Machine

Switch to another machine and pull files you need.

1. **Switch machine** - `m` to select another machine
2. **Review files** - `d` for diff view, `D` for VSCode diff
3. **Select files** - `Space` to check files
4. **Restore** - `R` to restore selected files to local

```
m (Select machine) → Review files → Space (Select) → R (Restore)
```

Existing files are automatically backed up to `~/.config/triton/archives/restore/` before restore.

### Example 3: Cleanup Orphaned Files

When files deleted locally still exist in the repository (no delete commit):

1. **Select your machine** - `m` to select your own machine
2. **Identify orphaned files** - Files that exist in repository but not locally
3. **Cleanup** - Command palette (`Ctrl+P`) → "Repository Cleanup"
4. **Commit** - `C` to commit the deletion

### Example 4: Archive Management

Archives accumulate with each restore operation. Clean up periodically:

```bash
triton archive list              # List archives
triton archive show <timestamp>  # Show specific archive contents
triton archive clean             # Delete old archives
triton archive clean --keep 5    # Keep only latest 5 archives
```

---

## Key Bindings

### Navigation

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move cursor |
| `Space` | Toggle file selection |
| `m` | Switch machine |
| `/` | Search files (incremental) |
| `?` | Show help |
| `q` | Quit |

### Display Modes

| Key | Mode | Description |
|-----|------|-------------|
| `p` / `1` | Preview | Repository file content |
| `l` / `2` | Local | Local file content |
| `d` / `3` | Diff | Unified diff (local vs repository) |
| `i` / `4` | Info | File details and sync status |
| `s` / `5` | Split | Side-by-side comparison |

### Actions

| Key | Action |
|-----|--------|
| `B` | Backup selected files (local → repository) |
| `R` | Restore selected files (repository → local) |
| `x` | Export file to specified location |
| `C` | Git commit and push |
| `P` | Git pull |
| `Ctrl+R` | Refresh data |

### VSCode Integration

| Key | Action |
|-----|--------|
| `D` | Open diff in VSCode/Cursor/Windsurf |
| `E` | Edit local file in VSCode/Cursor/Windsurf |

### Other

| Key | Action |
|-----|--------|
| `Ctrl+P` | Command palette |
| `F` | Show in Finder (macOS) |
| `t` | Toggle left pane |
| `-` | Group files by target |

---

## Command Palette

`Ctrl+P` opens the command palette with fuzzy search:

- **Backup Files** - Backup selected files
- **Restore Files** - Restore selected files
- **Export Files** - Export to specified location
- **Git Pull** - Pull latest changes
- **Git Commit Push** - Commit and push changes
- **Select Machine** - Switch to another machine
- **Repository Cleanup** - Remove orphaned files
- **VSCode Diff** - Open diff in external editor
- **Edit in VSCode** - Edit local file
- **Show in Finder** - Reveal in Finder (macOS)
- **Change Theme** - Switch UI theme
- **Show Help** - Display key bindings

---

## File Status Indicators

### Colors

- **Highlighted/colored** - File has local changes (differs from repository)
- **Normal** - File matches repository version

### Icons

| Icon | Meaning |
|------|---------|
| Lock icon | Encrypted file |
| Document icon | Normal file |

### Selection

- Checkbox checked - File selected for batch operations
- Checkbox empty - File not selected

---

## Search and Filter

Press `/` to open incremental search:

- Type to filter files by path
- Results update as you type
- Press `Enter` to confirm, `Escape` to cancel

This is useful for:
- Finding specific files in large backups
- Confirming which files are included in backup targets

---

## Configuration

TUI settings in `config.yml`:

```yaml
config:
  tui:
    theme: "nord"           # nord, gruvbox, textual-dark
    hide_system_files: true # Hide .DS_Store, Thumbs.db, etc.
```

See [CONFIGURATION.md](CONFIGURATION.md) for full reference.

---

## Tips

### Checking Backup Targets

TUI doubles as a way to verify what files are included in your backup configuration. Use `/` to search and confirm expected files are present.

### Supported Editors

VSCode integration works with:
- VS Code (`code`)
- VS Code Insiders (`code-insiders`)
- Cursor (`cursor`)
- Windsurf (`windsurf`)

The first available editor is used.

### Machine Detection

Your current machine is automatically detected and highlighted. VPN connections that change hostname are handled gracefully.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| TUI won't start | Check terminal supports UTF-8 |
| No machines found | Run `triton backup` first |
| Diff not showing | Local file may not exist |
| Keys not working | Terminal may not support raw mode |
| Display issues | Try wider terminal (120+ columns) |

---

## Related Documentation

- [README.md](README.md) - Quick start
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration reference
