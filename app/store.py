"""Tiny JSON storage for Loot Radar: config (your settings + game list) and state (what we've seen)."""

from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import paths

DATA_DIR = paths.DATA_DIR
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"

MODES = ("off", "alerts", "miner", "muted")

DEFAULT_CONFIG = {
    "steam_api_key": "",
    "steam_id": "",              # SteamID64 (resolved from whatever the user pasted)
    "steam_profile_input": "",   # what the user pasted (URL / vanity / id)
    "discord_webhook": "",
    "miner_url": "http://127.0.0.1:8080",
    "miner_password": "",
    "news_mode": "announcements",   # announcements | important | off
    "check_minutes": 30,
    "news_check_hours": 3,
    "sync_miner_webhook": True,
    "miner_memory_limit_mb": 2048,
    "auto_start_miner": True,       # start the built-in miner with Loot Radar
    "auto_update_miner": False,     # install new miner releases without asking
    "alert_library_drops": True,    # ping about drops for games you have but haven't set up  # restart the miner above this (0 = off)
    "steam_skipped": False,         # "Skip Steam for now" ticked: no setup reminders for it
    "discord_skipped": False,       # same for Discord
    "phone_access": False,          # second server on the network for your phone (see phone.py)
    "phone_pin": "",                # 6 digits, made on first use
    "phone_token": "",              # phone session secret; a new PIN replaces it (signs phones out)
    "deals_enabled": False,         # watch your Steam wishlist for discounts (see deals.py)
    "ggdeals_key": "",              # GG.deals Prices API key (free; key-shop and store prices)
    "deals_region": "",             # GG.deals region code ("" = its default)
    "deals_currency": "",           # estimate GG.deals prices in: "" = your Steam currency, "NONE" = no estimate
    "deals_min_discount": 50,       # ping when a Steam discount is at least this many percent
    "deals_keyshops": True,         # show and ping key-shop (reseller) prices too
    "deals_webhook": "",            # Discord channel for deals ("" = the main one)
    "deals_extra": [],              # Steam app IDs you added by hand
    "games": {},  # appid -> {name, playtime_min, last_played, mode, twitch_name, order}
}

DEFAULT_STATE = {
    "seen_news": {},          # appid -> [gid, ...]
    "alerted_campaigns": [],  # campaign ids we've already pinged about
    "library_updated": 0,
    "last_check": 0,
    "last_news_check": 0,
    "campaigns": [],          # latest campaigns for watched games (for the dashboard)
    "miner_status": "unknown",
    "log": [],                # [{ts, level, msg}]
}

_lock = threading.RLock()


class StoreError(OSError):
    """A settings file exists but couldn't be read. Never answered with defaults: saving those
    would overwrite (and so lose) everything in it."""


def _backup(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def _parse(path: Path) -> dict | None:
    """The file's contents, or None if it's missing, damaged or not a JSON object.
    Raises StoreError if it's there but Windows won't let us read it (OneDrive, antivirus)."""
    for attempt in range(10):  # a lock by OneDrive or antivirus usually lasts a moment
        try:
            text = path.read_text(encoding="utf-8")
            break
        except FileNotFoundError:
            return None
        except OSError as exc:
            if attempt == 9:
                raise StoreError(f"Couldn't read {path.name} ({exc.__class__.__name__}); "
                                 "it was left as it is.") from exc
            time.sleep(0.2)
    try:
        loaded = json.loads(text)
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _read(path: Path, default: dict) -> dict:
    data = copy.deepcopy(default)
    loaded = _parse(path)
    if loaded is None and path.exists():
        # Damaged (e.g. cut off by a power cut or a sync conflict): keep it aside, use the
        # previous good copy so nothing is lost.
        if path not in _damaged:
            _damaged.add(path)
            try:
                shutil.copy2(path, path.with_name(f"{path.stem}.damaged-{int(time.time())}{path.suffix}"))
            except OSError:
                pass
        loaded = _parse(_backup(path))
        if loaded is not None:
            print(time.strftime("%H:%M:%S"), "WARN", f"{path.name} was damaged; using its backup.", flush=True)
    elif loaded is None:
        loaded = _parse(_backup(path))  # missing: a save may have stopped halfway, see _write
    if loaded:
        data.update(loaded)
    return data


def _write(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    # The current file becomes the backup (a rename, so it costs nothing), then the new one goes in.
    # A damaged current file never replaces the good backup.
    try:
        if path.exists() and path not in _damaged:
            os.replace(path, _backup(path))
    except OSError:
        pass  # backup is a bonus; never let it stop a save
    os.replace(tmp, path)
    _damaged.discard(path)


_damaged: set[Path] = set()


def load_config() -> dict:
    with _lock:
        return _read(CONFIG_PATH, DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    with _lock:
        _write(CONFIG_PATH, cfg)


def update_config(**changes) -> dict:
    with _lock:
        cfg = load_config()
        cfg.update(changes)
        save_config(cfg)
        return cfg


def load_state() -> dict:
    with _lock:
        return _read(STATE_PATH, DEFAULT_STATE)


def save_state(state: dict) -> None:
    with _lock:
        _write(STATE_PATH, state)


def patch_state(**changes) -> dict:
    """Update only the given state keys (safe alongside log() calls from other threads)."""
    with _lock:
        state = load_state()
        state.update(changes)
        save_state(state)
        return state


@contextmanager
def edit_config():
    """Read, change and save the config with nothing else saving in between:
    with store.edit_config() as cfg: cfg["x"] = 1   (saved when the block ends without an error)."""
    with _lock:
        cfg = load_config()
        yield cfg
        save_config(cfg)


@contextmanager
def edit_state():
    """Like edit_config, for state.json."""
    with _lock:
        state = load_state()
        yield state
        save_state(state)


def log(msg: str, level: str = "info") -> None:
    """Append a line to the dashboard activity log (keeps the last 200)."""
    try:
        with _lock:
            state = load_state()
            state["log"] = (state.get("log") or [])[-199:] + [
                {"ts": int(time.time()), "level": level, "msg": msg}
            ]
            save_state(state)
    except OSError:  # state.json locked right now: the line still goes to lootradar.log
        pass
    print(time.strftime("%H:%M:%S"), level.upper(), msg, flush=True)
