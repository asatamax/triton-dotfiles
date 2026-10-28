"""Shared helpers for tests that build an isolated HOME / repository layout."""

from __future__ import annotations

from pathlib import Path

from triton_dotfiles.config import Config, ConfigManager
from triton_dotfiles.managers.file_manager import FileManager

MACHINE = "CurrentMachine"


def make_file_manager(
    env: dict,
    targets: list[dict],
    *,
    blacklist: list[str] | None = None,
    encrypt_list: list[str] | None = None,
    encryption: bool = False,
    skip_dirs: list[str] | None = None,
    max_file_size_mb: float | None = None,
    machine_name: str | None = MACHINE,
    use_hostname: bool = False,
) -> FileManager:
    """Build a FileManager from an in-memory config dict."""
    config: dict = {
        "targets": targets,
        "repository": {
            "path": str(env["repo"]),
            "use_hostname": use_hostname,
            "machine_name": machine_name,
        },
        "blacklist": blacklist or [],
        "encrypt_list": encrypt_list or [],
        "encryption": {"enabled": encryption},
    }
    if encryption:
        config["encryption"]["key_file"] = str(env["tmp"] / "master.key")
    if skip_dirs is not None:
        config["skip_dirs"] = skip_dirs
    if max_file_size_mb is not None:
        config["max_file_size_mb"] = max_file_size_mb

    config_manager = ConfigManager()
    config_manager._config = Config.from_dict({"config": config})
    return FileManager(config_manager)


def place(
    env: dict,
    local_rel: str | None,
    repo_rel: str | None = None,
    content: bytes = b"data",
) -> None:
    """Create a local file under HOME and its copy in the repository."""
    if local_rel is not None:
        local = env["home"] / local_rel
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(content)
    repo_path = env["backup_dir"] / (repo_rel or local_rel)
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.write_bytes(content)


def repo_has(env: dict, rel: str) -> bool:
    return (env["backup_dir"] / rel).exists()


def collected(fm: FileManager) -> set[str]:
    """Relative paths backup would collect from the first target."""
    target = fm.config_manager.config.targets[0]
    return {rel for _abs, rel in fm.collect_target_files(target)}


def write_file(path: Path, content: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
