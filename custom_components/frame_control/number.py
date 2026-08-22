"""Числовые сущности Frame Control: яркость (рамка) / громкость (ТВ)."""

import logging

from homeassistant.components.number import NumberEntity

from .common import shell

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data["host"]
    port = entry.data.get("port", 5555)
    device_type = entry.data.get("device_type") or "frame"

    async def run(cmd, timeout=15):
        return await hass.async_add_executor_job(shell, host, port, cmd, timeout)

    if device_type == "tv":
        volume_now = 0
        try:
            out = await run("media volume --stream 3 --get")
            for token in out.split():
                if token.isdigit():
                    volume_now = int(token) * 100 // 20
                    break
        except Exception:  # noqa: BLE001
            pass
        async_add_entities(
            [TvVolumeNumber(entry, run, volume_now)], update_before_add=True
        )
    else:
        brightness_now = 128
        try:
            out = await run("settings get system screen_brightness")
            brightness_now = int(out.strip())
        except Exception:  # noqa: BLE001
            pass
        async_add_entities(
            [FrameBrightnessNumber(entry, run, brightness_now)],
            update_before_add=True,
        )


class FrameBrightnessNumber(NumberEntity):
    """Яркость экрана рамки (0-255)."""

    _attr_has_entity_name = True

    def __init__(self, entry, run, value):
        self._entry = entry
        self._run = run
        self._attr_name = "Яркость рамки"
        self._attr_unique_id = f"{entry.entry_id}_brightness"
        self._attr_icon = "mdi:brightness-6"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 255
        self._attr_native_step = 1
        self._attr_native_value = value

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_set_native_value(self, value):
        self._attr_native_value = int(value)
        await self._run(f"settings put system screen_brightness {int(value)}")
        await self._run("settings put system screen_brightness_mode 0")
        self.async_write_ha_state()


class TvVolumeNumber(NumberEntity):
    """Громкость телевизора (0-100)."""

    _attr_has_entity_name = True

    def __init__(self, entry, run, value):
        self._entry = entry
        self._run = run
        self._attr_name = "Громкость ТВ"
        self._attr_unique_id = f"{entry.entry_id}_volume"
        self._attr_icon = "mdi:volume-high"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_value = value

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_set_native_value(self, value):
        self._attr_native_value = int(value)
        raw = max(0, min(20, round(int(value) * 20 / 100)))
        await self._run(f"media volume --stream 3 --set {raw}")
        self.async_write_ha_state()
