# Changelog

All notable changes to Loot Radar. Versions follow `MAJOR.MINOR.PATCH`:

- **Patch** (1.0.0 → 1.0.1): fixes and small tweaks. Most updates.
- **Minor** (1.0.x → 1.1.0): a new feature.
- **Major** (1.x → 2.0.0): a big overhaul.

## 1.0.1 (2026-11-09)

- Fixed first-time setup failing on PCs that only have Python 3.15 ("Failed building wheel for aiohttp" / "Microsoft Visual C++ 14.0 or greater is required"). START.bat now uses Python 3.10 to 3.14 and, if none is installed, offers to install Python 3.12 next to your other Python.
- If an earlier setup was built with a Python that's too new, START.bat rebuilds it automatically.

## 1.0.0 (2026-11-08)

First public release.

- Steam library with hours played, plus a PC scan for games installed with Epic, EA app, Battle.net, Ubisoft Connect, Xbox, Rockstar, Riot and GOG (no logins).
- Browse every Twitch drop campaign and add any game, Steam or not.
- Discord alerts for new drop campaigns, official Steam news, and drops for games you have but haven't set up.
- Built-in drop miner (Twitch Drops Miner), installed and updated from its official GitHub with one click; Twitch sign-in handled by Loot Radar.
- Muted-stream mode that really watches a live drops stream, muted and at the lowest quality.
- Overview with totals, a live "Now mining" card (countdown, channel, channel points), collapsible running drops and a clearable completed-drops list.
- Mining order: sorted by ending soonest at first, then drag or use arrows to reorder; "Sort by ending soonest" and "Keep sorted" options.
- Memory guard for the miner, system tray icon (no console window), and one-click self-updates from GitHub.
