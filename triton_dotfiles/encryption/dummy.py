"""
Dummy encryption implementation for triton-dotfiles.

Fallback implementation when the cryptography library is not available.
"""

from pathlib import Path
from typing import Optional, Union


class DummyEncryptionManager:
    """Dummy implementation when the cryptography library is not available."""

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
        """Dummy implementation: return data as-is."""
        return data

    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """Dummy implementation: return data as-is."""
        return encrypted_data

    def decrypt_file_content(self, file_path: Union[str, Path]) -> bytes:
        """Dummy implementation: read file content as-is."""
        try:
            with open(file_path, "rb") as f:
                return f.read()
        except Exception as e:
            raise Exception(f"File reading failed: {e}")
