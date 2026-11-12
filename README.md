# Loot Radar

Never miss a Twitch drop for the games you actually play.

*Made by **solitary_samurai**.*

Loot Radar reads your Steam library and the games installed from your other launchers, watches the games you pick for Twitch drop campaigns and official Steam news, pings your Discord, and collects the drops for you in the background.

![Loot Radar overview](docs/screenshot.png)

## What it does

| Feature | Details |
|---|---|
| Game library | Your Steam library (with hours played) plus games installed with Epic, EA app, Battle.net, Ubisoft Connect, Xbox, Rockstar, Riot and GOG (no logins needed). Set each game to **Off**, **Alerts**, **Auto-mine** or **Muted** |
| Any Twitch drop | **Browse drops** lists every campaign on Twitch, so you can add events and games that aren't on Steam (e.g. ExileCon) |
| Discord alerts | New drop campaigns (rewards, watch time, end date, account-link warning) and official Steam announcements |
| Auto-mine | Collects drops in the background with the built-in drop miner |
| Muted mode | Opens a real live stream, muted and at the lowest quality, in its own window of your default browser (Brave, Chrome, Edge or Vivaldi; otherwise Edge), and switches channel when it ends |
| Overview | Totals, the drop being mined right now with a live countdown, the channel and your channel points, collapsible running drops per game (with why a game isn't mining yet, like "only counts on these channels, both offline", and a Twitch button for each campaign), and a completed-drops list you can clear |
| System tray | Runs quietly next to the clock: double-click the icon to open the dashboard, right-click to restart or quit |
| Start with Windows | Optional tick box in Settings → Preferences: Loot Radar starts in the tray when you sign in |
| Game deals | Optional (Settings → Game deals): watches your Steam wishlist for Steam sales and, with a free GG.deals key, the cheapest key-shop price (with an estimate in your own currency at the latest exchange rate, and a reminder to check DRM, region and account/key); pings Discord on big Steam discounts and key-shop all-time lows |
| Phone access | Optional (Settings → Phone access): scan a QR code to see your drops on your phone, on home Wi-Fi or anywhere with Tailscale. PIN-protected; the phone never sees your keys or passwords |
| Updates | Checks GitHub every 6 hours for new versions of Loot Radar and the miner; one click to update |
| Memory guard | Restarts the miner if it ever uses too much memory |

## Install (Windows 10 or 11)

1. Download **LootRadarSetup.exe** from the [latest release](https://github.com/Winyshadow/loot-radar/releases/latest).
2. Open it. Windows may say *"Windows protected your PC"* because the installer isn't code-signed: click **More info → Run anyway**.
3. Click through the installer (no admin rights needed). Loot Radar opens in its own window, and the setup guide walks you through the rest.

Loot Radar then lives in the Start menu and in the system tray (the ^ icons next to the clock). Closing its window keeps it running in the tray; double-click the tray icon to open it again. Uninstall it like any app (Settings → Apps); it asks whether to keep your settings.

<details><summary>Other way: the zip with START.bat (needs no installer)</summary>

1. Click the green **Code** button on this page and choose **Download ZIP**.
2. Right-click the zip → **Extract All**, and put the folder somewhere permanent (e.g. `Documents\Loot Radar`).
3. Double-click **START.bat**. The first start installs everything it needs (including Python, if you don't have it) and opens the dashboard in your browser at <http://127.0.0.1:5577>. Double-click the tray icon, or START.bat again, to reopen it.
4. Optional: double-click **Create Desktop Shortcut.bat** for a desktop icon.

Already using the zip? **Settings → Updates → Switch to the installer version** moves you over, with your settings and the miner.
</details>

## Set up (about 10 minutes, once)

The first time Loot Radar starts, a **setup guide** walks you through these steps one at a time (skip the optional ones). You can run it again from **Settings → Setup**, or do it all yourself in **Settings**:

| Step | What to do |
|---|---|
| 1. Steam | Get a key at [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) (domain: `localhost`, click Register **once**, then approve the request in the Steam app on your phone under 🔔 notifications), paste it with your profile link. Your Steam profile's **Game details** must be **Public** |
| 2. Discord | In your server: channel ⚙️ → **Integrations → Webhooks → New Webhook → Copy Webhook URL**. Paste it and press **Send test** |
| 3. Drop miner | Press **Install miner**, then **Log the miner in to Twitch** and sign in |
| 4. Link games | Link your game accounts at [twitch.tv/drops/campaigns](https://www.twitch.tv/drops/campaigns), or drops never arrive |

Then go to **Library** or **Browse drops** and pick your games.

## Updating

Loot Radar tells you (on the dashboard and in Discord) when there's a new version of itself or of the miner. Press the button in **Settings → Updates** and it updates and restarts by itself. Your settings are kept.

## Good to know

- Right-click the tray icon → **Quit Loot Radar** to stop it (or **Quit Loot Radar and the miner**). **Show log** opens its log file.
- Something wrong? Tray icon → **Show log**. (Zip copy: run `START.bat console` from a command prompt to see the log live.)
- Prefer your browser over Loot Radar's own window? Settings → Preferences → **Open the dashboard in my browser instead**.
- Everything personal (Steam key, Discord webhook, Twitch sign-in) stays on your PC: in `%LOCALAPPDATA%\Loot Radar` (zip copy: `app\data`) and `%APPDATA%\TwitchDropsMiner`. It's never uploaded.
- Auto-mine uses [Twitch Drops Miner](https://github.com/SimpliAj/twitchdropsminer), which earns watch time without playing the video. That goes against Twitch's rules on cheating rewards, so there's some risk to the Twitch account you use with it. Muted mode really watches the stream.

## Credits

The drop miner is [Twitch Drops Miner](https://github.com/SimpliAj/twitchdropsminer) by SimpliAj, based on DevilXD's TwitchDropsMiner, used under the MIT licence. Loot Radar downloads it from its official GitHub releases; it isn't included in this repository.

## Licence

Loot Radar © 2026 solitary_samurai. All rights reserved. It's free to download and use for your own personal use; copying, changing, re-uploading or selling its code or artwork needs written permission. See [LICENSE](LICENSE). Want a friend to have it? Send them the link to this page.

## For maintainers: publishing an update

1. Make your changes.
2. Raise the number in `VERSION`: fixes and small tweaks `1.0.0` → `1.0.1`, a new feature → `1.1.0`, a big overhaul → `2.0.0`.
3. Add what changed to the top of `CHANGELOG.md`.
4. Commit and push to `main`, then publish a GitHub Release tagged `1.0.1`. Publishing it starts the **Build installer** workflow (`.github/workflows/release.yml`), which builds `LootRadarSetup.exe` and attaches it to the release a few minutes later.

Installed copies update once the release has its setup file; zip copies update from `main`. Everyone's Loot Radar checks every 6 hours. To build the installer on your own PC: `build\build.ps1` (see the top of that file). The update source is set by `UPDATE_REPO` at the top of `app/updates.py`. See [CHANGELOG.md](CHANGELOG.md) for the version history.
