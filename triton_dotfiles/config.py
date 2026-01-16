#!/usr/bin/env python3
"""
Dotfiles管理 - 設定管理モジュール
"""

import os
import re
import shutil
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

import yaml

from .utils import get_triton_dir


# --- Settings Key Definitions ---
# Each key defines: type, default, required, description, and optional choices/validation
SETTINGS_KEYS: Dict[str, Dict[str, Any]] = {
    "max_file_size_mb": {
        "type": "number",
        "default": 3.0,
        "required": False,
        "description": "Maximum file size in MB (0 = no limit)",
        "path": ["config", "max_file_size_mb"],
    },
    "encryption.enabled": {
        "type": "boolean",
        "default": False,
        "required": False,
        "description": "Enable AES-256-GCM encryption for sensitive files",
        "path": ["config", "encryption", "enabled"],
    },
    "encryption.key_file": {
        "type": "string",
        "default": "${TRITON_DIR:-~/.config/triton}/master.key",
        "required": False,
        "description": "Path to encryption master key file",
        "path": ["config", "encryption", "key_file"],
    },
    "repository.path": {
        "type": "string",
        "default": None,
        "required": True,
        "description": "Backup destination directory path",
        "path": ["config", "repository", "path"],
    },
    "repository.use_hostname": {
        "type": "boolean",
        "default": True,
        "required": False,
        "description": "Auto-detect machine name from hostname",
        "path": ["config", "repository", "use_hostname"],
    },
    "repository.machine_name": {
        "type": "string",
        "default": None,
        "required": False,
        "description": "Override auto-detected machine name (null = use hostname)",
        "path": ["config", "repository", "machine_name"],
    },
    "repository.auto_pull": {
        "type": "boolean",
        "default": True,
        "required": False,
        "description": "Automatically run git pull when TUI starts",
        "path": ["config", "repository", "auto_pull"],
    },
    "tui.theme": {
        "type": "enum",
        "default": None,
        "required": False,
        "description": "TUI color theme",
        "choices": ["nord", "gruvbox", "textual-dark"],
        "path": ["config", "tui", "theme"],
    },
    "tui.hide_system_files": {
        "type": "boolean",
        "default": True,
        "required": False,
        "description": "Hide system files in file list",
        "path": ["config", "tui", "hide_system_files"],
    },
}


