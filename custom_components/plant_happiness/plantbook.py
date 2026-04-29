"""Open PlantBook API client for Plant Happiness.

Handles OAuth2 client_credentials authentication and plant data lookups
against https://open.plantbook.io.  A single PlantBookClient instance is
created per config entry and cached in hass.data so tokens survive reloads
within the same HA session.

Typical flow
------------
1. client = PlantBookClient(hass, client_id, client_secret)
2. data = await client.async_get_plant_data("monstera deliciosa")
   → dict with soil_moist_min/max, temp_min/max, env_humid_min/max,
     light_lux_min/max, pid, display_pid, …
3. Pass the dict to the sensor so it can calibrate its scoring curves.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Open PlantBook API endpoints
_TOKEN_URL  = "https://open.plantbook.io/api/v1/token/"
_SEARCH_URL = "https://open.plantbook.io/api/v1/plant/search/"
_DETAIL_URL = "https://open.plantbook.io/api/v1/plant/detail/"

_TIMEOUT = 10  # seconds


class PlantBookAuthError(Exception):
    """Raised when the PlantBook OAuth2 handshake fails."""


class PlantBookClient:
    """Lightweight async wrapper around the Open PlantBook REST API.

    Tokens are cached on the instance; a single transparent refresh is
    attempted on a 401 response before giving up.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._hass = hass
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def async_authenticate(self) -> None:
        """Obtain a fresh OAuth2 access token.

        Raises :exc:`PlantBookAuthError` on any failure so callers can
        distinguish auth problems from connectivity problems.
        """
        session = async_get_clientsession(self._hass)
        try:
            resp = await session.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=_TIMEOUT,
            )
        except Exception as exc:
            raise PlantBookAuthError(f"Network error during auth: {exc}") from exc

        if resp.status != 200:
            body = await resp.text()
            raise PlantBookAuthError(
                f"PlantBook auth returned HTTP {resp.status}: {body[:120]}"
            )

        payload = await resp.json()
        token = payload.get("access_token")
        if not token:
            raise PlantBookAuthError("PlantBook response contained no access_token")

        self._token = token
        _LOGGER.debug("PlantBook: authenticated successfully")

    # ------------------------------------------------------------------
    # Internal GET helper
    # ------------------------------------------------------------------

    async def _get(self, url: str, **params: Any) -> dict[str, Any] | None:
        """Authenticated GET with a single token-refresh retry on 401."""
        if not self._token:
            await self.async_authenticate()

        session = async_get_clientsession(self._hass)
        headers = {"Authorization": f"Bearer {self._token}"}

        try:
            resp = await session.get(
                url, params=params, headers=headers, timeout=_TIMEOUT
            )

            if resp.status == 401:
                _LOGGER.debug("PlantBook: 401 received, refreshing token")
                await self.async_authenticate()
                headers["Authorization"] = f"Bearer {self._token}"
                resp = await session.get(
                    url, params=params, headers=headers, timeout=_TIMEOUT
                )

            if resp.status != 200:
                _LOGGER.warning(
                    "PlantBook GET %s returned HTTP %s", url, resp.status
                )
                return None

            return await resp.json()

        except PlantBookAuthError:
            raise
        except Exception as exc:
            _LOGGER.error("PlantBook request error for %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def async_search_pid(self, alias: str) -> str | None:
        """Return the best-matching plant *pid* for *alias*, or None."""
        data = await self._get(_SEARCH_URL, alias=alias, limit=1)
        if not data:
            return None
        results = data.get("results", [])
        if not results:
            _LOGGER.info("PlantBook: no results found for '%s'", alias)
            return None
        pid = results[0].get("pid")
        _LOGGER.debug("PlantBook: '%s' matched pid=%s", alias, pid)
        return pid

    async def async_get_plant_detail(self, pid: str) -> dict[str, Any] | None:
        """Return the full plant detail dict for *pid*, or None."""
        return await self._get(f"{_DETAIL_URL}{pid}/")

    async def async_get_plant_data(self, alias: str) -> dict[str, Any] | None:
        """High-level helper: search by alias and return the full detail dict.

        Returns ``None`` if the plant cannot be found or any error occurs.
        Errors are logged at WARNING/ERROR level so the integration can fall
        back to generic defaults without crashing.
        """
        try:
            pid = await self.async_search_pid(alias)
            if not pid:
                return None
            detail = await self.async_get_plant_detail(pid)
            if detail:
                _LOGGER.info(
                    "PlantBook: loaded data for '%s' (pid=%s, display='%s')",
                    alias,
                    pid,
                    detail.get("display_pid", pid),
                )
            return detail

        except PlantBookAuthError as exc:
            _LOGGER.error("PlantBook authentication failed: %s", exc)
            return None
        except Exception as exc:
            _LOGGER.error(
                "PlantBook unexpected error fetching '%s': %s", alias, exc
            )
            return None
