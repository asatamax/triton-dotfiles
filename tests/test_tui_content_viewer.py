"""Headless Pilot tests for ContentViewer (split scroll sync)."""

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Static

from triton_dotfiles.tui_textual.widgets.content_viewer import ContentViewer


class ViewerHostApp(App):
    """ContentViewer検証用のホストアプリ"""

    def compose(self) -> ComposeResult:
        yield ContentViewer()


async def test_split_scroll_sync_follows_both_directions():
    """片側のスクロールが反対側へ同期し、無限ループしない

    watch()コールバックはreactive変更時に発火するため、
    マウススクロール起因のクラッシュ（引数シグネチャ誤判定）の
    リグレッションガードを兼ねる。
    """
    app = ViewerHostApp()
    async with app.run_test(size=(100, 40)) as pilot:
        viewer = app.query_one(ContentViewer)
        viewer.set_view_mode("split")
        await pilot.pause()

        # スクロール可能になるよう左右に縦長コンテンツを入れる
        tall_content = "\n".join(f"line {i}" for i in range(200))
        app.query_one("#split-local-display", Static).update(tall_content)
        app.query_one("#split-backup-display", Static).update(tall_content)
        await pilot.pause()

        left = app.query_one("#split-local-container", ScrollableContainer)
        right = app.query_one("#split-backup-container", ScrollableContainer)

        left.scroll_y = 10
        await pilot.pause()
        assert right.scroll_y == 10

        right.scroll_y = 3
        await pilot.pause()
        assert left.scroll_y == 3


async def test_split_scroll_sync_survives_mouse_scroll_event():
    """マウスホイール相当のスクロール処理でもクラッシュしない"""
    app = ViewerHostApp()
    async with app.run_test(size=(100, 40)) as pilot:
        viewer = app.query_one(ContentViewer)
        viewer.set_view_mode("split")
        await pilot.pause()

        tall_content = "\n".join(f"line {i}" for i in range(200))
        app.query_one("#split-local-display", Static).update(tall_content)
        app.query_one("#split-backup-display", Static).update(tall_content)
        await pilot.pause()

        left = app.query_one("#split-local-container", ScrollableContainer)
        # マウスホイールと同じ内部経路（_scroll_to）を通す
        left.scroll_down(animate=False)
        await pilot.pause()

        assert left.scroll_y > 0
        right = app.query_one("#split-backup-container", ScrollableContainer)
        assert right.scroll_y == left.scroll_y
