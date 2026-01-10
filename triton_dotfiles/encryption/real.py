"""
Real encryption implementation for triton-dotfiles.

Provides AES-256-GCM encryption for file protection.
"""

import secrets
from pathlib import Path
from typing import Union

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


class EncryptionManager:
    """Manages AES-256-GCM encryption functionality."""

    def __init__(self, key_file: Union[str, Path]):
        """
        Initialize the encryption manager.

        Args:
            key_file: Path to the key file (required).
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library is not installed")

        if not key_file:
            raise ValueError("key_file is required for real encryption")

        self.key_file = Path(key_file)
        self._master_key = None
        self._encryption_key = None
        self._nonce_key = None

    def key_exists(self) -> bool:
        """Check if the key file exists."""
        return self.key_file.exists()

    def _load_master_key(self) -> bytes:
        """Load the master key from file."""
        if self._master_key is not None:
            return self._master_key

        if not self.key_exists():
            raise FileNotFoundError(f"Encryption key file not found: {self.key_file}")

        with open(self.key_file, "rb") as f:
            key_data = f.read()

        if len(key_data) != 32:
            raise ValueError("Invalid key file (must be 32 bytes)")
        self._master_key = key_data

        return self._master_key

    def _get_encryption_key(self) -> bytes:
        """Derive the encryption-specific key."""
        if self._encryption_key is not None:
            return self._encryption_key

        master_key = self._load_master_key()
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"TRITON_ENCRYPTION_KEY",
            backend=default_backend(),
        )
        self._encryption_key = hkdf.derive(master_key)
        return self._encryption_key

    def _get_nonce_key(self) -> bytes:
        """Derive the nonce-generation-specific key."""
        if self._nonce_key is not None:
            return self._nonce_key

        master_key = self._load_master_key()
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"TRITON_NONCE_KEY",
            backend=default_backend(),
        )
        self._nonce_key = hkdf.derive(master_key)
        return self._nonce_key

    def _generate_deterministic_nonce(self, data: bytes, file_path: str = "") -> bytes:
        """
        Generate a deterministic nonce from file path, data, and dedicated key.

        Args:
            data: Data to be encrypted.
            file_path: File path (for improved security).

        Returns:
            12-byte deterministic nonce.
        """
        nonce_key = self._get_nonce_key()

        # ファイルパス + データ + 専用キーの組み合わせからハッシュを生成
        hash_input = file_path.encode("utf-8") + data + nonce_key
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(hash_input)
        hash_output = digest.finalize()

        # ハッシュの最初の12バイトをnonceとして使用
        return hash_output[:12]

    def encrypt_data(self, data: bytes, file_path: str = "") -> bytes:
        """
        Encrypt data using AES-256-GCM.

        Args:
            data: Data to encrypt.
            file_path: File path (used for nonce generation).

        Returns:
            Encrypted data (nonce + ciphertext + tag).
        """
        encryption_key = self._get_encryption_key()

        # 決定論的nonceを生成（ファイルパス含む）
        nonce = self._generate_deterministic_nonce(data, file_path)

        # AES-256-GCM暗号化
        cipher = Cipher(
            algorithms.AES(encryption_key), modes.GCM(nonce), backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data) + encryptor.finalize()

        # nonce + ciphertext + tagの形式で結合
        return nonce + ciphertext + encryptor.tag

    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt AES-256-GCM encrypted data.

        Args:
            encrypted_data: Encrypted data (nonce + ciphertext + tag).

        Returns:
            Decrypted data.
        """
        encryption_key = self._get_encryption_key()

        if len(encrypted_data) < 28:  # nonce(12) + tag(16) の最小サイズ
            raise ValueError("Invalid encrypted data (size too small)")

        # データを分割
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:-16]
        tag = encrypted_data[-16:]

        # AES-256-GCM復号化
        cipher = Cipher(
            algorithms.AES(encryption_key),
            modes.GCM(nonce, tag),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()

        try:
            return decryptor.update(ciphertext) + decryptor.finalize()
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def decrypt_file_content(self, file_path: Union[str, Path]) -> bytes:
        """
        Read and decrypt an encrypted file.

        Args:
            file_path: Path to the encrypted file.

        Returns:
            Decrypted data.
        """
        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()
            return self.decrypt_data(encrypted_data)
        except Exception as e:
            raise Exception(f"File decryption failed: {e}")


def generate_random_key() -> bytes:
    """Generate a 32-byte random key for AES-256."""
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError("cryptography library is not installed")
    return secrets.token_bytes(32)
