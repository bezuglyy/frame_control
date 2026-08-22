"""Датчики Frame Control: заряд, uptime, RSSI (только рамка)."""

import logging

from homeassistant.components.sensor import SensorEntity

from .common import shell

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    host = entry.data["host"]
    port = entry.data.get("port", 5555)
    device_type = entry.data.get("device_type") or "frame"

    if device_type == "tv":
        async_add_entities([], update_before_add=True)
        return

    async def run(cmd, timeout=15):
        return await hass.async_add_executor_job(shell, host, port, cmd, timeout)

    battery_now = 0
    try:
        out = await run("dumpsys battery | grep level")
        battery_now = int(out.split(":")[-1].strip())
    except Exception:  # noqa: BLE001
        pass

    async_add_entities(
        [
            FrameBatterySensor(entry, run, battery_now),
            FrameUptimeSensor(entry, run),
            FrameRssiSensor(entry, run),
        ],
        update_before_add=True,
    )


def _device_info(entry):
    return {"identifiers": {("frame_control", entry.entry_id)}}


class FrameBatterySensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, run, value):
        self._entry = entry
        self._run = run
        self._attr_name = "Заряд рамки"
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_icon = "mdi:battery"
        self._attr_native_value = value
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_class = "battery"
        self._attr_should_poll = True
        self._attr_scan_interval = 600  # 10 мин

    @property
    def device_info(self):
        return _device_info(self._entry)

    async def async_update(self):
        out = await self._run("dumpsys battery | grep level")
        try:
            val = int(out.split(":")[-1].strip())
            self._attr_native_value = val
        except (ValueError, AttributeError):
            self._attr_native_value = None  # ADB недоступен
            _LOGGER.warning("Заряд рамки: ADB не ответил")


class FrameUptimeSensor(SensorEntity):
    """Аптайм рамки в минутах (падение = перезагрузка устройства)."""

    _attr_has_entity_name = True

    def __init__(self, entry, run):
        self._entry = entry
        self._run = run
        self._attr_name = "Аптайм рамки"
        self._attr_unique_id = f"{entry.entry_id}_uptime"
        self._attr_icon = "mdi:clock-outline"
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "min"
        self._attr_device_class = "duration"
        self._attr_should_poll = True
        self._attr_scan_interval = 600  # 10 мин

    @property
    def device_info(self):
        return _device_info(self._entry)

    async def async_update(self):
        out = await self._run("cat /proc/uptime")
        try:
            sec = float(out.split()[0])
            self._attr_native_value = round(sec / 60)
        except (ValueError, IndexError, AttributeError):
            self._attr_native_value = None


class FrameRssiSensor(SensorEntity):
    """Уровень Wi-Fi сигнала рамки (dBm)."""

    _attr_has_entity_name = True

    def __init__(self, entry, run):
        self._entry = entry
        self._run = run
        self._attr_name = "Wi-Fi сигнал рамки"
        self._attr_unique_id = f"{entry.entry_id}_rssi"
        self._attr_icon = "mdi:wifi"
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "dBm"
        self._attr_device_class = "signal_strength"
        self._attr_should_poll = True
        self._attr_scan_interval = 600  # 10 мин

    @property
    def device_info(self):
        return _device_info(self._entry)

    async def async_update(self):
        out = await self._run("cat /proc/net/wireless | grep wlan0")
        if "wlan0" not in out:
            out = await self._run("cat /proc/net/wireless | tail -1")
        try:
            # wlan0: 0000  0.  -44.  -256. ...
            parts = out.split()
            for i, p in enumerate(parts):
                try:
                    val = float(p)
                    if -120 <= val <= 0:
                        self._attr_native_value = val
                        break
                except ValueError:
                    continue
        except (ValueError, IndexError, AttributeError):
            self._attr_native_value = None
