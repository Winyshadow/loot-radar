# Changelog

All notable changes to Loot Radar. Versions follow `MAJOR.MINOR.PATCH`:

- **Patch** (1.0.0 → 1.0.1): fixes and small tweaks. Most updates.
- **Minor** (1.0.x → 1.1.0): a new feature.
- **Major** (1.x → 2.0.0): a big overhaul.

## 1.3.0 (2026-11-09)

- New: **Streamers** button on every sub-only drop. It lists the channels streaming that game live with drops on, most viewers first, with their stream title. Each one has **Watch** and **Subscribe** links (Subscribe opens Twitch's subscribe page for that streamer), so you can pick who to sub to for the drop.
- Shows the top 12 streamers, with "Show all" for the rest. There are also links to the drop's campaign page on Twitch (which lists the channels taking part) and to all of the game's streams.

## 1.2.0 (2026-11-09)

- Drops that need a paid sub to a streamer no longer hold up the mining queue. Watching never earns them, so they're left out of the mining order, "Sort by ending soonest", muted mode and the miner's game list. A game whose only live drops need a sub comes off the miner's list until it has a drop you can earn by watching.
- New **Sub-only drops** panel on the Overview, under Running drops. It lists every sub drop for your games, how many subs it needs and when it ends, so you can still see them.
- Running drops now shows only drops you can earn by watching. A campaign that mixes both (like Legion TD 2) shows its watch drops there and notes how many sub drops it has.
- Browse drops marks campaigns where every drop needs a sub with a "Sub only" tag.

## 1.1.0 (2026-11-09)

- New: **Start Loot Radar when I sign in to Windows** tick box (Settings → Preferences). Loot Radar then starts quietly in the system tray when you sign in, without opening the dashboard. It's saved as soon as you tick it, needs no admin rights, and shows up in Windows' Startup apps list as "Loot Radar".
- If you switch it off in Windows' Startup apps list, the tick box shows that. Ticking it again in Loot Radar switches it back on.
- If you move the Loot Radar folder, the startup entry follows it the next time Loot Radar starts.

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
