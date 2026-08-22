"""Frame Control v7 — рамки (X08C) и телевизоры (Android TV) по ADB."""

import asyncio
import logging
import os
import socket
from datetime import timedelta

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .common import shell

_LOGGER = logging.getLogger(__name__)

DOMAIN = "frame_control"
ADBKEY = "/config/adbkey"


def _shell_for_entry(hass, entry_id, cmd, timeout=15):
    """Выполнить ADB-команду для конкретного config entry."""
    data = hass.data.get(DOMAIN, {}).get(entry_id)
    if not data:
        _LOGGER.warning("frame_control: entry %s не найден", entry_id)
        return ""
    return shell(data["host"], data["port"], cmd, timeout)

SCREEN_ON_SCHEMA = vol.Schema({})
SCREEN_OFF_SCHEMA = vol.Schema({})
BRIGHTNESS_SCHEMA = vol.Schema(
    {vol.Required("brightness"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255))}
)
OPEN_URL_SCHEMA = vol.Schema({vol.Required("url"): cv.string})
OPEN_APP_SCHEMA = vol.Schema({vol.Required("package"): cv.string})
SET_VOLUME_SCHEMA = vol.Schema(
    {vol.Required("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))}
)
REBOOT_SCHEMA = vol.Schema({vol.Optional("entity_id"): cv.entity_ids})
SCREENSHOT_SCHEMA = vol.Schema({})


async def async_setup(hass, config):
    """YAML-совместимость."""
    return True


async def async_setup_entry(hass, entry):
    """Настройка из config entry."""
    conf = {**entry.data, **entry.options}
    host = conf[CONF_HOST]
    port = conf.get(CONF_PORT, 5555)
    device_type = conf.get("device_type") or "frame"
    shot_dir = conf.get("screenshot_dir", "/config/www/frames")
    os.makedirs(shot_dir, exist_ok=True)

    enable_motion = conf.get("enable_motion", bool(conf.get("motion_sensor")))
    motion_sensor = conf.get("motion_sensor") if enable_motion else None
    motion_timeout = conf.get("motion_timeout", 120)

    enable_illuminance = conf.get(
        "enable_illuminance", bool(conf.get("illuminance_sensor"))
    )
    illum_sensor = conf.get("illuminance_sensor") if enable_illuminance else None
    lux_min = conf.get("lux_min", 0)
    lux_max = conf.get("lux_max", 2000)
    bright_min = conf.get("brightness_min", 30)
    bright_max = conf.get("brightness_max", 255)

    # IP Webcam watchdog: порт, который надо держать открытым
    ipwebcam_port = conf.get("ipwebcam_port", 8080)
    watchdog_enabled = conf.get("watchdog_enabled", False)
    watchdog_interval = conf.get("watchdog_interval", 30)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "host": host,
        "port": port,
        "device_type": device_type,
        "screenshot_dir": shot_dir,
        "device_id": entry.entry_id,
    }

    async def _run(cmd, timeout=15, decode=True):
        return await hass.async_add_executor_job(
            shell, host, port, cmd, timeout, decode
        )

    # --- сервисы ---
    async def handle_screen_on(call):
        await _run("input keyevent 224")
        await _run("wm dismiss-keyguard")
        await _run("input keyevent 82")

    async def handle_screen_off(call):
        await _run("input keyevent 223")

    async def handle_brightness(call):
        value = call.data["brightness"]
        await _run(f"settings put system screen_brightness {value}")
        await _run("settings put system screen_brightness_mode 0")

    async def handle_open_url(call):
        url = call.data["url"]
        await _run(f'am start -a android.intent.action.VIEW -d "{url}"')

    async def handle_open_app(call):
        pkg = call.data["package"]
        await _run(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")

    async def handle_set_volume(call):
        volume = call.data["volume"]
        raw = max(0, min(20, round(volume * 20 / 100)))
        await _run(f"media volume --stream 3 --set {raw}")

    async def handle_reboot(call):
        eids = call.data.get("entity_id")
        if eids:
            reg = hass.helpers.entity_registry.async_get(hass)
            for eid in eids:
                ent = reg.async_get(eid)
                if ent and ent.config_entry_id:
                    _LOGGER.info("frame_control: reboot по entity %s (entry %s)", eid, ent.config_entry_id)
                    await hass.async_add_executor_job(
                        _shell_for_entry, hass, ent.config_entry_id, "reboot", 30
                    )
                else:
                    _LOGGER.warning("frame_control: entity %s не найдена", eid)
        else:
            await _run("reboot", timeout=30)

    async def handle_screenshot(call):
        fname = f"frame_{entry.entry_id[:4]}.png"
        path = os.path.join(shot_dir, fname)
        raw = await _run("screencap -p", 20, decode=False)
        if not isinstance(raw, bytes):
            raw = raw.encode("latin-1", errors="ignore")
        with open(path, "wb") as f:
            f.write(raw)

    hass.services.async_register(
        DOMAIN, "screen_on", handle_screen_on, SCREEN_ON_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "screen_off", handle_screen_off, SCREEN_OFF_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "set_brightness", handle_brightness, BRIGHTNESS_SCHEMA
    )
    hass.services.async_register(DOMAIN, "open_url", handle_open_url, OPEN_URL_SCHEMA)
    hass.services.async_register(DOMAIN, "open_app", handle_open_app, OPEN_APP_SCHEMA)
    hass.services.async_register(
        DOMAIN, "set_volume", handle_set_volume, SET_VOLUME_SCHEMA
    )
    hass.services.async_register(DOMAIN, "reboot", handle_reboot, REBOOT_SCHEMA)
    hass.services.async_register(
        DOMAIN, "screenshot", handle_screenshot, SCREENSHOT_SCHEMA
    )

    # --- платформы (сущности) ---
    platforms = ["switch", "number", "button"]
    if device_type == "frame":
        platforms.append("sensor")
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # --- Часы-рамка: показываем большие часы сразу после старта HA ---
    if device_type == "frame":

        async def _startup_clock():
            await asyncio.sleep(10)
            await _run("am start -n com.google.android.deskclock/com.android.deskclock.DeskClock")
            _LOGGER.info("Рамка: стартовые часы запущены")

        hass.loop.call_later(
            10,
            lambda: hass.async_create_background_task(_startup_clock(), "frame_control_startup_clock"),
        )

        # --- Физическая кнопка (KEYCODE_POWER) -> Алиса, через logcat-опрос ---
        async def _monitor_physical_button():
            while True:
                await asyncio.sleep(8)
                try:
                    # logcat завершается мгновенно (не блокирует ADB как getevent)
                    out = await _run(
                        "logcat -d -t 120 2>/dev/null | grep -E 'KEYCODE_POWER|key.*power|Power' | tail -5",
                        timeout=10,
                    )
                    if "KEYCODE_POWER" in out and "DOWN" in out:
                        _LOGGER.info("Рамка: нажата физическая кнопка — открываю Алису")
                        await _run("input keyevent 224")
                        await _run(
                            "am start -n com.yandex.iot/ru.yandex.searchplugin.MainActivity"
                        )

                        async def _back_to_clock():
                            await asyncio.sleep(120)
                            await _run(
                                "am start -n com.google.android.deskclock/com.android.deskclock.DeskClock"
                            )

                        hass.async_create_background_task(_back_to_clock(), "frame_control_clock_return")
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(5)

        hass.async_create_background_task(_monitor_physical_button(), "frame_control_button_monitor")

    # --- автоматика (только если блоки включены) ---
    motion_timer = None

    async def _show_clock_after_timeout():
        nonlocal motion_timer
        motion_timer = None
        # Экран-рамка: показываем большие часы вместо выключения экрана
        await _run("am start -n com.google.android.deskclock/com.android.deskclock.DeskClock")

    async def _motion_on():
        nonlocal motion_timer
        await _run("input keyevent 224")
        await _run("wm dismiss-keyguard")
        # Режим "часы по умолчанию": движение НЕ открывает Алису
        if motion_timer is not None:
            motion_timer.cancel()

        def _cb():
            hass.async_create_task(_show_clock_after_timeout())

        motion_timer = hass.loop.call_later(motion_timeout, _cb)

    async def _motion_off():
        nonlocal motion_timer
        if motion_timer is not None:
            motion_timer.cancel()
            motion_timer = None
        await _run("am start -n com.google.android.deskclock/com.android.deskclock.DeskClock")

    async def _handle_motion(event):
        ns = event.data.get("new_state")
        if ns is None:
            return
        if ns.state in ("on", "home", "detected", "open", "1"):
            await _motion_on()
        elif ns.state in ("off", "not_home", "clear", "closed", "0"):
            await _motion_off()

    if motion_sensor:
        async_track_state_change_event(hass, [motion_sensor], _handle_motion)
        _LOGGER.info("Блок движения активен: %s", motion_sensor)

    async def _handle_illuminance(event):
        ns = event.data.get("new_state")
        if ns is None or ns.state in ("unknown", "unavailable"):
            return
        try:
            lux = float(ns.state)
        except (TypeError, ValueError):
            return
        ratio = max(0.0, min(1.0, (lux - lux_min) / max(1, (lux_max - lux_min))))
        brightness = int(bright_min + ratio * (bright_max - bright_min))
        await _run(f"settings put system screen_brightness {brightness}")
        await _run("settings put system screen_brightness_mode 0")

    if illum_sensor:
        async_track_state_change_event(hass, [illum_sensor], _handle_illuminance)
        _LOGGER.info("Блок освещённости активен: %s", illum_sensor)

    # --- IP Webcam watchdog ---
    if watchdog_enabled and device_type == "frame":

        _CLOCK_APP = "am start -n com.google.android.deskclock/com.android.deskclock.DeskClock"

        async def _restart_ipwebcam():
            proc = await _run("ps -A | grep com.pas.webcam", timeout=15)
            if "com.pas.webcam" not in proc:
                _LOGGER.warning("IP Webcam процесс мёртв — запускаю Rolling")
                await _run("su 0 am start -n com.pas.webcam/.Rolling", timeout=15)
                await asyncio.sleep(6)
            await _run(
                "su 0 am start -n com.pas.webcam/.Rolling "
                "--ez start_server_on_boot true --ez notification true",
                timeout=15,
            )
            await asyncio.sleep(4)
            await _run(_CLOCK_APP, timeout=15)
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, ipwebcam_port), timeout=3
                )
                writer.close()
                await writer.wait_closed()
                _LOGGER.info("IP Webcam перезапущен и отвечает")
                await _run(_CLOCK_APP, timeout=15)
                return
            except (OSError, asyncio.TimeoutError):
                pass
            await _run(
                "su 0 am start -n com.pas.webcam/.Rolling "
                "--ez start_server_on_boot true --ez notification true",
                timeout=15,
            )
            await _run(_CLOCK_APP, timeout=15)

        async def _check_ipwebcam(_now=None):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, ipwebcam_port), timeout=3
                )
                writer.close()
                await writer.wait_closed()
                return
            except (OSError, asyncio.TimeoutError):
                pass

            _LOGGER.warning(
                "IP Webcam %s:%s не отвечает — перезапускаю", host, ipwebcam_port
            )
            await _restart_ipwebcam()

        entry.async_on_unload(
            async_track_time_interval(
                hass, _check_ipwebcam, timedelta(seconds=watchdog_interval)
            )
        )
        _LOGGER.info(
            "IP Webcam watchdog активен: %s:%s каждые %s сек",
            host,
            ipwebcam_port,
            watchdog_interval,
        )

    async def async_unload_entry(hass, entry):
        platforms = ["switch", "number", "button"]
        if device_type == "frame":
            platforms.append("sensor")
        for platform in platforms:
            await hass.config_entries.async_forward_entry_unload(entry, platform)
        return True

    entry.async_on_unload(async_unload_entry)
    _LOGGER.info("Frame Control v7 (%s:%s, тип=%s) готов", host, port, device_type)
    return True


async def async_unload_entry(hass, entry):
    return True
