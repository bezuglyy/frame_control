"""Переключатели Frame Control: экран (рамка) / питание (ТВ)."""

import logging

from homeassistant.components.switch import SwitchEntity

from .common import shell

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data["host"]
    port = entry.data.get("port", 5555)
    device_type = entry.data.get("device_type") or "frame"

    async def run(cmd, timeout=15):
        return await hass.async_add_executor_job(shell, host, port, cmd, timeout)

    is_on = False
    try:
        out = await run("dumpsys power | grep -i mWakefulness")
        is_on = "Awake" in out
    except Exception:  # noqa: BLE001
        pass

    if device_type == "tv":
        async_add_entities([TvPowerSwitch(entry, run, is_on)], update_before_add=True)
    else:
        async_add_entities(
            [FrameScreenSwitch(entry, run, is_on)], update_before_add=True
        )


class FrameScreenSwitch(SwitchEntity):
    """Экран рамки."""

    _attr_has_entity_name = True

    def __init__(self, entry, run, is_on):
        self._entry = entry
        self._run = run
        self._attr_name = "Экран рамки"
        self._attr_unique_id = f"{entry.entry_id}_screen"
        self._attr_icon = "mdi:monitor"
        self._attr_is_on = is_on

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_turn_on(self, **kwargs):
        await self._run("input keyevent 224")
        await self._run("wm dismiss-keyguard")
        await self._run("input keyevent 82")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._run("input keyevent 223")
        self._attr_is_on = False
        self.async_write_ha_state()


class TvPowerSwitch(SwitchEntity):
    """Питание телевизора."""

    _attr_has_entity_name = True

    def __init__(self, entry, run, is_on):
        self._entry = entry
        self._run = run
        self._attr_name = "Питание ТВ"
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_icon = "mdi:television"
        self._attr_is_on = is_on

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_turn_on(self, **kwargs):
        await self._run("input keyevent 26")
        await self._run("wm dismiss-keyguard")
        await self._run("input keyevent 82")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._run("input keyevent 26")
        self._attr_is_on = False
        self.async_write_ha_state()
