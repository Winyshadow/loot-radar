"""Why a running drop isn't being mined right now, so the Overview can say it in plain words.

The miner already skips a game with no live stream and mines the next one that has one, and Twitch
tells it the moment a channel goes live. What it doesn't say is *why* a game is waiting. Common
reasons: the campaign only counts on a few channels (often the game's own) and they're all offline,
or nobody is streaming the game with drops on.

reasons() returns {game name: {"code": ..., ...}} for running games that aren't being mined:
  offline     the campaign only counts on certain channels and all of them are offline
              ("channels": [{"name", "login"}], "last_live": ISO time or None)
  no_streams  nobody is streaming the game with drops on
  queued      it has live streams, but the miner (or muted mode) is busy with "behind"
  starting    it has live streams and the miner is free: it should start within minutes
  paused      the miner is paused
The dashboard turns these into sentences.
"""
import time

import requests

from checks import has_watch_work, norm
from watcher import CLIENT_ID, GQL_URL, drops_streams

USER_SECONDS = 1800    # which game a channel streams barely changes; look it up every 30 min
STREAMS_SECONDS = 300  # live drops streams for a game, from Twitch's directory
_users: dict[str, tuple[float, dict]] = {}
_live: dict[str, tuple[float, int]] = {}

USERS_QUERY = ("query($ids: [ID!]) { users(ids: $ids) { id login displayName "
               "stream { id game { displayName } } lastBroadcast { game { displayName } startedAt } } }")


def channel_info(ids: list[str]) -> dict[str, dict]:
    """Login, display name, game (live game, else the game it last streamed) and last time live,
    for Twitch channel ids. Works while the channel is offline. Cached; network trouble is skipped."""
    now = time.time()
    need = [i for i in ids if i not in _users or now - _users[i][0] > USER_SECONDS]
    for k in range(0, len(need), 50):
        try:
            r = requests.post(GQL_URL, json={"query": USERS_QUERY, "variables": {"ids": need[k:k + 50]}},
                              headers={"Client-Id": CLIENT_ID}, timeout=8)
            users = ((r.json() or {}).get("data") or {}).get("users") or []
        except Exception:
            continue
        for u in users:
            if not u or not u.get("id"):
                continue
            last = u.get("lastBroadcast") or {}
            live_game = ((u.get("stream") or {}).get("game") or {}).get("displayName")
            _users[str(u["id"])] = (now, {
                "login": u.get("login") or "", "name": u.get("displayName") or u.get("login") or "",
                "game": live_game or (last.get("game") or {}).get("displayName") or "",
                "last_live": last.get("startedAt")})
    return {i: _users[i][1] for i in ids if i in _users}


def live_count(game: str) -> int:
    """How many channels stream this game with drops on right now (cached 5 min)."""
    key = norm(game)
    hit = _live.get(key)
    if not hit or time.time() - hit[0] > STREAMS_SECONDS:
        try:
            hit = _live[key] = (time.time(), len(drops_streams(game, 10)))
        except Exception:
            return hit[1] if hit else 0
    return hit[1]


def _game_of(ch: dict) -> str:
    g = ch.get("game")
    return (g.get("name") or g.get("displayName") or "") if isinstance(g, dict) else (g or "")


def reasons(status: dict, channels: list[dict], campaigns: list[dict], muted: dict | None = None,
            info=channel_info, live=live_count) -> dict[str, dict]:
    games: dict[str, list] = {}
    for c in campaigns or []:
        if c.get("active") and c.get("linked") and c.get("mode") in ("miner", "muted") and has_watch_work(c):
            games.setdefault(c.get("game_name") or "", []).append(c)
    games.pop("", None)
    if not games:
        return {}
    mu = muted or {}
    current = (status.get("current_drop") or {}).get("game_name") or ""
    muted_game = mu.get("game") if mu.get("state") == "watching" else ""
    busy = current or muted_game or ""
    skip = {norm(x) for x in (current, muted_game) if x}

    # Channel-restricted campaigns: the miner lists their channels (marked acl_based), but an offline
    # channel has no game, so ask Twitch which game each one streams.
    acl = [c for c in channels or [] if c.get("acl_based") and c.get("id") is not None]
    meta = info([str(c["id"]) for c in acl]) if acl else {}

    out = {}
    for game in games:
        g = norm(game)
        if g in skip:
            continue
        mine = []
        for c in acl:
            m = meta.get(str(c["id"])) or {}
            if norm((_game_of(c) if c.get("online") else "") or m.get("game", "")) == g:
                mine.append((c, m))
        live_here = [c for c in channels or [] if c.get("online") and c.get("drops_enabled") and norm(_game_of(c)) == g]
        if status.get("paused"):
            out[game] = {"code": "paused"}
        elif live_here or (not mine and live(game)):
            out[game] = {"code": "queued", "behind": busy} if busy else {"code": "starting"}
        elif mine:
            out[game] = {"code": "offline",
                         "channels": [{"name": m.get("name") or c.get("name") or "",
                                       "login": m.get("login") or (c.get("name") or "").lower()} for c, m in mine],
                         "last_live": max((m.get("last_live") or "" for _, m in mine), default="") or None}
        else:
            out[game] = {"code": "no_streams"}
    return out
