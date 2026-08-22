"""Кнопки Frame Control: перезагрузка, скриншот, открыть Дом (рамка)."""

import logging
import os
from datetime import datetime

from homeassistant.components.button import ButtonEntity

from .common import shell

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data["host"]
    port = entry.data.get("port", 5555)
    device_type = entry.data.get("device_type") or "frame"
    shot_dir = entry.data.get("screenshot_dir", "/config/www/frames")

    async def run(cmd, timeout=15, decode=True):
        return await hass.async_add_executor_job(
            shell, host, port, cmd, timeout, decode
        )

    entities = [
        FrameRebootButton(entry, run),
        FrameScreenshotButton(entry, run, shot_dir),
    ]
    if device_type == "frame":
        entities.append(FrameOpenDomButton(entry, run))

    async_add_entities(entities, update_before_add=True)


class FrameRebootButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, run):
        self._entry = entry
        self._run = run
        self._attr_name = "Перезагрузка"
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        self._attr_icon = "mdi:restart"

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_press(self):
        await self._run("reboot", timeout=30)


class FrameScreenshotButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, run, shot_dir):
        self._entry = entry
        self._run = run
        self._shot_dir = shot_dir
        self._attr_name = "Скриншот"
        self._attr_unique_id = f"{entry.entry_id}_screenshot"
        self._attr_icon = "mdi:camera"

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_press(self):
        fname = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(self._shot_dir, fname)
        raw = await self._run("screencap -p", 20, decode=False)
        if not isinstance(raw, bytes):
            raw = raw.encode("latin-1", errors="ignore")
        with open(path, "wb") as f:
            f.write(raw)


class FrameOpenDomButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, run):
        self._entry = entry
        self._run = run
        self._attr_name = "Открыть Дом с Алисой"
        self._attr_unique_id = f"{entry.entry_id}_open_dom"
        self._attr_icon = "mdi:home-automation"

    @property
    def device_info(self):
        return {"identifiers": {("frame_control", self._entry.entry_id)}}

    async def async_press(self):
        await self._run("input keyevent 224")
        await self._run(
            "am start -n com.yandex.iot/ru.yandex.searchplugin.MainActivity"
        )

        # Автовозврат к часам через 120 секунд
        async def _back_to_clock():
            await self._run(
                "am start -n com.google.android.deskclock/com.android.deskclock.DeskClock"
            )

        self.hass.loop.call_later(
            120, lambda: self.hass.async_create_task(_back_to_clock())
        )
