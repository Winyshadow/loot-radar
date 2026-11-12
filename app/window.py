"""Loot Radar's own window (the installed app): the dashboard in a normal Windows window, using
Microsoft Edge WebView2, which is built into Windows 10 and 11. Same page as in a browser.

Closing the window only hides it: Loot Radar keeps running in the tray, and "Open Loot Radar"
(or starting it again) brings the window back. The page's own settings (open sections, the step
of the setup guide, ...) are kept in data/webview, like a browser would.
"""

from __future__ import annotations

import threading

_win = None
_ready = threading.Event()


def available() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


def active() -> bool:
    return _win is not None


def show() -> None:
    """Bring the window to the front (safe from any thread)."""
    if _win is None:
        return
    _ready.wait(10)
    try:
        _win.show()
        _win.restore()
    except Exception:
        pass


def run(url: str, hidden: bool, storage: str, on_first_close=None) -> None:
    """Open the window and run it until Loot Radar exits. Must be called on the main thread.
    Raises if the window can't be made (e.g. WebView2 missing), so the caller can fall back to
    the browser."""
    global _win
    import webview
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # target=_blank links: your browser
    told = {"done": False}

    def closing():
        try:
            _win.hide()
        except Exception:
            pass
        if on_first_close and not told["done"]:
            told["done"] = True
            on_first_close()
        return False  # keep running in the tray

    _win = webview.create_window("Loot Radar", url, width=1380, height=900, min_size=(420, 560),
                                 hidden=hidden, background_color="#071b27", text_select=True)
    _win.events.closing += closing
    _win.events.shown += lambda: _ready.set()
    _win.events.loaded += lambda: _ready.set()  # a hidden window loads its page too
    try:
        webview.start(gui="edgechromium", private_mode=False, storage_path=storage)
    except Exception:
        _win = None
        raise
