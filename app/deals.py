"""Deals: watches your Steam wishlist (plus games you add by hand) for discounts.

Every 6 hours (or when you press "Check deals now") it:
  * reads your Steam wishlist (IWishlistService, needs no key; the wishlist must be visible),
  * asks the Steam store for each game's price in your own currency,
  * asks GG.deals (official Prices API, free for hobby use, "Prices by GG.deals" credit required)
    for the cheapest key shop and its all-time low (GG.deals also sends the cheapest official
    store; it's kept in the data but not shown or pinged, since Steam's own price covers that),
  * and pings Discord when a game is at least N% off on Steam, or the key-shop price has just
    dropped to its lowest ever. The same deal is never pinged twice; a further drop pings again.

Prices are shown in each source's own currency. GG.deals has no South Africa region, so its prices
also get an estimate in your currency (your Steam currency, or the one picked in Settings), using the
latest exchange rate (ExchangeRate-API, no key needed; the European Central Bank's rates via
Frankfurter as a backup), refreshed every 6 hours.
"""

from __future__ import annotations

import re
import threading
import time

import requests

import notify
import store

STEAM_API = "https://api.steampowered.com"
STORE = "https://store.steampowered.com"
GG_API = "https://api.gg.deals/v1/prices/by-steam-app-id/"
CHECK_SECONDS = 6 * 3600
TIMEOUT = 25
HEADERS = {"User-Agent": "LootRadar (desktop app; deals check)"}
REGIONS = ("us", "eu", "gb", "au", "ca", "br", "pl", "de", "fr", "nl", "se", "dk", "no", "ch")

_lock = threading.Lock()


class DealsError(Exception):
    pass


# ------------------------------------------------------------------ sources
def wishlist(steam_id: str) -> list[int]:
    """App IDs on your Steam wishlist, highest priority first. Empty if it's empty or hidden."""
    try:
        r = requests.get(f"{STEAM_API}/IWishlistService/GetWishlist/v1/", params={"steamid": steam_id},
                         headers=HEADERS, timeout=TIMEOUT)
        items = (r.json().get("response") or {}).get("items") or []
    except (requests.RequestException, ValueError) as exc:
        raise DealsError(f"Couldn't read your Steam wishlist ({exc.__class__.__name__}).") from exc
    items.sort(key=lambda i: (i.get("priority") or 0) or 10**6)
    return [int(i["appid"]) for i in items if i.get("appid")]


def steam_prices(appids: list[int]) -> dict[int, dict]:
    """Steam store price per game, in your currency. Free or unlisted games come back without a price."""
    out: dict[int, dict] = {}
    for i in range(0, len(appids), 50):
        chunk = appids[i:i + 50]
        try:
            r = requests.get(f"{STORE}/api/appdetails", params={"appids": ",".join(map(str, chunk)),
                             "filters": "price_overview"}, headers=HEADERS, timeout=TIMEOUT)
            data = r.json() or {}
        except (requests.RequestException, ValueError) as exc:
            raise DealsError(f"Couldn't get prices from Steam ({exc.__class__.__name__}).") from exc
        for k, v in data.items():
            d = (v or {}).get("data") if (v or {}).get("success") else None
            po = d.get("price_overview") if isinstance(d, dict) else None
            if not po:  # free, not released yet, or not sold here (the name lookup says which)
                out[int(k)] = {"price": None}
                continue
            out[int(k)] = {
                "price": po.get("final", 0) / 100, "initial": po.get("initial", 0) / 100,
                "discount": int(po.get("discount_percent") or 0), "currency": po.get("currency", ""),
                "text": po.get("final_formatted") or "", "initial_text": po.get("initial_formatted") or "",
            }
        time.sleep(0.4)  # be gentle with the store API
    return out


