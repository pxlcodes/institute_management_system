from __future__ import annotations

from elh.config import AppConfig
from .attendance.disabled import DisabledAttendanceDevice, UnavailableAttendanceDevice
from .attendance.zkteco import ZKTecoAttendanceDevice
from .printing.disabled import DisabledReceiptPrinter, UnavailableReceiptPrinter
from .printing.network_escpos import NetworkEscPosPrinter


def create_attendance_device(config: AppConfig):
    driver = config.attendance_driver.strip().lower()
    if driver in {"", "disabled", "off", "false", "none"}:
        return DisabledAttendanceDevice()
    if driver in {"enabled", "on", "true"}:
        driver = "zkteco"
    if driver == "zkteco":
        try:
            return ZKTecoAttendanceDevice(
                config.zkteco_host, config.zkteco_port,
                config.zkteco_password, config.zkteco_timeout_seconds,
            )
        except ValueError as exc:
            return UnavailableAttendanceDevice(str(exc))
    return UnavailableAttendanceDevice(f"Unsupported attendance driver: {config.attendance_driver}")


def create_receipt_printer(config: AppConfig):
    driver = config.pos_printer_driver.strip().lower()
    if driver in {"", "disabled", "off", "false", "none"}:
        return DisabledReceiptPrinter()
    if driver in {"enabled", "on", "true", "network", "escpos"}:
        driver = "network_escpos"
    if driver == "network_escpos":
        try:
            return NetworkEscPosPrinter(
                config.pos_printer_host, config.pos_printer_port,
                config.pos_printer_chars_per_line,
            )
        except ValueError as exc:
            return UnavailableReceiptPrinter(str(exc))
    return UnavailableReceiptPrinter(f"Unsupported POS printer driver: {config.pos_printer_driver}")
