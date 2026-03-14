"""OneDrive Backup integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from .const import CONF_ADDON_URL, CONF_SCAN_INTERVAL, DEFAULT_ADDON_URL, DEFAULT_SCAN_INTERVAL, DOMAIN, SERVICE_RUN_TASK
from .coordinator import OneDriveBackupCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})

    domain_config = config.get(DOMAIN) or {}
    if not isinstance(domain_config, dict):
        _LOGGER.warning("Invalid %s configuration format. Expected an object.", DOMAIN)
        domain_config = {}

    addon_url = str(domain_config.get(CONF_ADDON_URL, DEFAULT_ADDON_URL)).strip().rstrip("/")
    scan_interval = int(domain_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    coordinator = OneDriveBackupCoordinator(hass=hass, addon_url=addon_url, scan_interval=scan_interval)
    hass.data[DOMAIN]["coordinator"] = coordinator

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.warning("Initial data refresh failed for %s: %s", DOMAIN, ex)

    run_task_schema = vol.Schema({vol.Optional("task_id"): cv.string})

    async def _run_task_service(call: ServiceCall) -> None:
        task_id = call.data.get("task_id")
        await coordinator.async_run_now(task_id=task_id)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_TASK,
        _run_task_service,
        schema=run_task_schema,
    )

    await async_load_platform(hass, "sensor", DOMAIN, {}, config)
    await async_load_platform(hass, "button", DOMAIN, {}, config)
    return True
