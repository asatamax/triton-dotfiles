from __future__ import annotations

from pathlib import Path

from triton_dotfiles.config import Config, ConfigManager
from triton_dotfiles.managers.file_manager import FileManager


class FakeEncryptionManager:
    def __init__(self, decrypted_data: bytes):
        self.decrypted_data = decrypted_data

    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        return self.decrypted_data


def test_restore_archives_plaintext_destination_for_encrypted_backup(
    tmp_path, monkeypatch
):
    triton_dir = tmp_path / "triton"
    monkeypatch.setenv("TRITON_DIR", str(triton_dir))

    target_dir = tmp_path / "ssh"
    target_dir.mkdir()
    local_file = target_dir / "id_rsa"
    local_file.write_bytes(b"old-secret")

    repo_dir = tmp_path / "repo"
    backup_dir = repo_dir / "RemoteMachine" / target_dir.name
    backup_dir.mkdir(parents=True)
    (backup_dir / "id_rsa.enc").write_bytes(b"encrypted-secret")

    config_manager = ConfigManager()
    config_manager._config = Config.from_dict(
        {
            "config": {
                "targets": [{"path": str(target_dir), "files": ["id_rsa"]}],
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

    file_manager = FileManager(config_manager)
    file_manager.encryption_manager = FakeEncryptionManager(b"new-secret")

    result = file_manager.restore_files("RemoteMachine")

    assert local_file.read_bytes() == b"new-secret"
    assert len(result["backed_up"]) == 1

    archived_file = Path(result["backed_up"][0])
    assert archived_file.is_relative_to(triton_dir / "archives")
    assert archived_file.read_bytes() == b"old-secret"
