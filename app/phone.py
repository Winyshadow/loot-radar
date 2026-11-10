"""Phone access: Loot Radar's dashboard on your phone, on home Wi-Fi or anywhere with Tailscale.

Off until you switch it on in Settings. Then a second, separate web server listens on your
network at PORT (5578); the PC's own dashboard stays on 127.0.0.1:5577 as before.

Everything that comes in through the phone server has to carry a cookie, and the only way to
get one is to type the PIN shown in Settings on the PC (or scan its QR code). Five wrong PINs
from one address lock it out for 10 minutes. The phone never receives your Steam key, Discord
link or passwords, and PC-only actions (Twitch login, phone settings, Windows start-up) are
refused. Making a new PIN signs every phone out.
"""

from __future__ import annotations

import io
import ipaddress
import secrets
import socket
import threading
import time

import store

PORT = 5578
COOKIE = "lr_phone"
SECRET_KEYS = ("steam_api_key", "discord_webhook", "miner_password", "phone_pin", "phone_token")
PC_ONLY_SETTINGS = SECRET_KEYS + ("steam_profile_input", "miner_url", "start_with_windows")
PC_ONLY_PATHS = ("/api/miner/login", "/api/phone")
OPEN_PATHS = ("/api/phone-login", "/icon.png", "/manifest.webmanifest", "/loot-radar.ico")
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")

_server = None
_lock = threading.Lock()
_fails: dict[str, list[float]] = {}


# ------------------------------------------------------------------ settings
def settings() -> dict:
    """PIN and session secret, created the first time they're needed."""
    cfg = store.load_config()
    changed = False
    if not cfg.get("phone_pin"):
        cfg["phone_pin"] = f"{secrets.randbelow(10**6):06d}"
        changed = True
    if not cfg.get("phone_token"):
        cfg["phone_token"] = secrets.token_urlsafe(32)
        changed = True
    if changed:
        store.update_config(phone_pin=cfg["phone_pin"], phone_token=cfg["phone_token"])
    return {"enabled": bool(cfg.get("phone_access")), "pin": cfg["phone_pin"], "token": cfg["phone_token"]}


def new_pin() -> None:
    """A fresh PIN and session secret: every phone has to enter the new PIN."""
    store.update_config(phone_pin=f"{secrets.randbelow(10**6):06d}", phone_token=secrets.token_urlsafe(32))


# ------------------------------------------------------------------ who's asking
def is_phone_request(req) -> bool:
    """True for anything that came in through the phone server (not the PC's own 127.0.0.1)."""
    return str(req.environ.get("SERVER_PORT")) == str(PORT)


def authorized(req) -> bool:
    s = settings()
    got = req.cookies.get(COOKIE, "")
    return s["enabled"] and bool(got) and secrets.compare_digest(got, s["token"])


def check_pin(addr: str, pin: str) -> tuple[bool, str]:
    """(ok, message). Five wrong tries from one address in 10 minutes locks it out."""
    now = time.time()
    tries = [t for t in _fails.get(addr, []) if now - t < 600]
    _fails[addr] = tries
    if len(tries) >= 5:
        return False, "Too many wrong PINs. Wait 10 minutes and try again."
    s = settings()
    if s["enabled"] and secrets.compare_digest(str(pin).strip(), s["pin"]):
        _fails.pop(addr, None)
        return True, ""
    tries.append(now)
    left = 5 - len(tries)
    return False, "That PIN isn't right." + (f" {left} tries left." if left else " Locked for 10 minutes.")


def redact(settings_out: dict) -> dict:
    """What the phone may see of your settings: secrets become a placeholder ("set" or empty)."""
    out = dict(settings_out)
    for k in SECRET_KEYS:
        if k in out:
            out[k] = "set" if out[k] else ""
    return out


