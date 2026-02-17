# Claude Code Skills for Triton

Claude Code skills for managing Triton dotfiles configuration.

## Installation

Copy or symlink the skill directory to `~/.claude/skills/`:

```bash
# Option 1: Symlink (recommended for development)
ln -s /path/to/triton-dotfiles/extras/skills/triton-config ~/.claude/skills/triton-config

# Option 2: Copy
cp -r /path/to/triton-dotfiles/extras/skills/triton-config ~/.claude/skills/
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `triton-config` | Manage backup targets, hooks, exclude/encrypt patterns via CLI |

## Usage

Once installed, Claude Code will automatically detect and use the skill when you mention:
- "triton config"
- "dotfiles backup target"
- "triton hook"
- Adding/removing backup targets

Example prompts:
- "Add ~/.config/nvim to triton backup targets"
- "List my triton backup targets"
- "Add a startup hook to dump my Brewfile"
