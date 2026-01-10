"""
Real encryption implementation for triton-dotfiles
AES-256-GCM暗号化によるファイル保護機能
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
    """AES-256-GCM暗号化機能を管理するクラス"""

    def __init__(self, key_file: Union[str, Path]):
        """
        暗号化マネージャーを初期化

        Args:
            key_file: キーファイルのパス（必須）
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
        """キーファイルが存在するかチェック"""
        return self.key_file.exists()

    def _load_master_key(self) -> bytes:
        """マスターキーを読み込み"""
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
        """暗号化専用キーを派生"""
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
        """nonce生成専用キーを派生"""
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
        ファイルパス、データ内容、専用キーから決定論的nonceを生成

        Args:
            data: 暗号化対象のデータ
            file_path: ファイルパス（セキュリティ向上のため）

        Returns:
            12バイトの決定論的nonce
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
        データをAES-256-GCMで暗号化

        Args:
            data: 暗号化するデータ
            file_path: ファイルパス（nonce生成に使用）

        Returns:
            暗号化されたデータ（nonce + ciphertext + tag）
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
        AES-256-GCMで暗号化されたデータを復号化

        Args:
            encrypted_data: 暗号化されたデータ（nonce + ciphertext + tag）

        Returns:
            復号化されたデータ
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
        暗号化ファイルを読み込んで復号化

        Args:
            file_path: 暗号化ファイルのパス

        Returns:
            復号化されたデータ
        """
        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()
            return self.decrypt_data(encrypted_data)
        except Exception as e:
            raise Exception(f"File decryption failed: {e}")


def generate_random_key() -> bytes:
    """AES-256用の32バイトランダムキーを生成"""
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError("cryptography ライブラリがインストールされていません")
    return secrets.token_bytes(32)
