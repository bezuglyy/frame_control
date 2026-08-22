"""Общие функции Frame Control."""

import logging

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

_LOGGER = logging.getLogger(__name__)

ADBKEY = "/config/adbkey"


def shell(host, port, cmd, timeout=15, decode=True):
    """Выполнить команду по ADB. Не бросает исключений — при ошибке возвращает пустой результат."""
    try:
        signer = PythonRSASigner.FromRSAKeyPath(ADBKEY)
        dev = AdbDeviceTcp(host, port, default_transport_timeout_s=timeout)
        dev.connect(rsa_keys=[signer], auth_timeout_s=15)
        res = dev.shell(cmd, timeout_s=timeout, decode=decode)
        return res if res is not None else ("" if decode else b"")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "ADB недоступен %s:%s (cmd=%s): %s",
            host,
            port,
            str(cmd).split()[0],
            exc,
        )
        return "" if decode else b""
    finally:
        try:
            dev.close()
        except Exception:  # noqa: BLE001
            pass
