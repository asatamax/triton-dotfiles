#!/usr/bin/env python3
"""
Utility functions for triton-dotfiles
"""

import os
import re
import sys
import fnmatch
import functools
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Type, List, Tuple


def safe_import(
    module_name: str, package: str = None, fallback_path: str = None
) -> Any:
    """
    Safe import handling.

    Args:
        module_name: Name of the module to import.
        package: Package name (for relative imports).
        fallback_path: Path to add to sys.path as fallback.

    Returns:
        Imported module.

    Raises:
        ImportError: If import fails.
    """
    try:
        # 相対インポートを試す
        if package:
            return __import__(module_name, fromlist=[package])
        else:
            return __import__(module_name)
    except ImportError:
        # フォールバック: 絶対パスでインポート
        if fallback_path:
            if fallback_path not in sys.path:
                sys.path.append(fallback_path)
            return __import__(module_name)
        raise


def get_package_root() -> Path:
    """Get the package root directory."""
    return Path(__file__).parent


def import_from_package(module_name: str) -> Any:
    """
    Import a module from the package uniformly.

    Args:
        module_name: Name of the module to import (e.g., 'config', 'file_manager').

    Returns:
        Imported module.
    """
    package_root = get_package_root()

    try:
        # 相対インポートを試す
        return __import__(
            f"triton_dotfiles.{module_name}", fromlist=["triton_dotfiles"]
        )
    except ImportError:
        # フォールバック: パッケージルートを追加して絶対インポート
        if str(package_root) not in sys.path:
            sys.path.append(str(package_root))
        return __import__(module_name)


def import_class_from_module(module_name: str, class_name: str) -> Type:
    """
    Import a specific class from a module.

    Args:
        module_name: Module name.
        class_name: Class name.

    Returns:
        Imported class.
    """
    module = import_from_package(module_name)
    return getattr(module, class_name)


def get_triton_dir() -> Path:
    """Get the Triton directory path (with environment variable support).

    Returns:
        Path: Triton directory path (absolute, resolved).

    Note:
        Uses TRITON_DIR environment variable if set,
        otherwise defaults to ~/.config/triton.
    """
    return Path(os.getenv("TRITON_DIR", "~/.config/triton")).expanduser().resolve()


# fnmatch.translate() の出力 "(?s:...)\\Z"（新しいPythonでは "\\z"）から本体を取り出す
_FNMATCH_TRANSLATION = re.compile(r"\A\(\?s:(.*)\)\\[Zz]\Z", re.DOTALL)


def _translate_glob_class(expression: str) -> str:
    """
    Translate one bracket expression such as ``[!a-]`` to a regex.

    The class contents are translated by fnmatch itself, so ranges, a leading
    ``]``, ``-`` and ``!`` behave exactly as in fnmatch. A separate lookahead
    keeps the class from matching '/', without altering its contents.

    Raises:
        ValueError: If the class can never match (e.g. ``[z-a]``).
    """
    match = _FNMATCH_TRANSLATION.match(fnmatch.translate(expression))
    if not match:
        raise ValueError(f"unsupported character class '{expression}'")
    body = match.group(1)
    if body == "(?!)":
        raise ValueError(f"character class '{expression}' matches nothing")
    return "(?!/)" + body


def _translate_glob_segment(segment: str) -> str:
    """Translate one '/'-free glob segment to a regex (fnmatch semantics, no '/')."""
    out = []
    i, n = 0, len(segment)
    while i < n:
        c = segment[i]
        i += 1
        if c == "*":
            if i < n and segment[i] == "*":
                # セグメント内の "**"（例: "a**"）は従来どおり "/" をまたいでマッチ
                while i < n and segment[i] == "*":
                    i += 1
                out.append(".*")
            else:
                out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i
            if j < n and segment[j] == "!":
                j += 1
            if j < n and segment[j] == "]":
                j += 1
            while j < n and segment[j] != "]":
                j += 1
            if j >= n:
                # 閉じ括弧がなければ fnmatch と同じく "[" はリテラル
                out.append(re.escape(c))
                continue
            out.append(_translate_glob_class(segment[i - 1 : j + 1]))
            i = j + 1
        else:
            out.append(re.escape(c))
    return "".join(out)