# ------------------------------------------------------------------ network addresses
def addresses() -> dict:
    """This PC's addresses a phone can reach: home network ones, and Tailscale's (100.x)."""
    wifi, tailscale = [], []
    try:  # the address Windows uses for the internet (no data is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            primary = s.getsockname()[0]
    except OSError:
        primary = ""
    try:
        import psutil
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            if name in stats and not stats[name].isup:
                continue
            for a in addrs:
                if a.family != socket.AF_INET:
                    continue
                ip = ipaddress.ip_address(a.address)
                if ip.is_loopback or ip.is_link_local:
                    continue
                if ip in TAILSCALE_NET:
                    tailscale.append(a.address)
                elif ip.is_private and a.address not in wifi:
                    wifi.append(a.address)
    except Exception:
        pass
    if primary in wifi:  # the main one first; virtual adapters (VMs, VPNs) after it
        wifi.remove(primary)
        wifi.insert(0, primary)
    elif primary and ipaddress.ip_address(primary).is_private and ipaddress.ip_address(primary) not in TAILSCALE_NET:
        wifi.insert(0, primary)
    return {"wifi": wifi, "tailscale": tailscale}


def url_for(addr: str) -> str:
    return f"http://{addr}:{PORT}/"


def qr_png(text: str) -> bytes:
    import qrcode
    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ the phone server
def sync(app) -> str:
    """Start or stop the phone server to match the setting. Returns a short status."""
    global _server
    want = settings()["enabled"]
    with _lock:
        if want and _server is None:
            try:
                from waitress import create_server
                _server = create_server(app, host="0.0.0.0", port=PORT, threads=4)
            except Exception as exc:  # port taken, or the network refused it
                store.log(f"Phone access couldn't start on port {PORT}: {exc}", "warn")
                return "error"
            threading.Thread(target=_server.run, name="phone", daemon=True).start()
            store.log(f"Phone access is on (port {PORT}).")
        elif not want and _server is not None:
            try:
                _server.close()
            except Exception:
                pass
            _server = None
            store.log("Phone access is off.")
    return "on" if _server is not None else "off"


def running() -> bool:
    return _server is not None


PIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Loot Radar</title><link rel="icon" href="/icon.png"><link rel="apple-touch-icon" href="/icon.png">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#071b27">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<style>
 body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(160deg,#0b2a3b,#071b27 70%);
      color:#e8f3f7;font:16px/1.5 "Segoe UI",system-ui,sans-serif;padding:20px;box-sizing:border-box}
 .box{width:100%;max-width:340px;text-align:center;background:rgba(13,42,58,.7);border:1px solid rgba(160,220,245,.2);border-radius:22px;padding:28px 22px}
 img{width:64px;height:64px;border-radius:16px} h1{font-size:22px;margin:12px 0 4px} p{color:#93b4c2;font-size:14px;margin:0 0 18px}
 input{width:100%;box-sizing:border-box;font:inherit;font-size:28px;letter-spacing:10px;text-align:center;padding:12px;border-radius:14px;
       border:1px solid rgba(160,220,245,.3);background:rgba(4,20,30,.6);color:#e8f3f7}
 button{margin-top:14px;width:100%;font:inherit;font-weight:700;padding:13px;border-radius:99px;border:0;background:#b6f03c;color:#0a2230}
 .err{color:#ff6b7a;font-size:14px;min-height:21px;margin-top:10px}
</style></head><body><form class="box" id="f">
<img src="/icon.png" alt=""><h1>Loot Radar</h1><p>Enter the PIN from Settings &rarr; Phone access on your PC.</p>
<input id="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]*" placeholder="------" autofocus>
<button>Open Loot Radar</button><div class="err" id="err"></div></form>
<script>
const f=document.getElementById("f"),pin=document.getElementById("pin"),err=document.getElementById("err");
async function go(v){err.textContent="";
  const r=await fetch("/api/phone-login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pin:v})});
  const j=await r.json().catch(()=>({}));
  if(r.ok&&j.ok){history.replaceState(null,"","/#/overview");location.reload();}else{err.textContent=j.error||"Couldn't sign in.";pin.select();}}
f.addEventListener("submit",e=>{e.preventDefault();if(!/^\\d{6}$/.test(pin.value)){err.textContent="Type the 6-digit PIN.";return;}go(pin.value);});
const m=location.hash.match(/pin-(\\d{6})/);if(m){pin.value=m[1];history.replaceState(null,"","/");go(m[1]);}
</script></body></html>"""
