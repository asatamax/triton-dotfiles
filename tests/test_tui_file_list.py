"""Headless Pilot tests for FileList expand/shrink selection."""

from textual.app import App, ComposeResult

from triton_dotfiles.tui_textual.widgets.file_list import FileList


class FileListHostApp(App):
    """FileList検証用のホストアプリ"""

    def compose(self) -> ComposeResult:
        yield FileList()


def _fake_file(name: str, **overrides) -> dict:
    base = {
        "name": name,
        "encrypted": False,
        "local_exists": True,
        "changed": False,
        "local_only": False,
        "target": "~/.claude",
    }
    base.update(overrides)
    return base


SKILL_FILES = [
    ".claude/skills/aaa/SKILL.md",  # 0
    ".claude/skills/aaa/references/1.md",  # 1
    ".claude/skills/aaa/scripts/test.sh",  # 2
    ".claude/skills/bbb/SKILL.md",  # 3
    ".zshrc",  # 4
]


async def _load(pilot, app) -> FileList:
    file_list = app.query_one(FileList)
    file_list.load_files("TestMachine", [_fake_file(n) for n in SKILL_FILES])
    await pilot.pause()
    file_list.list_view.focus()
    await pilot.pause()
    return file_list


async def test_expand_selection_widens_step_by_step():
    app = FileListHostApp()
    async with app.run_test() as pilot:
        file_list = await _load(pilot, app)

        # カーソルを .claude/skills/aaa/references/1.md へ
        file_list.list_view.index = 1
        await pilot.pause()

        await pilot.press(">")  # references/
        assert file_list.selected_files == {1}

        await pilot.press(">")  # aaa/
        assert file_list.selected_files == {0, 1, 2}

        await pilot.press(">")  # skills/
        assert file_list.selected_files == {0, 1, 2, 3}

        await pilot.press(">")  # .claude/
        assert file_list.selected_files == {0, 1, 2, 3}

        # トップレベルで打ち止め（全ファイル選択には拡大しない）
        await pilot.press(">")
        assert file_list.selected_files == {0, 1, 2, 3}
        assert 4 not in file_list.selected_files  # .zshrcは巻き込まれない

        # 拡大中もカーソルは維持される
        assert file_list.list_view.index == 1


async def test_shrink_selection_steps_back_toward_cursor():
    app = FileListHostApp()
    async with app.run_test() as pilot:
        file_list = await _load(pilot, app)
        file_list.list_view.index = 1
        await pilot.pause()

        for _ in range(3):  # references/ → aaa/ → skills/
            await pilot.press(">")
        assert file_list.selected_files == {0, 1, 2, 3}

        await pilot.press("<")  # aaa/
        assert file_list.selected_files == {0, 1, 2}

        await pilot.press("<")  # references/
        assert file_list.selected_files == {1}

        await pilot.press("<")  # カーソル行のみ
        assert file_list.selected_files == {1}

        # それ以上は縮小できない（クラッシュしない）
        await pilot.press("<")
        assert file_list.selected_files == {1}


async def test_expand_accumulates_across_anchors():
    """別の場所へ移動して再拡大すると選択が累積する"""
    app = FileListHostApp()
    async with app.run_test() as pilot:
        file_list = await _load(pilot, app)

        # aaa全体を選択
        file_list.list_view.index = 1
        await pilot.pause()
        await pilot.press(">")
        await pilot.press(">")
        assert file_list.selected_files == {0, 1, 2}

        # カーソルをbbbへ移して拡大 → aaaの選択は保持される
        file_list.list_view.index = 3
        await pilot.pause()
        await pilot.press(">")  # bbb/
        assert file_list.selected_files == {0, 1, 2, 3}


async def test_expand_on_top_level_file_warns():
    """ディレクトリを持たないファイルでは拡大しない"""
    app = FileListHostApp()
    async with app.run_test() as pilot:
        file_list = await _load(pilot, app)
        file_list.list_view.index = 4  # .zshrc
        await pilot.pause()

        await pilot.press(">")
        assert file_list.selected_files == set()