def steam_basics(appid: int) -> dict:
    """Name and cover picture for one game (looked up once, then cached)."""
    try:
        r = requests.get(f"{STORE}/api/appdetails", params={"appids": appid, "filters": "basic"},
                         headers=HEADERS, timeout=TIMEOUT)
        d = (r.json() or {}).get(str(appid)) or {}
        data = d.get("data") if d.get("success") else None
    except (requests.RequestException, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {"name": data.get("name") or "", "image": data.get("header_image") or "", "free": bool(data.get("is_free"))}


# Steam's bulk lookup needs a country; we take it from the currency Steam shows your prices in.
CURRENCY_COUNTRY = {"ZAR": "ZA", "USD": "US", "EUR": "DE", "GBP": "GB", "AUD": "AU", "CAD": "CA", "NZD": "NZ",
                    "BRL": "BR", "PLN": "PL", "INR": "IN", "JPY": "JP", "CNY": "CN", "KRW": "KR", "RUB": "RU",
                    "TRY": "TR", "MXN": "MX", "CHF": "CH", "NOK": "NO", "SEK": "SE", "DKK": "DK", "SGD": "SG",
                    "HKD": "HK", "TWD": "TW", "PHP": "PH", "IDR": "ID", "MYR": "MY", "THB": "TH", "VND": "VN",
                    "UAH": "UA", "KZT": "KZ", "CLP": "CL", "PEN": "PE", "COP": "CO", "UYU": "UY", "ILS": "IL",
                    "SAR": "SA", "AED": "AE", "QAR": "QA", "KWD": "KW", "CRC": "CR"}


def steam_basics_bulk(api_key: str, appids: list[int], country: str = "US") -> dict[int, dict]:
    """Names, cover pictures, free / coming-soon for many games at once (needs your Steam API key)."""
    import json as _json
    out: dict[int, dict] = {}
    for i in range(0, len(appids), 100):
        req = {"ids": [{"appid": a} for a in appids[i:i + 100]], "context": {"language": "english", "country_code": country},
               "data_request": {"include_assets": True, "include_release": True}}
        try:
            r = requests.get(f"{STEAM_API}/IStoreBrowseService/GetItems/v1/",
                             params={"key": api_key, "input_json": _json.dumps(req)}, headers=HEADERS, timeout=TIMEOUT)
            items = (r.json().get("response") or {}).get("store_items") or []
        except (requests.RequestException, ValueError):
            break
        for it in items:
            if not it.get("appid") or not it.get("name"):
                continue
            a = it.get("assets") or {}
            fmt, header = a.get("asset_url_format") or "", a.get("header") or ""
            img = ("https://shared.akamai.steamstatic.com/store_item_assets/" + fmt.replace("${FILENAME}", header)) if fmt and header else ""
            out[int(it["appid"])] = {"name": it["name"], "image": img, "free": bool(it.get("is_free")),
                                     "soon": bool((it.get("release") or {}).get("is_coming_soon"))}
    return out


def _num(v):
    try:
        return round(float(v), 2) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def ggdeals_prices(key: str, appids: list[int], region: str = "") -> dict[int, dict]:
    """Cheapest official store and key shop (now and all-time low) per game, from GG.deals."""
    out: dict[int, dict] = {}
    for i in range(0, len(appids), 100):
        chunk = appids[i:i + 100]
        params = {"ids": ",".join(map(str, chunk)), "key": key}
        if region:
            params["region"] = region
        try:
            r = requests.get(GG_API, params=params, headers=HEADERS, timeout=TIMEOUT)
            j = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise DealsError(f"Couldn't reach GG.deals ({exc.__class__.__name__}).") from exc
        if r.status_code != 200 or j.get("success") is False:
            data = j.get("data") if isinstance(j.get("data"), dict) else {}
            msg = data.get("message") or j.get("message") or f"HTTP {r.status_code}"
            if r.status_code in (401, 403):
                msg = "GG.deals didn't accept the API key. Check it in Settings → Deals."
            raise DealsError(f"GG.deals: {msg}")
        for k, v in (j.get("data") or {}).items():
            if not isinstance(v, dict):
                continue
            p = v.get("prices") if isinstance(v.get("prices"), dict) else v
            row = {
                "title": v.get("title") or "", "url": v.get("url") or "", "currency": p.get("currency") or "",
                "retail": _num(p.get("currentRetail")), "keyshop": _num(p.get("currentKeyshops")),
                "low_retail": _num(p.get("historicalRetail")), "low_keyshop": _num(p.get("historicalKeyshops")),
            }
            if row["retail"] == 0:  # free game: GG.deals' other numbers for it aren't meaningful
                row.update(retail=None, keyshop=None, low_retail=None, low_keyshop=None)
            out[int(k)] = row
        time.sleep(1)
    return out


# ------------------------------------------------------------------ currency estimates
FX_SECONDS = 6 * 3600
FX_SYMBOLS = {"ZAR": "R", "USD": "$", "EUR": "€", "GBP": "£", "AUD": "A$", "CAD": "C$", "NZD": "NZ$", "INR": "₹",
              "JPY": "¥", "BRL": "R$", "PLN": "zł", "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr"}


def _fetch_rates(base: str) -> dict | None:
    """Today's rates from `base` to every other currency, or None if both sources are down."""
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{base}", headers=HEADERS, timeout=12)
        j = r.json()
        if j.get("result") == "success" and isinstance(j.get("rates"), dict):
            when = j.get("time_last_update_unix") or time.time()
            return {"rates": j["rates"], "date": time.strftime("%Y-%m-%d", time.gmtime(when)),
                    "source": "Exchange Rate API", "source_url": "https://www.exchangerate-api.com"}
    except (requests.RequestException, ValueError):
        pass
    try:  # backup: the European Central Bank's daily rates (fewer currencies, but includes ZAR)
        r = requests.get("https://api.frankfurter.dev/v1/latest", params={"base": base}, headers=HEADERS, timeout=12)
        j = r.json()
        if isinstance(j.get("rates"), dict) and j["rates"]:
            return {"rates": j["rates"], "date": j.get("date") or "",
                    "source": "European Central Bank (Frankfurter)", "source_url": "https://frankfurter.dev"}
    except (requests.RequestException, ValueError):
        pass
    return None


def fx_rates(base: str) -> dict | None:
    """Latest rates from `base`, fetched at most every 6 hours (older saved rates if offline)."""
    base = (base or "").upper()
    if not base:
        return None
    saved = (store.load_state().get("fx") or {}).get(base)
    if saved and time.time() - (saved.get("at") or 0) < FX_SECONDS:
        return saved
    fresh = _fetch_rates(base)
    if not fresh:
        return saved
    fresh["at"] = int(time.time())
    fx = dict(store.load_state().get("fx") or {})
    fx[base] = fresh
    store.patch_state(fx=fx)
    return fresh


def target_currency(cfg: dict, steam_currency: str) -> str:
    """The currency to estimate in: the one picked in Settings, else your Steam currency. "" = none."""
    pick = (cfg.get("deals_currency") or "").upper()
    if pick == "NONE":
        return ""
    return pick or (steam_currency or "").upper()


def fx_for(block: dict, cfg: dict) -> dict | None:
    """How to turn GG.deals prices in this deals block into estimates (None = no estimate needed)."""
    rows = block.get("rows") or []
    steam_cur = next(((r.get("steam") or {}).get("currency") for r in rows if (r.get("steam") or {}).get("currency")), "")
    gg_cur = next(((r.get("gg") or {}).get("currency") for r in rows if (r.get("gg") or {}).get("currency")), "")
    to = target_currency(cfg, steam_cur)
    if not gg_cur or not to or to == gg_cur.upper():
        return None
    rates = fx_rates(gg_cur)
    rate = ((rates or {}).get("rates") or {}).get(to)
    if not rate:
        return None
    return {"from": gg_cur.upper(), "to": to, "rate": float(rate), "date": rates.get("date") or "",
            "source": rates.get("source") or "", "source_url": rates.get("source_url") or "",
            "auto": not cfg.get("deals_currency")}


def approx(value, fx: dict | None) -> str:
    """'≈ R 165' for a GG.deals price, or '' when there's no estimate."""
    if value is None or not fx:
        return ""
    v = value * fx["rate"]
    sym = FX_SYMBOLS.get(fx["to"], fx["to"])
    return f"≈ {sym} {v:,.0f}" if v >= 100 else f"≈ {sym} {v:,.2f}"


# ------------------------------------------------------------------ deciding what's a deal
def reasons(row: dict, min_discount: int, keyshops: bool, prev: dict | None) -> list[str]:
    """Why this game is worth a ping right now (empty = not a deal).
    "Lowest ever" only counts when the price has just dropped (or Steam has it on sale), so a game
    that has simply never been discounted doesn't count as a deal."""
    out = []
    s, g, prev = row.get("steam") or {}, row.get("gg") or {}, prev or {}
    if (s.get("discount") or 0) >= min_discount:
        out.append("steam_sale")
    on_sale = (s.get("discount") or 0) > 0
    if keyshops:  # the official-store price isn't used for pings (Steam's own price covers that)
        now, ever, before = g.get("keyshop"), g.get("low_keyshop"), prev.get("keyshop")
        if now is not None and ever is not None and now <= ever and (on_sale or (before is not None and now < before)):
            out.append("key_low")
    return out


# GG.deals only tells us the cheapest key-shop price, not which platform (DRM) or region that key
# is for, so every key-shop price carries this reminder.
KEY_REGION_TIP = ("**DRM:** GG.deals doesn't say which platform the cheapest key is for, and it's sometimes an "
                  "Xbox or other non-Steam key, so check it says **Steam**.\n"
                  "**Region:** **GLOBAL** or **ROW** (Rest of World) keys work in South Africa; EU-, US-, UK-, "
                  "Asia- or RU/CIS-only keys may not activate on your Steam account.\n"
                  "**Account/key:** buy a **game key** (\"Steam Key\" / \"CD Key\"), not an **account** or "
                  "\"gift\": accounts aren't yours and can be taken back.\n"
                  "\"All prices on GG.deals\" lists each offer.")

REASON_TEXT = {
    "steam_sale": "big Steam sale",
    "store_low": "lowest price ever (official stores)",
    "key_low": "lowest price ever (key shops)",
}


def should_ping(why: list[str], row: dict, last: dict | None) -> bool:
    """New deal, a new kind of deal, or at least 3% cheaper than when we last pinged it."""
    if not why:
        return False
    if not last:
        return True
    if set(why) - set(last.get("why") or []):
        return True
    for key, now in (("steam", (row.get("steam") or {}).get("price")),
                     ("keyshop", (row.get("gg") or {}).get("keyshop"))):
        before = (last.get("prices") or {}).get(key)
        if now is not None and before and now <= before * 0.97:
            return True
    return False


def _money(v, cur: str) -> str:
    return "" if v is None else (f"{cur} {v:,.2f}".strip() if cur else f"{v:,.2f}")


def deal_embed(row: dict, why: list[str], keyshops: bool, fx: dict | None = None) -> dict:
    s, g = row.get("steam") or {}, row.get("gg") or {}
    fx = fx if fx and fx.get("from") == (g.get("currency") or "").upper() else None

    def gg_money(v):
        est = approx(v, fx)
        return _money(v, g.get("currency")) + (f" ({est})" if est else "")

    fields = []
    if s.get("price") is not None:
        val = s.get("text") or _money(s["price"], s.get("currency", ""))
        if s.get("discount"):
            val = f"**{val}** ~~{s.get('initial_text') or _money(s.get('initial'), s.get('currency', ''))}~~ (−{s['discount']}%)"
        fields.append({"name": "Steam", "value": val, "inline": True})
    if keyshops and g.get("keyshop") is not None:
        low = " 🏆 lowest ever" if g.get("low_keyshop") is not None and g["keyshop"] <= g["low_keyshop"] else ""
        fields.append({"name": "Key shop (reseller)", "value": gg_money(g["keyshop"]) + low, "inline": True})
        fields.append({"name": "⚠️ Before buying a key, check DRM · region · account/key", "value": KEY_REGION_TIP, "inline": False})
    links = [f"[Steam page]({row['store_url']})"] + ([f"[All prices on GG.deals]({g['url']})"] if g.get("url") else [])
    fields.append({"name": "Links", "value": " · ".join(links), "inline": False})
    embed = {
        "title": f"🏷️ Deal: {row.get('name') or row['appid']}",
        "url": row["store_url"],
        "description": "Why: " + ", ".join(REASON_TEXT.get(w, w) for w in why),
        "color": notify.GREEN,
        "fields": fields,
        "image": {"url": row.get("image") or f"https://cdn.cloudflare.steamstatic.com/steam/apps/{row['appid']}/header.jpg"},
    }
    if g:
        foot = "Prices by GG.deals"
        if fx:
            one = f"{FX_SYMBOLS.get(fx['from'], fx['from'])}1 = {FX_SYMBOLS.get(fx['to'], fx['to'])} {fx['rate']:,.2f}"
            foot += f" · ≈ amounts are estimates at {one} (rates by {fx['source']}, {fx['date']})"
        embed["footer"] = {"text": foot}
    return embed


# ------------------------------------------------------------------ the check
def due() -> bool:
    cfg = store.load_config()
    return bool(cfg.get("deals_enabled")) and time.time() - (store.load_state().get("last_deals_check") or 0) > CHECK_SECONDS


def check(force: bool = False, ping: bool = True) -> dict:
    """Refresh every watched game's prices and ping new deals. Returns the saved deals block."""
    if not _lock.acquire(blocking=False):
        return store.load_state().get("deals") or {}
    try:
        return _check(force, ping)
    finally:
        _lock.release()


def _check(force: bool, ping: bool) -> dict:
    cfg, state = store.load_config(), store.load_state()
    if not cfg.get("deals_enabled") and not force:
        return state.get("deals") or {}
    now = int(time.time())
    errors, source = [], []
    wish: list[int] = []
    if cfg.get("steam_id"):
        try:
            wish = wishlist(cfg["steam_id"])
            source.append("wishlist")
        except DealsError as exc:
            errors.append(str(exc))
    extra = [int(x) for x in cfg.get("deals_extra") or [] if str(x).isdigit()]
    watch = list(dict.fromkeys(wish + extra))
    names = dict(state.get("deal_names") or {})
    steam: dict[int, dict] = {}
    gg: dict[int, dict] = {}
    if watch:
        try:
            steam = steam_prices(watch)
        except DealsError as exc:
            errors.append(str(exc))
        if cfg.get("ggdeals_key"):
            try:
                gg = ggdeals_prices(cfg["ggdeals_key"], watch, cfg.get("deals_region") or "")
            except DealsError as exc:
                errors.append(str(exc))
        missing = [a for a in watch if str(a) not in names]
        if missing and cfg.get("steam_api_key"):  # all names and pictures in a few calls
            cur = next((p.get("currency") for p in steam.values() if p.get("currency")), "")
            for a, info in steam_basics_bulk(cfg["steam_api_key"], missing, CURRENCY_COUNTRY.get(cur, "US")).items():
                names[str(a)] = info
        looked = 0
        for a in watch:  # without a Steam key (or for any it missed): a few per check
            if str(a) not in names and looked < 25:
                info = steam_basics(a)
                if info:
                    names[str(a)] = info
                looked += 1
                time.sleep(0.3)

    prev_prices = state.get("deal_prices") or {}
    alerts = dict(state.get("deal_alerts") or {})
    keyshops = cfg.get("deals_keyshops", True)
    min_disc = int(cfg.get("deals_min_discount") or 50)
    hook = cfg.get("deals_webhook") or cfg.get("discord_webhook") or ""
    fx = fx_for({"rows": [{"steam": steam.get(a) or {}, "gg": gg.get(a) or {}} for a in watch]}, cfg) if gg else None
    rows, embeds = [], []
    for a in watch:
        info, g = names.get(str(a)) or {}, gg.get(a) or {}
        row = {
            "appid": a, "name": info.get("name") or g.get("title") or f"App {a}", "image": info.get("image") or "",
            "store_url": f"{STORE}/app/{a}/", "gg_url": g.get("url") or "", "manual": a in extra and a not in wish,
            "steam": steam.get(a) or {}, "gg": g, "free": bool(info.get("free")), "soon": bool(info.get("soon")),
        }
        why = reasons(row, min_disc, keyshops, prev_prices.get(str(a)))
        row["why"] = why
        row["on_sale"] = (row["steam"].get("discount") or 0) > 0
        row["new_low"] = any(w in ("store_low", "key_low") for w in why)
        rows.append(row)
        last = alerts.get(str(a))
        if not why:
            alerts.pop(str(a), None)  # deal over: a later sale pings again
        elif should_ping(why, row, last):
            if ping and hook:
                embeds.append(deal_embed(row, why, keyshops, fx))
            alerts[str(a)] = {"why": why, "at": now, "prices": {
                "steam": row["steam"].get("price"), "retail": g.get("retail"), "keyshop": g.get("keyshop")}}
    sent = 0
    for i in range(0, len(embeds), 10):
        if notify.send(hook, embeds[i:i + 10]):
            sent += len(embeds[i:i + 10])
    if sent:
        store.log(f"Discord: {sent} new game deal{'s' if sent != 1 else ''}.")
    rows.sort(key=lambda r: (-(r["steam"].get("discount") or 0), not r["new_low"], r["name"].lower()))
    block = {
        "updated": now, "errors": errors, "source": source, "wishlist_count": len(wish), "extra_count": len(extra),
        "has_gg": bool(cfg.get("ggdeals_key")), "rows": rows, "fx": fx,
    }
    store.patch_state(
        deals=block, deal_names=names, deal_alerts=alerts, last_deals_check=now,
        deal_prices={str(r["appid"]): {"retail": r["gg"].get("retail"), "keyshop": r["gg"].get("keyshop")} for r in rows},
    )
    if errors:
        store.log("Deals check: " + " ".join(errors), "warn")
    return block


def appid_from(text: str) -> int | None:
    """A Steam store link (…/app/1245620/…) or a plain app ID."""
    text = str(text).strip()
    m = re.search(r"/app/(\d+)", text) or re.fullmatch(r"(\d{1,9})", text)
    return int(m.group(1)) if m else None


def test_ping() -> bool:
    cfg = store.load_config()
    hook = cfg.get("deals_webhook") or cfg.get("discord_webhook") or ""
    row = {"appid": 1245620, "name": "ELDEN RING (test message)", "store_url": f"{STORE}/app/1245620/", "image": "",
           "steam": {"price": 424.5, "initial": 849.0, "discount": 50, "currency": "ZAR", "text": "R 424.50",
                     "initial_text": "R 849.00"},
           "gg": {"retail": 29.99, "keyshop": 24.10, "low_retail": 29.99, "low_keyshop": 24.10, "currency": "USD",
                  "url": "https://gg.deals/"}}
    fx = fx_for({"rows": [row]}, cfg)
    return notify.send(hook, [deal_embed(row, ["steam_sale", "key_low"], cfg.get("deals_keyshops", True), fx)],
                       content="Test from Loot Radar: this is what a deal ping looks like.")
