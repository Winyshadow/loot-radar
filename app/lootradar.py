"""Loot Radar — watches your Steam games for Twitch drops and news, pings Discord, and collects drops.

Run with START.bat. Dashboard: http://127.0.0.1:5577
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import autostart
import checks
import memguard
import minerctl
import updates
import notify
import phone
import steam
import store
from miner import Miner, MinerError

HERE = Path(__file__).resolve().parent
PORT = 5577

app = Flask(__name__, static_folder=None)
watcher = None  # MutedWatcher, created at startup


def _err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code


def _bg(fn, *a, **kw):
    threading.Thread(target=fn, args=a, kwargs=kw, daemon=True).start()


@app.before_request
def _phone_gate():
    """Requests through the phone server need the PIN cookie; PC-only things are refused."""
    if not phone.is_phone_request(request):
        return None
    path = request.path
    if not phone.settings()["enabled"]:
        return _err("Phone access is switched off on the PC.", 403)
    if path in phone.OPEN_PATHS:
        return None
    if not phone.authorized(request):
        if path.startswith("/api/"):
            return _err("Enter the PIN first.", 401)
        return phone.PIN_PAGE, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}
    if any(path == p or path.startswith(p + "/") for p in phone.PC_ONLY_PATHS):
        return _err("That can only be done on the PC.", 403)
    return None


@app.post("/api/phone-login")
def api_phone_login():
    if not phone.is_phone_request(request):
        return _err("Only for the phone.", 404)
    ok, msg = phone.check_pin(request.remote_addr or "?", (request.get_json(silent=True) or {}).get("pin", ""))
    if not ok:
        return _err(msg, 401)
    store.log(f"A phone signed in to Loot Radar ({request.remote_addr}).")
    resp = jsonify({"ok": True})
    resp.set_cookie(phone.COOKIE, phone.settings()["token"], max_age=180 * 86400, httponly=True, samesite="Lax")
    return resp


@app.get("/manifest.webmanifest")
def manifest():
    """Lets "Add to Home Screen" on a phone show Loot Radar like an app."""
    return jsonify({
        "name": "Loot Radar", "short_name": "Loot Radar", "start_url": "/#/overview", "display": "standalone",
        "background_color": "#071b27", "theme_color": "#071b27",
        "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}],
    }), 200, {"Content-Type": "application/manifest+json"}


@app.get("/api/phone")
def api_phone():
    """Phone access details for Settings on the PC (the gate keeps the phone itself out)."""
    s, addrs = phone.settings(), phone.addresses()
    return jsonify({"ok": True, "enabled": s["enabled"], "running": phone.running(), "pin": s["pin"],
                    "port": phone.PORT, "wifi": addrs["wifi"], "tailscale": addrs["tailscale"]})


@app.post("/api/phone/config")
def api_phone_config():
    data = request.get_json(force=True) or {}
    if data.get("new_pin"):
        phone.new_pin()
        store.log("Made a new phone PIN; phones need to enter it again.")
    if "enabled" in data:
        store.update_config(phone_access=bool(data["enabled"]))
    status = phone.sync(app)
    if status == "error":
        store.update_config(phone_access=False)
        return _err(f"Couldn't open port {phone.PORT} (another program may be using it).", 500)
    return api_phone()


@app.get("/api/phone/qr.png")
def api_phone_qr():
    addr = request.args.get("addr", "")
    allowed = phone.addresses()
    if addr not in allowed["wifi"] + allowed["tailscale"]:
        return _err("Unknown address.", 400)
    png = phone.qr_png(phone.url_for(addr) + "#pin-" + phone.settings()["pin"])
    return png, 200, {"Content-Type": "image/png", "Cache-Control": "no-store"}


@app.get("/")
def index():
    return send_from_directory(HERE / "web", "index.html")


@app.get("/<path:name>.<ext>")
def static_file(name, ext):
    if ext not in ("png", "ico"):
        return _err("Not found.", 404)
    return send_from_directory(HERE / "web", f"{name}.{ext}")


_account = {"at": 0.0, "value": {"state": "unknown", "user": "", "status": ""}}


def _miner_account() -> dict:
    """Which Twitch account the miner is signed in to (asked at most every 15 s), so the
    dashboard can show it without anyone opening the miner itself."""
    if time.time() - _account["at"] < 15:
        return _account["value"]
    if not minerctl.running():
        value = {"state": "stopped", "user": "", "status": ""}
    else:
        cfg = store.load_config()
        try:
            login = Miner(cfg["miner_url"], cfg.get("miner_password", "")).status().get("login") or {}
            user, status = login.get("user_login") or "", login.get("status") or ""
            signed_in = bool(user) and "logged in" in status.lower()
            value = {"state": "in" if signed_in else "out", "user": user, "status": status}
        except MinerError as exc:
            value = {"state": "unknown", "user": "", "status": str(exc)}
    _account.update(at=time.time(), value=value)
    return value


@app.get("/api/state")
def api_state():
    cfg = store.load_config()
    state = store.load_state()
    games = [{"appid": appid, **g} for appid, g in (cfg.get("games") or {}).items()]
    games.sort(key=lambda g: -(g.get("playtime_min") or 0))
    settings = {k: v for k, v in cfg.items() if k != "games"}
    settings["start_with_windows"] = autostart.enabled()  # lives in Windows, not in config.json
    remote = phone.is_phone_request(request)
    settings = phone.redact(settings) if remote else {k: v for k, v in settings.items() if k != "phone_token"}
    return jsonify({
        "remote": remote,
        "settings": settings,
        "games": games,
        "campaigns": state.get("campaigns") or [],
        "completed": list(reversed(state.get("completed_drops") or [])),
        "claimed_total": state.get("claimed_total") or 0,
        "log": list(reversed(state.get("log") or []))[:80],
        "miner_status": state.get("miner_status", "unknown"),
        "miner_paused_by_us": state.get("miner_paused_by_us", False),
        "muted": watcher.status if watcher else {"state": "off"},
        "muted_manual": state.get("muted_manual"),
        "miner_memory": state.get("miner_memory"),
        "miner_login": getattr(watcher, "miner_login", {"state": "idle", "note": ""}),
        "miner_account": _miner_account(),
        "last_check": state.get("last_check", 0),
        "library_updated": state.get("library_updated", 0),
        "version": updates.current_version(),
        "updates": state.get("updates") or {},
        "update_job": updates.job,
        "miner_job": minerctl.job,
        "miner_builtin": minerctl.installed(),
        "miner_running": minerctl.running(),
        "miner_running_builtin": minerctl.is_builtin_running(),
        "now": int(time.time()),
    })


_points_cache: dict[str, tuple[float, int]] = {}


@app.get("/api/now")
def api_now():
    """What's being mined right now: current drop with exact time left, the channel being
    watched (viewers, logo) and channel points. Polled every few seconds by the Overview."""
    cfg = store.load_config()
    m = Miner(cfg["miner_url"], cfg.get("miner_password", ""))
    out = {"ok": True, "online": False, "muted": watcher.status if watcher else {"state": "off"}}
    try:
        st = m.status()
    except MinerError as exc:
        out["error"] = str(exc)
        return jsonify(out)
    out.update(online=True, status=st.get("status"), paused=st.get("paused"),
               paused_until=st.get("paused_until"), drop=st.get("current_drop"))

    # channel being watched (+ viewers from the channel list)
    ch = st.get("watching_channel")
    try:
        chans = m.channels()
    except MinerError:
        chans = []
    if ch:
        info = next((c for c in chans if str(c.get("id")) == str(ch.get("id"))), {})
        ch = {**ch, "viewers": info.get("viewers"), "drops_enabled": info.get("drops_enabled"),
              "online": info.get("online", True), "game_icon": info.get("game_icon")}
    out["channel"] = ch
    out["channel_count"] = sum(1 for c in chans if c.get("online"))

    # channel points: live balance for the current channel (cached 2 min), recent ones from history
    points = {}
    try:
        for login, snaps in (m.points_history() or {}).items():
            if snaps:
                points[login] = {"balance": snaps[-1].get("balance") or 0, "ts": snaps[-1].get("ts")}
    except MinerError:
        pass
    if ch and ch.get("login"):
        login = ch["login"].lower()
        cached = _points_cache.get(login)
        if not cached or time.time() - cached[0] > 120:
            try:
                bal = int(m.channel_points(login).get("balance") or 0)
                _points_cache[login] = cached = (time.time(), bal)
            except (MinerError, ValueError, TypeError):
                pass
        if cached:
            points[login] = {"balance": cached[1], "ts": None, "live": True}
    out["points"] = sorted(({"login": k, **v} for k, v in points.items()),
                           key=lambda p: (not p.get("live"), -(p["balance"] or 0)))[:8]

    # add what Loot Radar knows: reward image, game art, drops left in this campaign
    d = out["drop"]
    if d:
        camps = store.load_state().get("campaigns") or []
        camp = next((c for c in camps if c.get("id") == d.get("campaign_id")), None)
        if camp:
            pending = [x for x in camp["drops"] if not x.get("claimed") and not checks.is_sub_drop(x)]
            d["image"] = next((x.get("image") for x in camp["drops"] if x.get("id") == d.get("drop_id")), "")
            d["box_art"] = camp.get("box_art")
            d["drops_left"] = len(pending)
            d["campaign_minutes_left"] = sum(max(0, x["required"] - x["current"]) for x in pending)
            d["ends_at"] = camp.get("ends_at")
            d["mode"] = camp.get("mode")
    return jsonify(out)


@app.post("/api/settings")
def api_settings():
    data = request.get_json(force=True) or {}
    if phone.is_phone_request(request):  # the phone may change everyday options, not secrets or PC things
        data = {k: v for k, v in data.items() if k not in phone.PC_ONLY_SETTINGS}
    data.pop("phone_access", None)  # only through Settings > Phone access (/api/phone/config)
    if "start_with_windows" in data:
        if not autostart.supported():
            return _err("Starting with Windows only works on Windows.")
        try:
            autostart.set_enabled(bool(data["start_with_windows"]))
        except OSError as exc:
            return _err(f"Windows didn't allow changing the startup setting: {exc}")
        store.log("Loot Radar will now start when you sign in to Windows." if data["start_with_windows"]
                  else "Loot Radar will no longer start with Windows.")
    cfg = store.load_config()
    for key in ("steam_api_key", "discord_webhook", "miner_url", "miner_password", "news_mode"):
        if key in data:
            cfg[key] = str(data[key]).strip()
    for key, low in (("check_minutes", 5), ("news_check_hours", 1), ("miner_memory_limit_mb", 0)):
        if key in data:
            try:
                value = int(data[key])
                cfg[key] = 0 if key == "miner_memory_limit_mb" and value <= 0 else max(low, value)
                if key == "miner_memory_limit_mb" and 0 < cfg[key] < 512:
                    cfg[key] = 512  # the miner legitimately needs a few hundred MB
            except (TypeError, ValueError):
                pass
    for key in ("auto_start_miner", "auto_update_miner", "alert_library_drops", "priority_auto_sort",
                "steam_skipped", "discord_skipped"):
        if key in data:
            cfg[key] = bool(data[key])
    if "sync_miner_webhook" in data:
        cfg["sync_miner_webhook"] = bool(data["sync_miner_webhook"])
    if cfg.get("discord_webhook") and "discord.com/api/webhooks/" not in cfg["discord_webhook"] \
            and "discordapp.com/api/webhooks/" not in cfg["discord_webhook"]:
        return _err("That doesn't look like a Discord webhook link (it should contain discord.com/api/webhooks/).")
    profile = str(data.get("steam_profile_input", cfg.get("steam_profile_input", ""))).strip()
    if profile and (profile != cfg.get("steam_profile_input") or not cfg.get("steam_id")):
        if not cfg.get("steam_api_key"):
            return _err("Add your Steam API key first.")
        try:
            cfg["steam_id"] = steam.resolve_steam_id(cfg["steam_api_key"], profile)
        except steam.SteamError as exc:
            return _err(str(exc))
        cfg["steam_profile_input"] = profile
    store.save_config(cfg)
    first_library = cfg.get("steam_id") and cfg.get("steam_api_key") and not cfg.get("games")
    if first_library:
        try:
            checks.refresh_library()
        except steam.SteamError as exc:
            return _err(str(exc))
    return jsonify({"ok": True})


@app.post("/api/library/refresh")
def api_refresh():
    try:
        n = checks.refresh_library()
    except steam.SteamError as exc:
        return _err(str(exc))
    return jsonify({"ok": True, "count": n})


@app.post("/api/library/scan")
def api_scan():
    try:
        res = checks.scan_pc()
    except Exception as exc:
        return _err(f"Scan failed: {exc}")
    _bg(checks.run_cycle, watcher)
    return jsonify({"ok": True, **res})


@app.post("/api/games/<appid>")
def api_game(appid):
    data = request.get_json(force=True) or {}
    cfg = store.load_config()
    g = (cfg.get("games") or {}).get(appid)
    if not g:
        return _err("Unknown game.", 404)
    if "mode" in data:
        if data["mode"] not in store.MODES:
            return _err("Unknown mode.")
        g["mode"] = data["mode"]
        if appid.startswith("tw:") and g["mode"] == "off":
            del cfg["games"][appid]
            store.save_config(cfg)
            store.log(f"{g['name']}: removed (Twitch-only game).")
            _bg(checks.run_cycle, watcher)
            return jsonify({"ok": True})
    if "twitch_name" in data:
        g["twitch_name"] = str(data["twitch_name"]).strip()
    store.save_config(cfg)
    if "mode" in data:
        store.log(f"{g['name']}: set to {dict(off='Off', alerts='Alerts', miner='Auto-mine', muted='Muted stream')[g['mode']]}.")
    _bg(checks.run_cycle, watcher)  # apply right away (miner list, muted mode)
    return jsonify({"ok": True})


_streams_cache: dict[str, tuple[float, list]] = {}


@app.get("/api/streamers")
def api_streamers():
    """Live drops-enabled streamers for a game (for sub-only drops: pick who to sub to)."""
    game = (request.args.get("game") or "").strip()
    if not game:
        return _err("Which game?")
    from watcher import drops_streams
    cached = _streams_cache.get(game.lower())
    if not cached or time.time() - cached[0] > 180:
        try:
            cached = _streams_cache[game.lower()] = (time.time(), drops_streams(game, 30))
        except Exception as exc:  # network trouble or Twitch changed something
            return _err(f"Couldn't load streamers from Twitch: {exc}", 502)
    return jsonify({"ok": True, "streamers": cached[1]})


@app.get("/api/twitch-drops")
def api_twitch_drops():
    """Every campaign the miner can see, grouped by Twitch game, with your mode for each."""
    cfg = store.load_config()
    games = cfg.get("games") or {}
    try:
        campaigns = Miner(cfg["miner_url"], cfg.get("miner_password", "")).campaigns()
    except MinerError as exc:
        return _err(str(exc), 503)
    groups: dict[str, dict] = {}
    for c in campaigns:
        if c.get("expired"):
            continue
        name = c.get("game_name") or "?"
        grp = groups.setdefault(name, {"game_name": name, "box_art": c.get("game_box_art_url") or "",
                                       "campaigns": [], "active": False})
        grp["active"] = grp["active"] or bool(c.get("active"))
        grp["campaigns"].append({
            "name": c.get("name"), "active": c.get("active"), "upcoming": c.get("upcoming"),
            "starts_at": c.get("starts_at"), "ends_at": c.get("ends_at"), "linked": c.get("linked"),
            "link_url": c.get("link_url"), "claimed_drops": c.get("claimed_drops"),
            "total_drops": c.get("total_drops"),
            "sub_only": bool(c.get("drops")) and all(checks.is_sub_drop(d) for d in c["drops"]),
            "rewards": [b.get("name") for d in c.get("drops") or [] for b in d.get("benefits") or [] if b.get("name")],
        })
    out = []
    for name, grp in groups.items():
        m = checks.match_game(games, name, include_off=True)
        tw = games.get(checks.twitch_key(name))
        if tw:
            grp.update(appid=checks.twitch_key(name), mode=tw.get("mode", "off"), owned=None)
        elif m:
            src = None if m[0].startswith("tw:") else (m[1].get("source") or "steam")
            grp.update(appid=m[0], mode=m[1].get("mode", "off"),
                       owned=None if src is None else m[1]["name"], source=src,
                       installed=m[1].get("installed", True) if src not in (None, "steam") else None)
        else:
            grp.update(appid=None, mode="off", owned=None)
        out.append(grp)
    # games you have first, then live campaigns, then A-Z
    out.sort(key=lambda g: (not g.get("owned"), not g["active"], g["game_name"].lower()))
    return jsonify({"ok": True, "games": out})


@app.post("/api/twitch-game")
def api_twitch_game():
    """Add / change / remove a Twitch-only game (any Twitch category, e.g. ExileCon)."""
    data = request.get_json(force=True) or {}
    name = str(data.get("name", "")).strip()
    mode = data.get("mode", "miner")
    if not name:
        return _err("Type the game's name exactly as Twitch shows it.")
    if mode not in store.MODES:
        return _err("Unknown mode.")
    cfg = store.load_config()
    games = cfg.setdefault("games", {})
    key = checks.twitch_key(name)
    if mode == "off":
        if games.pop(key, None):
            store.log(f"{name}: removed (Twitch-only game).")
    else:
        g = games.get(key) or {"playtime_min": 0, "last_played": 0, "order": 0, "source": "twitch"}
        g.update(name=name, twitch_name=name, mode=mode)
        if data.get("box_art"):
            g["box_art"] = str(data["box_art"])
        games[key] = g
        label = dict(alerts="Alerts", miner="Auto-mine", muted="Muted stream")[mode]
        store.log(f"{name}: added from Twitch, set to {label}.")
    store.save_config(cfg)
    _bg(checks.run_cycle, watcher)
    return jsonify({"ok": True})


@app.post("/api/completed/clear")
def api_clear_completed():
    hours = float((request.get_json(silent=True) or {}).get("older_than_hours") or 0)
    n = checks.clear_completed(hours)
    return jsonify({"ok": True, "cleared": n})


@app.post("/api/miner/install")
def api_miner_install():
    if not minerctl.install_async():
        return _err("An install is already running.")
    store.log("Installing the latest drop miner…")
    return jsonify({"ok": True})


@app.post("/api/miner/start")
def api_miner_start():
    if minerctl.running():
        return jsonify({"ok": True, "note": "The miner is already running."})
    if not minerctl.start():
        return _err("The built-in miner isn't installed yet. Press Install first.")
    store.log("Started the drop miner.")
    _bg(checks.run_cycle, watcher)
    return jsonify({"ok": True})


@app.post("/api/miner/stop")
def api_miner_stop():
    minerctl.stop()
    store.log("Stopped the drop miner.")
    return jsonify({"ok": True})


@app.post("/api/updates/check")
def api_updates_check():
    _bg(updates.check, True)
    return jsonify({"ok": True})


@app.post("/api/updates/apply")
def api_updates_apply():
    if not updates.configured():
        return _err("Updates aren't set up for this copy of Loot Radar.")
    if not updates.update_loot_radar_async(_restart_for_update):
        return _err("An update is already running.")
    return jsonify({"ok": True})


def _restart_for_update():
    """Called after a self-update: close the muted-mode browser, then exit with the code that
    tells launcher.py to install any new packages and start the new version."""
    def go():
        time.sleep(1.5)  # let the dashboard see the "restarting" message
        _shutdown(False, updates.RESTART_CODE)
    threading.Thread(target=go, daemon=True).start()


@app.post("/api/priority")
def api_priority():
    data = request.get_json(force=True) or {}
    if data.get("sort") == "ending":
        order = checks.sort_priority_by_end()
    elif isinstance(data.get("order"), list):
        order = checks.set_priority([str(k) for k in data["order"]])
    else:
        return _err("Nothing to change.")
    _bg(checks.run_cycle, watcher)  # tell the miner right away
    return jsonify({"ok": True, "priority": order})


@app.post("/api/check")
def api_check():
    _bg(checks.run_cycle, watcher, True)
    return jsonify({"ok": True})


@app.post("/api/test-discord")
def api_test_discord():
    cfg = store.load_config()
    hook = (request.get_json(silent=True) or {}).get("webhook") or cfg.get("discord_webhook")
    if not hook:
        return _err("Paste your Discord webhook link first.")
    ok = notify.simple(hook, "✅ Loot Radar is connected",
                       "Drop campaigns and news for the games you pick will show up here.")
    return jsonify({"ok": ok}) if ok else _err("Discord didn't accept the message. Check the webhook link.")


@app.post("/api/test-miner")
def api_test_miner():
    cfg = store.load_config()
    try:
        n = len(Miner(cfg["miner_url"], cfg.get("miner_password", "")).campaigns())
    except MinerError as exc:
        return _err(str(exc))
    return jsonify({"ok": True, "campaigns": n})


@app.post("/api/miner/login")
def api_miner_login():
    import miner_bridge
    if not hasattr(watcher, "login_for_miner"):
        return _err("The login window is disabled in this mode.")
    watcher.login_for_miner(miner_bridge.install_session)
    store.log("Opening a Twitch sign-in window for the drop miner…")
    return jsonify({"ok": True})


@app.post("/api/muted/watch")
def api_muted_watch():
    game = str((request.get_json(force=True) or {}).get("game_name", "")).strip()
    if not game:
        return _err("Which game?")
    store.patch_state(muted_manual=game)
    store.log(f"Muted mode: you asked to watch {game}.")
    watcher.want(game)
    watcher.resume_after_close()
    return jsonify({"ok": True})


@app.post("/api/muted/stop")
def api_muted_stop():
    store.patch_state(muted_manual=None)
    watcher.want(None)
    store.log("Muted mode stopped.")
    _bg(checks.run_cycle, watcher)
    return jsonify({"ok": True})


@app.post("/api/muted/resume")
def api_muted_resume():
    watcher.resume_after_close()
    _bg(checks.run_cycle, watcher)
    return jsonify({"ok": True})


CHECK_SECONDS = 120  # drop progress refresh (the miner is local, so this is cheap)


def scheduler():
    """Drops + progress every 2 minutes (Steam news on its own slower timer); a light miner
    pause/resume sync and memory check every 30 seconds."""
    last_full = 0.0
    time.sleep(3)
    while True:
        try:
            if time.time() - last_full >= CHECK_SECONDS:
                last_full = time.time()
                checks.run_cycle(watcher)
            checks.sync_pause(watcher)
            updates.check()  # only actually checks GitHub every 6 hours
            if os.name == "nt" and time.time() - (store.load_state().get("pc_scanned") or 0) > 6 * 3600:
                checks.scan_pc()
            memguard.check()
        except Exception as exc:  # never let the timer die
            store.log(f"Check failed: {exc}", "error")
        time.sleep(30)


LOG_PATH = store.DATA_DIR / "lootradar.log"


def _log_to_file() -> None:
    """With no console window, everything that used to print there goes to data/lootradar.log."""
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 2_000_000:
            LOG_PATH.replace(LOG_PATH.with_suffix(".old.log"))
    except OSError:
        pass
    f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


def _already_running() -> bool:
    try:
        import requests
        return requests.get(f"http://127.0.0.1:{PORT}/api/state", timeout=3).status_code == 200
    except Exception:
        return False


def _shutdown(stop_miner: bool = False, code: int = 0) -> None:
    """Close the muted-mode browser and the tray icon, optionally the miner, then exit."""
    try:
        if stop_miner:
            minerctl.stop()
            store.log("Stopped the drop miner.")
        if watcher and hasattr(watcher, "shutdown"):
            watcher.shutdown()
            time.sleep(2)
    finally:
        import tray
        t = threading.Thread(target=tray.stop, daemon=True)  # never let the icon block an exit
        t.start()
        t.join(2)
        os._exit(code)


def _serve() -> None:
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=PORT, threads=6, _quiet=True)
    except ImportError:
        app.run(host="127.0.0.1", port=PORT, threaded=True)


def main():
    global watcher
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-muted", action="store_true", help="disable muted-stream mode (testing)")
    parser.add_argument("--console", action="store_true", help="log to this window, no tray icon")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{PORT}"
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _already_running():
        # START.bat / the shortcut while Loot Radar is already running: just show the dashboard.
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    if not args.console:
        _log_to_file()

    if args.no_muted:
        class _Off:
            status = {"state": "off"}
            def want(self, *_): pass
            def skip_channel(self): pass
            def resume_after_close(self): pass
        watcher = _Off()
    else:
        from watcher import MutedWatcher
        watcher = MutedWatcher(store.DATA_DIR / "browser-profile")

    store.log(f"Loot Radar {updates.current_version()} started.")
    autostart.refresh_path()
    _bg(minerctl.autostart)
    threading.Thread(target=scheduler, name="scheduler", daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    phone.sync(app)  # phone access, if you switched it on (its own server, port 5578)
    import tray
    if args.console or not tray.available():
        print(f"\n  Loot Radar is running. Dashboard: {url}\n  Close this window to stop it.\n", flush=True)
        _serve()
        return 0

    threading.Thread(target=_serve, name="web", daemon=True).start()
    state = store.load_state()
    first = not state.get("tray_tip_shown")
    if first:
        store.patch_state(tray_tip_shown=True)
    cfg = store.load_config()
    tray.run(url, on_quit=lambda stop_miner: _shutdown(stop_miner, 0),
             on_restart=lambda: _shutdown(False, updates.RESTART_CODE),
             miner_url=cfg.get("miner_url") or "http://127.0.0.1:8080", log_path=LOG_PATH, first_time=first)
    return 0


if __name__ == "__main__":
    sys.exit(main())
