"""Talks to Twitch Drops Miner's local dashboard API (it runs at http://127.0.0.1:8080 by default)."""

from __future__ import annotations

import requests

TIMEOUT = 10


class MinerError(Exception):
    pass


class Miner:
    def __init__(self, base_url: str, password: str = ""):
        self.base = (base_url or "http://127.0.0.1:8080").rstrip("/")
        self.password = password or ""

    def _headers(self) -> dict:
        # The miner accepts its dashboard password through this header for app-to-app calls.
        return {"X-Fleet-Password": self.password} if self.password else {}

    def _request(self, method: str, path: str, **kw):
        try:
            r = requests.request(
                method, self.base + path, headers=self._headers(), timeout=TIMEOUT,
                allow_redirects=False, **kw,
            )
        except requests.RequestException as exc:
            raise MinerError("The drop miner isn't running (or isn't on " + self.base + ").") from exc
        if r.status_code in (301, 302, 303, 307):
            raise MinerError(
                "The drop miner is waiting for its first-time setup. Open its dashboard once and "
                "choose 'Start without password'."
            )
        if r.status_code == 401:
            raise MinerError("The drop miner has a dashboard password. Enter it in Loot Radar's settings.")
        if r.status_code == 503:
            raise MinerError("The drop miner is still starting up (or not logged in to Twitch yet).")
        if r.status_code != 200:
            raise MinerError(f"The drop miner answered with HTTP {r.status_code}.")
        try:
            return r.json()
        except ValueError as exc:
            raise MinerError("The drop miner sent back something unexpected.") from exc

    def campaigns(self) -> list[dict]:
        return self._request("GET", "/api/campaigns").get("campaigns", [])

    def settings(self) -> dict:
        data = self._request("GET", "/api/settings")
        return data.get("settings", data) if isinstance(data, dict) else {}

    def status(self) -> dict:
        return self._request("GET", "/api/status")

    def channels(self) -> list[dict]:
        return self._request("GET", "/api/channels").get("channels", [])

    def channel_points(self, login: str) -> dict:
        return self._request("GET", f"/api/channel-points/{login}")

    def points_history(self, days: int = 30) -> dict:
        return self._request("GET", f"/api/analytics/points?days={days}").get("channels", {})

    def pause(self) -> None:
        self._request("POST", "/api/pause")

    def resume(self) -> None:
        self._request("POST", "/api/resume")

    def update_settings(self, changes: dict) -> None:
        self._request("POST", "/api/settings", json=changes)
