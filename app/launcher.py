"""Starts Loot Radar without a console window and keeps it running across updates.

START.bat first runs   python launcher.py --prepare   in its (visible) window: that installs any
new Python packages with progress shown, and clears out a stuck earlier start. Then it starts
pythonw launcher.py   (no window), which:
  * starts lootradar.py and restarts it when an update finishes (exit code 3),
  * writes everything, including crashes, to app/data/lootradar.log,
  * shows a message box if Loot Radar fails to start.
"""

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESTART_CODE = 3
REQ = HERE / "requirements.txt"
VENV = HERE / ".venv"
REQ_STAMP = VENV / "lootradar-requirements.sha1"
LOG = HERE / "data" / "lootradar.log"
PORT = 5577
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def console_python() -> str:
    """python.exe next to pythonw.exe: pip behaves better with a real console interpreter."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return sys.executable


def packages_ok() -> bool:
    try:
        return REQ_STAMP.read_text().strip() == hashlib.sha1(REQ.read_bytes()).hexdigest()
    except OSError:
        return False


def ensure_packages(visible: bool) -> bool:
    """Install requirements.txt if it changed since the last install. Returns success."""
    if packages_ok():
        return True
    if visible:
        print("  Installing new parts for Loot Radar (one time, takes a minute)...", flush=True)
    try:
        r = subprocess.run(
            [console_python(), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", "-q", "-r", str(REQ)],
            cwd=str(HERE), stdin=subprocess.DEVNULL, timeout=900,
            creationflags=0 if visible else NO_WINDOW,
            stdout=None if visible else sys.stdout, stderr=None if visible else sys.stderr,
        )
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Installing packages failed: {exc}", file=sys.stderr, flush=True)
        ok = False
    if ok:
        try:
            REQ_STAMP.write_text(hashlib.sha1(REQ.read_bytes()).hexdigest())
        except OSError:
            pass
        if visible:
            print("  Done.", flush=True)
    return ok


def running() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/state", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def clear_stuck_starts() -> None:
    """Loot Radar isn't answering, but an earlier start from this folder may still be hanging
    (e.g. waiting on an install). Stop those so this start is clean."""
    try:
        import psutil
    except ImportError:
        return
    venv = str(VENV).lower()
    keep = {os.getpid()}
    try:  # never this process or what started it (the venv's python.exe is a small redirector)
        keep |= {a.pid for a in psutil.Process().parents()}
    except Exception:
        pass
    for p in psutil.process_iter(["pid", "exe", "cmdline"]):
        try:
            if p.info["pid"] in keep:
                continue
            exe = (p.info.get("exe") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            mine = exe.startswith(venv) or ("launcher.py" in cmd or "lootradar.py" in cmd) and str(HERE).lower() in cmd
            if mine and ("launcher.py" in cmd or "lootradar.py" in cmd or " pip " in f" {cmd} "
                         or "-m pip" in cmd):
                p.kill()
        except Exception:
            continue


def apply_pending_start_bat() -> None:
    """An update can't swap START.bat while it runs; do it a few seconds later instead."""
    def later():
        time.sleep(8)
        new = ROOT / "START.bat.new"
        if new.exists():
            try:
                os.replace(new, ROOT / "START.bat")
            except OSError:
                pass
    threading.Thread(target=later, daemon=True).start()


def message_box(text: str) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "Loot Radar", 0x10)
            return
        except Exception:
            pass
    print(text, file=sys.stderr)


def last_log_lines(n: int = 8) -> str:
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def prepare() -> int:
    """Run by START.bat in its window before the hidden start."""
    if not running():
        clear_stuck_starts()
    if not ensure_packages(visible=True):
        print("\n  Couldn't install Loot Radar's parts (see the messages above).")
        print("  Check your internet connection and run START.bat again.")
        return 1
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--prepare" in args:
        return prepare()
    console = "--console" in args
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = None
    if not console:  # pythonw: no console, so everything goes to the log file
        logf = open(LOG, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = logf
    if not ensure_packages(visible=console):
        message_box("Loot Radar couldn't install the parts it needs.\n\n" + last_log_lines()
                    + "\n\nCheck your internet connection and run START.bat again.")
        return 1
    apply_pending_start_bat()
    while True:
        started = time.time()
        code = subprocess.call(
            [sys.executable, str(HERE / "lootradar.py"), *args], cwd=str(HERE),
            stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,  # crashes land in the log too
            creationflags=0 if console else NO_WINDOW,
        )
        if code == RESTART_CODE:
            print("Loot Radar is restarting (update or restart from the tray).", flush=True)
            ensure_packages(visible=console)
            args = [a for a in args if a != "--no-browser"] + ["--no-browser"]  # the tab is already open
            continue
        if code != 0 and time.time() - started < 60:
            message_box("Loot Radar couldn't start.\n\n" + (last_log_lines() or f"Exit code {code}.")
                        + f"\n\nThe full log is in:\n{LOG}")
        return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
