"""Headless Pilot tests for TUI dialogs and the status bar.

Textual's run_test() runs fully headless, so these tests do not conflict
with the "never run the TUI" rule (which protects real terminals).
"""

from rich.text import Text
from textual.app import App

from triton_dotfiles.tui_textual.widgets.dialogs import (
    ConfirmationDialog,
    InputDialog,
    MessageDialog,
    OperationReportDialog,
    ThreeChoiceDialog,
)
from triton_dotfiles.tui_textual.widgets.status_bar import StatusBar


class DialogHostApp(App):
    """ダイアログ検証用の空アプリ"""


def _sample_report(**overrides) -> OperationReportDialog:
    params = {
        "title": "Backup complete",
        "status": "success",
        "machine_label": "TestMachine → repo",
        "counts": [("Copied", 3, "green"), ("Unchanged", 59, "white")],
        "changes": [("+", ".config/new.toml", "green"), ("M", ".zshrc", "yellow")],
        "collapsed_sections": [("Unchanged files", [".aws/config", ".gitconfig"])],
        "actions": [("Commit & Push", "commit"), ("Dry Run", "dry")],
    }
    params.update(overrides)
    return OperationReportDialog(**params)


async def test_report_dialog_focuses_primary_action_and_esc_closes():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        results = []
        app.push_screen(_sample_report(), results.append)
        await pilot.pause()

        # 同期ファースト: Commit & Pushがデフォルトフォーカス
        assert app.focused.id == "action-commit"

        await pilot.press("escape")
        await pilot.pause()
        # Esc離脱は常に安全（何も実行しない）
        assert results == ["close"]


async def test_report_dialog_shortcut_keys():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        results = []
        app.push_screen(_sample_report(), results.append)
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert results == ["commit"]

        app.push_screen(_sample_report(), results.append)
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert results[-1] == "dry"


async def test_report_dialog_destructive_action_defaults_to_close():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        results = []
        report = _sample_report(
            title="Cleanup Dry Run",
            status="warning",
            actions=[("Run Cleanup", "run")],
            focus_action=False,
        )
        app.push_screen(report, results.append)
        await pilot.pause()

        # 削除系の継続アクションはCloseがデフォルト
        assert app.focused.id == "close-button"

        await pilot.press("r")
        await pilot.pause()
        assert results == ["run"]


async def test_confirmation_dialog_destructive_focuses_no():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        results = []
        dialog = ConfirmationDialog(
            "Restore",
            "Restore 3 files",
            "Local files will be overwritten.",
            file_list=[".zshrc", ".gitconfig", ".aws/config"],
            destructive=True,
        )
        app.push_screen(dialog, results.append)
        await pilot.pause()

        # ローカル破壊系はNoがデフォルト → Enterで安全側
        assert app.focused.id == "no-button"
        await pilot.press("enter")
        await pilot.pause()
        assert results == [False]


async def test_confirmation_dialog_default_focuses_yes_side():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        results = []
        app.push_screen(ConfirmationDialog("Backup", "Run backup?"), results.append)
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert results == [True]


async def test_three_choice_dialog_default_focus():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        results = []
        app.push_screen(
            ThreeChoiceDialog("Cleanup", "Delete orphans?", default="dry"),
            results.append,
        )
        await pilot.pause()
        assert app.focused.id == "dry-button"

        await pilot.press("escape")
        await pilot.pause()
        assert results == ["no"]


async def test_message_dialog_enter_closes():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        app.push_screen(MessageDialog("Info", "done", "success"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # ダイアログが閉じてアプリのデフォルト画面に戻る
        assert app.screen is app.screen_stack[0]


async def test_input_dialog_live_validation_and_submit():
    app = DialogHostApp()
    async with app.run_test() as pilot:
        seen: list[str] = []

        def validator(value: str) -> Text:
            seen.append(value)
            return Text(f"checked: {value}")

        results = []
        dialog = InputDialog(
            "Export", "Enter path:", "~/export", live_validator=validator
        )
        app.push_screen(dialog, results.append)
        await pilot.pause()

        # 初期値が検証される
        assert seen[0] == "~/export"

        # 入力変更のたびにライブ検証される
        # （Inputはフォーカス時に全選択されるため、タイプで全置換される）
        await pilot.press("x")
        await pilot.pause()
        assert seen[-1] == "x"

        await pilot.press("enter")
        await pilot.pause()
        assert results == ["x"]


def test_status_bar_drift_segments():
    status_bar = StatusBar()

    status_bar._git_status = {
        "success": True,
        "uncommitted": 3,
        "ahead": 1,
        "behind": 0,
    }
    plain = status_bar._build_drift_text().plain
    assert "● 3 uncommitted" in plain
    assert "↑1 unpushed" in plain

    status_bar._git_status = {
        "success": True,
        "uncommitted": 0,
        "ahead": 0,
        "behind": 2,
    }
    assert "↓2 behind" in status_bar._build_drift_text().plain

    # 完全同期時は何も表示しない
    status_bar._git_status = {
        "success": True,
        "uncommitted": 0,
        "ahead": 0,
        "behind": 0,
    }
    assert status_bar._build_drift_text().plain == ""

    # 取得失敗時も表示しない（インジケータは補助情報）
    status_bar._git_status = {"success": False}
    assert status_bar._build_drift_text().plain == ""
