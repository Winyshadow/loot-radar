"""Where Loot Radar's files live. There are two ways to have Loot Radar:

* The installed app (LootRadarSetup.exe, Loot Radar 2.0 and later). The program lives in
      C:\\Users\\<you>\\AppData\\Local\\Programs\\Loot Radar       (replaced by every update)
  and everything personal in
      C:\\Users\\<you>\\AppData\\Local\\Loot Radar\\data and \\miner   (kept by updates and uninstall)
* The zip with START.bat (the original way). Everything stays inside that folder, as before:
  app/data, miner/ and the code itself.

Every other module asks this one instead of working out paths from its own location.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Loot Radar"
FROZEN = bool(getattr(sys, "frozen", False))  # True in the installed app (built with PyInstaller)

# Where the installed app keeps your data (also used by the zip copy when it moves you over).
INSTALLED_HOME = Path(os.environ.get("LOOTRADAR_HOME")
                      or Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME)

if FROZEN:
    INSTALL_DIR = Path(sys.executable).resolve().parent         # the folder with LootRadar.exe
    CODE_DIR = Path(getattr(sys, "_MEIPASS", INSTALL_DIR))      # bundled files (web page, VERSION)
    HOME = INSTALLED_HOME
    DATA_DIR = HOME / "data"
    MINER_DIR = HOME / "miner"
    VERSION_FILE = CODE_DIR / "VERSION"
else:
    CODE_DIR = Path(__file__).resolve().parent                  # app/
    INSTALL_DIR = CODE_DIR.parent                               # the folder with START.bat
    HOME = INSTALL_DIR
    DATA_DIR = CODE_DIR / "data"
    MINER_DIR = INSTALL_DIR / "miner"
    VERSION_FILE = INSTALL_DIR / "VERSION"

WEB_DIR = CODE_DIR / "web"
LOG_PATH = DATA_DIR / "lootradar.log"
APP_MODE = "installed" if FROZEN else "zip"