@functools.lru_cache(maxsize=1024)
def _compile_globstar_pattern(pattern: str) -> "re.Pattern[str]":
    """
    Compile a pattern containing '**' to a regex, segment by segment.

    ``**`` as a whole segment matches zero or more directories (a trailing
    ``**`` matches everything below). Within a segment ``*`` and ``?`` never
    match '/', ``[...]`` and ``[!...]`` are character classes as in fnmatch
    (so ``[old]`` matches one of 'o', 'l', 'd'; ``[[]old]`` matches the literal
    name ``[old]``), and every other character is literal.

    Raises:
        ValueError: If the pattern cannot be compiled (e.g. ``[z-a]``).
    """
    segments = pattern.split("/")
    parts = []
    try:
        for index, segment in enumerate(segments):
            is_last = index == len(segments) - 1
            if segment == "**":
                parts.append(".*" if is_last else "(?:.*/)?")
            else:
                parts.append(
                    _translate_glob_segment(segment) + ("" if is_last else "/")
                )
        return re.compile(r"\A" + "".join(parts) + r"\Z", re.DOTALL)
    except (re.error, ValueError) as e:
        raise ValueError(f"Invalid pattern '{pattern}': {e}") from e


def _legacy_globstar_match(path_str: str, pattern: str) -> bool:
    """
    The '**' translation used up to v1.3.1, kept only for encryption decisions.

    It did not escape regex metacharacters, so it matched some paths the
    current translation does not (``**/token(1).json`` matched ``token1.json``).
    Files already encrypted because of such a match must stay encrypted, so
    encryption decisions accept a match from either translation. Errors count
    as no match, as they did then.
    """
    regex_pattern = pattern
    regex_pattern = regex_pattern.replace(".", r"\.")
    regex_pattern = regex_pattern.replace("?", ".")
    regex_pattern = regex_pattern.replace("**/", "__GLOBSTAR_SLASH__")
    regex_pattern = regex_pattern.replace("**", "__GLOBSTAR__")
    regex_pattern = regex_pattern.replace("*", "[^/]*")
    regex_pattern = regex_pattern.replace("__GLOBSTAR_SLASH__", "(?:.*/)?")
    regex_pattern = regex_pattern.replace("__GLOBSTAR__", ".*")
    try:
        return bool(re.match(f"^{regex_pattern}$", path_str))
    except re.error:
        return False


def glob_pattern_error(pattern: str) -> str | None:
    """
    Return why a pattern cannot be used, or None when it is valid.

    Used by config validation so an invalid pattern is reported instead of
    silently never matching (which would fail open for encryption).
    """
    if "**" not in pattern:
        return None
    try:
        _compile_globstar_pattern(pattern)
    except ValueError as e:
        return str(e)
    return None


def matches_glob_pattern(path: Path, pattern: str) -> bool:
    """
    Check if a path matches a glob pattern.

    Supports:
    - Basic wildcards: *.txt, config.*
    - Globstar: **/*.md, **/node_modules/**
    - Path matching: packages/*/src

    Args:
        path: Path to check (relative path).
        pattern: Glob pattern.

    Returns:
        True if matched.

    Raises:
        ValueError: If a globstar pattern cannot be compiled.
    """
    # パスをPOSIX形式に正規化
    path_str = str(PurePosixPath(path))

    # globstarパターン（**）はセグメント単位で正規表現に変換
    if "**" in pattern:
        return bool(_compile_globstar_pattern(pattern).match(path_str))

    # 標準のfnmatchを使用
    # パス全体とファイル名の両方でマッチを試みる
    if fnmatch.fnmatch(path_str, pattern):
        return True
    # ファイル名のみでもマッチを試みる
    if fnmatch.fnmatch(path.name, pattern):
        return True
    return False


