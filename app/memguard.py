"""Memory guard for Twitch Drops Miner.

The miner is really several processes: the program itself, its dashboard window (an Edge
window) and short-lived hidden Edge windows it opens to renew a Twitch security token. Task
Manager shows them all under "TwitchDropsMiner". This module:
  * records how much each part uses every 5 minutes (data/miner-memory.csv), so a leak can be
    traced to the exact part, and
  * restarts the miner cleanly if the total goes over your limit, before Windows runs out of
    memory and freezes. The miner keeps its Twitch login across restarts.
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path

import notify
import store

SAMPLE_EVERY = 300        # seconds between rows in the CSV
COOLDOWN = 600            # don't restart more often than this
_last_sample = 0.0
_last_restart = 0.0


def _kind(proc) -> str:
    """Label a miner child process so the CSV says which part is using memory."""
    try:
        name = (proc.name() or "").lower()
        cmd = " ".join(proc.cmdline() or []).lower()
    except Exception:
        return "other"
    if name not in ("msedge.exe", "chrome.exe", "brave.exe", "msedge", "chrome"):
        return "other"
    if "dashboard-window" in cmd:
        return "dashboard window"
    if "tdm-chrome" in cmd or "remote-debugging-port" in cmd:
        return "token/login browser"
    return "browser"


def miner_snapshot():
    """Returns (main_processes, {part: MB}, total_MB, exe) for every running miner."""
    try:
        import psutil
    except ImportError:
        return [], {}, 0.0, None
    mains, parts, exe = [], {}, None
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() == "twitchdropsminer.exe":
            mains.append(p)
    seen = set()
    for m in mains:
        try:
            exe = exe or m.exe()
            procs = [(m, "miner program")] + [(c, _kind(c)) for c in m.children(recursive=True)]
        except Exception:
            continue
        for proc, part in procs:
            if proc.pid in seen:
                continue
            seen.add(proc.pid)
            try:
                mb = proc.memory_info().rss / 1048576
            except Exception:
                continue
            parts[part] = parts.get(part, 0.0) + mb
    return mains, parts, sum(parts.values()), exe


def _record(parts: dict, total: float, count: int) -> None:
    path = store.DATA_DIR / "miner-memory.csv"
    new = not path.exists()
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "total_mb", "miner_program_mb", "dashboard_window_mb",
                        "token_login_browser_mb", "other_browser_mb", "other_mb", "browser_processes"])
        w.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"), round(total),
            round(parts.get("miner program", 0)), round(parts.get("dashboard window", 0)),
            round(parts.get("token/login browser", 0)), round(parts.get("browser", 0)),
            round(parts.get("other", 0)), count,
        ])
    # keep the file small: last ~2 weeks of 5-minute rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 4100:
            path.write_text("\n".join(lines[:1] + lines[-4000:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def _restart(mains, exe: str | None) -> bool:
    import psutil
    for m in mains:
        try:
            for c in m.children(recursive=True):
                c.kill()
            m.kill()
        except Exception:
            pass
    psutil.wait_procs(mains, timeout=8)
    if not exe:
        exe = store.load_config().get("miner_exe")
    if exe and Path(exe).exists():
        time.sleep(2)
        launch_miner(exe)
        return True
    return False


def launch_miner(exe: str) -> None:
    """Start the miner without its own dashboard window (Loot Radar's dashboard covers it, and
    that window was the part of the miner whose memory kept growing). Its tray icon still has
    'Open dashboard' if you want it."""
    cwd = str(Path(exe).parent)
    if hasattr(os, "startfile"):
        os.startfile(exe, "open", "--no-browser", cwd)
    else:  # not Windows: only used by the automated tests
        import shlex
        import subprocess
        extra = shlex.split(os.environ.get("LOOTRADAR_MINER_TEST_ARGS", ""))
        subprocess.Popen([exe, *extra, "--no-browser"], cwd=cwd, start_new_session=True)


DASHBOARD_LIMIT_MB = 1024
_last_trim = 0.0


def _trim_dashboard(mains) -> bool:
    """Close just the miner's own dashboard window; mining carries on untouched."""
    closed = False
    for m in mains:
        try:
            for c in m.children(recursive=True):
                if _kind(c) == "dashboard window":
                    c.kill()
                    closed = True
        except Exception:
            continue
    return closed


def check() -> dict | None:
    """Called every 30 seconds. Returns the latest numbers for the dashboard."""
    global _last_sample, _last_restart
    mains, parts, total, exe = miner_snapshot()
    if not mains:
        store.patch_state(miner_memory=None)
        return None
    if exe:
        cfg = store.load_config()
        if cfg.get("miner_exe") != exe:
            store.update_config(miner_exe=exe)
    now = time.time()
    biggest = max(parts.items(), key=lambda kv: kv[1]) if parts else ("?", 0)
    info = {"total_mb": round(total), "parts": {k: round(v) for k, v in parts.items()},
            "biggest": biggest[0], "ts": int(now)}
    store.patch_state(miner_memory=info)

    if now - _last_sample >= SAMPLE_EVERY:
        _last_sample = now
        try:
            import psutil  # noqa: F401
            count = sum(1 for m in mains for c in m.children(recursive=True)
                        if _kind(c) != "other")
        except Exception:
            count = 0
        _record(parts, total, count)

    global _last_trim
    if parts.get("dashboard window", 0) > DASHBOARD_LIMIT_MB and now - _last_trim > COOLDOWN:
        _last_trim = now
        if _trim_dashboard(mains):
            store.log(f"Closed the miner's own dashboard window — it had grown to "
                      f"{parts['dashboard window'] / 1024:.1f} GB. Mining carries on; use Loot Radar's "
                      "dashboard instead.", "warn")
            return info

    limit = int(store.load_config().get("miner_memory_limit_mb") or 0)
    if limit and total > limit and now - _last_restart > COOLDOWN:
        _last_restart = now
        detail = ", ".join(f"{k} {v / 1024:.1f} GB" for k, v in
                           sorted(parts.items(), key=lambda kv: -kv[1]) if v >= 100)
        restarted = _restart(mains, exe)
        msg = (f"The drop miner was using {total / 1024:.1f} GB of memory ({detail}). "
               + ("Restarted it — it keeps its Twitch login, so farming carries on."
                  if restarted else "Stopped it; start TwitchDropsMiner.exe again."))
        store.log(msg, "warn")
        hook = store.load_config().get("discord_webhook")
        if hook:
            notify.simple(hook, "🧹 Miner memory guard", msg, notify.ORANGE)
    return info
