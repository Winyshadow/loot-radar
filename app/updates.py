"""Update checks for Loot Radar itself and for the built-in drop miner.

Loot Radar, two kinds of copy (see paths.py):
* Installed app: compares its version with the newest GitHub Release that has LootRadarSetup.exe
  attached. "Update Loot Radar" downloads that setup file, runs it silently and quits; the setup
  replaces the program and starts the new version. Your data is elsewhere and isn't touched.
* Zip copy: compares the VERSION file here with the VERSION file on GitHub (UPDATE_REPO, main
  branch). "Update Loot Radar" downloads that branch, copies it over this folder (your settings
  in app/data, the Python packages in app/.venv and the miner are left alone) and restarts.
  Once a release has the setup file, zip copies can also "Switch to the installer version":
  your settings and the miner are copied to the installed app's place, then the setup opens.

Miner: compares the installed version with its newest GitHub release.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import requests

import autostart
import minerctl
import notify
import paths
import store

# The GitHub repo Loot Radar updates itself from ("owner/name").
UPDATE_REPO = "Winyshadow/loot-radar"
BRANCH = "main"

ROOT = paths.INSTALL_DIR  # zip copy: the folder with START.bat
VERSION_FILE = paths.VERSION_FILE
RAW_URL = os.environ.get("LOOTRADAR_RAW_URL", f"https://raw.githubusercontent.com/{UPDATE_REPO}/{BRANCH}/VERSION")
ZIP_URL = os.environ.get("LOOTRADAR_ZIP_URL", f"https://codeload.github.com/{UPDATE_REPO}/zip/refs/heads/{BRANCH}")
RELEASE_API = os.environ.get("LOOTRADAR_RELEASE_API", f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest")
SETUP_NAME = "LootRadarSetup.exe"
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
                              "configured": configured(), "page": REPO_PAGE, "error": None,
                              "mode": paths.APP_MODE}
        info["installer"] = None  # the newest release's setup file, if it has one
        if configured():
            try:
                info["installer"] = latest_installer()
            except Exception as exc:
                if paths.FROZEN:
                    info["loot_radar"]["error"] = f"Couldn't check ({exc.__class__.__name__})"
            try:
                if paths.FROZEN:  # installed app: updates come as a new setup file in a Release
                    rel = info["installer"]
                    if rel:
                        info["loot_radar"].update(latest=rel["version"], page=rel["page"],
                                                  available=bool(rel["url"]) and minerctl.newer(rel["version"], current_version()))
                else:
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


def latest_installer() -> dict | None:
    """The newest GitHub Release: {version, url (of LootRadarSetup.exe, or None), size, page}."""
    r = requests.get(RELEASE_API, timeout=20, headers={"Accept": "application/vnd.github+json"})
    if r.status_code == 404:  # no releases at all
        return None
    r.raise_for_status()
    data = r.json()
    asset = next((a for a in data.get("assets") or [] if a.get("name") == SETUP_NAME), None)
    return {"version": str(data.get("tag_name", "")).lstrip("vV"),
            "url": asset.get("browser_download_url") if asset else None,
            "size": asset.get("size") if asset else None,
            "page": data.get("html_url") or f"{REPO_PAGE}/releases"}


# ------------------------------------------------------------------ self-update
def update_loot_radar_async(on_done) -> bool:
    """on_done(exit_code): called when Loot Radar should quit (3 = restart, 0 = the setup takes over)."""
    if job["state"] == "working":
        return False
    job.update(state="working", note="Downloading the new version…")
    target = _update_installed if paths.FROZEN else _update
    threading.Thread(target=target, args=(on_done,), daemon=True).start()
    return True


def switch_to_installer_async(on_done) -> bool:
    """Zip copy only: move your settings and the miner over to the installed app, then open its setup."""
    if paths.FROZEN or job["state"] == "working":
        return False
    job.update(state="working", note="Downloading the installer…")
    threading.Thread(target=_switch, args=(on_done,), daemon=True).start()
    return True


def _download_setup() -> tuple[Path, str]:
    """Download the newest LootRadarSetup.exe to a temp folder. Returns (path, version)."""
    rel = latest_installer()
    if not rel or not rel.get("url"):
        raise RuntimeError("The newest release doesn't have the installer yet. Try again in a little while.")
    dest = Path(tempfile.gettempdir()) / f"LootRadarSetup-{rel['version']}.exe"
    with requests.get(rel["url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or rel.get("size") or 0)
        done = 0
        tmp = dest.with_suffix(".part")
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total:
                    job["note"] = f"Downloading Loot Radar {rel['version']}… {done * 100 // total}%"
    data_ok = tmp.stat().st_size > 1_000_000 and tmp.read_bytes()[:2] == b"MZ"
    if not data_ok or (rel.get("size") and tmp.stat().st_size != rel["size"]):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("The download doesn't look like Loot Radar's installer, so nothing was changed.")
    os.replace(tmp, dest)
    return dest, rel["version"]


def _launch_detached(args: list[str]) -> None:
    """Start the setup so it keeps running after Loot Radar quits."""
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(args, creationflags=flags | 0x01000000, close_fds=True)  # + CREATE_BREAKAWAY_FROM_JOB
            return
        except OSError:
            pass
    subprocess.Popen(args, creationflags=flags, close_fds=True)


def _update_installed(on_done) -> None:
    """Installed app: run the new setup silently; it closes this copy and starts the new one."""
    try:
        setup, version = _download_setup()
        job.update(note=f"Installing Loot Radar {version}. It starts again by itself in a moment…")
        store.log(f"Installing Loot Radar {version} (the setup restarts it).")
        _launch_detached([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LAUNCH=1"])
        job.update(state="done")
        on_done(0)
    except Exception as exc:
        msg = (str(exc).splitlines() or [exc.__class__.__name__])[0][:240]
        job.update(state="error", note=f"Update failed: {msg}")
        store.log(f"Loot Radar update failed: {msg}", "error")


CACHE_DIRS = ("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
              "GrShaderCache", "GraphiteDawnCache", "ShaderCache", "Service Worker", "*.tmp", "*.part")


def _copy_tree(src: Path, dst: Path) -> int:
    """Copy a folder, skipping browser caches and files Windows won't let go of. Returns problems."""
    try:
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*CACHE_DIRS))
        return 0
    except shutil.Error as exc:  # copies everything it can, then lists what it couldn't
        return len(exc.args[0]) if exc.args and isinstance(exc.args[0], list) else 1


