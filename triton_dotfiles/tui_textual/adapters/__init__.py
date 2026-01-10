"""
TUI-specific adapters for triton-dotfiles
Wraps core managers for TUI presentation layer
"""

from .file_adapter import TUIFileAdapter as TUIFileAdapter

__all__ = ["TUIFileAdapter"]
