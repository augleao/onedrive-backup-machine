"""Data coordinator for OneDrive Backup integration."""
from __future__ import annotations

import json
from datetime import timedelta

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN


class OneDriveBackupCoordinator(DataUpdateCoordinator):
    """Coordinate data updates and API calls to the add-on."""

    def __init__(self, hass: HomeAssistant, addon_url: str, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(5, int(scan_interval))),
        )
        self._addon_url = addon_url.rstrip("/")

    async def _api_request(self, method: str, path: str, payload: dict | None = None) -> dict:
        session = async_get_clientsession(self.hass)
        url = f"{self._addon_url}{path}"
        try:
            async with session.request(method, url, json=payload, timeout=15) as response:
                text = await response.text()
                data = {}
                if text:
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        data = {"raw": text}
                if response.status >= 400:
                    msg = data.get("message") or data.get("error") or f"HTTP {response.status}"
                    raise UpdateFailed(f"{path} failed: {msg}")
                if isinstance(data, dict):
                    return data
                return {}
        except ClientError as ex:
            raise UpdateFailed(f"Connection failed for {path}: {ex}") from ex

    async def _async_update_data(self) -> dict:
        status = await self._api_request("GET", "/api/status")
        tasks = await self._api_request("GET", "/api/tasks")
        jobs = await self._api_request("GET", "/api/jobs")
        return {
            "status": status,
            "tasks": tasks.get("tasks", []),
            "jobs": jobs.get("jobs", []),
        }

    async def async_run_now(self, task_id: str | None = None) -> dict:
        if task_id:
            return await self._api_request("POST", f"/api/tasks/{task_id}/run")
        return await self._api_request("POST", "/api/backup")


import logging

_LOGGER = logging.getLogger(__name__)
