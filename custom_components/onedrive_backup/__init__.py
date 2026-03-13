"""Minimal OneDrive Backup integration for Home Assistant."""
from homeassistant.core import HomeAssistant


async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault("onedrive_backup", {})
    return True
