"""Update checks for Loot Radar itself and for the built-in drop miner.

Loot Radar: compares the VERSION file here with the VERSION file on GitHub (UPDATE_REPO,
main branch). "Update Loot Radar" downloads that branch, copies it over this folder (your
settings in app/data, the Python packages in app/.venv and the miner are left alone) and
restarts. To publish an update: change the code, bump VERSION, push to GitHub.

Miner: compares the installed version with its newest GitHub release.
"""

from __future__ import annotations

import io
import os
import shutil
import threading
import time
import zipfile
from pathlib import Path

import requests

import minerctl
import notify
import store

# The GitHub repo Loot Radar updates itself from ("owner/name").
UPDATE_REPO = "Winyshadow/loot-radar"
BRANCH = "main"

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
RAW_URL = os.environ.get("LOOTRADAR_RAW_URL", f"https://raw.githubusercontent.com/{UPDATE_REPO}/{BRANCH}/VERSION")
ZIP_URL = os.environ.get("LOOTRADAR_ZIP_URL", f"https://codeload.github.com/{UPDATE_REPO}/zip/refs/heads/{BRANCH}")
REPO_PAGE = f"https://github.com/{UPDATE_REPO}"

# Never overwritten by an update: personal data, installed packages, the miner, git metadata.
KEEP = ("app/data", "app/.venv", "miner", ".git")
CHECK_EVERY = 6 * 3600
RESTART_CODE = 3  # launcher.py restarts Loot Radar when it exits with this

job = {"state": "idle", "note": ""}
_check_lock = threading.Lock()


def configured() -> bool:
    return "CHANGE-ME" not in UPDATE_REPO or "LOOTRADAR_RAW_URL" in os.environ


def current_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


# ------------------------------------------------------------------ checking
def miner_current_version() -> str | None:
    info = minerctl.installed()
    if info and info.get("version"):
        return info["version"]
    # someone else's copy (e.g. the one you downloaded yourself): ask it
    cfg = store.load_config()
    try:
        r = requests.get((cfg.get("miner_url") or "http://127.0.0.1:8080").rstrip("/") + "/api/version",
                         timeout=10, allow_redirects=False)
        if r.status_code == 200:
            return r.json().get("current_version")
    except (requests.RequestException, ValueError):
        pass
    return None


def check(force: bool = False) -> dict:
    """Refresh both update checks (at most every 6 hours unless forced). Returns the summary."""
    if not _check_lock.acquire(blocking=False):
        return store.load_state().get("updates") or {}
    try:
        state = store.load_state()
        info = dict(state.get("updates") or {})
        if not force and time.time() - info.get("checked", 0) < CHECK_EVERY:
            return info

        info["loot_radar"] = {"current": current_version(), "latest": None, "available": False,
                              "configured": configured(), "page": REPO_PAGE, "error": None}
        if configured():
            try:
                r = requests.get(RAW_URL, timeout=15, headers={"Cache-Control": "no-cache"})
                r.raise_for_status()
                latest = r.text.strip().splitlines()[0].strip()
                info["loot_radar"].update(latest=latest, available=minerctl.newer(latest, current_version()))
            except Exception as exc:
                info["loot_radar"]["error"] = f"Couldn't check ({exc.__class__.__name__})"

        builtin = minerctl.installed()
        info["miner"] = {"current": miner_current_version(), "latest": None, "available": False,
                         "builtin": bool(builtin), "page": f"https://github.com/{minerctl.MINER_REPO}/releases",
                         "error": None}
        try:
            rel = minerctl.latest_release()
            info["miner"].update(latest=rel["version"], page=rel["page"], has_download=bool(rel["url"]),
                                 available=minerctl.newer(rel["version"], info["miner"]["current"]))
        except Exception as exc:
            info["miner"]["error"] = str(exc)[:160]

        info["checked"] = int(time.time())
        store.patch_state(updates=info)
        _notify(info)

        cfg = store.load_config()
        if (cfg.get("auto_update_miner") and info["miner"]["available"] and builtin
                and info["miner"].get("has_download")):
            store.log(f"Auto-updating the drop miner to v{info['miner']['latest']}.")
            minerctl.install_async()
        return info
    finally:
        _check_lock.release()


def _notify(info: dict) -> None:
    """One Discord ping per new version."""
    state = store.load_state()
    told = list(state.get("update_notified") or [])
    hook = store.load_config().get("discord_webhook")
    lines = []
    lr, mn = info.get("loot_radar") or {}, info.get("miner") or {}
    if lr.get("available") and f"lr:{lr['latest']}" not in told:
        told.append(f"lr:{lr['latest']}")
        lines.append(f"**Loot Radar {lr['latest']}** is out (you have {lr['current']}).")
    if mn.get("available") and f"mn:{mn['latest']}" not in told:
        told.append(f"mn:{mn['latest']}")
        lines.append(f"**Drop miner {mn['latest']}** is out (you have {mn['current']}).")
    if not lines:
        return
    store.patch_state(update_notified=told[-50:])
    store.log("Update available: " + " ".join(l.replace("**", "") for l in lines))
    if hook:
        notify.simple(hook, "⬆️ Update available",
                      "\n".join(lines) + "\nOpen Loot Radar → Settings → Updates to install it in one click.",
                      notify.BLUE)


def forget_miner_notice() -> None:
    """After installing a miner, refresh the summary so the banner goes away."""
    state = store.load_state()
    info = dict(state.get("updates") or {})
    mn = dict(info.get("miner") or {})
    inst = minerctl.installed()
    if inst:
        mn.update(current=inst.get("version"), builtin=True,
                  available=minerctl.newer(mn.get("latest"), inst.get("version")))
        info["miner"] = mn
        store.patch_state(updates=info)


# ------------------------------------------------------------------ self-update
def update_loot_radar_async(on_done) -> bool:
    if job["state"] == "working":
        return False
    job.update(state="working", note="Downloading the new version…")
    threading.Thread(target=_update, args=(on_done,), daemon=True).start()
    return True


def _keep(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(rel == k or rel.startswith(k + "/") for k in KEEP)


def _update(on_done) -> None:
    try:
        r = requests.get(ZIP_URL, timeout=120)
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            raise RuntimeError("The download was empty.")
        top = names[0].split("/")[0] + "/"
        if not all(n.startswith(top) for n in names):
            top = ""
        if not any(n == top + "VERSION" for n in names) or not any(n == top + "app/lootradar.py" for n in names):
            raise RuntimeError("The download doesn't look like Loot Radar, so nothing was changed.")

        job["note"] = "Installing…"
        changed = 0
        for n in names:
            rel = n[len(top):]
            if not rel or _keep(rel) or ".." in Path(rel).parts:
                continue
            data = zf.read(n)
            dest = ROOT / rel
            if dest.exists() and dest.read_bytes() == data:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rel == "START.bat":
                # The running START.bat can't be swapped safely; it applies this on next start.
                dest = ROOT / "START.bat.new"
            tmp = dest.with_name(dest.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            changed += 1
        new_version = current_version()
        job.update(state="done", note=f"Updated to Loot Radar {new_version} — restarting…")
        store.log(f"Loot Radar updated to {new_version} ({changed} files). Restarting.")
        info = dict(store.load_state().get("updates") or {})
        if info.get("loot_radar"):
            info["loot_radar"].update(current=new_version, available=False)
            store.patch_state(updates=info)
        on_done()
    except Exception as exc:
        msg = (str(exc).splitlines() or [exc.__class__.__name__])[0][:240]
        job.update(state="error", note=f"Update failed: {msg}")
        store.log(f"Loot Radar update failed: {msg}", "error")
