"""
Dummy encryption implementation for triton-dotfiles.

Fail-closed implementation when the cryptography library is not available.
"""

from pathlib import Path
from typing import Optional, Union


class DummyEncryptionManager:
    """Fail-closed implementation when cryptography is not available."""

    def __init__(
        self,
        key_file: Optional[Union[str, Path]] = None,
    ):
        if key_file:
            self.key_file = Path(key_file)
        else:
            self.key_file = Path.home() / ".config" / "triton" / "master.key"

    def key_exists(self) -> bool:
        return self.key_file.exists()

    def encrypt_data(self, data: bytes, file_path: str = "") -> bytes:
        """Fail instead of silently writing plaintext."""
        raise RuntimeError("cryptography library is required for encryption")

    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """Fail instead of treating encrypted data as plaintext."""
        raise RuntimeError("cryptography library is required for decryption")

    def decrypt_file_content(self, file_path: Union[str, Path]) -> bytes:
        """Fail instead of treating encrypted files as plaintext."""
        raise RuntimeError("cryptography library is required for decryption")
