"""
Encryption module for triton-dotfiles.

Provides a unified interface for encryption functionality.
"""

import importlib.util
from pathlib import Path
from typing import Optional, Union

from .real import EncryptionManager, generate_random_key
from .dummy import DummyEncryptionManager

CRYPTOGRAPHY_AVAILABLE = importlib.util.find_spec("cryptography") is not None


def get_encryption_manager(
    key_file: Optional[Union[str, Path]] = None,
) -> Union[EncryptionManager, DummyEncryptionManager]:
    """
    Get an appropriate EncryptionManager instance.

    Args:
        key_file: Path to the key file.

    Returns:
        EncryptionManager or DummyEncryptionManager instance.
    """
    if CRYPTOGRAPHY_AVAILABLE:
        return EncryptionManager(key_file)
    else:
        return DummyEncryptionManager(key_file)


def create_encryption_key(
    key_path: Optional[Union[str, Path]] = None,
    force: bool = False,
) -> str:
    """
    Create an encryption key file.

    Args:
        key_path: Path to save the key file (default: ~/.config/triton/master.key).
        force: Overwrite existing key if True.

    Returns:
        Path to the created key file.

    Raises:
        FileExistsError: If key exists and force is False.
    """
    if key_path is None:
        key_path = Path.home() / ".config" / "triton" / "master.key"

    key_path = Path(key_path)

    # 既存キーのチェック
    if key_path.exists() and not force:
        raise FileExistsError(
            f"Key file already exists: {key_path}\n"
            "WARNING: Overwriting will make all encrypted files unrecoverable!\n"
            "Use --force to overwrite if you are sure."
        )

    key_path.parent.mkdir(parents=True, exist_ok=True)

    if not CRYPTOGRAPHY_AVAILABLE:
        # cryptographyが利用できない場合はダミーファイルを作成
        key_path.write_text("dummy_key_for_testing")
        key_path.chmod(0o600)
        return str(key_path)

    # 32バイトのランダムキーを保存
    key = generate_random_key()
    with open(key_path, "wb") as f:
        f.write(key)

    # キーファイルのアクセス権限を所有者のみに制限
    key_path.chmod(0o600)

    return str(key_path)


# 公開インターフェース
__all__ = [
    "get_encryption_manager",
    "create_encryption_key",
    "EncryptionManager",
    "DummyEncryptionManager",
    "CRYPTOGRAPHY_AVAILABLE",
]