def move_to_installed_home(src_data: Path, src_miner: Path, home: Path) -> str:
    """Copy a zip copy's settings and miner to where the installed app keeps them.
    Never overwrites an installed app that already has settings. Returns a short note."""
    dst_data, dst_miner = home / "data", home / "miner"
    if (dst_data / "config.json").exists():
        return "The installed app already has settings, so they were kept as they are."
    problems = _copy_tree(src_data, dst_data) if src_data.exists() else 0
    if src_miner.exists() and not (dst_miner / "TwitchDropsMiner").exists():
        problems += _copy_tree(src_miner, dst_miner)
        shutil.rmtree(dst_miner / "_download", ignore_errors=True)
    cfg_path = dst_data / "config.json"
    if cfg_path.exists():  # remember where it came from, so the new app can say the old folder may go
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["migrated_from"] = str(src_data.parent.parent)
        cfg.pop("miner_exe", None)  # points into the old folder; the new app finds its own
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"Copied your settings and the miner ({problems} file(s) skipped)." if problems else "Copied your settings and the miner."


def _switch(on_done) -> None:
    try:
        setup, version = _download_setup()
        job.update(note="Stopping the miner…")
        minerctl.stop()
        job.update(note="Copying your settings and the miner…")
        note = move_to_installed_home(paths.DATA_DIR, paths.MINER_DIR, paths.INSTALLED_HOME)
        store.log(f"Switching to the installed Loot Radar {version}. {note}")
        args = [str(setup)]
        if not autostart.enabled():
            args.append("/MERGETASKS=!startup")  # keep "start with Windows" the way you had it
        job.update(state="done", note="The installer is open. Follow its steps; this copy closes now.")
        _launch_detached(args)
        on_done(0)
    except Exception as exc:
        msg = (str(exc).splitlines() or [exc.__class__.__name__])[0][:240]
        job.update(state="error", note=f"Switching failed: {msg}")
        store.log(f"Switching to the installer failed: {msg}", "error")
        try:
            minerctl.autostart()
        except Exception:
            pass


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
        on_done(RESTART_CODE)
    except Exception as exc:
        msg = (str(exc).splitlines() or [exc.__class__.__name__])[0][:240]
        job.update(state="error", note=f"Update failed: {msg}")
        store.log(f"Loot Radar update failed: {msg}", "error")
