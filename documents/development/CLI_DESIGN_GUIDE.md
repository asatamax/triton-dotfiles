# CLI Design Guide

Guidelines for output format and style in Triton CLI.

## Basic Principles

1. **No emojis** - Emojis like are not supported - they have inconsistent width and break layouts
2. **Unicode symbols are OK** - Symbols like `✓✗!⚫⚪` have consistent width
3. **Combine color with prefixes** - Ensures accessibility for color vision diversity and readability in logs

## Color Scheme

| Purpose | Color | Colorama |
|---------|-------|----------|
| Success, exists, added | Green | `Fore.GREEN` |
| Warning, modified | Yellow | `Fore.YELLOW` |
| Error, failure, deleted | Red | `Fore.RED` |
| Info, labels | Cyan | `Fore.CYAN` |
| Normal text | Default | `Style.RESET_ALL` |

## Command Type Patterns

### Configuration Commands (Status/Validation)

`config validate`, `config target list`, `config target check`, etc.

Use symbol-based expressions:

```
✓ ~/.ssh/config
✗ ~/.tmux.conf (not found)
! Path does not exist: /Users/hiro/.m2
```

| State | Symbol | Color |
|-------|--------|-------|
| Success, exists | `✓` | Green |
| Failure, missing | `✗` | Red |
| Warning | `!` | Yellow |

### Action Commands (Execution/Modification)

`backup`, `restore`, `git-commit-push`, `export`, etc.

Use text prefixes:

```
Error: Failed to copy ~/.zshrc - Permission denied
Warning: File already exists, creating backup
```

| State | Prefix | Color |
|-------|--------|-------|
| Error | `Error:` | Red |
| Warning | `Warning:` | Yellow |
| Success | (completion message with info) | Green or default |

## Diff Display (Git-style)

```
M .aws/config          # Modified (yellow)
+ .config/bat/config   # Added (green)
- .old/removed.txt     # Deleted (red)
```

| State | Prefix | Color |
|-------|--------|-------|
| Modified | `M` | Yellow |
| Added | `+` | Green |
| Deleted | `-` | Red |

Detailed diff display (unified diff format):
```
  --- a/.aws/config
  +++ b/.aws/config
  @@ -3,10 +3,6 @@        # Cyan
  -removed line           # Red
  +added line             # Green
```

## List Display

### Index Numbers

List items include index numbers (in green):

```
Targets:
  [0] ~/.config/triton (recursive)
  [1] ~/.ssh (recursive)
  [2] ~/.aws (recursive)
```

This prepares for future number-based selection options.

### Machine List

Current machine shown with `⚫`, others with `⚪`:

```
Available machines:
  ⚪ HomePC (91 files)
  ⚫ WorkLaptop (62 files)
  ⚪ OfficeDesktop (75 files)
```

## Message Formats

### Headers/Sections

Keep it simple, add color as needed:

```python
click.echo(f"{Fore.CYAN}Targets:{Style.RESET_ALL}")
```

### Summary

Compact single-line format:

```
0 errors, 9 warnings
37 unchanged, 18 modified, +36, -7
```

### Completion Messages

Include useful information:

```
Backup complete: 62 files copied
Restore complete: 5 files restored
```

### Confirmation Prompts

State the purpose clearly:

```
Restore 5 files to ~/.config? [y/N]:
Delete 3 orphaned files? [y/N]:
```

### Dry-run Display

Use parenthetical format:

```
(dry-run) Would copy ~/.zshrc
(dry-run) Would delete ~/.old/config
```

### Progress Display

Output filenames (useful for log reference):

```
Copying ~/.zshrc
Copying ~/.vimrc
Copying ~/.config/git/ignore
Backup complete: 62 files copied
```

## Exception Rules

Follow this guide as a rule. When exceptions are necessary, document the reason in a code comment:

```python
# CLI Design Guide exception: reason for not using symbol here is...
click.echo(f"{Fore.RED}Error: {message}{Style.RESET_ALL}")
```

## Implementation Examples

### Configuration Commands

```python
# Success
click.echo(f"  {Fore.GREEN}✓{Style.RESET_ALL} {file_path}")

# Failure
click.echo(f"  {Fore.RED}✗{Style.RESET_ALL} {file_path} (not found)")

# Warning
click.echo(f"  {Fore.YELLOW}!{Style.RESET_ALL} Path does not exist: {path}")
```

### Action Commands

```python
# Error
click.echo(f"{Fore.RED}Error: {message}{Style.RESET_ALL}")

# Warning
click.echo(f"{Fore.YELLOW}Warning: {message}{Style.RESET_ALL}")

# Completion
click.echo(f"Backup complete: {count} files copied")
```

### Diff Display

```python
# File list
if status == "added":
    print(f"{Fore.GREEN}+ {path}{Style.RESET_ALL}")
elif status == "deleted":
    print(f"{Fore.RED}- {path}{Style.RESET_ALL}")
elif status == "modified":
    print(f"{Fore.YELLOW}M {path}{Style.RESET_ALL}")

# Diff details
if line.startswith("+"):
    print(f"  {Fore.GREEN}{line}{Style.RESET_ALL}")
elif line.startswith("-"):
    print(f"  {Fore.RED}{line}{Style.RESET_ALL}")
elif line.startswith("@@"):
    print(f"  {Fore.CYAN}{line}{Style.RESET_ALL}")
```
