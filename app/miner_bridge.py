"""Hands a Twitch login from Loot Radar's own browser window to Twitch Drops Miner.

Why: on some PCs the miner's own login window closes half a second after opening, so it can
never log in. Loot Radar's window works, so we log in there and give the miner that session:
validate the token, stop the miner, write its cookie file, start it again.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests

import store

WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # the miner uses Twitch's web client


class BridgeError(Exception):
    pass


def miner_data_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "TwitchDropsMiner"


def cookies_path() -> Path:
    base = miner_data_dir()
    try:
        account = json.loads((base / "web_config.json").read_text(encoding="utf-8")).get("active_account")
        if account:
            return base / "accounts" / account / "cookies.jar"
    except (OSError, ValueError):
        pass
    return base / "cookies.jar"


def validate(token: str) -> dict:
    try:
        r = requests.get("https://id.twitch.tv/oauth2/validate",
                         headers={"Authorization": f"OAuth {token}"}, timeout=15)
    except requests.RequestException as exc:
        raise BridgeError(f"Couldn't reach Twitch to check the login ({exc.__class__.__name__}).") from exc
    if r.status_code != 200:
        raise BridgeError("Twitch didn't accept that login. Sign out and in again in the Loot Radar window.")
    info = r.json()
    if info.get("client_id") != WEB_CLIENT_ID:
        raise BridgeError("That login came from an unexpected Twitch client, so the miner can't use it.")
    return info


def _miner_processes():
    import psutil
    found = []
    for p in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if name == "twitchdropsminer.exe":
                found.append(("miner", p))
            elif name in ("msedge.exe", "chrome.exe", "brave.exe") and "twitchdropsminer" in cmd \
                    and "dashboard-window" in cmd:
                found.append(("dashboard", p))
        except Exception:
            continue
    return found


def _write_cookie_file(path: Path, token: str, unique_id: str) -> None:
    import aiohttp
    from yarl import URL

    async def _go():
        jar = aiohttp.CookieJar()
        if path.exists():
            try:
                jar.load(path)
            except Exception:
                jar.clear()
        cookies = {"auth-token": token}
        if unique_id:
            cookies["unique_id"] = unique_id
        jar.update_cookies(cookies, URL("https://www.twitch.tv"))
        jar.save(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_go())


def install_session(token: str, unique_id: str) -> str:
    """Give the miner this Twitch session. Returns a message for the dashboard log."""
    info = validate(token)
    login = info.get("login") or "your account"

    procs = _miner_processes()
    exe = next((p.info.get("exe") for kind, p in procs if kind == "miner" and p.info.get("exe")), None)
    cfg = store.load_config()
    if exe:
        store.update_config(miner_exe=exe)
    else:
        exe = cfg.get("miner_exe") or ""

    # Stop the miner first so it can't overwrite the cookie file when it exits.
    for kind, p in procs:
        try:
            p.kill()
        except Exception:
            pass
    deadline = time.time() + 8
    while time.time() < deadline and any(k == "miner" for k, _ in _miner_processes()):
        time.sleep(0.3)

    path = cookies_path()
    if path.exists():
        shutil.copy2(path, path.with_suffix(".jar.bak"))
    _write_cookie_file(path, token, unique_id)

    if exe and Path(exe).exists():
        import memguard
        memguard.launch_miner(exe)
        return f"Drop miner logged in to Twitch as {login} and restarted."
    return f"Drop miner login saved for {login}. Start TwitchDropsMiner.exe and it will be logged in."
