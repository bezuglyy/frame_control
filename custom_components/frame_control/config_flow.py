"""Config flow для Frame Control — рамки и телевизоры, условные блоки датчиков."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import selector

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_LABELS = {
    "frame": "Рамка (X08C)",
    "tv": "Телевизор (Android TV)",
}

BASE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=5555): int,
        vol.Optional("device_type", default="frame"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"label": v, "value": k} for k, v in DEVICE_TYPE_LABELS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional("enable_motion", default=False): bool,
        vol.Optional("enable_illuminance", default=False): bool,
        vol.Optional("watchdog_enabled", default=False): bool,
        vol.Optional("ipwebcam_port", default=8080): int,
        vol.Optional("watchdog_interval", default=30): int,
    }
)

MOTION_SCHEMA = vol.Schema(
    {
        vol.Optional("motion_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        ),
        vol.Optional("motion_timeout", default=120): int,
    }
)

ILLUM_SCHEMA = vol.Schema(
    {
        vol.Optional("illuminance_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional("lux_min", default=0): int,
        vol.Optional("lux_max", default=2000): int,
        vol.Optional("brightness_min", default=30): int,
        vol.Optional("brightness_max", default=255): int,
    }
)


class FrameControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow для Frame Control."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Шаг 1: базовые параметры и галочки блоков."""
        errors = {}
        if user_input is not None:
            if self._host_already_configured(user_input[CONF_HOST]):
                errors["base"] = "already_configured"
            else:
                self._conf = dict(user_input)
                if user_input.get("enable_motion"):
                    return await self.async_step_motion()
                if user_input.get("enable_illuminance"):
                    return await self.async_step_illuminance()
                return self._create_entry()
        return self.async_show_form(
            step_id="user",
            data_schema=BASE_SCHEMA,
            errors=errors,
        )

    async def async_step_motion(self, user_input=None):
        """Шаг 2a: датчик движения (если блок включён)."""
        if user_input is not None:
            self._conf.update(user_input)
            if self._conf.get("enable_illuminance"):
                return await self.async_step_illuminance()
            return self._create_entry()
        return self.async_show_form(step_id="motion", data_schema=MOTION_SCHEMA)

    async def async_step_illuminance(self, user_input=None):
        """Шаг 2b: датчик освещённости (если блок включён)."""
        if user_input is not None:
            self._conf.update(user_input)
            return self._create_entry()
        return self.async_show_form(step_id="illuminance", data_schema=ILLUM_SCHEMA)

    def _create_entry(self):
        device_type = self._conf.get("device_type", "frame")
        label = DEVICE_TYPE_LABELS.get(device_type, "Устройство")
        return self.async_create_entry(
            title=f"{label} {self._conf[CONF_HOST]}",
            data=self._conf,
        )

    def _host_already_configured(self, host):
        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == host:
                return True
        return False

    @staticmethod
    def async_get_options_flow(config_entry):
        """Поток изменения настроек."""
        return FrameControlOptionsFlow(config_entry)


class FrameControlOptionsFlow(config_entries.OptionsFlow):
    """Изменение настроек Frame Control."""

    def __init__(self, config_entry):
        self._entry = config_entry
        self._conf = {}

    async def async_step_init(self, user_input=None):
        """Шаг 1: базовые параметры и галочки."""
        if user_input is not None:
            self._conf = dict(user_input)
            if user_input.get("enable_motion"):
                return await self.async_step_motion()
            if user_input.get("enable_illuminance"):
                return await self.async_step_illuminance()
            return self._create_entry()
        data = self._entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
                    vol.Required(CONF_PORT, default=data.get(CONF_PORT, 5555)): int,
                    vol.Optional(
                        "device_type", default=data.get("device_type", "frame")
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"label": v, "value": k}
                                for k, v in DEVICE_TYPE_LABELS.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "enable_motion",
                        default=data.get(
                            "enable_motion", bool(data.get("motion_sensor"))
                        ),
                    ): bool,
                    vol.Optional(
                        "enable_illuminance",
                        default=data.get(
                            "enable_illuminance",
                            bool(data.get("illuminance_sensor")),
                        ),
                    ): bool,
                    vol.Optional(
                        "watchdog_enabled",
                        default=data.get("watchdog_enabled", False),
                    ): bool,
                    vol.Optional(
                        "ipwebcam_port", default=data.get("ipwebcam_port", 8080)
                    ): int,
                    vol.Optional(
                        "watchdog_interval",
                        default=data.get("watchdog_interval", 30),
                    ): int,
                }
            ),
        )

    async def async_step_motion(self, user_input=None):
        """Шаг 2a: датчик движения."""
        if user_input is not None:
            self._conf.update(user_input)
            if self._conf.get("enable_illuminance"):
                return await self.async_step_illuminance()
            return self._create_entry()
        data = self._entry.data
        return self.async_show_form(
            step_id="motion",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "motion_sensor",
                        default=data.get("motion_sensor"),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    ),
                    vol.Optional(
                        "motion_timeout",
                        default=data.get("motion_timeout", 120),
                    ): int,
                }
            ),
        )

    async def async_step_illuminance(self, user_input=None):
        """Шаг 2b: датчик освещённости."""
        if user_input is not None:
            self._conf.update(user_input)
            return self._create_entry()
        data = self._entry.data
        return self.async_show_form(
            step_id="illuminance",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "illuminance_sensor",
                        default=data.get("illuminance_sensor"),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional("lux_min", default=data.get("lux_min", 0)): int,
                    vol.Optional("lux_max", default=data.get("lux_max", 2000)): int,
                    vol.Optional(
                        "brightness_min", default=data.get("brightness_min", 30)
                    ): int,
                    vol.Optional(
                        "brightness_max", default=data.get("brightness_max", 255)
                    ): int,
                }
            ),
        )

    def _create_entry(self):
        data = dict(self._entry.data)
        if not self._conf.get("enable_motion"):
            data.pop("motion_sensor", None)
            data.pop("motion_timeout", None)
        if not self._conf.get("enable_illuminance"):
            data.pop("illuminance_sensor", None)
            data.pop("lux_min", None)
            data.pop("lux_max", None)
            data.pop("brightness_min", None)
            data.pop("brightness_max", None)
        data.pop("camera_entity", None)
        data.pop("camera_url", None)
        return self.async_create_entry(title="", data={**data, **self._conf})
