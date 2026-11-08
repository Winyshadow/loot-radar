"""Scan this PC for games installed through other launchers (read-only, no logins).

Sources:
  Epic        - the launcher's install files in ProgramData\\Epic\\EpicGamesLauncher\\Data\\Manifests
  EA app, Battle.net, Rockstar, Riot, Ubisoft, GOG
              - Windows' installed-programs list (the same one "Apps > Installed apps" shows)
  Ubisoft     - also Ubisoft Connect's own install records in the registry
  Xbox        - games in XboxGames folders (Xbox app / Game Pass)
  GOG Galaxy  - its library database, which also lists games from stores you linked to it,
                including ones you own but haven't installed, and play time
Steam games are skipped here; Loot Radar already gets those from Steam.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import string
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCES = {
    "epic": "Epic", "ea": "EA app", "battlenet": "Battle.net", "ubisoft": "Ubisoft",
    "xbox": "Xbox", "rockstar": "Rockstar", "riot": "Riot", "gog": "GOG", "amazon": "Amazon",
}

# Things in the installed-programs list that belong to a launcher but aren't games.
JUNK = re.compile(
    r"launcher|anti-?cheat|vanguard|redist|runtime|directx|vc_?redist|visual c\+\+|social club|"
    r"prerequisite|installer|updater|\bupdate\b|helper|overlay|background service|\bservices?$|sdk|benchmark|"
    r"^battle\.net$|^ea app$|^origin$|^ubisoft connect$|^riot client$|^gog galaxy|^xbox$|"
    r"punkbuster|easyanticheat|battleye|\bdemo\b|dedicated server|soundtrack|artbook",
    re.I,
)


def program_data() -> Path:
    return Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData")


def clean(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[™®©]", "", name or "")).strip()


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", clean(name).lower().replace("&", " and ")).strip("-")
    return s or "game"


# ------------------------------------------------------------------ Epic
def epic() -> list[dict]:
    folder = program_data() / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    out = []
    for f in sorted(folder.glob("*.item")) if folder.exists() else []:
        try:
            m = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        name = clean(m.get("DisplayName", ""))
        cats = [str(c).lower() for c in m.get("AppCategories") or []]
        if not name or m.get("bIsIncompleteInstall"):
            continue
        if cats and "games" not in cats:
            continue  # Unreal Engine, plugins, etc.
        main = m.get("MainGameAppName")
        if main and main != m.get("AppName"):
            continue  # DLC
        out.append({"name": name, "source": "epic", "id": m.get("AppName") or name})
    return out


# ------------------------------------------------------------------ Windows installed programs
def installed_programs() -> list[dict]:
    try:
        import winreg
    except ImportError:
        return []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    out = []
    for hive, path in roots:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, sub) as k:
                    entry = {"key": sub}
                    for field in ("DisplayName", "Publisher", "UninstallString", "InstallLocation", "SystemComponent"):
                        try:
                            entry[field] = winreg.QueryValueEx(k, field)[0]
                        except OSError:
                            entry[field] = ""
                    out.append(entry)
            except OSError:
                continue
    return out


def classify(entry: dict) -> str | None:
    """Which launcher installed this program (None = not a launcher game)."""
    name = clean(str(entry.get("DisplayName") or ""))
    pub = str(entry.get("Publisher") or "").lower()
    un = str(entry.get("UninstallString") or "").lower()
    key = str(entry.get("key") or "").lower()
    if not name or str(entry.get("SystemComponent")) == "1" or JUNK.search(name):
        return None
    if "steam://" in un or key.startswith("steam app"):
        return None
    if "uplay://" in un or "ubisoft game launcher" in un or key.startswith("uplay install"):
        return "ubisoft"
    if "battle.net" in un or pub.startswith("blizzard"):
        return "battlenet"
    if "riotclientservices" in un or pub.startswith("riot games"):
        return "riot"
    if "ea desktop" in un or "eainstaller" in un or "\\origin" in un or pub.startswith("electronic arts"):
        return "ea"
    if pub.startswith("rockstar games"):
        return "rockstar"
    if pub.startswith("gog") or "gog.com" in un or "gog galaxy" in un:
        return "gog"
    if "amazon games" in un or pub.startswith("amazon game"):
        return "amazon"
    return None


def from_installed_programs() -> list[dict]:
    out = []
    for e in installed_programs():
        src = classify(e)
        if src:
            out.append({"name": clean(e["DisplayName"]), "source": src, "id": e.get("key")})
    return out


# ------------------------------------------------------------------ Ubisoft Connect's own records
def ubisoft() -> list[dict]:
    try:
        import winreg
    except ImportError:
        return []
    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs")
    except OSError:
        return []
    i = 0
    while True:
        try:
            gid = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        try:
            with winreg.OpenKey(root, gid) as k:
                folder = str(winreg.QueryValueEx(k, "InstallDir")[0]).rstrip("/\\")
        except OSError:
            continue
        if folder and Path(folder).exists():
            out.append({"name": clean(Path(folder).name), "source": "ubisoft", "id": gid})
    return out


# ------------------------------------------------------------------ Xbox / Game Pass
def _gaming_root(drive: Path) -> Path | None:
    """The Xbox app writes a small '.GamingRoot' file at the top of each drive it installs to."""
    f = drive / ".GamingRoot"
    try:
        data = f.read_bytes()
    except OSError:
        return None
    try:
        rel = data[8:].decode("utf-16-le").split("\x00")[0].strip()
    except UnicodeDecodeError:
        return None
    return drive / rel if rel else None


def xbox() -> list[dict]:
    if os.name != "nt" and not os.environ.get("LOOTRADAR_XBOX_ROOTS"):
        return []
    roots = []
    if os.environ.get("LOOTRADAR_XBOX_ROOTS"):  # tests
        roots = [Path(p) for p in os.environ["LOOTRADAR_XBOX_ROOTS"].split(os.pathsep)]
    else:
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if not drive.exists():
                continue
            gr = _gaming_root(drive)
            for cand in (gr, drive / "XboxGames"):
                if cand and cand.exists() and cand not in roots:
                    roots.append(cand)
    out = []
    for root in roots:
        try:
            dirs = [d for d in root.iterdir() if d.is_dir()]
        except OSError:
            continue
        for d in dirs:
            cfgs = [d / "Content" / "MicrosoftGame.config", d / "MicrosoftGame.config"]
            name = None
            for cfg in cfgs:
                if cfg.exists():
                    try:
                        tree = ET.parse(cfg)
                        sv = next((el for el in tree.iter() if el.tag.endswith("ShellVisuals")), None)
                        name = sv.get("DefaultDisplayName") if sv is not None else None
                    except (ET.ParseError, OSError):
                        name = None
                    break
            if name or any(c.exists() for c in cfgs):
                out.append({"name": clean(name or d.name), "source": "xbox", "id": d.name})
    return out


# ------------------------------------------------------------------ GOG Galaxy (owned + play time)
GALAXY_PREFIX = {"gog": "gog", "epic": "epic", "origin": "ea", "uplay": "ubisoft", "battlenet": "battlenet",
                 "xboxone": "xbox", "xbox": "xbox", "rockstar": "rockstar", "riot": "riot", "amazon": "amazon"}


def gog_galaxy() -> list[dict]:
    db = Path(os.environ.get("LOOTRADAR_GALAXY_DB") or program_data() / "GOG.com" / "Galaxy" / "storage" / "galaxy-2.0.db")
    if not db.exists():
        return []
    tmp = Path(tempfile.mkdtemp()) / "galaxy.db"
    try:
        shutil.copy2(db, tmp)  # Galaxy keeps the file open; read a copy
        con = sqlite3.connect(str(tmp))
        rows = con.execute(
            "SELECT DISTINCT lr.releaseKey, gp.value FROM LibraryReleases lr "
            "JOIN GamePieces gp ON gp.releaseKey = lr.releaseKey "
            "JOIN GamePieceTypes t ON t.id = gp.gamePieceTypeId WHERE t.type = 'title'"
        ).fetchall()
        try:
            times = dict(con.execute("SELECT releaseKey, MAX(minutesInGame) FROM GameTimes GROUP BY releaseKey").fetchall())
        except sqlite3.Error:
            times = {}
        con.close()
    except (sqlite3.Error, OSError):
        return []
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    out, seen = [], set()
    for key, value in rows:
        prefix = str(key).split("_", 1)[0].lower()
        src = GALAXY_PREFIX.get(prefix)
        if not src or key in seen:  # steam_ and unknown stores are skipped
            continue
        seen.add(key)
        try:
            name = clean(json.loads(value).get("title") or "")
        except (ValueError, AttributeError):
            continue
        if name and not JUNK.search(name):
            out.append({"name": name, "source": src, "id": key, "owned_only": True,
                        "playtime_min": int(times.get(key) or 0)})
    return out


# ------------------------------------------------------------------ all together
READERS = (epic, from_installed_programs, ubisoft, xbox, gog_galaxy)


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(name).lower().replace("&", " and ")).strip()


def scan() -> tuple[list[dict], list[str]]:
    """All games found on this PC (one entry per game) and any readers that failed."""
    found: dict[str, dict] = {}
    errors = []
    for reader in READERS:
        try:
            items = reader()
        except Exception as exc:  # one broken launcher must never stop the others
            errors.append(f"{reader.__name__}: {exc}")
            continue
        for g in items:
            n = norm(g["name"])
            if not n:
                continue
            have = found.get(n)
            if have is None:
                found[n] = {**g, "installed": not g.get("owned_only")}
            else:  # same game from two places: installed beats owned-only, keep play time
                if not g.get("owned_only"):
                    have["installed"] = True
                    if have.get("owned_only"):
                        have.update(source=g["source"], id=g["id"], owned_only=False)
                have["playtime_min"] = max(have.get("playtime_min", 0), g.get("playtime_min", 0))
    # The same game under a longer store name ("Tom Clancy's Rainbow Six Siege" vs "Rainbow Six
    # Siege"): keep one, preferring the installed copy.
    import checks
    items = sorted(found.values(), key=lambda g: (not g.get("installed"), -len(g["name"])))
    merged: list[dict] = []
    for g in items:
        twin = next((m for m in merged if checks.same_game_suffix(m["name"], g["name"])), None)
        if twin is None:
            merged.append(g)
        else:
            twin["playtime_min"] = max(twin.get("playtime_min", 0), g.get("playtime_min", 0))
    return merged, errors
