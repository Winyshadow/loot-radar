"""Start Loot Radar when you sign in to Windows.

Uses your own "Run" list in the registry (HKEY_CURRENT_USER, no admin needed), the same place
Discord, Steam etc. use. The entry starts launcher.py hidden in the tray, without opening the
dashboard. Windows' Settings > Apps > Startup (or Task Manager) can also switch it off; that's
read back here, so the tick box always shows what Windows will really do.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "Loot Radar"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    pythonw = HERE / ".venv" / "Scripts" / "pythonw.exe"
    return f'"{pythonw}" "{HERE / "launcher.py"}" --no-browser'


def _read(key_path: str):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            return winreg.QueryValueEx(k, NAME)[0]
    except OSError:
        return None


def _switched_off_in_windows() -> bool:
    """Windows keeps a separate on/off flag per entry; an odd first byte means 'Disabled'."""
    flag = _read(APPROVED_KEY)
    return isinstance(flag, (bytes, bytearray)) and len(flag) > 0 and flag[0] % 2 == 1


def enabled() -> bool:
    if not supported():
        return False
    return bool(_read(RUN_KEY)) and not _switched_off_in_windows()


def set_enabled(on: bool) -> None:
    """Add or remove the entry. Raises OSError if Windows refuses."""
    import winreg
    if on:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
        _clear_windows_flag()  # ticking the box here also undoes "Disabled" in Windows' Startup list
    else:
        for path in (RUN_KEY, APPROVED_KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, NAME)
            except FileNotFoundError:
                pass


def _clear_windows_flag() -> None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except FileNotFoundError:
        pass


def refresh_path() -> None:
    """If the Loot Radar folder was moved, point the existing entry at the new place."""
    if not supported():
        return
    try:
        current = _read(RUN_KEY)
        if current and current != command():
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
    except OSError:
        pass