def matches_any_pattern(
    file_path: Path,
    patterns: List[str],
    relative_path: Path | None = None,
    legacy_globstar: bool = False,
) -> bool:
    """
    Check if a file matches any pattern in the list (OR evaluation).

    Used for priority rules like blacklist or encrypt_list. A pattern matches
    when it matches any of these forms of the file path (union, so a pattern
    never matches fewer files than matching the path alone):

    - the path as given (absolute for global lists) and its normalized form
    - its basename
    - the path relative to the home directory (when under home)
    - the path relative to the target (when the caller knows it), raw and
      normalized (so ``sub/../secrets/token`` also matches as ``secrets/token``)

    Args:
        file_path: File path to check.
        patterns: List of patterns.
        relative_path: Path relative to the target, if known.
        legacy_globstar: Also accept a match from the v1.3.1 '**' translation.
            Set for encryption decisions only (see _legacy_globstar_match).

    Returns:
        True if any pattern matched.
    """
    # 候補はPOSIX形式の文字列で1回だけ作る（ファイル数×パターン数で呼ばれるため）
    file_str = str(PurePosixPath(file_path))
    # ".." を含むdirect pathでも判定できるよう、正規化した形も候補に加える（和集合）
    normalized_str = str(PurePosixPath(os.path.normpath(file_path)))
    candidates = [file_str, file_path.name, normalized_str]
    home_prefix = str(PurePosixPath(Path.home())) + "/"
    for path_str in (file_str, normalized_str):
        if path_str.startswith(home_prefix):
            candidates.append(path_str[len(home_prefix) :])
    if relative_path is not None:
        candidates.append(str(PurePosixPath(relative_path)))
        candidates.append(str(PurePosixPath(os.path.normpath(relative_path))))
    candidates = list(dict.fromkeys(candidates))

    for pattern in patterns:
        if "**" in pattern:
            regex = _compile_globstar_pattern(pattern)
            if any(regex.match(candidate) for candidate in candidates):
                return True
            if legacy_globstar and any(
                _legacy_globstar_match(candidate, pattern) for candidate in candidates
            ):
                return True
        # basenameも候補にあるため、各候補の全体マッチでmatches_glob_patternと同じ判定になる
        elif any(fnmatch.fnmatch(candidate, pattern) for candidate in candidates):
            return True
    return False


def normalize_direct_path(entry: str) -> str:
    """
    Normalize a config direct-path entry for exact matching.

    Backslashes are config-side separators; '.', '..' and duplicate
    separators are collapsed so ``./app/conf`` and ``sub/../keep.txt`` match
    the scanned paths ``app/conf`` and ``keep.txt``.
    """
    return os.path.normpath(entry.replace("\\", "/"))


# Glob special characters pattern for direct path detection
GLOB_CHARS_PATTERN = re.compile(r"[*?\[\]]")


def is_direct_path(pattern: str) -> bool:
    """
    Determine if a pattern is a direct path (not a glob pattern).

    A direct path contains path separators (/ or \\) but no glob wildcards.
    This is used to optimize file collection by directly checking file existence
    instead of scanning entire directory trees.

    Args:
        pattern: Pattern string to check.

    Returns:
        True if the pattern is a direct path, False if it's a glob pattern.

    Examples:
        >>> is_direct_path("app-services/.env")           # True (direct path)
        >>> is_direct_path("src/main/config.yml")     # True (direct path)
        >>> is_direct_path(".zshrc")                  # False (no path separator)
        >>> is_direct_path("**/*.yml")                # False (contains glob)
        >>> is_direct_path("!app-services/.env")          # False (exclusion pattern)
    """
    # Empty string is not a direct path
    if not pattern:
        return False

    # Exclusion patterns (starting with !) are not direct paths
    if pattern.startswith("!"):
        return False

    # Patterns containing glob characters are not direct paths
    if GLOB_CHARS_PATTERN.search(pattern):
        return False

    # Direct path must contain a path separator (POSIX or Windows)
    return "/" in pattern or "\\" in pattern


def separate_direct_and_pattern_files(
    patterns: List[str],
) -> Tuple[List[str], List[str]]:
    """
    Separate a list of file patterns into direct paths and glob patterns.

    This enables optimization where direct paths can be checked with a simple
    stat() call instead of scanning the entire directory tree.

    Args:
        patterns: List of file patterns from config.

    Returns:
        Tuple of (direct_paths, glob_patterns).
        - direct_paths: Paths that can be directly accessed (e.g., "app/.env")
        - glob_patterns: Patterns requiring directory scanning (e.g., "*.py")

    Examples:
        >>> separate_direct_and_pattern_files(["app/.env", "*.yml", "!*.log"])
        (["app/.env"], ["*.yml", "!*.log"])
    """
    direct_paths = []
    glob_patterns = []

    for p in patterns:
        if is_direct_path(p):
            direct_paths.append(p)
        else:
            glob_patterns.append(p)

    return direct_paths, glob_patterns


# Windows drive-letter prefix (e.g. "C:/", "C:")
WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


