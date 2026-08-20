from __future__ import annotations

from typing import Protocol

from elh.models import AttendanceDeviceUser, AttendanceEvent


class AttendanceDeviceError(RuntimeError):
    pass


class AttendanceDevice(Protocol):
    def fetch_events(self) -> list[AttendanceEvent]: ...
    def fetch_users(self) -> list[AttendanceDeviceUser]: ...
    def health(self) -> tuple[bool, str]: ...
