"""The work Loot Radar does on a timer: drops, news, miner sync and muted-mode decisions."""

from __future__ import annotations

import re
import threading
import time

import notify
import steam
import store
from miner import Miner, MinerError

_cycle_lock = threading.Lock()


def norm(name: str) -> str:
    name = re.sub(r"[™®©]", "", (name or "").lower()).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[™®©]", "", name or "")).strip()


# Edition words that stores tack onto the end of a name but Twitch usually leaves off
# ("Crimson Desert Enhanced" on Steam is "Crimson Desert" on Twitch). Only stripped from the
# END of a name, and never numbers, so sequels ("Path of Exile 2") always stay separate.
_EDITION_TAIL = re.compile(
    r"(?:\s|[:\-–—])+(?:enhanced|remastered|remaster|definitive|deluxe|complete|ultimate|"
    r"anniversary|goty|game of the year|director'?s cut|special|gold|premium|standard|hd|"
    r"redux|edition)\s*$",
    re.I,
)


def base_title(name: str) -> str:
    """'The Witcher 3: Wild Hunt — Remastered' -> 'The Witcher 3: Wild Hunt'."""
    name = clean_name(name)
    while True:
        shorter = _EDITION_TAIL.sub("", name).rstrip(" :-–—")
        if shorter == name or not shorter:
            return name
        name = shorter


def match_game(games: dict, twitch_game: str, include_off: bool = False):
    """Find which watched game a Twitch campaign belongs to: exact names first, then names
    that only differ by an edition word. include_off also searches games set to Off."""
    target = norm(twitch_game)
    if not target:
        return None
    watched = [(appid, g) for appid, g in games.items() if include_off or g.get("mode", "off") != "off"]
    for appid, g in watched:
        if norm(g.get("twitch_name") or "") == target or norm(g.get("name")) == target:
            return appid, g
    target_base = norm(base_title(twitch_game))
    for appid, g in watched:
        if not g.get("twitch_name") and norm(base_title(g.get("name"))) == target_base:
            return appid, g
    for appid, g in watched:
        if not g.get("twitch_name") and same_game_suffix(g.get("name"), twitch_game):
            return appid, g
    return None


def same_game_suffix(a: str, b: str) -> bool:
    """'Tom Clancy's Rainbow Six Siege' vs 'Rainbow Six Siege': one name is the other plus a
    publisher/series prefix. The shorter one needs 3+ words (or 14+ letters) and the same
    numbers, so 'Path of Exile' never matches 'Path of Exile 2'."""
    a, b = norm(base_title(a)), norm(base_title(b))
    if not a or not b or a == b:
        return a == b and bool(a)
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    if not long_.endswith(" " + short):
        return False
    if len(short.split()) < 3 and len(short) < 14:
        return False
    digits = lambda s: {w for w in s.split() if w.isdigit()}
    return digits(short) == digits(long_)


def possible_match(games: dict, twitch_game: str):
    """A campaign that looks like one of your games but isn't an exact match
    (same first two words), e.g. a different subtitle. Used to suggest a Twitch name."""
    words = norm(base_title(twitch_game)).split()
    if len(words) < 2:
        return None
    for appid, g in games.items():
        if g.get("mode", "off") == "off" or g.get("twitch_name"):
            continue
        mine = norm(base_title(g.get("name"))).split()
        if mine[:2] == words[:2] and mine != words:
            # a different number means a different game in the series (Path of Exile vs 2)
            if {w for w in mine if w.isdigit()} != {w for w in words if w.isdigit()}:
                continue
            return appid, g
    return None


def twitch_key(name: str) -> str:
    """Key for a Twitch-only game (not from Steam) in the games list."""
    return "tw:" + norm(name).replace(" ", "-")


def fully_claimed(c: dict) -> bool:
    total = c.get("total_drops") or 0
    return bool(total) and (c.get("claimed_drops") or 0) >= total


def is_sub_drop(d: dict) -> bool:
    """A drop you only get by subscribing (paying) to a streamer. Watching never earns it."""
    return bool(d.get("subs") or d.get("required_subs"))


def has_watch_work(c: dict) -> bool:
    """True if this campaign still has a drop you can earn just by watching. Sub-only drops
    don't count, so they never hold up the mining order or muted mode."""
    for d in c.get("drops") or []:
        claimed = d.get("claimed", d.get("is_claimed"))
        required = d.get("required", d.get("required_minutes")) or 0
        if not claimed and not is_sub_drop(d) and required > 0:
            return True
    return False


