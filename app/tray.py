"""Loot Radar's icon in the Windows system tray (the hidden-icons area next to the clock).

Double-click: open the dashboard. Right-click: miner dashboard, log, restart, quit.
"""

from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
_icon = None


def available() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def stop() -> None:
    """Remove the icon (call before the process exits so no ghost icon is left behind)."""
    global _icon
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass
        _icon = None


def run(url: str, on_quit, on_restart, miner_url: str, log_path: Path, first_time: bool) -> None:
    """Show the tray icon. Blocks until Quit/Restart (run it on the main thread)."""
    global _icon
    import pystray
    from PIL import Image

    image = Image.open(HERE / "web" / "icon.png")

    def open_dashboard(icon=None, item=None):
        webbrowser.open(url)

    def open_miner(icon=None, item=None):
        webbrowser.open(miner_url)

    def show_log(icon=None, item=None):
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(log_path))
        except OSError:
            pass

    def quit_app(icon, item):
        threading.Thread(target=on_quit, args=(False,), daemon=True).start()

    def quit_all(icon, item):
        threading.Thread(target=on_quit, args=(True,), daemon=True).start()

    def restart(icon, item):
        threading.Thread(target=on_restart, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Open Loot Radar", open_dashboard, default=True),
        pystray.MenuItem("Open miner dashboard", open_miner),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show log", show_log),
        pystray.MenuItem("Restart Loot Radar", restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Loot Radar", quit_app),
        pystray.MenuItem("Quit Loot Radar and the miner", quit_all),
    )
    _icon = pystray.Icon("LootRadar", image, "Loot Radar", menu)

    def setup(icon):
        icon.visible = True
        if first_time:
            try:
                icon.notify("Loot Radar runs down here now. Double-click the icon to open it, "
                            "right-click for more.", "Loot Radar")
            except Exception:
                pass

    _icon.run(setup=setup)
