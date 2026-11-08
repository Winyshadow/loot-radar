"""Steam Web API helpers: resolve your profile, list owned games, read official news."""

from __future__ import annotations

import html
import re

import requests

API = "https://api.steampowered.com"
TIMEOUT = 20


class SteamError(Exception):
    pass


def _get(path: str, params: dict) -> dict:
    try:
        r = requests.get(f"{API}/{path}", params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SteamError(f"Couldn't reach Steam ({exc.__class__.__name__}).") from exc
    if r.status_code in (401, 403):
        raise SteamError("Steam rejected the API key. Double-check it on steamcommunity.com/dev/apikey.")
    if r.status_code != 200:
        raise SteamError(f"Steam answered with HTTP {r.status_code}.")
    try:
        return r.json()
    except ValueError as exc:
        raise SteamError("Steam sent back something unexpected.") from exc


def resolve_steam_id(api_key: str, text: str) -> str:
    """Accepts a SteamID64, a profile URL (/profiles/... or /id/...), or a custom URL name."""
    text = (text or "").strip().rstrip("/")
    if not text:
        raise SteamError("Paste your Steam profile link first.")
    m = re.search(r"(7656\d{13})", text)
    if m:
        return m.group(1)
    m = re.search(r"steamcommunity\.com/id/([^/?#]+)", text)
    vanity = m.group(1) if m else text
    data = _get("ISteamUser/ResolveVanityURL/v1/", {"key": api_key, "vanityurl": vanity})
    resp = data.get("response", {})
    if resp.get("success") == 1 and resp.get("steamid"):
        return resp["steamid"]
    raise SteamError(f"Couldn't find a Steam profile called '{vanity}'.")


def owned_games(api_key: str, steam_id: str) -> list[dict]:
    data = _get(
        "IPlayerService/GetOwnedGames/v1/",
        {
            "key": api_key,
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        },
    )
    games = data.get("response", {}).get("games")
    if games is None:
        raise SteamError(
            "Steam returned no games. Your profile's 'Game details' is probably set to private: "
            "Steam > your profile > Edit Profile > Privacy Settings > Game details > Public."
        )
    return [
        {
            "appid": str(g["appid"]),
            "name": g.get("name") or f"App {g['appid']}",
            "playtime_min": int(g.get("playtime_forever") or 0),
            "last_played": int(g.get("rtime_last_played") or 0),
        }
        for g in games
    ]


_BBCODE = re.compile(r"\[/?[a-z0-9*]+(?:=[^\]]*)?\]", re.I)
_STEAM_TOKENS = re.compile(r"\{STEAM_[A-Z_]+\}\S*")
_TAGS = re.compile(r"<[^>]+>")


def clean_text(text: str, limit: int = 300) -> str:
    text = _STEAM_TOKENS.sub("", text or "")
    text = _BBCODE.sub("", text)
    text = _TAGS.sub("", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def news(appid: str, count: int = 6) -> list[dict]:
    """Official announcements only (patch notes, events, new leagues) — no third-party press."""
    data = _get(
        "ISteamNews/GetNewsForApp/v2/",
        {
            "appid": appid,
            "count": count,
            "maxlength": 600,
            "feeds": "steam_community_announcements",
            "format": "json",
        },
    )
    items = data.get("appnews", {}).get("newsitems") or []
    return [
        {
            "gid": str(i.get("gid")),
            "title": i.get("title") or "(untitled)",
            "url": i.get("url") or f"https://store.steampowered.com/news/app/{appid}",
            "summary": clean_text(i.get("contents", "")),
            "date": int(i.get("date") or 0),
        }
        for i in items
    ]


IMPORTANT_WORDS = re.compile(
    r"\b(drops?|twitch|free|giveaway|event|league|season|launch|release|reward|cosmetic|"
    r"skins?|login|log in|claim|bonus|anniversary|festival|expansion)\b",
    re.I,
)


def looks_important(item: dict) -> bool:
    return bool(IMPORTANT_WORDS.search(item["title"]) or IMPORTANT_WORDS.search(item["summary"][:200]))


def header_image(appid: str) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
