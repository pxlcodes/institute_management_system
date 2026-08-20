from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AttendanceEvent:
    device_user_id: str
    occurred_at: datetime
    event_type: str = "check-in"
    device_serial: str = ""
    verification_mode: str = "unknown"


@dataclass(frozen=True)
class AttendanceDeviceUser:
    """A user record read from an attendance device directory."""

    device_user_id: str
    name: str = ""
    uid: int | None = None
    privilege: str = ""
    card_number: str = ""
    device_serial: str = ""


@dataclass(frozen=True)
class DeviceUserMapping:
    device_user_id: str
    person_type: str
    person_id: int