def target_backup_subdir(expanded_path: Path) -> str:
    """
    Return a target's backup location relative to the machine backup directory.

    Shared by backup, restore and cleanup so the destination rule exists once.

    - Home directory: the machine directory itself ("")
    - Under home: the home-relative path (~/.ssh -> ".ssh")
    - Outside home: the directory name only (/opt/dots -> "dots")

    Args:
        expanded_path: Target path with ~ and environment variables expanded.

    Returns:
        Relative backup directory as a POSIX-style string.
    """
    home = Path.home()
    if expanded_path == home:
        return ""
    # 文字列の前方一致ではなくパス要素で判定する（/Users/alice-work は /Users/alice 配下ではない）
    if expanded_path.is_relative_to(home):
        return str(expanded_path.relative_to(home))
    return expanded_path.name


def backup_relative_destination(backup_subdir: str, relative_path: str) -> str:
    """
    Return a file's backup location relative to the machine backup directory.

    The result is lexically normalized so that writing to it never makes the
    filesystem traverse a ".." segment on the repository side, where a
    symlink could redirect it. Path components are used as they are: only the
    platform separator splits them, so a backslash inside a POSIX file name
    stays part of that name. Config-supplied direct paths are converted to "/"
    by the caller before they get here.

    Args:
        backup_subdir: The target's backup location (see target_backup_subdir).
        relative_path: The file path relative to the target, as collected.

    Returns:
        A normalized relative path (it may start with ".." or be absolute for
        invalid entries; callers check containment).
    """
    return os.path.normpath(os.path.join(backup_subdir, relative_path))


def direct_path_violation(expanded_target_path: Path, direct_path: str) -> str | None:
    """
    Check that a direct path stays inside the machine backup directory.

    Direct paths must be relative. ".." is allowed only while the resolved
    backup destination stays inside the machine backup directory.

    Args:
        expanded_target_path: Target path with ~ and environment variables expanded.
        direct_path: Direct path entry from the target's ``files`` list.

    Returns:
        A reason string when the entry is invalid, otherwise None.

    Examples:
        >>> direct_path_violation(Path.home() / "proj", "/etc/hosts")
        'absolute paths are not allowed'
        >>> direct_path_violation(Path.home() / "proj", "../../x")
        'leaves the backup directory'
        >>> direct_path_violation(Path.home() / "proj" / "sub", "../keep.json")
    """
    # collect_target_files() Phase 1と同じ正規化（Windowsの区切り文字を/に統一）
    normalized = direct_path.replace("\\", "/")
    if normalized.startswith(("/", "~")) or WINDOWS_DRIVE_PATTERN.match(normalized):
        return "absolute paths are not allowed"

    destination = backup_relative_destination(
        target_backup_subdir(expanded_target_path), normalized
    )
    if Path(destination).parts[:1] == (os.pardir,):
        return "leaves the backup directory"

    return None


def machine_name_violation(name: object) -> str | None:
    """
    Check that a machine name is a single safe path component.

    The machine name becomes ``<repository>/<machine name>``, the base of
    every containment check, so it must not be able to point anywhere else.
    Unsafe names are refused, never sanitized: sanitizing would silently move
    the machine's backup directory.

    Args:
        name: Configured or auto-detected machine name.

    Returns:
        A reason string when the name is unsafe, otherwise None.

    Examples:
        >>> machine_name_violation("My Mac.local")
        >>> machine_name_violation("../x")
        'must not contain path separators'
    """
    if not isinstance(name, str) or not name:
        return "is empty"
    if name in (os.curdir, os.pardir):
        return "must not be '.' or '..'"
    if "/" in name or "\\" in name:
        return "must not contain path separators"
    if name.startswith("."):
        # .git / .github 等のリポジトリ管理用ディレクトリと衝突させない
        return "must not start with '.'"
    if "\0" in name:
        return "must not contain NUL characters"
    if WINDOWS_DRIVE_PATTERN.match(name):
        return "must not start with a drive letter"
    return None


def is_within_directory(path: Path, directory: Path) -> bool:
    """
    Check lexically (without resolving symlinks) that path is inside directory.

    Args:
        path: Path to check.
        directory: Directory that must contain the path.

    Returns:
        True if the normalized path is strictly inside the normalized directory.
    """
    normalized_path = Path(os.path.normpath(path))
    normalized_dir = Path(os.path.normpath(directory))
    return normalized_path != normalized_dir and normalized_path.is_relative_to(
        normalized_dir
    )


