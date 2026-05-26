from __future__ import annotations

import pytest

import triton_dotfiles.encryption as encryption
from triton_dotfiles.encryption.dummy import DummyEncryptionManager


def test_get_encryption_manager_requires_cryptography(monkeypatch, tmp_path):
    monkeypatch.setattr(encryption, "CRYPTOGRAPHY_AVAILABLE", False)

    with pytest.raises(ImportError, match="cryptography"):
        encryption.get_encryption_manager(tmp_path / "master.key")


def test_create_encryption_key_requires_cryptography(monkeypatch, tmp_path):
    monkeypatch.setattr(encryption, "CRYPTOGRAPHY_AVAILABLE", False)
    key_path = tmp_path / "triton" / "master.key"

    with pytest.raises(ImportError, match="cryptography"):
        encryption.create_encryption_key(key_path)

    assert not key_path.exists()
    assert not key_path.parent.exists()


def test_dummy_encryption_manager_fails_closed(tmp_path):
    manager = DummyEncryptionManager(tmp_path / "master.key")

    with pytest.raises(RuntimeError, match="cryptography"):
        manager.encrypt_data(b"secret")

    with pytest.raises(RuntimeError, match="cryptography"):
        manager.decrypt_data(b"secret")

    with pytest.raises(RuntimeError, match="cryptography"):
        manager.decrypt_file_content(tmp_path / "secret.enc")
