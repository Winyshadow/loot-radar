"""Loot Radar's own window (the installed app): the dashboard in a normal Windows window, using
Microsoft Edge WebView2, which is built into Windows 10 and 11. Same page as in a browser.

Closing the window only hides it: Loot Radar keeps running in the tray, and "Open Loot Radar"
(or starting it again) brings the window back. The page's own settings (open sections, the step
of the setup guide, ...) are kept in data/webview, like a browser would.
"""

from __future__ import annotations

import os
import threading

_win = None
_ready = threading.Event()
TITLE = "Loot Radar"
CHROME = "#0b2636"  # the menu bar's colour (--chrome in index.html); the title bar gets it too
TEXT = "#e8f3f7"


def _colorref(hex_color: str) -> int:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return r | g << 8 | b << 16


def _hwnds() -> list[int]:
    """Our own top-level windows titled "Loot Radar" (hidden ones too)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found, me = [], os.getpid()
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == me:
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(h, buf, 64)
            if buf.value == TITLE:
                found.append(h)
        return True

    user32.EnumWindows(proc(each), 0)
    return found


def _paint_title_bar() -> None:
    """Give the title bar and window border the menu bar's colour, so the window and the page
    look like one surface (Windows 11). Windows 10 only takes the dark title bar."""
    try:
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.windll.dwmapi
        for h in _hwnds():
            for attr, value in ((20, 1),                       # dark title bar buttons
                                (35, _colorref(CHROME)),       # title bar colour
                                (34, _colorref(CHROME)),       # border colour
                                (36, _colorref(TEXT))):        # title text colour
                v = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(wintypes.HWND(h), attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


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
    _paint_title_bar()


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

    def ready():
        _paint_title_bar()
        _ready.set()

    # ?app=window: the page drops its browser look (rounded card, gap) and fills the window
    url = url.rstrip("/") + "/?app=window"
    _win = webview.create_window(TITLE, url, width=1380, height=900, min_size=(420, 560),
                                 hidden=hidden, background_color="#071b27", text_select=True)
    _win.events.closing += closing
    _win.events.shown += ready
    _win.events.loaded += ready  # a hidden window loads its page too
    try:
        webview.start(gui="edgechromium", private_mode=False, storage_path=storage)
    except Exception:
        _win = None
        raise
