"""Plant Happiness — a HACS-compatible Home Assistant integration.

Creates a sensor entity per plant that:
  - Tracks soil moisture, ambient light, temperature (optional), humidity (optional)
  - Computes a weighted happiness score (0–100)
  - Exposes a mood state string (thriving/happy/okay/struggling/need_water/dark/critical)
  - Provides all per-sensor status labels and colors as attributes
    so the plant-happiness-card can render everything from one entity.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plant Happiness from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Re-register update listener so options changes reload the entry
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload so sensor picks up new entity IDs."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