# ------------------------------------------------------------------ Steam library
def refresh_library() -> int:
    cfg = store.load_config()
    if not (cfg["steam_api_key"] and cfg["steam_id"]):
        raise steam.SteamError("Add your Steam API key and profile in Settings first.")
    owned = steam.owned_games(cfg["steam_api_key"], cfg["steam_id"])
    games = cfg.get("games") or {}
    fresh = {}
    for g in owned:
        old = games.get(g["appid"], {})
        fresh[g["appid"]] = {
            **g,
            "mode": old.get("mode", "off"),
            "twitch_name": old.get("twitch_name", ""),
            "order": old.get("order", 0),
        }
    # keep watched games even if they vanished (e.g. family-shared)
    for appid, g in games.items():
        if appid not in fresh and (g.get("mode", "off") != "off" or not appid.isdigit()):
            fresh[appid] = g  # Twitch-only games and other stores' games are managed separately
    cfg["games"] = fresh
    store.save_config(cfg)
    store.patch_state(library_updated=int(time.time()))
    store.log(f"Steam library refreshed: {len(owned)} games.")
    return len(owned)


def _hint_possible_match(games: dict, c: dict, hinted: list, hook: str) -> None:
    """Once per campaign: 'Twitch has drops for X — is that your game Y?'"""
    cid = c.get("id")
    if not cid or cid in hinted or not (c.get("active") or c.get("upcoming")):
        return
    pm = possible_match(games, c.get("game_name", ""))
    if not pm:
        return
    hinted.append(cid)
    appid, g = pm
    text = (f"Twitch has drops for **{c.get('game_name')}**, which looks like your game **{g['name']}** "
            f"but isn't spelled the same. If it's the same game, open Loot Radar and type "
            f"`{c.get('game_name')}` in the Twitch name box next to {g['name']}.")
    store.log(f"Possible match: Twitch '{c.get('game_name')}' looks like your '{g['name']}'. "
              "Set its Twitch name if it's the same game.", "warn")
    if hook:
        notify.simple(hook, "🤔 Is this your game?", text, notify.ORANGE)


