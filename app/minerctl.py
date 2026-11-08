"""Built-in drop miner: install, update, start and stop Twitch Drops Miner from inside Loot Radar.

The miner (github.com/SimpliAj/twitchdropsminer, MIT licence) is downloaded from its official
GitHub release into  <Loot Radar>/miner/TwitchDropsMiner/  the first time you press Install.
Its Twitch login and settings live in %APPDATA%\\TwitchDropsMiner, so they survive updates and
are shared with any copy you ran before.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import zipfile
from pathlib import Path

import requests

import store

ROOT = Path(__file__).resolve().parent.parent
MINER_DIR = ROOT / "miner"
APP_DIR = MINER_DIR / "TwitchDropsMiner"
EXE = APP_DIR / "TwitchDropsMiner.exe"
INFO = MINER_DIR / "installed.json"

MINER_REPO = "SimpliAj/twitchdropsminer"
RELEASES_API = os.environ.get("LOOTRADAR_MINER_API", f"https://api.github.com/repos/{MINER_REPO}/releases/latest")
ASSET_SUFFIX = os.environ.get("LOOTRADAR_MINER_ASSET", "-windows-x64.zip")

# Progress of a running install/update, shown on the dashboard.
job = {"state": "idle", "note": "", "pct": 0}
_job_lock = threading.Lock()


# ------------------------------------------------------------------ versions
def parse_version(v: str | None) -> tuple:
    nums = []
    for part in str(v or "").lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums or [0])


def newer(latest: str | None, current: str | None) -> bool:
    return bool(latest) and bool(current) and parse_version(latest) > parse_version(current)


def installed() -> dict | None:
    """{"version": "1.8.18", "installed_at": ...} for the built-in miner, or None."""
    if not EXE.exists():
        return None
    try:
        return json.loads(INFO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": None}


def latest_release() -> dict:
    """Newest miner release on GitHub: {version, url, page, published}."""
    r = requests.get(RELEASES_API, timeout=20, headers={"Accept": "application/vnd.github+json"})
    if r.status_code == 403:
        raise RuntimeError("GitHub is rate-limiting update checks right now; try again in an hour.")
    r.raise_for_status()
    data = r.json()
    asset = next((a for a in data.get("assets") or [] if str(a.get("name", "")).endswith(ASSET_SUFFIX)), None)
    return {
        "version": str(data.get("tag_name", "")).lstrip("vV"),
        "url": asset.get("browser_download_url") if asset else None,
        "size": asset.get("size") if asset else None,
        "page": data.get("html_url") or f"https://github.com/{MINER_REPO}/releases",
        "published": data.get("published_at"),
    }


# ------------------------------------------------------------------ processes
def processes():
    try:
        import psutil
    except ImportError:
        return []
    found = []
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() in ("twitchdropsminer.exe", "twitchdropsminer"):
            found.append(p)
    return found


def running() -> bool:
    return bool(processes())


def running_exe() -> str | None:
    for p in processes():
        try:
            return p.exe()
        except Exception:
            continue
    return None


def is_builtin_running() -> bool:
    exe = running_exe()
    try:
        return bool(exe) and Path(exe).resolve() == EXE.resolve()
    except OSError:
        return False


def stop(timeout: float = 10) -> None:
    """Stop every running miner (its browser windows go with it)."""
    procs = processes()
    if not procs:
        return
    import psutil
    for p in procs:
        try:
            for c in p.children(recursive=True):
                c.kill()
            p.kill()
        except Exception:
            pass
    psutil.wait_procs(procs, timeout=timeout)
    time.sleep(1.5)  # let Windows release the files


def start() -> bool:
    """Start the built-in miner (hidden dashboard window) if it isn't already running."""
    if running():
        return True
    if not EXE.exists():
        return False
    import memguard
    memguard.launch_miner(str(EXE))
    store.update_config(miner_exe=str(EXE))
    threading.Thread(target=finish_first_run, daemon=True).start()
    return True


