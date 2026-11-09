"""Loot Radar's own Edge window: Twitch sign-in for the miner, and muted-stream mode.

It starts your installed Microsoft Edge (or Chrome) as a completely normal window, with its own
profile in data/browser-profile, so you sign in to Twitch there once. Loot Radar never automates
the page itself (Twitch's login page refuses "automated" browsers). It only talks to the browser
over its DevTools port, the same way Twitch Drops Miner does, to:
  * read the Twitch login cookie after you sign in, and
  * point the tab at a live drops-enabled stream (and switch when it goes offline).
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import requests

import store

GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Twitch's public web client id
# Persisted query for Twitch's game directory page (same one Twitch Drops Miner uses).
DIRECTORY_HASH = "cb5dc816e139dcb8a118f14b4b677d59abc224a4b016c4bc2bb00a47fe0ddec4"
RECHECK_SECONDS = 600
SKIP_SECONDS = 3600

BROWSER_ARGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--mute-audio",
    "--autoplay-policy=no-user-gesture-required",
    # keep the player running when the window is minimised or covered
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]


def slugify(name: str) -> str:
    """Twitch category slug from a game name (same rules Twitch Drops Miner uses)."""
    s = re.sub(r"'", "", name.lower())
    s = re.sub(r"\W+", "-", s)
    return re.sub(r"-{2,}", "-", s.strip("-"))


def drops_channels_gql(game_name: str, limit: int = 30) -> list[str]:
    """Live channels with drops enabled for a game, most viewers first."""
    return [s["login"] for s in drops_streams(game_name, limit)]


def drops_streams(game_name: str, limit: int = 30) -> list[dict]:
    """Live drops-enabled streams for a game, most viewers first, with the details the
    dashboard shows (name, viewers, title, picture)."""
    body = {
        "operationName": "DirectoryPage_Game",
        "variables": {
            "limit": limit,
            "slug": slugify(game_name),
            "imageWidth": 50,
            "includeCostreaming": False,
            "options": {
                "broadcasterLanguages": [],
                "freeformTags": None,
                "includeRestricted": ["SUB_ONLY_LIVE"],
                "recommendationsContext": {"platform": "web"},
                "sort": "VIEWER_COUNT",
                "systemFilters": ["DROPS_ENABLED"],
                "tags": [],
                "requestID": "JIRA-VXP-2397",
            },
            "sortTypeIsRecency": False,
        },
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": DIRECTORY_HASH}},
    }
    r = requests.post(GQL_URL, json=body, headers={"Client-Id": CLIENT_ID}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        data = data[0]
    if data.get("errors"):
        raise RuntimeError(str(data["errors"])[:200])
    game = (data.get("data") or {}).get("game")
    if not game:
        return []
    out = []
    for edge in (game.get("streams") or {}).get("edges") or []:
        node = edge.get("node") or {}
        b = node.get("broadcaster")
        if b and b.get("login"):
            out.append({
                "login": b["login"], "name": b.get("displayName") or b["login"],
                "avatar": b.get("profileImageURL") or "", "partner": bool((b.get("roles") or {}).get("isPartner")),
                "viewers": node.get("viewersCount") or 0, "title": node.get("title") or "",
            })
    return out


class BrowserGone(Exception):
    """The browser window was closed (by you) or crashed."""


class PlainBrowser:
    """A normal Edge/Chrome window we can talk to over its DevTools port without touching pages."""

    def __init__(self, profile_dir: Path):
        self.profile_dir = profile_dir
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.ws = None
        self._id = 0

    # -- start / stop ------------------------------------------------------------------
    @staticmethod
    def find_exe() -> str:
        override = os.environ.get("LOOTRADAR_BROWSER")
        if override:
            return override
        roots = [os.environ.get(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            for root in roots:
                if root and os.path.exists(os.path.join(root, rel)):
                    return os.path.join(root, rel)
        for name in ("msedge", "google-chrome", "chrome", "chromium"):
            found = shutil.which(name)
            if found:
                return found
        raise RuntimeError("Couldn't find Microsoft Edge or Google Chrome.")

    def start(self, url: str = "about:blank") -> None:
        import websocket  # websocket-client

        self.kill_leftovers()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        args = [self.find_exe(), f"--user-data-dir={self.profile_dir}",
                f"--remote-debugging-port={self.port}", *BROWSER_ARGS, url]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 30
        while True:
            try:
                info = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=2).json()
                break
            except (requests.RequestException, ValueError):
                if self.proc.poll() is not None or time.time() > deadline:
                    self.stop()
                    raise RuntimeError("The browser window closed straight away. Try again in a moment.")
                time.sleep(0.4)
        # Browser-level connection only; no Origin header (Chrome/Edge reject unknown origins).
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], timeout=20, suppress_origin=True)

    def running(self) -> bool:
        return self.ws is not None and self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        # Close politely first so the browser saves its cookies (your Twitch sign-in) to disk.
        if self.ws is not None:
            try:
                self.call("Browser.close")
            except Exception:
                pass
            try:
                self.ws.close()
            except Exception:
                pass
        self.ws = None
        if self.proc is not None:
            try:
                self.proc.wait(timeout=8)
            except Exception:
                pass
            self.proc = None
        self.kill_leftovers()

    def kill_leftovers(self) -> None:
        """Stop anything still running on our profile (e.g. after a crash or an older version)."""
        try:
            import psutil
        except ImportError:
            return
        marker = str(self.profile_dir).lower()
        for p in psutil.process_iter(["cmdline"]):
            try:
                if marker in " ".join(p.info.get("cmdline") or []).lower():
                    p.kill()
            except Exception:
                continue

    # -- DevTools calls ------------------------------------------------------------------
    def call(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        if self.ws is None:
            raise BrowserGone()
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        try:
            self.ws.send(json.dumps(msg))
            while True:
                reply = json.loads(self.ws.recv())
                if reply.get("id") == self._id:
                    break
        except Exception as exc:
            if method == "Browser.close":
                return {}
            raise BrowserGone() from exc
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error'].get('message')}")
        return reply.get("result", {})

    def twitch_cookies(self) -> dict:
        cookies = self.call("Storage.getCookies").get("cookies", [])
        return {c["name"]: c["value"] for c in cookies if c.get("domain", "").endswith("twitch.tv")}

    def tabs(self) -> list[dict]:
        return [t for t in self.call("Target.getTargets").get("targetInfos", []) if t.get("type") == "page"]

    def current_url(self) -> str:
        tabs = self.tabs()
        if not tabs:
            raise BrowserGone()
        return tabs[0].get("url", "")

    def navigate(self, url: str, low_quality: bool = False) -> None:
        tabs = self.tabs()
        if not tabs:
            raise BrowserGone()
        on_twitch = "twitch.tv" in tabs[0].get("url", "")
        sid = self.call("Target.attachToTarget", {"targetId": tabs[0]["targetId"], "flatten": True})["sessionId"]
        try:
            if low_quality and not on_twitch:
                # Twitch's settings live in its own storage, so be on twitch.tv before setting them.
                self.call("Page.navigate", {"url": url}, session=sid)
                time.sleep(3)
            if low_quality:
                self._set_twitch_prefs(sid)
            self.call("Page.navigate", {"url": url}, session=sid)
        finally:
            try:
                self.call("Target.detachFromTarget", {"sessionId": sid})
            except Exception:
                pass

    def _set_twitch_prefs(self, sid: str) -> None:
        """Lowest video quality (saves bandwidth) and skip the mature-content click-through."""
        storage = {"securityOrigin": "https://www.twitch.tv", "isLocalStorage": True}
        try:
            self.call("DOMStorage.enable", session=sid)
            for key, value in (("video-quality", '{"default":"160p30"}'), ("mature", "true")):
                self.call("DOMStorage.setDOMStorageItem", {"storageId": storage, "key": key, "value": value},
                          session=sid)
        except RuntimeError:
            pass


class MutedWatcher:
    def __init__(self, profile_dir: Path):
        self.browser = PlainBrowser(profile_dir)
        self.q: queue.Queue = queue.Queue()
        self.status = {"state": "idle", "game": None, "channel": None, "since": None, "note": ""}
        self.miner_login = {"state": "idle", "note": ""}  # idle | waiting | working | done | error
        self._skipped: dict[str, float] = {}
        self._thread = threading.Thread(target=self._run, name="loot-radar-browser", daemon=True)
        self._thread.start()

    # ---- called from other threads -------------------------------------------------
    def want(self, game_name: str | None) -> None:
        self.q.put(("want", game_name))

    def skip_channel(self) -> None:
        self.q.put(("skip", None))

    def resume_after_close(self) -> None:
        self.q.put(("unpause", None))

    def login_for_miner(self, on_session) -> None:
        """Open the window, let you sign in to Twitch, then call on_session(token, unique_id)."""
        self.q.put(("miner_login", on_session))

    def shutdown(self) -> None:
        self.q.put(("quit", None))

    @property
    def active(self) -> bool:
        return self.status["state"] == "watching"

    # ---- browser thread ------------------------------------------------------------
    def _set(self, state: str, note: str = "", **kw) -> None:
        if state != self.status["state"]:
            self.status["since"] = int(time.time())
        self.status.update(state=state, note=note, **kw)

    def _find_channels(self, game: str) -> list[str]:
        now = time.time()
        self._skipped = {k: v for k, v in self._skipped.items() if v > now}
        return [c for c in drops_channels_gql(game) if c not in self._skipped]

    def _run(self) -> None:
        br = self.browser
        desired = current = channel = None
        last_check = 0.0
        paused_by_close = False
        login_prompted = False
        miner_cb = None  # set while a "log the miner in" request is waiting for your sign-in

        while True:
            waiting_for_you = bool(miner_cb) or self.status["state"] == "needs_login"
            try:
                cmd, arg = self.q.get(timeout=2 if waiting_for_you else 20)
            except queue.Empty:
                cmd, arg = None, None
            if cmd == "quit":
                br.stop()
                break
            if cmd == "want" and arg != desired:
                desired, paused_by_close, last_check = arg, False, 0.0
            elif cmd == "skip" and channel:
                self._skipped[channel] = time.time() + SKIP_SECONDS
                store.log(f"Muted mode: drops weren't progressing on {channel}, trying another channel.", "warn")
                channel, last_check = None, 0.0
            elif cmd == "unpause":
                paused_by_close, last_check = False, 0.0
            elif cmd == "miner_login":
                miner_cb, login_prompted = arg, False
                self.miner_login = {"state": "waiting", "note": "Sign in to Twitch in the Loot Radar window"}

            try:
                # Did you close the window yourself? Then stay out of the way until asked again.
                if br.ws is not None and not br.running():
                    raise BrowserGone()

                if (desired is None or paused_by_close) and not miner_cb:
                    if br.ws is not None:
                        br.stop()
                    channel = current = None
                    self._set("paused" if paused_by_close else "idle",
                              "Closed by you" if paused_by_close else "", game=desired, channel=None)
                    continue

                if br.ws is None:
                    br.start()
                    channel, login_prompted = None, False

                # Needs a Twitch sign-in in this window (one time).
                cookies = br.twitch_cookies()
                if not cookies.get("auth-token"):
                    if not login_prompted or "twitch.tv" not in br.current_url():
                        br.navigate("https://www.twitch.tv/login")
                        login_prompted = True
                        store.log("Sign in to Twitch in the Loot Radar window that just opened "
                                  "(one time only — the miner and muted mode both use it).")
                    if not miner_cb:
                        self._set("needs_login", "Sign in to Twitch in the Loot Radar window",
                                  game=desired, channel=None)
                    continue

                if miner_cb:
                    cb, miner_cb = miner_cb, None
                    self.miner_login = {"state": "working", "note": "Passing the login to the miner…"}
                    try:
                        msg = cb(cookies.get("auth-token", ""), cookies.get("unique_id", ""))
                        self.miner_login = {"state": "done", "note": msg}
                        store.log(msg)
                    except Exception as exc:
                        self.miner_login = {"state": "error", "note": str(exc)}
                        store.log(f"Couldn't log the miner in: {exc}", "error")
                    if desired is None or paused_by_close:
                        br.stop()
                        self._set("idle", "", game=None, channel=None)
                        continue
                    channel = None  # the tab is on Twitch's home page now; go pick a stream

                if desired != current or channel is None or time.time() - last_check > RECHECK_SECONDS:
                    last_check = time.time()
                    try:
                        logins = self._find_channels(desired)
                    except Exception as exc:
                        store.log(f"Muted mode: couldn't look up live streams ({exc}).", "warn")
                        self._set("error", "Couldn't look up live streams; retrying soon",
                                  game=desired, channel=channel)
                        last_check = time.time() - RECHECK_SECONDS + 120
                        continue
                    if not logins:
                        if channel is not None or desired != current:
                            br.navigate("about:blank")
                        channel, current = None, desired
                        self._set("waiting", f"No live drops-enabled streams for {desired} right now",
                                  game=desired, channel=None)
                        continue
                    if desired != current or channel not in logins[:10]:
                        old = channel
                        channel = logins[0]
                        br.navigate(f"https://www.twitch.tv/{channel}", low_quality=True)
                        store.log(f"Muted mode: watching {channel} for {desired}"
                                  + (f" (switched from {old})" if old else "") + ".")
                    current = desired
                    self._set("watching", "", game=desired, channel=channel)

            except BrowserGone:
                br.stop()
                channel = current = None
                if miner_cb:
                    miner_cb = None
                    self.miner_login = {"state": "idle", "note": ""}
                    store.log("Miner login cancelled (the window was closed).")
                elif desired and not paused_by_close:
                    paused_by_close = True
                    store.log("Muted mode: you closed the browser window, so it's paused. "
                              "Press 'Resume muted mode' on the dashboard to restart it.")
                self._set("paused" if paused_by_close else "idle",
                          "Closed by you" if paused_by_close else "", game=desired, channel=None)
            except Exception as exc:
                msg = (str(exc).splitlines() or [exc.__class__.__name__])[0][:200]
                store.log(f"Loot Radar browser error: {msg}", "error")
                self._set("error", msg, game=desired, channel=channel)
                if miner_cb:
                    self.miner_login = {"state": "error", "note": msg}
                    miner_cb = None
                last_check = time.time() - RECHECK_SECONDS + 120  # retry in ~2 minutes