# ------------------------------------------------------------------ other launchers
def scan_pc() -> dict:
    """Add games from Epic, EA, Battle.net, Ubisoft, Xbox, Rockstar, Riot, GOG to the library.
    Games you already have on Steam are skipped. New ones start as Off."""
    import gamescan
    found, errors = gamescan.scan()
    cfg = store.load_config()
    games = cfg.get("games") or {}
    steam_names = {norm(base_title(g["name"])) for k, g in games.items() if k.isdigit()}
    seen = set()
    counts: dict[str, int] = {}
    steam_list = [g["name"] for k, g in games.items() if k.isdigit()]
    for f in found:
        if norm(base_title(f["name"])) in steam_names or any(same_game_suffix(f["name"], n) for n in steam_list):
            continue
        key = f"{f['source']}:{gamescan.slug(f['name'])}"
        if key in seen:
            continue
        seen.add(key)
        old = games.get(key, {})
        games[key] = {
            **old,
            "name": f["name"], "source": f["source"], "installed": f.get("installed", True), "removed": False,
            "playtime_min": max(int(old.get("playtime_min") or 0), int(f.get("playtime_min") or 0)),
            "last_played": old.get("last_played", 0), "mode": old.get("mode", "off"),
            "twitch_name": old.get("twitch_name", ""), "order": old.get("order", 0),
        }
        counts[f["source"]] = counts.get(f["source"], 0) + 1
    # games that were uninstalled: forget them, unless you set them up
    for key in [k for k in games if ":" in k and k.split(":", 1)[0] in gamescan.SOURCES and k not in seen]:
        if games[key].get("mode", "off") == "off":
            del games[key]
        else:
            games[key].update(installed=False, removed=True)
    cfg["games"] = games
    store.save_config(cfg)
    store.patch_state(pc_scanned=int(time.time()))
    total = sum(counts.values())
    detail = ", ".join(f"{gamescan.SOURCES[s]} {n}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    store.log(f"Scanned this PC: {total} games from other launchers" + (f" ({detail})." if detail else "."))
    for e in errors:
        store.log(f"PC scan: {e}", "warn")
    return {"total": total, "by_source": counts}


def library_game(games: dict, twitch_game: str):
    """A game you have (installed from another launcher, or 1h+ on Steam) that matches a
    campaign but isn't set up in Loot Radar yet."""
    m = match_game(games, twitch_game, include_off=True)
    if not m or m[1].get("mode", "off") != "off":
        return None
    appid, g = m
    if appid.startswith("tw:"):
        return None
    if appid.isdigit():
        return m if (g.get("playtime_min") or 0) >= 60 else None
    return m


# ------------------------------------------------------------------ miner sync
# ------------------------------------------------------------------ mining priority
_FAR = "9999"


def _end_key(appid: str, games: dict, relevant: list[dict]) -> tuple:
    """Sort key for 'ending soonest': live campaigns by end time, then upcoming, then games
    with no campaign (by hours played). Campaigns with only sub drops left count as none."""
    camps = [c for c in relevant if c.get("appid") == appid and has_watch_work(c)]
    live = [c.get("ends_at") or _FAR for c in camps if c.get("active")]
    if live:
        return (0, min(live), 0)
    soon = [c.get("starts_at") or _FAR for c in camps if c.get("upcoming")]
    if soon:
        return (1, min(soon), 0)
    return (2, _FAR, -(games.get(appid, {}).get("playtime_min") or 0))


def update_priority(cfg: dict, relevant: list[dict]) -> list[str]:
    """Keep Loot Radar's mining order (cfg["priority"], a list of game keys). The first time,
    or with "keep sorted" on, it's sorted by ending soonest. After that your order stays;
    newly added games slot in by their end time without moving the others."""
    games = cfg.get("games") or {}
    active = [k for k, g in games.items() if g.get("mode", "off") != "off"]
    key = lambda k: _end_key(k, games, relevant)
    if "priority" not in cfg or cfg.get("priority_auto_sort"):
        order = sorted(active, key=key)
    else:
        order = [k for k in cfg["priority"] if k in games and games[k].get("mode", "off") != "off"]
        for k in sorted((k for k in active if k not in order), key=key):
            kk = key(k)
            if kk[0] == 2:  # no campaign yet: goes to the end
                order.append(k)
                continue
            # right after the last game that ends sooner (or at the same time)
            pos = max((i + 1 for i, o in enumerate(order) if key(o) <= kk), default=0)
            order.insert(pos, k)
    if order != cfg.get("priority"):
        cfg["priority"] = order
        fresh = store.load_config()
        fresh["priority"] = order
        store.save_config(fresh)
    return order


def sort_priority_by_end() -> list[str]:
    cfg = store.load_config()
    relevant = store.load_state().get("campaigns") or []
    games = cfg.get("games") or {}
    order = sorted((k for k, g in games.items() if g.get("mode", "off") != "off"),
                   key=lambda k: _end_key(k, games, relevant))
    store.update_config(priority=order)
    store.log("Mining order sorted by ending soonest.")
    return order


def set_priority(order: list[str]) -> list[str]:
    """Save an order from the dashboard (games it didn't mention keep their place at the end)."""
    cfg = store.load_config()
    games = cfg.get("games") or {}
    valid = [k for k in dict.fromkeys(order) if k in games and games[k].get("mode", "off") != "off"]
    rest = [k for k in cfg.get("priority") or [] if k not in valid and k in games
            and games[k].get("mode", "off") != "off"]
    new = valid + rest
    store.update_config(priority=new, priority_auto_sort=False)
    return new


def sync_miner(miner: Miner, cfg: dict, campaigns: list[dict] | None) -> None:
    games = cfg.get("games") or {}
    twitch_names = {}
    live_work, sub_only_live = set(), set()
    for c in campaigns or []:
        m = match_game(games, c.get("game_name", ""))
        if m:
            twitch_names[m[0]] = c["game_name"]
            if c.get("active") and not c.get("expired"):
                if has_watch_work(c):
                    live_work.add(m[0])
                elif any(is_sub_drop(d) and not d.get("is_claimed") for d in c.get("drops") or []):
                    sub_only_live.add(m[0])
    # A game whose only live drops need a paid sub stays off the miner's list (until a drop
    # you can earn by watching shows up), so the miner never sits on it.
    skip = sub_only_live - live_work
    order = cfg.get("priority") or []
    rank = {k: i for i, k in enumerate(order)}
    mined = sorted(
        ((appid, g) for appid, g in games.items() if g.get("mode") == "miner" and appid not in skip),
        key=lambda x: (rank.get(x[0], 10**6), -(x[1].get("playtime_min") or 0)),
    )
    wanted = []
    for appid, g in mined:
        if g.get("twitch_name") or twitch_names.get(appid):
            names = [g.get("twitch_name") or twitch_names[appid]]
        else:
            # No campaign seen yet: give the miner both spellings so a future campaign matches.
            names = [clean_name(g["name"]), base_title(g["name"])]
        for n in names:
            if n and n.lower() not in {w.lower() for w in wanted}:
                wanted.append(n)

    current = miner.settings()
    changes = {}
    # games_to_watch = the miner's manual-order list: it mines them exactly in this order.
    if list(current.get("games_to_watch") or []) != wanted:
        changes["games_to_watch"] = wanted
    if current.get("preferred_games"):
        changes["preferred_games"] = []  # older Loot Radar versions used this list; empty it
    # Only mine the games you picked. Until you've picked any (no Steam, nothing added yet), let
    # the miner mine every drop your linked accounts can get, so a fresh setup isn't idle.
    picked = any(g.get("mode") in ("miner", "muted") for g in games.values())
    if current.get("priority_list_only") is not picked:
        changes["priority_list_only"] = picked
        store.log("Mining only the games you picked." if picked else
                  "No games picked yet, so the miner mines any drop your linked accounts can get. "
                  "Pick games in Library or Browse drops to choose what it mines.")
    if current.get("auto_prioritize"):
        changes["auto_prioritize"] = False  # Loot Radar owns the order now
    hook = cfg.get("discord_webhook", "")
    if cfg.get("sync_miner_webhook") and hook and current.get("discord_webhook_drops") != hook:
        changes["discord_webhook_drops"] = hook  # the miner announces claimed drops itself
    if changes:
        miner.update_settings(changes)
        if "games_to_watch" in changes:
            store.log("Mining order updated: " + (", ".join(wanted) if wanted else
                                                  "(nothing picked)" if not picked else "(nothing to mine right now)"))


# ------------------------------------------------------------------ completed drops
def _note_claims(camp: dict, completed: list, cleared: set) -> None:
    """Add newly claimed drops to the Completed list (unless you've cleared them)."""
    known = {c["id"] for c in completed}
    for d in camp["drops"]:
        if d["claimed"] and d["id"] not in known and d["id"] not in cleared:
            completed.append({
                "id": d["id"], "reward": d["name"], "image": d.get("image", ""),
                "game_name": camp["game_name"], "campaign": camp["name"], "box_art": camp.get("box_art", ""),
                "minutes": d["required"], "ts": int(time.time()),
            })
            known.add(d["id"])


def drop_unclaimed(campaigns: list, completed: list) -> list:
    """Take drops off the Completed list that the miner now says were never claimed.

    The miner can briefly think a drop is claimed (its own minute count ran ahead of Twitch's) and
    only learns the truth when it reloads your progress from Twitch, e.g. 479 of 480 minutes when
    the campaign ended. Returns the removed entries (the list is changed in place)."""
    unclaimed = {d.get("id") for c in campaigns or [] for d in c.get("drops") or []
                 if d.get("id") and d.get("is_claimed") is False}
    gone = [e for e in completed if e.get("id") in unclaimed]
    if gone:
        completed[:] = [e for e in completed if e.get("id") not in unclaimed]
    return gone


def clear_completed(older_than_hours: float = 0) -> int:
    """Hide completed drops (all, or only ones older than N hours). Returns how many."""
    state = store.load_state()
    cutoff = time.time() - older_than_hours * 3600
    keep, gone = [], []
    for c in state.get("completed_drops") or []:
        (gone if c.get("ts", 0) <= cutoff else keep).append(c)
    cleared = list(state.get("cleared_drops") or []) + [c["id"] for c in gone]
    store.patch_state(completed_drops=keep, cleared_drops=cleared[-3000:])
    return len(gone)


# ------------------------------------------------------------------ miner pause while watching
def sync_pause(watcher) -> None:
    """Real watching and the miner share one Twitch account (Twitch only counts one stream at a
    time), so pause the miner while muted mode is actually watching, and resume it afterwards."""
    if watcher is None:
        return
    state = store.load_state()
    we_paused = state.get("miner_paused_by_us", False)
    watching = watcher.status.get("state") == "watching"
    if watching == we_paused:
        return
    cfg = store.load_config()
    miner = Miner(cfg["miner_url"], cfg.get("miner_password", ""))
    try:
        miner.pause() if watching else miner.resume()
    except MinerError:
        return
    store.patch_state(miner_paused_by_us=watching)
    store.log("Paused the drop miner while muted mode watches." if watching else "Resumed the drop miner.")


# ------------------------------------------------------------------ main cycle
def run_cycle(watcher=None, force_news: bool = False) -> None:
    if not _cycle_lock.acquire(blocking=False):
        return  # a check is already running
    try:
        _run_cycle(watcher, force_news)
    finally:
        _cycle_lock.release()


def _run_cycle(watcher, force_news: bool) -> None:
    cfg = store.load_config()
    state = store.load_state()
    games = cfg.get("games") or {}
    hook = cfg.get("discord_webhook", "")
    now = int(time.time())

    # Daily Steam library refresh (picks up new games and playtime)
    if cfg["steam_api_key"] and cfg["steam_id"] and now - state.get("library_updated", 0) > 86400:
        try:
            refresh_library()
            cfg = store.load_config()
            games = cfg["games"]
        except steam.SteamError as exc:
            store.log(f"Steam library refresh failed: {exc}", "warn")

    # 1) Twitch drop campaigns (read from the miner, which is logged in to Twitch as you)
    miner = Miner(cfg["miner_url"], cfg.get("miner_password", ""))
    alerted = list(state.get("alerted_campaigns") or [])
    hinted = list(state.get("hinted_campaigns") or [])
    completed = list(state.get("completed_drops") or [])
    cleared = set(state.get("cleared_drops") or [])
    claimed_before = len(completed)
    relevant, campaigns = [], None
    try:
        campaigns = miner.campaigns()
        miner_status = "ok"
    except MinerError as exc:
        miner_status = str(exc)
    if miner_status != state.get("miner_status"):
        store.log(("Drop miner connected." if miner_status == "ok" else f"Drop miner: {miner_status}"),
                  "info" if miner_status == "ok" else "warn")

    for c in campaigns or []:
        if c.get("expired"):
            continue
        m = match_game(games, c.get("game_name", ""))
        if not m:
            lib = library_game(games, c.get("game_name", "")) if cfg.get("alert_library_drops", True) else None
            cid = c.get("id")
            if lib and cid and cid not in alerted and (c.get("active") or c.get("upcoming")) and not fully_claimed(c):
                alerted.append(cid)
                if hook:
                    notify.send(hook, [notify.campaign_embed(c, "off")])
                store.log(f"Drops for {c.get('game_name')}, a game you have (not set up in Loot Radar yet).")
            elif not lib:
                _hint_possible_match(games, c, hinted, hook)
            continue
        appid, g = m
        progress = [(d.get("current_minutes") or 0, d.get("required_minutes") or 0) for d in c.get("drops") or []]
        relevant.append({
            "id": c.get("id"), "appid": appid, "mode": g["mode"], "game_name": c.get("game_name"),
            "name": c.get("name"), "active": c.get("active"), "upcoming": c.get("upcoming"),
            "starts_at": c.get("starts_at"), "ends_at": c.get("ends_at"), "linked": c.get("linked"),
            "link_url": c.get("link_url"), "claimed_drops": c.get("claimed_drops"),
            "total_drops": c.get("total_drops"), "watched_minutes": sum(p[0] for p in progress),
            "box_art": c.get("game_box_art_url") or "", "subs_only": bool(c.get("subscription_required")),
            "campaign_url": c.get("campaign_url") or "",
            "drops": [
                {"id": d.get("id") or f"{c.get('id')}:{d.get('name')}",
                 "name": ", ".join(b.get("name", "") for b in d.get("benefits") or []) or d.get("name"),
                 "image": next((b.get("image_url") for b in d.get("benefits") or [] if b.get("image_url")), ""),
                 "current": d.get("current_minutes") or 0, "required": d.get("required_minutes") or 0,
                 "claimed": bool(d.get("is_claimed")), "subs": d.get("required_subs") or 0}
                for d in c.get("drops") or []
            ],
        })
        _note_claims(relevant[-1], completed, cleared)
        cid = c.get("id")
        if cid and cid not in alerted and (c.get("active") or c.get("upcoming")):
            alerted.append(cid)
            if fully_claimed(c):
                continue
            if hook and notify.send(hook, [notify.campaign_embed(c, g["mode"])]):
                store.log(f"Discord: new drop campaign for {c.get('game_name')} — {c.get('name')}.")
            elif hook:
                store.log("Discord message failed — check the webhook link in Settings.", "warn")
            else:
                store.log(f"New drop campaign for {c.get('game_name')} (add a Discord webhook to get pinged).")

    # 2) Keep the mining order and the miner's game list in sync with your picks
    if campaigns is not None:
        update_priority(cfg, relevant)
        try:
            sync_miner(miner, cfg, campaigns)
        except MinerError as exc:
            store.log(f"Couldn't update the miner's game list: {exc}", "warn")

    # 3) Muted-stream mode: pick what to watch (manual choice first, then soonest-ending campaign)
    muted_target = state.get("muted_manual") or None
    if not muted_target:
        rank = {k: i for i, k in enumerate(store.load_config().get("priority") or [])}
        candidates = sorted(
            (c for c in relevant
             if c["mode"] == "muted" and c["active"] and c["linked"] and has_watch_work(c)),
            key=lambda c: (rank.get(c.get("appid"), 10**6), c.get("ends_at") or ""),
        )
        muted_target = candidates[0]["game_name"] if candidates else None
    stall = state.get("muted_stall") or {}
    if watcher is not None:
        watcher.want(muted_target)
        # Stall check: if watched minutes don't move for 45 min on this channel, try another one.
        st = watcher.status
        camp = next((c for c in relevant if c["game_name"] == muted_target and c["active"]), None)
        if st.get("state") == "watching" and camp and campaigns is not None:
            key = f"{camp['id']}|{st.get('channel')}"
            if stall.get("key") != key or camp["watched_minutes"] > stall.get("minutes", -1):
                stall = {"key": key, "minutes": camp["watched_minutes"], "since": now}
            elif now - stall.get("since", now) > 2700:
                watcher.skip_channel()
                stall = {}
        else:
            stall = {}

    # 4) Official Steam news for watched games
    seen_news = dict(state.get("seen_news") or {})
    news_due = now - state.get("last_news_check", 0) > cfg.get("news_check_hours", 3) * 3600
    if cfg.get("news_mode", "announcements") != "off" and (force_news or news_due):
        for appid, g in games.items():
            if g.get("mode", "off") == "off" or not appid.isdigit():
                continue  # Steam only has news for Steam games (not Twitch-only or other stores)
            try:
                items = steam.news(appid)
            except steam.SteamError as exc:
                store.log(f"News check failed for {g['name']}: {exc}", "warn")
                continue
            seen = seen_news.get(appid)
            if seen is None:  # first time: remember what's there, don't spam old posts
                seen_news[appid] = [i["gid"] for i in items]
                continue
            new = [i for i in items if i["gid"] not in seen][:3]
            for item in reversed(new):
                important = steam.looks_important(item)
                if cfg.get("news_mode") == "important" and not important:
                    continue
                if hook and notify.send(hook, [notify.news_embed(g["name"], appid, item, important)]):
                    store.log(f"Discord: {g['name']} news — {item['title']}")
                else:
                    store.log(f"{g['name']} news: {item['title']}")
            seen_news[appid] = ([i["gid"] for i in new] + seen)[:60]
        store.patch_state(last_news_check=now)

    if campaigns is not None:
        newly = len(completed) - claimed_before
        # Also checks expired campaigns: that's where a drop that just missed out shows up.
        wrong = drop_unclaimed(campaigns, completed)
        for e in wrong:
            store.log(f"{e.get('reward')} ({e.get('game_name')}) wasn't actually claimed: Twitch shows it unfinished. "
                      "Took it off Completed drops.", "warn")
        extra = {"completed_drops": completed[-300:]}
        if newly or wrong:
            extra["claimed_total"] = max(0, int(state.get("claimed_total") or 0) + newly - len(wrong))
        store.patch_state(**extra)
    else:
        relevant = state.get("campaigns") or []  # miner offline: keep showing the last known list

    store.patch_state(
        campaigns=relevant, miner_status=miner_status, alerted_campaigns=alerted[-500:],
        hinted_campaigns=hinted[-500:],
        seen_news=seen_news, muted_stall=stall, last_check=now,
    )
