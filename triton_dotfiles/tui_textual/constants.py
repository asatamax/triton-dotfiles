"""
TUI constants for Triton Dotfiles.

Centralizes magic numbers and configuration values used across TUI components.
"""

# File preview limits
MAX_PREVIEW_LINES = 1000
"""Maximum number of lines to display in file preview."""

MAX_DIFF_LINES = 50
"""Maximum number of diff lines to display before truncation."""

# Binary detection
BINARY_SAMPLE_SIZE = 512
"""Number of bytes to sample when detecting binary files."""

BINARY_CONTROL_CHAR_THRESHOLD = 0.3
"""Threshold ratio of control characters to consider a file binary."""

# Hex preview
HEX_PREVIEW_MAX_SIZE = 512
"""Maximum file size in bytes for hex preview display."""

HEX_PREVIEW_BYTES = 256
"""Number of bytes to show in hex preview."""

HEX_LINE_WIDTH = 32
"""Characters per line in hex preview (16 bytes = 32 hex chars)."""
