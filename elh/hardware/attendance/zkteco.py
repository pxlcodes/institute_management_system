from __future__ import annotations

from elh.models import AttendanceDeviceUser, AttendanceEvent
from .base import AttendanceDeviceError


class ZKTecoAttendanceDevice:
    """pyzk adapter; pyzk is imported only when the device is actually used."""

    def __init__(self, host: str, port: int = 4370, password: int = 0, timeout: int = 10):
        if not host:
            raise ValueError("ELH_ZKTECO_HOST is required when the ZKTeco driver is enabled.")
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    def _client(self):
        try:
            from zk import ZK
        except ImportError as exc:
            raise AttendanceDeviceError(
                "ZKTeco support requires: python -m pip install -r requirements-hardware.txt"
            ) from exc
        client = ZK(
            self.host,
            port=self.port,
            timeout=self.timeout,
            password=self.password,
            force_udp=False,
            ommit_ping=False,
        )
        # pyzk creates a UDP socket in its constructor and then overwrites it
        # with a TCP socket in connect(). Close that unused socket first.
        initial_socket = getattr(client, "_ZK__sock", None)
        if initial_socket is not None:
            initial_socket.close()
        return client

    @staticmethod
    def _close_connection(connection) -> None:
        """Close pyzk cleanly even when its disconnect command is rejected."""
        try:
            connection.disconnect()
        except Exception:
            # Some firmware does not acknowledge CMD_EXIT. pyzk then leaves
            # its private socket open, so the raw close below is still needed.
            pass
        raw_socket = getattr(connection, "_ZK__sock", None)
        if raw_socket is not None:
            try:
                raw_socket.close()
            except OSError:
                pass

    def fetch_events(self) -> list[AttendanceEvent]:
        connection = None
        try:
            connection = self._client().connect()
            serial = str(connection.get_serialnumber() or "")
            records = connection.get_attendance() or []
            return [
                AttendanceEvent(
                    device_user_id=str(record.user_id), occurred_at=record.timestamp,
                    event_type="check-in" if getattr(record, "punch", 0) in (0, 4) else "check-out",
                    device_serial=serial, verification_mode=str(getattr(record, "status", "unknown")),
                ) for record in records
            ]
        except AttendanceDeviceError:
            raise
        except Exception as exc:
            raise AttendanceDeviceError(f"Cannot read ZKTeco device at {self.host}:{self.port}: {exc}") from exc
        finally:
            if connection is not None:
                self._close_connection(connection)

    def fetch_users(self) -> list[AttendanceDeviceUser]:
        """Read user IDs and names stored in the ZKTeco device."""
        connection = None
        try:
            connection = self._client().connect()
            serial = str(connection.get_serialnumber() or "")
            users = connection.get_users() or []
            return [
                AttendanceDeviceUser(
                    device_user_id=str(user.user_id),
                    name=str(getattr(user, "name", "") or "").strip(),
                    uid=int(user.uid) if getattr(user, "uid", None) is not None else None,
                    privilege=str(getattr(user, "privilege", "") or ""),
                    card_number=str(getattr(user, "card", "") or ""),
                    device_serial=serial,
                )
                for user in users
            ]
        except AttendanceDeviceError:
            raise
        except Exception as exc:
            raise AttendanceDeviceError(
                f"Cannot read users from ZKTeco device at {self.host}:{self.port}: {exc}"
            ) from exc
        finally:
            if connection is not None:
                self._close_connection(connection)

    def health(self) -> tuple[bool, str]:
        connection = None
        try:
            connection = self._client().connect()
            return True, f"Connected to ZKTeco {connection.get_device_name()}"
        except Exception as exc:
            return False, str(exc)
        finally:
            if connection is not None:
                self._close_connection(connection)
