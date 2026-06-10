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
) -> EncryptionManager:
    """
    Get an EncryptionManager instance.

    Args:
        key_file: Path to the key file.

    Returns:
        EncryptionManager instance.
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError("cryptography library is required for encryption")

    return EncryptionManager(key_file)


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
        ImportError: If cryptography is not available.
    """
    if key_path is None:
        key_path = Path.home() / ".config" / "triton" / "master.key"

    key_path = Path(key_path)

    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError("cryptography library is required to create encryption keys")

    # 既存キーのチェック
    if key_path.exists() and not force:
        raise FileExistsError(
            f"Key file already exists: {key_path}\n"
            "WARNING: Overwriting will make all encrypted files unrecoverable!\n"
            "Use --force to overwrite if you are sure."
        )

    key_path.parent.mkdir(parents=True, exist_ok=True)

    # 32バイトのランダムキーを保存
    key = generate_random_key()
    with open(key_path, "wb") as f:
        f.write(key)

    # キーファイルのアクセス権限を所有者のみに制限
    key_path.chmod(0o600)

    return str(key_path)


def verify_key_against_repository(
    key_file: Union[str, Path],
    repo_path: Union[str, Path],
) -> dict:
    """
    Verify that an encryption key can decrypt files in a repository.

    Picks the first ``.enc`` file found in the repository and attempts a
    test decryption. This detects key mismatches (e.g. a master.key from a
    different vault) before any restore operation is attempted.

    Args:
        key_file: Path to the master.key file.
        repo_path: Path to the vault repository root.

    Returns:
        Dictionary with verification results:
        - verified: True if a test decryption succeeded.
        - skipped: True if verification could not run (no key / no .enc files).
        - tested_file: Path of the .enc file used for the test, if any.
        - error: Failure reason when verified is False.
    """
    result = {"verified": False, "skipped": False, "tested_file": None, "error": None}

    key_path = Path(key_file)
    if not key_path.exists():
        result["skipped"] = True
        result["error"] = f"Key file not found: {key_path}"
        return result

    repo_root = Path(repo_path)
    if not repo_root.exists():
        result["skipped"] = True
        result["error"] = f"Repository not found: {repo_root}"
        return result

    encrypted_file = next(
        (f for f in repo_root.rglob("*.enc") if f.is_file()),
        None,
    )
    if encrypted_file is None:
        result["skipped"] = True
        result["error"] = "No encrypted files found in repository"
        return result

    result["tested_file"] = str(encrypted_file)

    try:
        manager = get_encryption_manager(key_path)
        manager.decrypt_file_content(encrypted_file)
        result["verified"] = True
    except Exception as e:
        result["error"] = str(e)

    return result


# 公開インターフェース
__all__ = [
    "get_encryption_manager",
    "create_encryption_key",
    "verify_key_against_repository",
    "EncryptionManager",
    "DummyEncryptionManager",
    "CRYPTOGRAPHY_AVAILABLE",
]