def finish_first_run(wait: float = 60) -> None:
    """A brand-new miner waits for a 'password or not' choice on its dashboard. Loot Radar
    talks to it for you, so choose 'Start without password' (it only listens on this PC)."""
    base = (store.load_config().get("miner_url") or "http://127.0.0.1:8080").rstrip("/")
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            r = requests.get(base + "/api/settings", timeout=5, allow_redirects=False)
        except requests.RequestException:
            time.sleep(2)
            continue
        if r.status_code in (302, 303, 307) and "__setup" in r.headers.get("location", ""):
            try:
                requests.post(base + "/__setup_post", data={"action": "skip"}, timeout=10, allow_redirects=False)
                store.log("Finished the miner's first-time setup for you (no dashboard password).")
            except requests.RequestException:
                pass
        return
    return


def autostart() -> None:
    """Called when Loot Radar starts: bring the built-in miner up if it isn't running."""
    if not store.load_config().get("auto_start_miner", True):
        return
    if EXE.exists() and not running():
        if start():
            store.log("Started the built-in drop miner.")


# ------------------------------------------------------------------ install / update
def install_async(release: dict | None = None) -> bool:
    """Download + install (or update to) the newest miner in the background."""
    with _job_lock:
        if job["state"] in ("downloading", "installing"):
            return False
        job.update(state="downloading", note="Checking GitHub…", pct=0)
    threading.Thread(target=_install, args=(release,), daemon=True).start()
    return True


def _install(release: dict | None) -> None:
    tmp = MINER_DIR / "_download"
    try:
        rel = release or latest_release()
        if not rel.get("url"):
            raise RuntimeError("The newest miner release has no Windows download yet. Try again later.")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        zip_path = tmp / "miner.zip"

        job.update(note=f"Downloading the miner v{rel['version']}…")
        with requests.get(rel["url"], stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or rel.get("size") or 0)
            done = 0
            with zip_path.open("wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        job["pct"] = int(done * 100 / total)

        job.update(state="installing", note="Unpacking…", pct=100)
        out = tmp / "unpacked"
        with zipfile.ZipFile(zip_path) as zf:
            for m in zf.namelist():  # refuse anything that would land outside the folder
                target = (out / m).resolve()
                if not str(target).startswith(str(out.resolve())):
                    raise RuntimeError("The download looked wrong (unsafe paths), so it wasn't installed.")
            zf.extractall(out)
        exe = next((p for p in out.rglob("*") if p.name.lower() == "twitchdropsminer.exe"), None)
        if exe is None:
            raise RuntimeError("The download didn't contain TwitchDropsMiner.exe.")

        was_running = running()
        job.update(note="Stopping the miner…")
        stop()
        job.update(note="Installing…")
        old = MINER_DIR / f"_old_{int(time.time())}"
        if APP_DIR.exists():
            APP_DIR.rename(old)
        shutil.move(str(exe.parent), str(APP_DIR))
        INFO.write_text(json.dumps({"version": rel["version"], "installed_at": int(time.time())}), encoding="utf-8")
        shutil.rmtree(old, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
        store.update_config(miner_exe=str(EXE))

        if os.name != "nt":
            os.chmod(EXE, 0o755)  # zip files don't keep the "executable" flag outside Windows

        verb = "Updated" if was_running else "Installed"
        job.update(note="Starting the miner…")
        try:
            start()
            job.update(state="done", note=f"{verb} the drop miner v{rel['version']}.", pct=100)
        except Exception as exc:
            job.update(state="error", pct=100,
                       note=f"{verb} the drop miner v{rel['version']}, but it didn't start ({exc}). Press Start.")
        store.log(job["note"], "info" if job["state"] == "done" else "warn")
        import updates
        updates.forget_miner_notice()
    except Exception as exc:
        msg = (str(exc).splitlines() or [exc.__class__.__name__])[0][:240]
        if "WinError 5" in msg or "WinError 32" in msg:
            msg = ("Windows wouldn't let go of the miner's files. Close the miner from its tray icon "
                   "and try again.")
        job.update(state="error", note=msg)
        store.log(f"Miner install failed: {msg}", "error")
        # the old copy is still in place if renaming never happened; restart whatever we have
        try:
            if not APP_DIR.exists():
                olds = sorted(MINER_DIR.glob("_old_*"))
                if olds:
                    olds[-1].rename(APP_DIR)
            start()
        except Exception:
            pass