def get_machine_name_unified(
    use_hostname: bool = True, configured_machine_name: Optional[str] = None
) -> str:
    """
    統一されたマシン名取得ロジック
    - configured_machine_nameが設定されている場合はそれを優先
    - VPN接続時のip-192.168...形式を回避
    - macOS/Linux/Windowsでの適切なマシン名取得
    """
    # If machine_name is explicitly configured, use it
    if configured_machine_name:
        return configured_machine_name

    if use_hostname:
        hostname = socket.gethostname().split(".")[0]
        # IPアドレス形式やVPN形式の場合はplatform.nodeまたはSCUTILを試す
        # IP形式: 192.168.*, 10.*, ip-192-168-*, ip-10-* など
        is_ip_like = (
            hostname.replace(".", "").replace(":", "").isdigit()  # 純粋なIP
            or hostname.startswith("10.")
            or hostname.startswith("192.168.")  # 標準IP
            or hostname.startswith("ip-10-")
            or hostname.startswith("ip-192-168-")  # VPN形式
        )

        if is_ip_like:
            try:
                import platform

                alt_name = platform.node().split(".")[0]
                # platform.nodeも同様に判定
                alt_is_ip_like = (
                    alt_name.replace(".", "").replace(":", "").isdigit()
                    or alt_name.startswith("10.")
                    or alt_name.startswith("192.168.")
                    or alt_name.startswith("ip-10-")
                    or alt_name.startswith("ip-192-168-")
                )
                if alt_name and not alt_is_ip_like:
                    return alt_name
            except ImportError:
                pass

            # macOSの場合はscutilを試す
            try:
                import subprocess

                result = subprocess.run(
                    ["scutil", "--get", "ComputerName"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                computer_name = result.stdout.strip()
                if computer_name:
                    return computer_name
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        return hostname
    elif configured_machine_name:
        return configured_machine_name
    else:
        raise ValueError("Machine name not configured")


def expand_env_vars(value: Any, missing_vars: Set[str] = None) -> Any:
    """環境変数を展開（${VAR}または${VAR:-default}形式をサポート）"""
    if missing_vars is None:
        missing_vars = set()

    if isinstance(value, str):
        # ${VAR:-default} パターンを処理
        def replace_env_var(match):
            var_expr = match.group(1)
            if ":-" in var_expr:
                var_name, default_value = var_expr.split(":-", 1)
                env_value = os.getenv(var_name)
                if env_value is None:
                    missing_vars.add(var_name)
                    return default_value
                return env_value
            else:
                var_name = var_expr
                env_value = os.getenv(var_name)
                if env_value is None:
                    missing_vars.add(var_name)
                    return f"${{{var_name}}}"  # 未定義の場合は元の形式を保持
                return env_value

        # ${VAR} または ${VAR:-default} パターンを置換
        expanded = re.sub(r"\$\{([^}]+)\}", replace_env_var, value)
        return expanded

    elif isinstance(value, dict):
        return {k: expand_env_vars(v, missing_vars) for k, v in value.items()}

    elif isinstance(value, list):
        return [expand_env_vars(item, missing_vars) for item in value]

    return value


@dataclass
class Target:
    """バックアップ対象の設定"""

    path: str
    files: Optional[List[str]] = None
    recursive: bool = False
    encrypt_files: Optional[List[str]] = None

    def __post_init__(self):
        if self.files is None:
            self.files = []
        if self.encrypt_files is None:
            self.encrypt_files = []


@dataclass
class EncryptionConfig:
    """暗号化設定"""

    enabled: bool = False
    key_file: Optional[str] = None


@dataclass
class RepositoryConfig:
    """リポジトリ設定"""

    use_hostname: bool = True
    machine_name: Optional[str] = None
    path: Optional[str] = None  # バックアップ先ディレクトリ
    excluded_directories: Optional[List[str]] = (
        None  # マシン検索時に除外するディレクトリ
    )
    auto_pull: bool = True  # 起動時に自動でgit pullを実行（デフォルト: True）


@dataclass
class TUIConfig:
    """TUI設定"""

    hide_system_files: bool = True
    system_file_patterns: List[str] = None
    theme: Optional[str] = None  # テーマ名（例: "nord", "gruvbox", "textual-dark"）

    def __post_init__(self):
        if self.system_file_patterns is None:
            self.system_file_patterns = [
                ".DS_Store",
                "._*",
                "Thumbs.db",
                "desktop.ini",
                ".Spotlight-V100",
                ".Trashes",
                "ehthumbs.db",
            ]


@dataclass
class HooksConfig:
    """Hooks設定（起動時コマンド実行）"""

    on_startup: List[str] = None  # 起動時に実行するコマンドリスト
    timeout: int = 30  # 全hook合計のタイムアウト（秒）

    def __post_init__(self):
        if self.on_startup is None:
            self.on_startup = []
        # 単一文字列の場合はリストに変換
        elif isinstance(self.on_startup, str):
            self.on_startup = [self.on_startup]


@dataclass
class Config:
    """dotfiles管理の設定"""

    targets: List[Target]
    blacklist: List[str]
    encrypt_list: List[str]
    repository: RepositoryConfig
    encryption: EncryptionConfig
    tui: TUIConfig
    hooks: HooksConfig
    max_file_size_mb: float = 3.0  # デフォルト3MB

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """辞書からConfigオブジェクトを作成"""
        config_data = data.get("config", {})

        # targetsの変換
        targets = []
        for i, target_data in enumerate(config_data.get("targets", [])):
            # pathが必須であることを確認
            if "path" not in target_data:
                raise ValueError(
                    f"Target {i}: 'path' is required. Use 'path' -> 'files' format only."
                )

            # filesとrecursiveの組み合わせ処理
            # （バリデーション時に詳細な情報が表示される）

            targets.append(
                Target(
                    path=target_data["path"],
                    files=target_data.get("files", []),
                    recursive=target_data.get("recursive", False),
                    encrypt_files=target_data.get("encrypt_files", []),
                )
            )

        # repositoryの変換
        repo_data = config_data.get("repository", {})
        repository = RepositoryConfig(
            use_hostname=repo_data.get("use_hostname", True),
            machine_name=repo_data.get("machine_name"),
            path=repo_data.get("path"),
            excluded_directories=repo_data.get("excluded_directories"),
            auto_pull=repo_data.get("auto_pull", True),
        )

        # encryptionの変換
        encryption_data = config_data.get("encryption", {})
        encryption = EncryptionConfig(
            enabled=encryption_data.get("enabled", False),
            key_file=encryption_data.get("key_file"),
        )

        # tuiの変換
        tui_data = config_data.get("tui", {})
        tui = TUIConfig(
            hide_system_files=tui_data.get("hide_system_files", True),
            system_file_patterns=tui_data.get("system_file_patterns"),
            theme=tui_data.get("theme"),
        )

        # hooksの変換
        hooks_data = config_data.get("hooks", {})
        hooks = HooksConfig(
            on_startup=hooks_data.get("on_startup"),
            timeout=hooks_data.get("timeout", 30),
        )

        return cls(
            targets=targets,
            blacklist=config_data.get("blacklist", []),
            encrypt_list=config_data.get("encrypt_list", []),
            repository=repository,
            encryption=encryption,
            tui=tui,
            hooks=hooks,
            max_file_size_mb=config_data.get("max_file_size_mb", 3.0),
        )


class ConfigManager:
    """設定ファイルの管理クラス"""

    def __init__(self, config_path: str = "config.yml"):
        self.config_path = Path(config_path)
        self._config = None
        self._missing_env_vars = set()

    def load_config(self) -> Config:
        """設定ファイルを読み込み（環境変数展開含む）"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 環境変数を展開し、未定義変数を記録
        self._missing_env_vars.clear()
        expanded_data = expand_env_vars(data, self._missing_env_vars)

        self._config = Config.from_dict(expanded_data)
        return self._config

    @property
    def config(self) -> Config:
        """設定オブジェクトを取得（遅延読み込み）"""
        if self._config is None:
            self._config = self.load_config()
        return self._config

    @property
    def missing_env_vars(self) -> Set[str]:
        """未定義の環境変数リストを取得"""
        if self._config is None:
            self.load_config()
        return self._missing_env_vars.copy()

    def get_machine_name(self) -> str:
        """マシン名を取得（統一ロジック使用）"""
        return get_machine_name_unified(
            use_hostname=self.config.repository.use_hostname,
            configured_machine_name=self.config.repository.machine_name,
        )

    def get_excluded_directories(self) -> List[str]:
        """マシン検索時に除外するディレクトリリストを取得"""
        # 設定ファイルで指定された除外ディレクトリ
        configured_excluded = self.config.repository.excluded_directories or []

        # デフォルトの除外ディレクトリ（開発関連・システム関連）
        default_excluded = [
            "scripts",  # スクリプトディレクトリ
            "__pycache__",  # Python cache
            "triton_dotfiles",  # パッケージディレクトリ
            ".git",  # Git ディレクトリ
            ".pytest_cache",  # Pytest cache
            "node_modules",  # Node.js modules
            ".venv",  # Python virtual environment
            "venv",  # Python virtual environment
            "build",  # Build directory
            "dist",  # Distribution directory
            ".tox",  # Tox testing directory
            ".coverage",  # Coverage data
        ]

        # 重複を除去して結合
        return list(set(configured_excluded + default_excluded))

    def validate_config(self) -> List[str]:
        """設定の妥当性をチェック（環境変数未定義警告含む）"""
        errors = []
        warnings = []

        # 未定義環境変数の警告
        if self.missing_env_vars:
            for var in sorted(self.missing_env_vars):
                warnings.append(f"!Environment variable '{var}' is not defined")

        # 基本チェック
        if not self.config.targets:
            errors.append("✗No targets specified")

        # 各targetのチェック
        for i, target in enumerate(self.config.targets):
            if not target.path:
                errors.append(f"✗Target {i}: path is empty")
            elif "${" in target.path:
                # 環境変数が未展開の場合
                warnings.append(
                    f"!Target {i}: path contains undefined environment variables: {target.path}"
                )

            # パス展開してチェック
            try:
                Path(target.path).expanduser()

                # ターゲット論理規則のバリデーション
                if not target.recursive and not target.files:
                    errors.append(
                        f"✗Target {i}: non-recursive targets must specify 'files' list"
                    )

                if target.files and not isinstance(target.files, list):
                    errors.append(f"✗Target {i}: 'files' must be a list")

                if target.files:
                    for j, file_pattern in enumerate(target.files):
                        if not file_pattern or not isinstance(file_pattern, str):
                            errors.append(
                                f"✗Target {i}, file {j}: empty or invalid filename pattern"
                            )

                # encrypt_filesのバリデーション
                if target.encrypt_files and not isinstance(target.encrypt_files, list):
                    errors.append(f"✗Target {i}: 'encrypt_files' must be a list")

                if target.encrypt_files:
                    for j, encrypt_pattern in enumerate(target.encrypt_files):
                        if not encrypt_pattern or not isinstance(encrypt_pattern, str):
                            errors.append(
                                f"✗Target {i}, encrypt_files {j}: empty or invalid pattern"
                            )

                # 論理性のチェック（情報提供）
                if target.recursive and target.files:
                    warnings.append(
                        f"iTarget {i}: recursive filtered mode - collecting '{target.files}' from all subdirectories"
                    )
                elif target.recursive and not target.files:
                    warnings.append(
                        f"iTarget {i}: recursive all mode - collecting all files from directory tree"
                    )
                elif not target.recursive and target.files:
                    warnings.append(
                        f"iTarget {i}: files only mode - collecting '{target.files}' from direct path only"
                    )

            except Exception as e:
                errors.append(f"✗Target {i}: invalid path format: {e}")

        # リポジトリパスのチェック
        if not self.config.repository.path:
            errors.append("✗Repository path is required")
        elif "${" in str(self.config.repository.path):
            warnings.append(
                f"!Repository path contains undefined environment variables: {self.config.repository.path}"
            )

        # blacklistパターンのチェック
        if not self.config.blacklist:
            warnings.append("!No blacklist patterns specified")

        # ファイルサイズ制限の情報表示
        if self.config.max_file_size_mb > 0:
            warnings.append(
                f"iFile size limit: {self.config.max_file_size_mb}MB (files larger than this will be skipped)"
            )

        # 警告とエラーを結合して返す
        return warnings + errors

    def get_validation_errors(self) -> List[str]:
        """エラーのみを取得（警告・情報は除外）"""
        results = self.validate_config()
        # ✗で始まるもののみをエラーとして扱う
        return [result for result in results if result.startswith("✗")]

    def expand_path(self, path: str) -> Path:
        """パスを展開（~やシェル変数を解決）"""
        return Path(os.path.expandvars(os.path.expanduser(path)))

    def is_blacklisted(self, file_path: Path) -> bool:
        """ファイルがblacklistに該当するかチェック"""
        from .utils import matches_any_pattern

        return matches_any_pattern(file_path, self.config.blacklist)

    def should_encrypt(self, file_path: Path) -> bool:
        """ファイルが暗号化対象かチェック（グローバルencrypt_listのみ）"""
        if not self.config.encryption.enabled:
            return False

        from .utils import matches_any_pattern

        return matches_any_pattern(file_path, self.config.encrypt_list)

    def should_encrypt_file(
        self, file_path: Path, target: "Target", relative_path: Path
    ) -> bool:
        """
        ファイルが暗号化対象かチェック（target.encrypt_filesを優先）

        評価順序:
        1. target.encrypt_filesにマッチ → 暗号化
        2. グローバルencrypt_listにマッチ → 暗号化
        3. どちらにもマッチしない → 平文

        Args:
            file_path: チェック対象のファイルパス（絶対パス）
            target: 対象のTarget設定
            relative_path: targetのpathからの相対パス

        Returns:
            暗号化すべき場合True
        """
        if not self.config.encryption.enabled:
            return False

        from .utils import matches_any_pattern

        # 1. target.encrypt_filesを優先チェック（相対パスでマッチング）
        if target.encrypt_files:
            if matches_any_pattern(relative_path, target.encrypt_files):
                return True

        # 2. グローバルencrypt_listをチェック（絶対パスでマッチング）
        return matches_any_pattern(file_path, self.config.encrypt_list)

    def should_exclude(self, file_path: Path) -> bool:
        """ファイルが除外対象かチェック（暗号化無効時のencrypt_listとblacklist）"""
        # 常にblacklistをチェック
        if self.is_blacklisted(file_path):
            return True

        # 暗号化が無効の場合、encrypt_listも除外対象
        if not self.config.encryption.enabled:
            from .utils import matches_any_pattern

            return matches_any_pattern(file_path, self.config.encrypt_list)

        return False

    def should_skip_target(self, target: "Target") -> bool:
        """環境変数未定義によりtargetをスキップすべきかチェック"""
        # パスに未定義の環境変数が含まれている場合はスキップ
        if "${" in target.path:
            return True

        # ファイルリストに未定義の環境変数が含まれている場合もスキップ
        for file_pattern in target.files or []:
            if "${" in file_pattern:
                return True

        return False

    def is_file_too_large(self, file_path: Path) -> bool:
        """ファイルサイズが制限を超えているかチェック"""
        try:
            if not file_path.exists() or not file_path.is_file():
                return False

            file_size_mb = file_path.stat().st_size / (1024 * 1024)  # バイトをMBに変換
            return file_size_mb > self.config.max_file_size_mb
        except (OSError, PermissionError):
            # ファイルアクセスエラーの場合は制限対象外として扱う
            return False

    def get_file_size_mb(self, file_path: Path) -> float:
        """Get file size in MB."""
        try:
            if file_path.exists() and file_path.is_file():
                return file_path.stat().st_size / (1024 * 1024)
            return 0.0
        except (OSError, PermissionError):
            return 0.0

    # --- Config Management Methods ---

    def normalize_path(self, path: str) -> str:
        """
        Normalize path to use ~/ format for user home paths.

        Examples:
            /Users/username/.ssh -> ~/.ssh
            /Users/username -> ~/
            ~/ -> ~/
            ./relative -> ~/current/working/dir/relative (if under home)
            /etc/hosts -> /etc/hosts (unchanged)
            ${ENV_VAR}/path -> ~/expanded/path (if under home)
        """
        # Expand environment variables first, then ~ and resolve to absolute path
        env_expanded = os.path.expandvars(path)
        expanded = Path(env_expanded).expanduser().resolve()
        home = Path.home()

        # If path is under user home, convert to ~/ format
        try:
            relative_to_home = expanded.relative_to(home)
            # Handle home directory itself (relative_to_home is empty/current dir)
            if str(relative_to_home) == ".":
                return "~/"
            return f"~/{relative_to_home}"
        except ValueError:
            # Path is not under home directory
            return str(expanded)

    def backup_config_file(self) -> Optional[Path]:
        """
        Backup config file to archives/config/{timestamp}/ directory.

        Uses the same timestamp format as restore archives (YYYYmmdd_HHMMSS).

        Returns:
            Path to backup file, or None if config doesn't exist
        """
        if not self.config_path.exists():
            return None

        # Use same timestamp format as restore archives
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create archive directory: archives/config/{timestamp}/
        triton_dir = get_triton_dir()
        archive_dir = triton_dir / "archives" / "config" / timestamp
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Copy config to archive
        backup_path = archive_dir / self.config_path.name
        shutil.copy2(self.config_path, backup_path)
        return backup_path

    def find_target_by_path(self, normalized_path: str) -> Optional[Target]:
        """Find existing target by normalized path."""
        for target in self.config.targets:
            # Both paths must be normalized to ~/format for consistent comparison
            if self.normalize_path(target.path) == normalized_path:
                return target
        return None

    def is_path_covered_by_recursive(
        self, normalized_path: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if path is covered by an existing recursive target.

        Returns:
            Tuple of (is_covered, covering_target_path)
        """
        check_path = Path(normalized_path).expanduser().resolve()

        for target in self.config.targets:
            if not target.recursive:
                continue

            target_path = Path(target.path).expanduser().resolve()

            # Check if the new path is under an existing recursive target
            try:
                check_path.relative_to(target_path)
                # Path is under this recursive target
                return (True, target.path)
            except ValueError:
                continue

        return (False, None)

    def is_file_covered_by_non_recursive_target(
        self, normalized_path: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a file path is covered by an existing non-recursive target's files list.

        Args:
            normalized_path: Normalized path to check (e.g., ~/foo/bar.txt)

        Returns:
            Tuple of (is_covered, target_path, matched_file_pattern)
        """
        check_path = Path(normalized_path).expanduser().resolve()

        # Only check if it's a file (or looks like a file path)
        if check_path.exists() and check_path.is_dir():
            return (False, None, None)

        for target in self.config.targets:
            # Skip recursive targets (handled by is_path_covered_by_recursive)
            if target.recursive:
                continue

            target_path = Path(target.path).expanduser().resolve()

            # Check if the file is under this target's directory
            try:
                relative_path = check_path.relative_to(target_path)
            except ValueError:
                continue

            # Check if the relative path matches any file pattern in the target
            relative_str = str(relative_path)
            for file_pattern in target.files:
                # Handle exact match
                if relative_str == file_pattern:
                    return (True, target.path, file_pattern)

                # Handle glob patterns using fnmatch
                import fnmatch

                if fnmatch.fnmatch(relative_str, file_pattern):
                    return (True, target.path, file_pattern)

        return (False, None, None)

    def would_cover_existing_targets(
        self, normalized_path: str, recursive: bool
    ) -> list[str]:
        """
        Check if adding a recursive target would cover existing targets.

        Returns:
            List of existing target paths that would be covered
        """
        if not recursive:
            return []

        covered = []
        new_path = Path(normalized_path).expanduser().resolve()

        for target in self.config.targets:
            target_path = Path(target.path).expanduser().resolve()

            try:
                target_path.relative_to(new_path)
                # Existing target is under the new recursive path
                covered.append(target.path)
            except ValueError:
                continue

        return covered

    def add_target(
        self,
        path: str,
        files: Optional[List[str]] = None,
        recursive: bool = False,
        encrypt_files: Optional[List[str]] = None,
        backup: bool = True,
    ) -> dict:
        """
        Add a new target to the configuration.

        Args:
            path: Target path (will be normalized)
            files: List of file patterns
            recursive: Whether to backup recursively
            encrypt_files: List of files to encrypt
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', and optionally 'backup_path'
        """
        normalized = self.normalize_path(path)

        # Check for exact duplicate
        existing = self.find_target_by_path(normalized)
        if existing:
            return {
                "success": False,
                "message": f"Target {normalized} already exists",
            }

        # Check if covered by recursive target
        is_covered, covering_path = self.is_path_covered_by_recursive(normalized)
        if is_covered:
            return {
                "success": False,
                "message": f"Path {normalized} is already covered by recursive target {covering_path}",
            }

        # Check if file is covered by non-recursive target's files list
        is_file_covered, target_path, matched_pattern = (
            self.is_file_covered_by_non_recursive_target(normalized)
        )
        if is_file_covered:
            return {
                "success": False,
                "message": f"File {normalized} is already included in target {target_path} (matches pattern: {matched_pattern})",
            }

        # Check if this would cover existing targets (warning only for recursive)
        if recursive:
            would_cover = self.would_cover_existing_targets(normalized, recursive)
            if would_cover:
                return {
                    "success": False,
                    "message": f"Recursive target {normalized} would cover existing targets: {', '.join(would_cover)}. Remove them first.",
                }

        # Validate files requirement for non-recursive targets
        if not recursive and not files:
            return {
                "success": False,
                "message": "Non-recursive targets must specify files list",
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, add target, and save (preserves environment variables)
        raw_data = self._load_raw_config()
        # Preserve environment variable format if present, otherwise use normalized path
        path_to_save = path if "${" in path else normalized
        new_target_dict: Dict[str, Any] = {"path": path_to_save}
        if files:
            new_target_dict["files"] = files
        if recursive:
            new_target_dict["recursive"] = recursive
        if encrypt_files:
            new_target_dict["encrypt_files"] = encrypt_files

        raw_data["config"]["targets"].append(new_target_dict)
        self._save_raw_config(raw_data)

        # Invalidate cached config (will reload on next access)
        self._config = None

        # Create Target object for return value
        new_target = Target(
            path=normalized,
            files=files or [],
            recursive=recursive,
            encrypt_files=encrypt_files or [],
        )

        result = {
            "success": True,
            "message": f"Added target {normalized}",
            "target": new_target,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def remove_target(self, path: str, backup: bool = True) -> dict:
        """
        Remove a target from the configuration.

        Args:
            path: Target path to remove
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', and optionally 'backup_path'
        """
        normalized = self.normalize_path(path)

        # Find target index in expanded config
        # Both paths must be normalized to ~/format for consistent comparison
        target_index = None
        removed_target = None
        for i, target in enumerate(self.config.targets):
            if self.normalize_path(target.path) == normalized:
                target_index = i
                removed_target = target
                break

        if target_index is None:
            return {
                "success": False,
                "message": f"Target {normalized} not found",
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, remove target by index, and save (preserves environment variables)
        raw_data = self._load_raw_config()
        raw_data["config"]["targets"].pop(target_index)
        self._save_raw_config(raw_data)

        # Invalidate cached config (will reload on next access)
        self._config = None

        result = {
            "success": True,
            "message": f"Removed target {normalized}",
            "target": removed_target,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def modify_target(
        self,
        path: str,
        add_files: Optional[List[str]] = None,
        remove_files: Optional[List[str]] = None,
        add_encrypt_files: Optional[List[str]] = None,
        remove_encrypt_files: Optional[List[str]] = None,
        recursive: Optional[bool] = None,
        backup: bool = True,
    ) -> dict:
        """
        Modify an existing target's configuration.

        Args:
            path: Target path to modify (will be normalized)
            add_files: File patterns to add to the files list
            remove_files: File patterns to remove from the files list
            add_encrypt_files: Patterns to add to encrypt_files list
            remove_encrypt_files: Patterns to remove from encrypt_files list
            recursive: Set recursive flag (None = no change)
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', 'target', and optionally 'backup_path'
        """
        normalized = self.normalize_path(path)

        # Find existing target
        # Both paths must be normalized to ~/format for consistent comparison
        target_index = None
        for i, target in enumerate(self.config.targets):
            if self.normalize_path(target.path) == normalized:
                target_index = i
                break

        if target_index is None:
            return {
                "success": False,
                "message": f"Target {normalized} not found",
                "changed": False,
            }

        # Check if any modification is requested
        has_modification = any(
            [
                add_files,
                remove_files,
                add_encrypt_files,
                remove_encrypt_files,
                recursive is not None,
            ]
        )
        if not has_modification:
            return {
                "success": False,
                "message": "No modification specified. Use --add-files, --remove-files, --add-encrypt-files, --remove-encrypt-files, --recursive, or --no-recursive.",
                "changed": False,
            }

        # Load raw config to modify
        raw_data = self._load_raw_config()
        raw_target = raw_data["config"]["targets"][target_index]

        # Track changes
        changes = []

        # Handle files list modifications
        current_files = list(raw_target.get("files", []))
        if add_files:
            added = []
            for f in add_files:
                if f not in current_files:
                    current_files.append(f)
                    added.append(f)
            if added:
                changes.append(f"Added files: {', '.join(added)}")

        if remove_files:
            removed = []
            for f in remove_files:
                if f in current_files:
                    current_files.remove(f)
                    removed.append(f)
            if removed:
                changes.append(f"Removed files: {', '.join(removed)}")

        # Handle encrypt_files list modifications
        current_encrypt = list(raw_target.get("encrypt_files", []))
        if add_encrypt_files:
            added = []
            for f in add_encrypt_files:
                if f not in current_encrypt:
                    current_encrypt.append(f)
                    added.append(f)
            if added:
                changes.append(f"Added encrypt_files: {', '.join(added)}")

        if remove_encrypt_files:
            removed = []
            for f in remove_encrypt_files:
                if f in current_encrypt:
                    current_encrypt.remove(f)
                    removed.append(f)
            if removed:
                changes.append(f"Removed encrypt_files: {', '.join(removed)}")

        # Handle recursive flag
        current_recursive = raw_target.get("recursive", False)
        if recursive is not None and recursive != current_recursive:
            # Validate: switching to non-recursive requires files
            if not recursive and not current_files:
                return {
                    "success": False,
                    "message": "Cannot disable recursive without files. Add --add-files or keep --recursive.",
                    "changed": False,
                }
            changes.append(f"Changed recursive: {current_recursive} -> {recursive}")
            current_recursive = recursive

        # Check if files are required after modifications
        if not current_recursive and not current_files:
            return {
                "success": False,
                "message": "Non-recursive targets must have at least one file pattern.",
                "changed": False,
            }

        # If no actual changes were made
        if not changes:
            return {
                "success": True,
                "message": "No changes needed (already in desired state)",
                "changed": False,
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Update raw target
        if current_files:
            raw_target["files"] = current_files
        elif "files" in raw_target:
            del raw_target["files"]

        if current_encrypt:
            raw_target["encrypt_files"] = current_encrypt
        elif "encrypt_files" in raw_target:
            del raw_target["encrypt_files"]

        if current_recursive:
            raw_target["recursive"] = current_recursive
        elif "recursive" in raw_target:
            del raw_target["recursive"]

        # Save updated config
        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        # Create updated Target object for return
        updated_target = Target(
            path=normalized,
            files=current_files if current_files else None,
            recursive=current_recursive,
            encrypt_files=current_encrypt if current_encrypt else None,
        )

        result = {
            "success": True,
            "message": f"Modified target {normalized}: {'; '.join(changes)}",
            "changed": True,
            "target": updated_target,
            "changes": changes,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def check_target_path(self, path: str) -> dict:
        """
        Check a path for potential target addition.

        Returns detailed information about the path and any conflicts.
        """
        normalized = self.normalize_path(path)
        expanded = Path(normalized).expanduser()

        result = {
            "path": normalized,
            "expanded_path": str(expanded),
            "exists": expanded.exists(),
            "is_directory": expanded.is_dir() if expanded.exists() else None,
            "is_file": expanded.is_file() if expanded.exists() else None,
            "conflicts": [],
            "warnings": [],
            "suggestions": [],
        }

        # Check for duplicates
        existing = self.find_target_by_path(normalized)
        if existing:
            result["conflicts"].append(f"Target {normalized} already exists")

        # Check if covered by recursive target
        is_covered, covering_path = self.is_path_covered_by_recursive(normalized)
        if is_covered:
            result["conflicts"].append(
                f"Path is covered by recursive target {covering_path}"
            )

        # Check if file is covered by non-recursive target's files list
        is_file_covered, target_path, matched_pattern = (
            self.is_file_covered_by_non_recursive_target(normalized)
        )
        if is_file_covered:
            result["conflicts"].append(
                f"File is already included in target {target_path} "
                f"(matches pattern: {matched_pattern})"
            )

        # Count files if directory exists
        if expanded.exists() and expanded.is_dir():
            try:
                file_count = sum(1 for f in expanded.rglob("*") if f.is_file())
                result["file_count"] = file_count
            except PermissionError:
                result["warnings"].append("Cannot read directory contents")

        # Generate suggestions
        if not result["conflicts"]:
            if expanded.is_dir():
                result["suggestions"].append(
                    f"triton config target add {normalized} --recursive"
                )
                result["suggestions"].append(
                    f'triton config target add {normalized} --files "*"'
                )
            elif expanded.is_file():
                parent = self.normalize_path(str(expanded.parent))
                result["suggestions"].append(
                    f'triton config target add {parent} --files "{expanded.name}"'
                )

        return result

    def _load_raw_config(self) -> dict:
        """Load config as raw dict without environment variable expansion."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _save_raw_config(self, data: dict) -> None:
        """Save raw config dict to YAML file (preserves environment variables and key order)."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                width=120,
                sort_keys=False,
            )

    def _save_config(self) -> None:
        """Save current config to YAML file."""
        # Convert config to dict
        config_dict = self._config_to_dict()

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                config_dict, f, default_flow_style=False, allow_unicode=True, width=120
            )

    def _config_to_dict(self) -> dict:
        """Convert Config object to dictionary for YAML serialization."""
        targets_list = []
        for target in self.config.targets:
            target_dict = {"path": target.path}
            if target.files:
                target_dict["files"] = target.files
            if target.recursive:
                target_dict["recursive"] = target.recursive
            if target.encrypt_files:
                target_dict["encrypt_files"] = target.encrypt_files
            targets_list.append(target_dict)

        # hooks設定（空の場合は省略）
        hooks_dict = {}
        if self.config.hooks.on_startup:
            hooks_dict["on_startup"] = self.config.hooks.on_startup
        if self.config.hooks.timeout != 30:  # デフォルト値以外の場合のみ出力
            hooks_dict["timeout"] = self.config.hooks.timeout

        result = {
            "config": {
                "repository": {
                    "path": self.config.repository.path,
                    "use_hostname": self.config.repository.use_hostname,
                    "machine_name": self.config.repository.machine_name,
                    "auto_pull": self.config.repository.auto_pull,
                    "excluded_directories": self.config.repository.excluded_directories,
                },
                "targets": targets_list,
                "encryption": {
                    "enabled": self.config.encryption.enabled,
                    "key_file": self.config.encryption.key_file,
                },
                "blacklist": self.config.blacklist,
                "encrypt_list": self.config.encrypt_list,
                "max_file_size_mb": self.config.max_file_size_mb,
                "tui": {
                    "hide_system_files": self.config.tui.hide_system_files,
                    "system_file_patterns": self.config.tui.system_file_patterns,
                    "theme": self.config.tui.theme,
                },
            }
        }

        # hooksは設定がある場合のみ追加
        if hooks_dict:
            result["config"]["hooks"] = hooks_dict

        return result

    def get_config_as_dict(self) -> dict:
        """Get current config as dictionary (for JSON output)."""
        return self._config_to_dict()

    # --- Pattern List Management (Common Logic) ---

    def _validate_pattern(self, pattern: str) -> tuple[bool, Optional[str], list[str]]:
        """
        Validate a pattern for addition to blacklist/encrypt_list.

        Returns:
            Tuple of (is_valid, error_message, warnings)
        """
        warnings = []

        # Normalize
        pattern = pattern.strip() if pattern else ""

        # Validation: empty pattern
        if not pattern:
            return (False, "Pattern cannot be empty", [])

        # Warnings (non-blocking)
        if pattern == "*":
            warnings.append("Pattern '*' will match everything")
        if "//" in pattern:
            warnings.append(f"Pattern contains consecutive slashes: {pattern}")

        return (True, None, warnings)

    def _add_pattern_to_list(
        self,
        list_name: str,
        pattern: str,
        backup: bool = True,
    ) -> dict:
        """
        Add a pattern to a config list (blacklist or encrypt_list).

        Idempotent: returns success even if pattern already exists.

        Args:
            list_name: 'blacklist' or 'encrypt_list'
            pattern: Pattern to add
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path', 'warnings'
        """
        # Validate pattern
        is_valid, error_msg, warnings = self._validate_pattern(pattern)
        if not is_valid:
            return {"success": False, "message": error_msg}

        pattern = pattern.strip()

        # Get current list
        current_list = getattr(self.config, list_name, [])

        # Idempotent check
        if pattern in current_list:
            result = {
                "success": True,
                "message": f"Pattern already exists: {pattern}",
                "changed": False,
                "pattern": pattern,
            }
            if warnings:
                result["warnings"] = warnings
            return result

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, add pattern, and save
        raw_data = self._load_raw_config()

        # Ensure list exists
        if list_name not in raw_data.get("config", {}):
            raw_data.setdefault("config", {})[list_name] = []

        raw_data["config"][list_name].append(pattern)
        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Added pattern: {pattern}",
            "changed": True,
            "pattern": pattern,
        }
        if backup_path:
            result["backup_path"] = backup_path
        if warnings:
            result["warnings"] = warnings

        return result

    def _remove_pattern_from_list(
        self,
        list_name: str,
        pattern: str,
        backup: bool = True,
    ) -> dict:
        """
        Remove a pattern from a config list (blacklist or encrypt_list).

        Idempotent: returns success even if pattern doesn't exist.

        Args:
            list_name: 'blacklist' or 'encrypt_list'
            pattern: Pattern to remove
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        pattern = pattern.strip() if pattern else ""

        # Get current list
        current_list = getattr(self.config, list_name, [])

        # Idempotent check
        if pattern not in current_list:
            return {
                "success": True,
                "message": f"Pattern not found: {pattern}",
                "changed": False,
                "pattern": pattern,
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, remove pattern, and save
        raw_data = self._load_raw_config()

        if list_name in raw_data.get("config", {}):
            raw_data["config"][list_name] = [
                p for p in raw_data["config"][list_name] if p != pattern
            ]

        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Removed pattern: {pattern}",
            "changed": True,
            "pattern": pattern,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    # --- Exclude (Blacklist) Management ---

    def add_exclude_pattern(self, pattern: str, backup: bool = True) -> dict:
        """
        Add a pattern to the global blacklist (exclude list).

        Idempotent: returns success even if pattern already exists.

        Args:
            pattern: Glob pattern to exclude
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path', 'warnings'
        """
        return self._add_pattern_to_list("blacklist", pattern, backup)

    def remove_exclude_pattern(self, pattern: str, backup: bool = True) -> dict:
        """
        Remove a pattern from the global blacklist (exclude list).

        Idempotent: returns success even if pattern doesn't exist.

        Args:
            pattern: Glob pattern to remove
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        return self._remove_pattern_from_list("blacklist", pattern, backup)

    # --- Encrypt List Management ---

    def add_encrypt_pattern(self, pattern: str, backup: bool = True) -> dict:
        """
        Add a pattern to the global encryption list.

        Idempotent: returns success even if pattern already exists.

        Args:
            pattern: Glob pattern for files to encrypt
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path', 'warnings'
        """
        return self._add_pattern_to_list("encrypt_list", pattern, backup)

    def remove_encrypt_pattern(self, pattern: str, backup: bool = True) -> dict:
        """
        Remove a pattern from the global encryption list.

        Idempotent: returns success even if pattern doesn't exist.

        Args:
            pattern: Glob pattern to remove
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        return self._remove_pattern_from_list("encrypt_list", pattern, backup)

    # --- Hooks Management Methods ---

    def add_startup_hook(self, command: str, backup: bool = True) -> dict:
        """
        Add a startup hook command.

        Idempotent: returns success even if hook already exists.

        Args:
            command: Command to execute on startup
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        if not command or not command.strip():
            return {
                "success": False,
                "message": "Command cannot be empty",
            }

        command = command.strip()

        # Idempotent check
        if command in self.config.hooks.on_startup:
            return {
                "success": True,
                "message": f"Hook already exists: {command}",
                "changed": False,
                "command": command,
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, add hook, and save
        raw_data = self._load_raw_config()

        # Ensure hooks section exists
        if "hooks" not in raw_data.get("config", {}):
            raw_data.setdefault("config", {})["hooks"] = {}

        hooks_section = raw_data["config"]["hooks"]

        # Ensure on_startup is a list
        if "on_startup" not in hooks_section:
            hooks_section["on_startup"] = []
        elif isinstance(hooks_section["on_startup"], str):
            hooks_section["on_startup"] = [hooks_section["on_startup"]]

        hooks_section["on_startup"].append(command)
        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Added startup hook: {command}",
            "changed": True,
            "command": command,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def remove_startup_hook(self, command: str, backup: bool = True) -> dict:
        """
        Remove a startup hook command.

        Idempotent: returns success even if hook doesn't exist.

        Args:
            command: Command to remove
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        command = command.strip() if command else ""

        # Idempotent check
        if command not in self.config.hooks.on_startup:
            return {
                "success": True,
                "message": f"Hook not found: {command}",
                "changed": False,
                "command": command,
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, remove hook, and save
        raw_data = self._load_raw_config()
        hooks_section = raw_data.get("config", {}).get("hooks", {})

        if "on_startup" in hooks_section:
            on_startup = hooks_section["on_startup"]
            if isinstance(on_startup, str):
                if on_startup == command:
                    hooks_section["on_startup"] = []
            elif isinstance(on_startup, list):
                hooks_section["on_startup"] = [h for h in on_startup if h != command]

            # Clean up empty hooks section
            if not hooks_section.get("on_startup"):
                del hooks_section["on_startup"]
            if not hooks_section or (
                len(hooks_section) == 1
                and "timeout" in hooks_section
                and hooks_section["timeout"] == 30
            ):
                if "hooks" in raw_data.get("config", {}):
                    del raw_data["config"]["hooks"]

        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Removed startup hook: {command}",
            "changed": True,
            "command": command,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def set_hooks_timeout(self, timeout: int, backup: bool = True) -> dict:
        """
        Set hooks timeout value.

        Args:
            timeout: Timeout in seconds (must be positive)
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', and optionally 'backup_path'
        """
        if timeout <= 0:
            return {
                "success": False,
                "message": "Timeout must be a positive integer",
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Load raw config, set timeout, and save
        raw_data = self._load_raw_config()

        # Ensure hooks section exists
        if "hooks" not in raw_data.get("config", {}):
            raw_data.setdefault("config", {})["hooks"] = {}

        raw_data["config"]["hooks"]["timeout"] = timeout
        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Set hooks timeout to {timeout} seconds",
            "timeout": timeout,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    # --- Settings Management Methods ---

    def _parse_setting_value(self, key: str, value: str) -> tuple[bool, Any, str]:
        """
        Parse and validate a setting value based on its type definition.

        Args:
            key: Setting key name
            value: String value to parse

        Returns:
            Tuple of (is_valid, parsed_value, error_message)
        """
        if key not in SETTINGS_KEYS:
            return (False, None, f"Unknown setting key: {key}")

        key_def = SETTINGS_KEYS[key]
        key_type = key_def["type"]

        try:
            if key_type == "boolean":
                lower_val = value.lower()
                if lower_val in ("true", "on", "yes", "1"):
                    return (True, True, "")
                elif lower_val in ("false", "off", "no", "0"):
                    return (True, False, "")
                else:
                    return (
                        False,
                        None,
                        f"Invalid boolean value: {value} (use true/false, on/off, yes/no)",
                    )

            elif key_type == "number":
                parsed = float(value)
                return (True, parsed, "")

            elif key_type == "string":
                return (True, value, "")

            elif key_type == "enum":
                choices = key_def.get("choices", [])
                if value in choices:
                    return (True, value, "")
                elif value.lower() == "null" or value == "":
                    return (True, None, "")
                else:
                    return (
                        False,
                        None,
                        f"Invalid value: {value} (choices: {', '.join(choices)})",
                    )

            else:
                return (False, None, f"Unknown type: {key_type}")

        except ValueError as e:
            return (False, None, f"Invalid value: {e}")

    def _get_nested_value(self, data: dict, path: list) -> Any:
        """Get a value from nested dict using path list."""
        current = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current

    def _set_nested_value(self, data: dict, path: list, value: Any) -> None:
        """Set a value in nested dict using path list, creating intermediate dicts."""
        current = data
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def _delete_nested_value(self, data: dict, path: list) -> bool:
        """Delete a value from nested dict using path list. Returns True if deleted."""
        current = data
        for key in path[:-1]:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        if path[-1] in current:
            del current[path[-1]]
            return True
        return False

    def get_setting(self, key: str) -> dict:
        """
        Get a setting value.

        Args:
            key: Setting key (e.g., 'max_file_size_mb', 'repository.auto_pull')

        Returns:
            dict with 'success', 'key', 'value', 'default', 'type', 'description'
        """
        if key not in SETTINGS_KEYS:
            return {
                "success": False,
                "message": f"Unknown setting key: {key}",
                "available_keys": list(SETTINGS_KEYS.keys()),
            }

        key_def = SETTINGS_KEYS[key]
        raw_data = self._load_raw_config()
        current_value = self._get_nested_value(raw_data, key_def["path"])

        # If not set, use default
        if current_value is None:
            current_value = key_def["default"]

        return {
            "success": True,
            "key": key,
            "value": current_value,
            "default": key_def["default"],
            "type": key_def["type"],
            "description": key_def["description"],
            "choices": key_def.get("choices"),
            "required": key_def["required"],
        }

    def set_setting(self, key: str, value: str, backup: bool = True) -> dict:
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Value to set (as string, will be parsed based on type)
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        if key not in SETTINGS_KEYS:
            return {
                "success": False,
                "message": f"Unknown setting key: {key}",
                "available_keys": list(SETTINGS_KEYS.keys()),
            }

        key_def = SETTINGS_KEYS[key]

        # Parse and validate value
        is_valid, parsed_value, error_msg = self._parse_setting_value(key, value)
        if not is_valid:
            return {"success": False, "message": error_msg}

        # Check if value is already set to the same
        raw_data = self._load_raw_config()
        current_value = self._get_nested_value(raw_data, key_def["path"])
        if current_value == parsed_value:
            return {
                "success": True,
                "message": f"Setting already has value: {key} = {parsed_value}",
                "changed": False,
                "key": key,
                "value": parsed_value,
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Set the value
        self._set_nested_value(raw_data, key_def["path"], parsed_value)
        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Set {key} = {parsed_value}",
            "changed": True,
            "key": key,
            "value": parsed_value,
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def unset_setting(self, key: str, backup: bool = True) -> dict:
        """
        Unset a setting (reset to default by removing from config).

        Args:
            key: Setting key
            backup: Whether to backup config before modifying

        Returns:
            dict with 'success', 'message', 'changed', and optionally 'backup_path'
        """
        if key not in SETTINGS_KEYS:
            return {
                "success": False,
                "message": f"Unknown setting key: {key}",
                "available_keys": list(SETTINGS_KEYS.keys()),
            }

        key_def = SETTINGS_KEYS[key]

        # Check if required
        if key_def["required"]:
            return {
                "success": False,
                "message": f"Cannot unset required setting: {key}",
            }

        # Check if already unset
        raw_data = self._load_raw_config()
        current_value = self._get_nested_value(raw_data, key_def["path"])
        if current_value is None:
            return {
                "success": True,
                "message": f"Setting already unset: {key} (default: {key_def['default']})",
                "changed": False,
                "key": key,
                "default": key_def["default"],
            }

        # Backup config if requested
        backup_path = None
        if backup:
            backup_path = self.backup_config_file()

        # Delete the value
        self._delete_nested_value(raw_data, key_def["path"])
        self._save_raw_config(raw_data)

        # Invalidate cached config
        self._config = None

        result = {
            "success": True,
            "message": f"Unset {key} (reset to default: {key_def['default']})",
            "changed": True,
            "key": key,
            "default": key_def["default"],
        }
        if backup_path:
            result["backup_path"] = backup_path

        return result

    def list_settings(self) -> dict:
        """
        List all available settings with their current values.

        Returns:
            dict with 'success', 'settings' (list of setting info dicts)
        """
        raw_data = self._load_raw_config()
        settings_list = []

        for key, key_def in SETTINGS_KEYS.items():
            current_value = self._get_nested_value(raw_data, key_def["path"])
            is_default = current_value is None

            settings_list.append(
                {
                    "key": key,
                    "value": current_value if not is_default else key_def["default"],
                    "default": key_def["default"],
                    "is_default": is_default,
                    "type": key_def["type"],
                    "description": key_def["description"],
                    "required": key_def["required"],
                    "choices": key_def.get("choices"),
                }
            )

        return {
            "success": True,
            "settings": settings_list,
        }


def _get_template_path() -> Path:
    """テンプレートファイルのパスを取得"""
    # パッケージ内のテンプレートディレクトリ
    package_dir = Path(__file__).parent
    return package_dir / "templates" / "config-template.yml"


def create_default_config(output_path: str = "config-template.yml"):
    """
    デフォルトの設定ファイルを生成

    テンプレートファイル（templates/config-template.yml）をコピーして出力する。
    """
    template_path = _get_template_path()

    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    # テンプレートを読み込んでコピー
    template_content = template_path.read_text(encoding="utf-8")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template_content, encoding="utf-8")

    print(f"Config template created: {output_path}")
    print("Next steps:")
    print("   1. cp config-template.yml ${TRITON_DIR:-~/.config/triton}/config.yml")
    print("   2. export TRITON_REPO_PATH=~/your-dotfiles-repo")
    print("   3. triton config validate")
    print("   4. triton init key  # Generate encryption key")
    print("   5. triton backup")
    print()
    print("Tip: Use 'export TRITON_DIR=~/my-custom-triton' for custom locations")


if __name__ == "__main__":
    # テスト用（実際には使用されない）
    pass
