"""Discord webhook notifications."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

PURPLE = 0x9146FF   # Twitch purple — drop campaigns
BLUE = 0x1B9AF7     # Steam blue — news
GREEN = 0x3BA55D
ORANGE = 0xF0A020


def send(webhook: str, embeds: list[dict], content: str = "") -> bool:
    """Post to a Discord webhook. Returns True on success. Retries once if rate-limited."""
    if not webhook:
        return False
    payload = {"username": "Loot Radar", "embeds": embeds[:10]}
    if content:
        payload["content"] = content
    for _ in range(3):
        try:
            r = requests.post(webhook, json=payload, timeout=15)
        except requests.RequestException:
            return False
        if r.status_code == 429:
            try:
                wait = float(r.json().get("retry_after", 2))
            except ValueError:
                wait = 2.0
            time.sleep(min(wait, 30))
            continue
        return r.status_code in (200, 204)
    return False


def _ts(iso: str) -> str:
    """ISO time -> Discord timestamp that shows in the reader's own timezone."""
    try:
        return f"<t:{int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp())}:f>"
    except (ValueError, AttributeError):
        return iso or "?"


def _rel(iso: str) -> str:
    try:
        return f"<t:{int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp())}:R>"
    except (ValueError, AttributeError):
        return ""


MODE_TEXT = {
    "off": "🎮 You have this game, but it isn't set up in Loot Radar. Open Loot Radar → Browse drops and pick Auto-mine to collect it.",
    "alerts": "🔔 Alerts only — watch it yourself if you want it.",
    "miner": "🤖 Auto-mining is on — the miner will collect this for you.",
    "muted": "🔇 Muted-stream mode — Loot Radar will open a muted live stream for you.",
}


def campaign_embed(c: dict, mode: str) -> dict:
    drops = c.get("drops") or []
    lines = []
    for d in drops[:8]:
        rewards = ", ".join(b.get("name", "") for b in (d.get("benefits") or []) if b.get("name"))
        mins = int(d.get("required_minutes") or 0)
        when = f"{mins // 60}h{mins % 60:02d}m" if mins >= 60 else f"{mins}m"
        lines.append(f"• **{rewards or d.get('name', 'Drop')}** — watch {when}")
    if len(drops) > 8:
        lines.append(f"…and {len(drops) - 8} more")

    status = "Starts " + _rel(c.get("starts_at", "")) if c.get("upcoming") else "Live now"
    fields = [
        {"name": "When", "value": f"{status}\nEnds {_ts(c.get('ends_at', ''))} ({_rel(c.get('ends_at', ''))})", "inline": False},
        {"name": "What you do", "value": MODE_TEXT.get(mode, ""), "inline": False},
    ]
    if not c.get("linked"):
        link = c.get("link_url") or "https://www.twitch.tv/drops/campaigns"
        fields.insert(0, {
            "name": "⚠️ Account not linked",
            "value": f"Link your game account to Twitch first or the drop won't arrive: [link it here]({link})",
            "inline": False,
        })
    embed = {
        "title": f"🎁 Twitch drops: {c.get('game_name', '?')}",
        "description": f"**{c.get('name', '')}**\n" + ("\n".join(lines) if lines else ""),
        "url": "https://www.twitch.tv/drops/campaigns",
        "color": PURPLE,
        "fields": fields,
    }
    if c.get("game_box_art_url"):
        embed["thumbnail"] = {"url": c["game_box_art_url"]}
    return embed


def news_embed(game_name: str, appid: str, item: dict, important: bool) -> dict:
    embed = {
        "title": ("⭐ " if important else "📰 ") + item["title"][:240],
        "url": item["url"],
        "description": item["summary"],
        "color": ORANGE if important else BLUE,
        "author": {"name": game_name},
        "thumbnail": {"url": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_184x69.jpg"},
    }
    if item.get("date"):
        embed["timestamp"] = datetime.fromtimestamp(item["date"], timezone.utc).isoformat()
    return embed


def simple(webhook: str, title: str, text: str, color: int = GREEN) -> bool:
    return send(webhook, [{"title": title, "description": text, "color": color}])
