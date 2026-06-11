#!/usr/bin/env python3
"""
Version information for triton-dotfiles
"""

__version__ = "1.2.1"


def get_version() -> str:
    """Get the application version.

    Returns:
        Version string
    """
    return __version__


if __name__ == "__main__":
    print(get_version())