def destination_violation(
    path: Path, directory: Path, allow_symlink: bool = False
) -> str | None:
    """
    Check that writing to (or unlinking) path cannot affect anything outside directory.

    Complements :func:`is_within_directory` (lexical). The path must already be
    lexically inside the directory. Both sides are resolved, so a directory that
    is itself reached through a symlink (e.g. a symlinked repository) is fine.

    - path must not be a symlink (writing would follow it), unless allow_symlink
      is set for an unlink-only path where removing the link itself is harmless.
    - If path exists, it must be a regular file (writing into a directory would
      create a file below it).
    - The nearest existing ancestor of path's parent, resolved, must be inside
      (or equal to) the resolved directory, so that creating the missing
      parents cannot go through a symlinked directory.
    - Any error while resolving (symlink loops, permissions) counts as a violation.

    Args:
        path: Destination file path (lexically inside directory).
        directory: Directory that must contain the real destination.
        allow_symlink: Accept path itself being a symlink (for unlink targets).

    Returns:
        A reason string when the destination is unsafe, otherwise None.
    """
    try:
        if path.is_symlink():
            if not allow_symlink:
                return "is a symlink"
        elif os.path.lexists(path) and not path.is_file():
            return "exists and is not a regular file"

        # ".."を含むパスもOSの解決順に従って辿るため、正規化せずに祖先をたどる
        current = path.parent
        while current != directory and current != current.parent:
            if os.path.lexists(current):
                break
            current = current.parent

        if not os.path.lexists(current):
            # directory自体がまだ存在しない（初回バックアップのdry-run等）
            return None

        resolved = current.resolve()
        resolved_dir = directory.resolve()
        if resolved != resolved_dir and not resolved.is_relative_to(resolved_dir):
            return "resolves outside the backup directory via a symlink"
    except (OSError, RuntimeError) as e:
        # RuntimeErrorはPython 3.11以前のシンボリックリンクループ
        return f"cannot be resolved ({e})"

    return None


# アーカイブ実行ディレクトリ名: YYYYmmdd_HHMMSS（同一秒の衝突時は _1, _2, ...）
ARCHIVE_RUN_NAME_PATTERN = re.compile(r"^(\d{8}_\d{6})(?:_([1-9]\d*))?$")
ARCHIVE_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def create_unique_archive_dir(parent: Path, timestamp: str) -> Path:
    """
    Create a new archive run directory that no earlier run has used.

    The directory is ``parent/<timestamp>``; when that already exists (two
    runs within the same second) ``_1``, ``_2``, ... is appended. The
    directory is created with ``exist_ok=False`` so a run never writes into
    another run's archive.

    Args:
        parent: Directory holding archive runs.
        timestamp: Run timestamp (YYYYmmdd_HHMMSS).

    Returns:
        The created directory.
    """
    parent.mkdir(parents=True, exist_ok=True)
    suffix = 0
    while True:
        name = timestamp if suffix == 0 else f"{timestamp}_{suffix}"
        candidate = parent / name
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            suffix += 1


def parse_archive_run_name(name: str) -> tuple[datetime, int] | None:
    """
    Parse an archive run directory name.

    Args:
        name: Directory name such as ``20250102_030405`` or ``20250102_030405_1``.

    Returns:
        (created, suffix) or None when the name is not an archive run.
    """
    match = ARCHIVE_RUN_NAME_PATTERN.match(name)
    if not match:
        return None
    try:
        created = datetime.strptime(match.group(1), ARCHIVE_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return created, int(match.group(2) or 0)


def write_private_file(path: Path, data: bytes) -> None:
    """
    Write data, creating the file readable by the owner only.

    A new file is created with mode 0o600 from the start (no window where it
    is world-readable). An existing file keeps its current mode.

    Args:
        path: Destination file.
        data: Content to write.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def make_dirs(directory: Path, mode: int = 0o777) -> list[Path]:
    """
    Create directory and any missing parents with mode (umask applies).

    Existing directories are left unchanged.

    Args:
        directory: Directory to create.
        mode: Mode for each created directory.

    Returns:
        The directories that were created, outermost first.
    """
    missing = []
    current = directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    created = list(reversed(missing))
    for path in created:
        path.mkdir(mode=mode, exist_ok=True)
    return created


def make_private_dirs(directory: Path) -> list[Path]:
    """
    Create directory and any missing parents with mode 0o700.

    Existing directories are left unchanged.

    Args:
        directory: Directory to create.

    Returns:
        The directories that were created, outermost first.
    """
    return make_dirs(directory, 0o700)
