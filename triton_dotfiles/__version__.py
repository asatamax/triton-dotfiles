#!/usr/bin/env python3
"""
Version information for triton-dotfiles
"""

import subprocess
from pathlib import Path
from typing import Optional

# Static version (fallback)
__version__ = "1.0.1"


def get_git_version() -> Optional[str]:
    """
    Get version from git tag

    Returns:
        Git tag version if available, None otherwise
    """
    try:
        # Get the directory of this file
        repo_root = Path(__file__).parent.parent

        # Try to get the latest git tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return None


def get_version() -> str:
    """
    Get the application version

    Always returns the static version for consistency.
    Git version is available via get_version_info() for reference.

    Returns:
        Version string
    """
    return __version__


def get_version_info() -> dict:
    """
    Get detailed version information

    Returns:
        Dictionary with version details
    """
    git_version = get_git_version()

    return {
        "version": get_version(),
        "git_version": git_version,
        "static_version": __version__,
        "source": "git" if git_version else "static",
    }


if __name__ == "__main__":
    print(get_version())
