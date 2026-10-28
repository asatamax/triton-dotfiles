"""Exit codes of action commands: failures exit 1, success paths exit 0."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from click.testing import CliRunner

from triton_dotfiles import cli as cli_module
from triton_dotfiles.config import HooksConfig

MACHINE = "M"


class FakeConfigManager:
    hooks = HooksConfig()

    def __init__(self, config_path=None):
        self.config = SimpleNamespace(hooks=FakeConfigManager.hooks)

    def get_machine_name(self) -> str:
        return MACHINE


class FakeFileManager:
    """CLIが委譲する結果だけを返すFileManager"""

    results: ClassVar[dict] = {}
    machines: ClassVar[list[dict]] = [{"name": MACHINE, "file_count": 1}]

    def __init__(self, config_manager):
        self.repo_root = Path("/nonexistent-repo")

    def get_available_machines(self):
        return self.machines

    def backup_files(self, machine_name, dry_run=False, verbose=False):
        return self.results

    def restore_files(self, source_machine, target=None, dry_run=False):
        return self.results

    def restore_specific_files(self, source_machine, files, target=None, dry_run=False):
        return self.results

    def cleanup_repository_files(self, machine_name, dry_run=False):
        return self.results

    def export_file(self, *args, **kwargs):
        return {
            "source": "s",
            "destination": "d",
            "encrypted": False,
            "decrypted": False,
        }

    def git_pull_repository(self, dry_run=False):
        return self.results

    def git_commit_push_repository(self, machine_name=None, dry_run=False):
        return self.results


@pytest.fixture
def run(tmp_path, monkeypatch):
    triton_dir = tmp_path / "triton"
    triton_dir.mkdir()
    (triton_dir / "config.yml").write_text("config: {}\n")
    monkeypatch.setenv("TRITON_DIR", str(triton_dir))
    monkeypatch.setattr(cli_module, "ConfigManager", FakeConfigManager)
    monkeypatch.setattr(cli_module, "FileManager", FakeFileManager)
    monkeypatch.setattr(
        cli_module.ValidationDisplay,
        "display_validation_results",
        staticmethod(lambda *a, **k: True),
    )
    monkeypatch.setattr(FakeConfigManager, "hooks", HooksConfig())

    def _run(args: list[str], results: dict | None = None, input: str | None = None):
        monkeypatch.setattr(FakeFileManager, "results", results or {})
        return CliRunner().invoke(cli_module.cli, args, input=input)

    return _run


def _backup_results(errors: list[str]) -> dict:
    return {"copied": [], "unchanged": [], "skipped": [], "errors": errors}


def _restore_results(errors: list[str]) -> dict:
    return {"restored": [], "unchanged": [], "backed_up": [], "errors": errors}


def _cleanup_results(errors: list[str]) -> dict:
    return {"deleted": [], "would_delete": [], "errors": errors}


# --- backup ---


def test_backup_with_errors_exits_1(run) -> None:
    result = run(["backup"], _backup_results(["Failed to copy x"]))
    assert result.exit_code == 1, result.output
    assert "Failed to copy x" in result.output


def test_backup_without_errors_exits_0(run) -> None:
    result = run(["backup"], _backup_results([]))
    assert result.exit_code == 0, result.output


# --- restore / export ---


def test_restore_unknown_machine_exits_1(run) -> None:
    result = run(["restore", "Nope", "--dry-run"])
    assert result.exit_code == 1, result.output
    assert "Machine 'Nope' not found" in result.output


def test_restore_with_errors_exits_1(run) -> None:
    result = run(["restore", MACHINE, "--dry-run"], _restore_results(["boom"]))
    assert result.exit_code == 1, result.output


def test_selective_restore_with_errors_exits_1(run) -> None:
    result = run(
        ["restore", MACHINE, "-f", ".zshrc", "--dry-run"], _restore_results(["boom"])
    )
    assert result.exit_code == 1, result.output


def test_restore_without_errors_exits_0(run) -> None:
    result = run(["restore", MACHINE, "--dry-run"], _restore_results([]))
    assert result.exit_code == 0, result.output


def test_restore_declined_exits_0(run) -> None:
    result = run(["restore", MACHINE], _restore_results([]), input="n\n")
    assert result.exit_code == 0, result.output


def test_export_unknown_machine_exits_1(run, tmp_path) -> None:
    result = run(["export", "Nope", ".zshrc", str(tmp_path / "out")])
    assert result.exit_code == 1, result.output


def test_export_success_exits_0(run, tmp_path) -> None:
    result = run(["export", MACHINE, ".zshrc", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output


# --- cleanup-repository ---


def test_cleanup_with_errors_exits_1(run) -> None:
    result = run(["cleanup-repository"], _cleanup_results(["denied"]), input="y\n")
    assert result.exit_code == 1, result.output


def test_cleanup_without_errors_exits_0(run) -> None:
    result = run(["cleanup-repository"], _cleanup_results([]), input="y\n")
    assert result.exit_code == 0, result.output


def test_cleanup_dry_run_without_errors_exits_0(run) -> None:
    result = run(["cleanup-repository", "--dry-run"], _cleanup_results([]))
    assert result.exit_code == 0, result.output


# --- git-pull / git-commit-push ---


def _git_result(success: bool, **extra) -> dict:
    return {
        "success": success,
        "message": "ok" if success else "failed",
        "output": "",
        "error": "" if success else "stderr",
        **extra,
    }


def test_git_pull_failure_exits_1(run) -> None:
    result = run(["git-pull"], _git_result(False))
    assert result.exit_code == 1, result.output


def test_git_pull_success_exits_0(run) -> None:
    result = run(["git-pull"], _git_result(True))
    assert result.exit_code == 0, result.output


def test_git_commit_push_failure_exits_1(run) -> None:
    result = run(["git-commit-push", "--yes"], _git_result(False))
    assert result.exit_code == 1, result.output


def test_git_commit_push_pull_required_exits_1_with_correct_hint(run) -> None:
    result = run(
        ["git-commit-push", "--yes"],
        _git_result(False, error="PULL_REQUIRED", need_pull=True, commits_behind=2),
    )
    assert result.exit_code == 1, result.output
    assert "triton git-pull" in result.output
    assert "'triton pull'" not in result.output


def test_git_commit_push_success_exits_0(run) -> None:
    result = run(["git-commit-push", "--yes"], _git_result(True))
    assert result.exit_code == 0, result.output


def test_git_commit_push_warns_about_other_staged_paths(run) -> None:
    result = run(
        ["git-commit-push", "--yes"],
        _git_result(True, other_staged=["Other/o.txt"]),
    )
    assert result.exit_code == 0, result.output
    assert "Warning:" in result.output
    assert "Other/o.txt" in result.output


# --- hooks run (real HookManager) ---


def _set_hooks(monkeypatch, commands: list[str], timeout: int = 30) -> None:
    monkeypatch.setattr(
        FakeConfigManager, "hooks", HooksConfig(on_startup=commands, timeout=timeout)
    )


def test_hooks_run_failure_exits_1(run, monkeypatch) -> None:
    _set_hooks(monkeypatch, ["true", "false"])
    result = run(["hooks", "run"])
    assert result.exit_code == 1, result.output


def test_hooks_run_timeout_exits_1(run, monkeypatch) -> None:
    _set_hooks(monkeypatch, ["sleep 5"], timeout=1)
    result = run(["hooks", "run"])
    assert result.exit_code == 1, result.output


def test_hooks_run_success_exits_0(run, monkeypatch) -> None:
    _set_hooks(monkeypatch, ["true"])
    result = run(["hooks", "run"])
    assert result.exit_code == 0, result.output


def test_hooks_run_dry_run_exits_0(run, monkeypatch) -> None:
    _set_hooks(monkeypatch, ["false"])
    result = run(["hooks", "run", "--dry-run"])
    assert result.exit_code == 0, result.output


# --- cleanup-repository next-step hint ---


def test_cleanup_hint_recommends_git_commit_push(run) -> None:
    results = {"deleted": [".old"], "would_delete": [], "errors": []}
    result = run(["cleanup-repository"], results, input="y\n")
    assert result.exit_code == 0, result.output
    assert "triton git-commit-push" in result.output
    assert "git add ." not in result.output


# --- archive list / show / clean ---


def _archives(tmp_path: Path) -> Path:
    return tmp_path / "triton" / "archives"


def _make_archive(root: Path, name: str, files: dict[str, bytes] | None = None) -> None:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    for rel, data in (files or {"f.txt": b"x"}).items():
        path = run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _listed(run, *args: str) -> list[str]:
    result = run(["archive", "list", "--json", *args])
    assert result.exit_code == 0, result.output
    return [a["timestamp"] for a in json.loads(result.output)]


def test_archive_list_includes_suffixed_runs_sorted_numerically(run, tmp_path) -> None:
    root = _archives(tmp_path)
    for name in [
        "20250101_000000",
        "20250101_000000_1",
        "20250101_000000_2",
        "20250101_000000_10",
        "20250102_000000",
    ]:
        _make_archive(root, name)

    assert _listed(run) == [
        "20250102_000000",
        "20250101_000000_10",
        "20250101_000000_2",
        "20250101_000000_1",
        "20250101_000000",
    ]


def test_archive_list_ignores_non_contract_dirs(run, tmp_path) -> None:
    root = _archives(tmp_path)
    _make_archive(root, "20250101_000000")
    for name in ["notes", "20250101_000000_0", "20250101_000000_01", "2025_1"]:
        _make_archive(root, name)
    _make_archive(root / "config", "20250103_000000_1")
    _make_archive(root / "config", "junk")

    assert _listed(run) == ["20250103_000000_1", "20250101_000000"]


def test_archive_clean_keep_considers_suffixed_runs(run, tmp_path) -> None:
    root = _archives(tmp_path)
    for name in ["20250101_000000", "20250101_000000_1", "20250101_000000_2"]:
        _make_archive(root, name)

    result = run(["archive", "clean", "--keep", "1", "--force"])

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in root.iterdir()) == ["20250101_000000_2"]


def test_archive_show_suffixed_run_with_outside_home_files(run, tmp_path) -> None:
    root = _archives(tmp_path)
    _make_archive(
        root,
        "20250101_000000_1",
        {".zshrc": b"z", "_root/opt/a_b/c": b"1", "_root/opt/a/b_c": b"2"},
    )

    text = run(["archive", "show", "20250101_000000_1"])
    assert text.exit_code == 0, text.output
    assert "  .zshrc (" in text.output
    assert "  /opt/a_b/c (" in text.output
    assert "  /opt/a/b_c (" in text.output
    assert "_root" not in text.output.split("Files (")[1]

    as_json = run(["archive", "show", "20250101_000000_1", "--json"])
    files = {f["path"]: f["stored_path"] for f in json.loads(as_json.output)["files"]}
    assert files == {
        ".zshrc": ".zshrc",
        "/opt/a/b_c": "_root/opt/a/b_c",
        "/opt/a_b/c": "_root/opt/a_b/c",
    }


@pytest.mark.parametrize(
    "name",
    ["../../outside", "..", "config", "20250101_000000_0", "20250101_000000_01", "x"],
)
def test_archive_show_rejects_non_contract_names(run, tmp_path, name) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    _make_archive(_archives(tmp_path), "20250101_000000_0")
    _make_archive(_archives(tmp_path), "20250101_000000_01")

    result = run(["archive", "show", name])

    assert result.exit_code == 1, result.output
    assert "Invalid archive name" in result.output
    assert "secret.txt" not in result.output


@pytest.mark.parametrize("option", ["--keep", "--older-than"])
def test_archive_clean_rejects_negative_values(run, tmp_path, option) -> None:
    root = _archives(tmp_path)
    for name in ["20250101_000000", "20250102_000000"]:
        _make_archive(root, name)

    result = run(["archive", "clean", option, "-1", "--force"])

    assert result.exit_code != 0, result.output
    assert sorted(p.name for p in root.iterdir()) == [
        "20250101_000000",
        "20250102_000000",
    ]
