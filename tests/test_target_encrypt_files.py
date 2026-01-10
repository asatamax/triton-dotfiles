#!/usr/bin/env python3
"""
Target encrypt_files Tests

target単位でencrypt_filesを指定する機能のテスト
"""

import pytest
from pathlib import Path

from triton_dotfiles.config import Target, Config, ConfigManager


class TestTargetEncryptFiles:
    """Target.encrypt_filesの基本機能テスト"""

    def test_target_with_encrypt_files(self):
        """Target.encrypt_filesが正しく読み込まれる"""
        target = Target(
            path="~/.m2",
            files=["settings.xml", "toolchains.xml"],
            encrypt_files=["settings.xml"],
        )

        assert target.path == "~/.m2"
        assert target.files == ["settings.xml", "toolchains.xml"]
        assert target.encrypt_files == ["settings.xml"]

    def test_target_without_encrypt_files(self):
        """encrypt_filesが指定されていない場合は空リスト"""
        target = Target(path="~/.ssh", files=["config"])

        assert target.encrypt_files == []

    def test_config_from_dict_with_encrypt_files(self):
        """YAMLからencrypt_filesを読み込む"""
        data = {
            "config": {
                "targets": [
                    {
                        "path": "~/.m2",
                        "files": ["settings.xml"],
                        "encrypt_files": ["settings.xml"],
                    }
                ],
                "repository": {"path": "~/repo"},
                "blacklist": [],
                "encrypt_list": [],
                "encryption": {"enabled": True},
            }
        }

        config = Config.from_dict(data)

        assert len(config.targets) == 1
        assert config.targets[0].encrypt_files == ["settings.xml"]


class TestShouldEncryptFile:
    """should_encrypt_file()メソッドのテスト"""

    def test_encrypt_by_target_encrypt_files(self, tmp_path):
        """target.encrypt_filesにマッチする場合、暗号化対象となる"""
        # 設定作成
        data = {
            "config": {
                "targets": [
                    {
                        "path": "~/.m2",
                        "files": ["settings.xml", "toolchains.xml"],
                        "encrypt_files": ["settings.xml"],
                    }
                ],
                "repository": {"path": str(tmp_path)},
                "blacklist": [],
                "encrypt_list": [],  # グローバルencrypt_listは空
                "encryption": {"enabled": True},
            }
        }

        config_manager = ConfigManager()
        config_manager._config = Config.from_dict(data)
        target = config_manager.config.targets[0]

        # settings.xmlは暗号化対象
        assert config_manager.should_encrypt_file(
            Path("/home/user/.m2/settings.xml"),
            target,
            Path("settings.xml"),
        )

        # toolchains.xmlは暗号化対象外
        assert not config_manager.should_encrypt_file(
            Path("/home/user/.m2/toolchains.xml"),
            target,
            Path("toolchains.xml"),
        )

    def test_encrypt_by_global_encrypt_list(self, tmp_path):
        """グローバルencrypt_listにマッチする場合、暗号化対象となる"""
        data = {
            "config": {
                "targets": [
                    {
                        "path": "~/.ssh",
                        "files": ["id_rsa", "config"],
                        # encrypt_filesは指定なし
                    }
                ],
                "repository": {"path": str(tmp_path)},
                "blacklist": [],
                "encrypt_list": ["**/*.key", "id_rsa*"],  # グローバルルール
                "encryption": {"enabled": True},
            }
        }

        config_manager = ConfigManager()
        config_manager._config = Config.from_dict(data)
        target = config_manager.config.targets[0]

        # id_rsaはグローバルencrypt_listにマッチ
        assert config_manager.should_encrypt_file(
            Path("/home/user/.ssh/id_rsa"),
            target,
            Path("id_rsa"),
        )

        # configは暗号化対象外
        assert not config_manager.should_encrypt_file(
            Path("/home/user/.ssh/config"),
            target,
            Path("config"),
        )

    def test_target_encrypt_files_priority(self, tmp_path):
        """target.encrypt_filesがグローバルencrypt_listより優先される"""
        data = {
            "config": {
                "targets": [
                    {
                        "path": "~/project",
                        "files": ["**/*.xml"],
                        "encrypt_files": ["secret.xml"],
                    }
                ],
                "repository": {"path": str(tmp_path)},
                "blacklist": [],
                "encrypt_list": ["**/*.key"],  # xmlは含まない
                "encryption": {"enabled": True},
            }
        }

        config_manager = ConfigManager()
        config_manager._config = Config.from_dict(data)
        target = config_manager.config.targets[0]

        # secret.xmlはtarget.encrypt_filesにマッチ
        assert config_manager.should_encrypt_file(
            Path("/home/user/project/secret.xml"),
            target,
            Path("secret.xml"),
        )

        # other.xmlは暗号化対象外
        assert not config_manager.should_encrypt_file(
            Path("/home/user/project/other.xml"),
            target,
            Path("other.xml"),
        )

    def test_encryption_disabled(self, tmp_path):
        """暗号化が無効の場合、常にFalse"""
        data = {
            "config": {
                "targets": [
                    {
                        "path": "~/.m2",
                        "files": ["settings.xml"],
                        "encrypt_files": ["settings.xml"],
                    }
                ],
                "repository": {"path": str(tmp_path)},
                "blacklist": [],
                "encrypt_list": ["**/*.key"],
                "encryption": {"enabled": False},  # 暗号化無効
            }
        }

        config_manager = ConfigManager()
        config_manager._config = Config.from_dict(data)
        target = config_manager.config.targets[0]

        # 暗号化無効なのでFalse
        assert not config_manager.should_encrypt_file(
            Path("/home/user/.m2/settings.xml"),
            target,
            Path("settings.xml"),
        )

    def test_pattern_matching_in_encrypt_files(self, tmp_path):
        """encrypt_filesでパターンマッチングが機能する"""
        data = {
            "config": {
                "targets": [
                    {
                        "path": "~/.aws",
                        "files": ["**/*"],
                        "encrypt_files": ["**/*credentials*", "**/*.pem"],
                    }
                ],
                "repository": {"path": str(tmp_path)},
                "blacklist": [],
                "encrypt_list": [],
                "encryption": {"enabled": True},
            }
        }

        config_manager = ConfigManager()
        config_manager._config = Config.from_dict(data)
        target = config_manager.config.targets[0]

        # credentialsを含むファイル
        assert config_manager.should_encrypt_file(
            Path("/home/user/.aws/credentials"),
            target,
            Path("credentials"),
        )

        # .pemファイル
        assert config_manager.should_encrypt_file(
            Path("/home/user/.aws/cert.pem"),
            target,
            Path("cert.pem"),
        )

        # マッチしないファイル
        assert not config_manager.should_encrypt_file(
            Path("/home/user/.aws/config"),
            target,
            Path("config"),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
