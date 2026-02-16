"""
Version check module for triton-dotfiles.

Checks GitHub releases API for new versions and caches results.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from .utils import get_triton_dir
from .__version__ import __version__


# GitHub API endpoint for latest release
GITHUB_API_URL = "https://api.github.com/repos/asatamax/triton-dotfiles/releases/latest"

# Cache settings
CACHE_FILENAME = ".version_cache.json"
CACHE_DURATION_HOURS = 1


class VersionCheckResult(NamedTuple):
    """Result of version check."""

    update_available: bool
    current_version: str
    latest_version: str | None
    error: str | None = None


def _get_cache_path() -> Path:
    """Get path to version cache file."""
    return get_triton_dir() / CACHE_FILENAME


def _read_cache() -> dict | None:
    """Read cached version info if valid.

    Returns:
        Cached data dict if valid and not expired, None otherwise.
    """
    cache_path = _get_cache_path()

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)

        # Check if cache is expired
        checked_at = datetime.fromisoformat(data.get("checked_at", ""))
        if datetime.now() - checked_at > timedelta(hours=CACHE_DURATION_HOURS):
            return None

        return data
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _write_cache(latest_version: str) -> None:
    """Write version info to cache.

    Args:
        latest_version: Latest version string from GitHub.
    """
    cache_path = _get_cache_path()

    try:
        # Ensure parent directory exists
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "checked_at": datetime.now().isoformat(),
            "latest_version": latest_version,
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        # Silently ignore cache write errors
        pass


def _fetch_latest_version() -> str | None:
    """Fetch latest version from GitHub API.

    Returns:
        Latest version string (without 'v' prefix) or None on error.
    """
    try:
        request = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"triton-dotfiles/{__version__}",
            },
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            tag_name = data.get("tag_name", "")

            # Remove 'v' prefix if present (e.g., "v1.0.1" -> "1.0.1")
            if tag_name.startswith("v"):
                return tag_name[1:]
            return tag_name

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        # Network errors, API errors, or parse errors - silently return None
        return None
    except Exception:
        # Any other unexpected errors
        return None


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse version string into tuple for comparison.

    Args:
        version: Version string like "1.0.1"

    Returns:
        Tuple of integers like (1, 0, 1)
    """
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)


def _is_newer_version(current: str, latest: str) -> bool:
    """Check if latest version is newer than current.

    Args:
        current: Current version string
        latest: Latest version string

    Returns:
        True if latest is newer than current.
    """
    return _parse_version(latest) > _parse_version(current)


def check_for_updates(force: bool = False) -> VersionCheckResult:
    """Check if a newer version is available.

    Uses cached result if available and not expired.
    Network errors are silently ignored (returns no update available).

    Args:
        force: If True, bypass cache and check GitHub directly.

    Returns:
        VersionCheckResult with update status.
    """
    current_version = __version__

    # Try cache first (unless force is True)
    if not force:
        cached = _read_cache()
        if cached:
            latest = cached.get("latest_version")
            if latest:
                return VersionCheckResult(
                    update_available=_is_newer_version(current_version, latest),
                    current_version=current_version,
                    latest_version=latest,
                )

    # Fetch from GitHub
    latest = _fetch_latest_version()

    if latest is None:
        # Network error or API error - return no update (silent failure)
        return VersionCheckResult(
            update_available=False,
            current_version=current_version,
            latest_version=None,
            error="Could not check for updates",
        )

    # Cache the result
    _write_cache(latest)

    return VersionCheckResult(
        update_available=_is_newer_version(current_version, latest),
        current_version=current_version,
        latest_version=latest,
    )


def get_update_message() -> str | None:
    """Get update notification message if update is available.

    Returns:
        Message string like "Update available: v1.0.1" or None if no update.
    """
    result = check_for_updates()

    if result.update_available and result.latest_version:
        return f"Update available: v{result.latest_version}"

    return None
