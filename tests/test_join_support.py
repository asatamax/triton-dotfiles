from __future__ import annotations

import subprocess
from pathlib import Path

from triton_dotfiles.config import Config, ConfigManager
from triton_dotfiles.encryption import (
    create_encryption_key,
    get_encryption_manager,
    verify_key_against_repository,
)
from triton_dotfiles.managers.file_manager import FileManager
from triton_dotfiles.managers.git_manager import GitManager
from triton_dotfiles.wizard_common import (
    read_repository_path_from_config,
    scan_vault_machines,
)


def _make_config_manager(repo_dir: Path) -> ConfigManager:
    config_manager = ConfigManager()
    config_manager._config = Config.from_dict(
        {
            "config": {
                "targets": [],
                "repository": {
                    "path": str(repo_dir),
                    "use_hostname": False,
                    "machine_name": "CurrentMachine",
                },
                "blacklist": [],
                "encrypt_list": [],
                "encryption": {"enabled": False},
            }
        }
    )
    return config_manager


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test"] + args,
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _make_source_repo(tmp_path: Path) -> Path:
    src = tmp_path / "src-vault"
    machine_dir = src / "MachineA"
    machine_dir.mkdir(parents=True)
    (machine_dir / ".zshrc").write_text("export FOO=bar\n")
    _git(["init"], src)
    _git(["add", "-A"], src)
    _git(["commit", "-m", "initial"], src)
    return src


# --- verify_key_against_repository ---


def test_verify_key_success(tmp_path):
    key_path = tmp_path / "master.key"
    create_encryption_key(key_path)

    vault = tmp_path / "vault"
    ssh_dir = vault / "MachineA" / ".ssh"
    ssh_dir.mkdir(parents=True)
    manager = get_encryption_manager(key_path)
    (ssh_dir / "id_rsa.enc").write_bytes(manager.encrypt_data(b"secret", "id_rsa"))

    result = verify_key_against_repository(key_path, vault)

    assert result["verified"] is True
    assert result["skipped"] is False
    assert result["tested_file"].endswith("id_rsa.enc")


def test_verify_key_mismatch(tmp_path):
    right_key = tmp_path / "right.key"
    wrong_key = tmp_path / "wrong.key"
    create_encryption_key(right_key)
    create_encryption_key(wrong_key)

    vault = tmp_path / "vault"
    vault.mkdir()
    manager = get_encryption_manager(right_key)
    (vault / "secret.enc").write_bytes(manager.encrypt_data(b"secret", "secret"))

    result = verify_key_against_repository(wrong_key, vault)

    assert result["verified"] is False
    assert result["skipped"] is False
    assert result["error"]


def test_verify_key_skipped_without_encrypted_files(tmp_path):
    key_path = tmp_path / "master.key"
    create_encryption_key(key_path)

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "plain.txt").write_text("hello")

    result = verify_key_against_repository(key_path, vault)

    assert result["verified"] is False
    assert result["skipped"] is True


def test_verify_key_skipped_without_key(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    result = verify_key_against_repository(tmp_path / "missing.key", vault)

    assert result["verified"] is False
    assert result["skipped"] is True


# --- GitManager.clone_repository ---


def test_clone_repository_success(tmp_path):
    src = _make_source_repo(tmp_path)
    dest = tmp_path / "vault"

    result = GitManager.clone_repository(str(src), dest)

    assert result["success"] is True
    assert (dest / ".git").exists()
    assert (dest / "MachineA" / ".zshrc").exists()


def test_clone_repository_rejects_non_empty_dir(tmp_path):
    src = _make_source_repo(tmp_path)
    dest = tmp_path / "vault"
    dest.mkdir()
    (dest / "existing.txt").write_text("data")

    result = GitManager.clone_repository(str(src), dest)

    assert result["success"] is False
    assert result["error"] == "DEST_NOT_EMPTY"


def test_clone_repository_rejects_existing_clone(tmp_path):
    src = _make_source_repo(tmp_path)
    dest = tmp_path / "vault"
    assert GitManager.clone_repository(str(src), dest)["success"] is True

    result = GitManager.clone_repository(str(src), dest)

    assert result["success"] is False
    assert result["error"] == "ALREADY_CLONED"


def test_get_remote_url(tmp_path):
    src = _make_source_repo(tmp_path)
    dest = tmp_path / "vault"
    GitManager.clone_repository(str(src), dest)

    assert GitManager(dest).get_remote_url() == str(src)
    assert GitManager(tmp_path / "nowhere").get_remote_url() == ""


# --- FileManager.ensure_machine_backup_dir ---


def test_ensure_machine_backup_dir_creates_folder(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    file_manager = FileManager(_make_config_manager(repo_dir))

    result = file_manager.ensure_machine_backup_dir("CurrentMachine")

    assert result == repo_dir / "CurrentMachine"
    assert result.is_dir()

    # Idempotent on an existing folder
    assert file_manager.ensure_machine_backup_dir("CurrentMachine") == result


def test_ensure_machine_backup_dir_without_repository(tmp_path):
    repo_dir = tmp_path / "missing-repo"
    file_manager = FileManager(_make_config_manager(repo_dir))

    assert file_manager.ensure_machine_backup_dir("CurrentMachine") is None
    assert not repo_dir.exists()


# --- wizard_common helpers ---


def test_scan_vault_machines(tmp_path):
    vault = tmp_path / "vault"
    (vault / "B4F" / ".ssh").mkdir(parents=True)
    (vault / "B4F" / ".ssh" / "config").write_text("Host *\n")
    (vault / "B4F" / ".zshrc").write_text("alias ll='ls -l'\n")
    (vault / "Empty").mkdir()
    (vault / ".git").mkdir()

    machines = scan_vault_machines(vault)

    assert [m["name"] for m in machines] == ["B4F", "Empty"]
    assert machines[0]["file_count"] == 2
    assert machines[1]["file_count"] == 0


def test_read_repository_path_from_config(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "config:\n  repository:\n    path: ~/dotfiles-vault\n",
    )

    result = read_repository_path_from_config(config_path)

    assert result == Path("~/dotfiles-vault").expanduser()
    assert read_repository_path_from_config(tmp_path / "missing.yml") is None
