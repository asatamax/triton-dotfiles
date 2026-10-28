"""Tests for v1.3.2 encryption and pattern fixes (A1, A3, A4, A5, A6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.repo_env import (
    MACHINE,
    collected,
    make_file_manager,
    place,
    repo_has,
    write_file,
)
from triton_dotfiles.encryption import create_encryption_key
from triton_dotfiles.utils import matches_glob_pattern


class TestTargetEncryptFilesWithEncryptionDisabled:
    """A1: target encrypt_files fail closed when encryption is disabled."""

    def _fm(self, env):
        return make_file_manager(
            env,
            [
                {
                    "path": "~/.app",
                    "recursive": True,
                    "files": ["**/*"],
                    "encrypt_files": ["secret.env"],
                }
            ],
            encryption=False,
        )

    def test_matching_file_not_backed_up_in_plaintext(self, env):
        write_file(env["home"] / ".app" / "secret.env", b"token")
        write_file(env["home"] / ".app" / "other.txt", b"x")
        fm = self._fm(env)

        results = fm.backup_files(MACHINE)

        assert results["copied"] == ["other.txt"]
        assert not repo_has(env, ".app/secret.env")

    def test_existing_encrypted_copy_not_removed(self, env):
        write_file(env["home"] / ".app" / "secret.env", b"token")
        write_file(env["backup_dir"] / ".app" / "secret.env.enc", b"encrypted")
        fm = self._fm(env)

        results = fm.backup_files(MACHINE)

        assert repo_has(env, ".app/secret.env.enc")
        assert results["cleaned"] == []

    def test_cleanup_keeps_encrypted_copy(self, env):
        place(env, ".app/secret.env", repo_rel=".app/secret.env.enc")
        fm = self._fm(env)

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == []

    def test_validate_warns(self, env):
        fm = self._fm(env)

        results = fm.config_manager.validate_config()

        assert any(r.startswith("!") and "encrypt_files" in r for r in results)
        assert not any(
            "encrypt_files" in e for e in fm.config_manager.get_validation_errors()
        )


class TestCustomKeyFileProtected:
    """A3: a configured key_file outside TRITON_DIR is never backed up."""

    def test_custom_key_file_skipped(self, env):
        key = env["home"] / "keys" / "custom.key"
        create_encryption_key(key)
        write_file(env["home"] / "keys" / "notes.txt")
        fm = make_file_manager(
            env,
            [{"path": "~/keys", "recursive": True}],
            encryption=True,
            key_file=key,
        )

        results = fm.backup_files(MACHINE)

        assert results["copied"] == ["notes.txt"]
        assert not repo_has(env, "keys/custom.key")
        assert not repo_has(env, "keys/custom.key.enc")
        assert any("custom.key" in s for s in results["skipped"])


class TestGlobalPatternsWithSlash:
    """A4: global encrypt_list / blacklist patterns containing '/' match."""

    def test_encrypt_list_target_relative_pattern(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        write_file(env["home"] / ".aws" / "sso" / "cache" / "tok.json", b"secret")
        fm = make_file_manager(
            env,
            [{"path": "~/.aws", "recursive": True}],
            encrypt_list=["sso/cache/*"],
            encryption=True,
        )

        fm.backup_files(MACHINE)

        assert repo_has(env, ".aws/sso/cache/tok.json.enc")
        assert not repo_has(env, ".aws/sso/cache/tok.json")

    def test_blacklist_target_relative_globstar(self, env):
        write_file(env["home"] / "proj" / ".git" / "config")
        write_file(env["home"] / "proj" / "a.txt")
        fm = make_file_manager(
            env, [{"path": "~/proj", "recursive": True}], blacklist=[".git/**"]
        )

        assert collected(fm) == {"a.txt"}

    def test_blacklist_home_relative_pattern(self, env):
        fm = make_file_manager(
            env, [{"path": "~", "files": [".zshrc"]}], blacklist=[".config/app/*"]
        )
        cm = fm.config_manager

        assert cm.is_blacklisted(env["home"] / ".config" / "app" / "cache.db")
        assert not cm.is_blacklisted(env["home"] / ".config" / "other" / "x")

    def test_existing_basename_and_absolute_matches_kept(self, env):
        fm = make_file_manager(
            env,
            [{"path": "~", "files": [".zshrc"]}],
            blacklist=["*.log", "*/OpenVPN/*/config.conf"],
        )
        cm = fm.config_manager

        assert cm.is_blacklisted(env["home"] / "a" / "b.log")
        assert cm.is_blacklisted(
            env["home"] / "Library" / "OpenVPN" / "x" / "config.conf"
        )


class TestGlobstarRegexTranslation:
    """A5: '**' patterns escape regex metacharacters and follow fnmatch classes."""

    @pytest.mark.parametrize(
        ("pattern", "path", "expected"),
        [
            ("**/token(1).json", "a/token(1).json", True),
            ("**/token(1).json", "a/token1.json", False),
            ("**/my+keys/*", "x/my+keys/k", True),
            ("**/my+keys/*", "x/myykeys/k", False),
            ("**/[!a]*.key", "x/b.key", True),
            ("**/[!a]*.key", "x/a.key", False),
            ("**/[old]/*", "x/o/f", True),
            ("**/[old]/*", "x/[old]/f", False),
            ("**/[[]old]/*", "x/[old]/f", True),
            ("**/a?b", "x/a/b", False),
            ("**/a?b", "x/acb", True),
            ("**/*.md", "README.md", True),
            ("**/node_modules/**", "a/node_modules/b/c", True),
            ("a/**/b", "a/b", True),
            ("a/**/b", "a/x/y/b", True),
        ],
    )
    def test_translation(self, pattern, path, expected):
        assert matches_glob_pattern(Path(path), pattern) is expected

    def test_invalid_pattern_raises_and_is_reported(self, env):
        with pytest.raises(ValueError):
            matches_glob_pattern(Path("x/b"), "**/[z-a]")

        fm = make_file_manager(
            env,
            [{"path": "~", "files": [".zshrc"]}],
            encrypt_list=["**/[z-a]"],
        )
        errors = fm.config_manager.get_validation_errors()

        assert any("[z-a]" in e for e in errors), errors


class TestDirectPathOrderedEvaluation:
    """A6: a later '!' pattern excludes an earlier direct path."""

    def test_negated_direct_path_not_collected(self, env):
        write_file(env["home"] / "proj" / "app" / ".env")
        write_file(env["home"] / "proj" / "app" / "keep.env")
        fm = make_file_manager(
            env,
            [{"path": "~/proj", "files": ["app/.env", "app/keep.env", "!app/.env"]}],
        )

        assert collected(fm) == {"app/keep.env"}

    def test_cleanup_agrees(self, env):
        place(env, "proj/app/.env")
        place(env, "proj/app/keep.env")
        fm = make_file_manager(
            env,
            [{"path": "~/proj", "files": ["app/.env", "app/keep.env", "!app/.env"]}],
        )

        assert fm.cleanup_repository_files(MACHINE, dry_run=True)["would_delete"] == [
            "proj/app/.env"
        ]

    def test_reinclusion_after_negation(self, env):
        write_file(env["home"] / "proj" / "app" / ".env")
        fm = make_file_manager(
            env,
            [{"path": "~/proj", "files": ["!app/*", "app/.env"]}],
        )

        assert collected(fm) == {"app/.env"}


class TestEncryptionNeverNarrows:
    """AA1: encryption decisions keep every match of the previous '**' translation."""

    def test_legacy_match_stays_encrypted(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        write_file(env["home"] / ".app" / "token1.json", b"secret")
        write_file(env["backup_dir"] / ".app" / "token1.json.enc", b"old")
        fm = make_file_manager(
            env,
            [{"path": "~/.app", "recursive": True}],
            encrypt_list=["**/token(1).json"],
            encryption=True,
        )

        fm.backup_files(MACHINE)

        assert repo_has(env, ".app/token1.json.enc")
        assert not repo_has(env, ".app/token1.json")

    def test_target_encrypt_files_legacy_match(self, env):
        fm = make_file_manager(
            env,
            [
                {
                    "path": "~/.app",
                    "recursive": True,
                    "encrypt_files": ["**/my+keys/*"],
                }
            ],
            encryption=True,
        )
        cm = fm.config_manager
        target = cm.config.targets[0]
        local = env["home"] / ".app" / "x" / "myykeys" / "k"

        assert cm.should_encrypt_file(local, target, Path("x/myykeys/k"))

    def test_blacklist_uses_new_semantics_only(self, env):
        fm = make_file_manager(
            env,
            [{"path": "~", "files": [".zshrc"]}],
            blacklist=["**/token(1).json"],
        )

        assert not fm.config_manager.is_blacklisted(env["home"] / "a" / "token1.json")


class TestCharacterClasses:
    """AA2: classes keep fnmatch contents and never match '/'."""

    @pytest.mark.parametrize(
        ("pattern", "path", "expected"),
        [
            ("**/[!-a]*.key", "x/Z.key", True),
            ("**/[!-a]*.key", "x/-.key", False),
            ("**/[!-a]*.key", "x/a.key", False),
            ("**/[!a-]*.key", "x/Z.key", True),
            ("**/[!a-]*.key", "x/-.key", False),
            ("**/[]a]x", "d/]x", True),
            ("**/[]a]x", "d/ax", True),
            ("**/[]a]x", "d/bx", False),
            ("**/[!]a]x", "d/bx", True),
            ("**/[!]a]x", "d/]x", False),
            ("**/a[+-0]b", "d/a.b", True),
            ("**/a[+-0]b", "d/a/b", False),
            ("**/a[!x]b", "d/a/b", False),
        ],
    )
    def test_class_semantics(self, pattern, path, expected):
        assert matches_glob_pattern(Path(path), pattern) is expected


class TestDirectEntriesNormalized:
    """AA4/AA5: direct entries (with or without '!') match the normalized path."""

    def test_negated_parent_reference_excluded_in_both_phases(self, env):
        write_file(env["home"] / "proj" / "sub" / "x.txt")
        write_file(env["home"] / "proj" / "keep.txt")
        write_file(env["home"] / "proj" / "other.txt")
        files = ["**/*", "sub/../keep.txt", "!sub/../keep.txt"]
        fm = make_file_manager(
            env, [{"path": "~/proj", "recursive": True, "files": files}]
        )

        assert "keep.txt" not in collected(fm)
        assert "sub/../keep.txt" not in collected(fm)
        write_file(env["backup_dir"] / "proj" / "keep.txt")
        result = fm.cleanup_repository_files(MACHINE, dry_run=True)
        assert result["would_delete"] == ["proj/keep.txt"]

    def test_dot_slash_negation_excluded(self, env):
        write_file(env["home"] / "proj" / "app" / "conf")
        fm = make_file_manager(
            env, [{"path": "~/proj", "files": ["./app/conf", "!./app/conf"]}]
        )

        assert collected(fm) == set()
        write_file(env["backup_dir"] / "proj" / "app" / "conf")
        result = fm.cleanup_repository_files(MACHINE, dry_run=True)
        assert result["would_delete"] == ["proj/app/conf"]


OVERLAPPING_TARGETS = [
    {"path": "~/.app", "files": ["secret"], "encrypt_files": ["secret"]},
    {"path": "~", "files": [".app/secret"]},
]


class TestEncryptionAcrossOverlappingTargets:
    """Z1: every target containing a file contributes its encrypt_files."""

    def test_enabled_overlapping_target_does_not_write_plaintext(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        write_file(env["home"] / ".app" / "secret", b"token")
        fm = make_file_manager(env, OVERLAPPING_TARGETS, encryption=True)

        fm.backup_files(MACHINE)

        assert repo_has(env, ".app/secret.enc")
        assert not repo_has(env, ".app/secret")

    def test_disabled_overlapping_target_excludes(self, env):
        write_file(env["home"] / ".app" / "secret", b"token")
        fm = make_file_manager(env, OVERLAPPING_TARGETS, encryption=False)

        fm.backup_files(MACHINE)

        assert not repo_has(env, ".app/secret")

    def test_cleanup_stale_plaintext_resolved(self, env):
        place(env, ".app/secret")
        place(env, None, repo_rel=".app/secret.enc")
        fm = make_file_manager(env, OVERLAPPING_TARGETS, encryption=True)

        result = fm.cleanup_repository_files(MACHINE, dry_run=True)

        assert result["would_delete"] == [".app/secret"]


DIRECT_WITH_PARENT = [{"path": "~/proj", "files": ["sub/../secrets/token"]}]


class TestNormalizedRelativePathMatching:
    """Z2: patterns also match the normalized target-relative path."""

    def _local(self, env):
        (env["home"] / "proj" / "sub").mkdir(parents=True)
        write_file(env["home"] / "proj" / "secrets" / "token", b"token")

    def test_enabled_direct_path_with_parent_encrypted(self, env):
        create_encryption_key(env["tmp"] / "master.key")
        self._local(env)
        fm = make_file_manager(
            env, DIRECT_WITH_PARENT, encrypt_list=["secrets/**"], encryption=True
        )

        fm.backup_files(MACHINE)

        assert repo_has(env, "proj/secrets/token.enc")
        assert not repo_has(env, "proj/secrets/token")

    def test_disabled_direct_path_with_parent_excluded(self, env):
        self._local(env)
        fm = make_file_manager(
            env, DIRECT_WITH_PARENT, encrypt_list=["secrets/**"], encryption=False
        )

        fm.backup_files(MACHINE)

        assert not repo_has(env, "proj/secrets/token")

    def test_blacklist_direct_path_with_parent(self, env):
        self._local(env)
        fm = make_file_manager(env, DIRECT_WITH_PARENT, blacklist=["secrets/**"])

        assert collected(fm) == set()
