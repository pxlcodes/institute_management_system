from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable

from elh.hardware.attendance.base import AttendanceDeviceError
from elh.services.attendance import AttendanceService, AttendanceSyncResult

logger = logging.getLogger("elh.attendance.poller")


class AttendancePoller:
    """Thread-safe background daemon that polls the biometric attendance terminal."""

    def __init__(
        self,
        service: AttendanceService,
        interval_seconds: int = 60,
        enabled: bool = True,
        on_punches_imported: Callable[[AttendanceSyncResult], None] | None = None,
    ):
        self.service = service
        self.interval_seconds = max(5, int(interval_seconds))
        self._enabled = bool(enabled)
        self.on_punches_imported = on_punches_imported

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Operational metrics and status
        self.last_polled_at: datetime | None = None
        self.last_saved_count: int = 0
        self.total_saved_count: int = 0
        self.poll_count: int = 0
        self.last_error: str | None = None
        self.device_healthy: bool = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if self._enabled and not self.is_running:
            self.start()
        elif not self._enabled and self.is_running:
            self.stop()

    def set_interval(self, seconds: int) -> None:
        self.interval_seconds = max(5, int(seconds))

    def start(self) -> bool:
        """Start the background polling worker thread."""
        with self._lock:
            if not self._enabled:
                logger.info("Attendance poller is disabled; not starting background thread.")
                return False
            if self.is_running:
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="elh-attendance-poller",
            )
            self._thread.start()
            logger.info("Attendance background poller started (interval: %ds).", self.interval_seconds)
            return True

    def stop(self, timeout: float = 3.0) -> None:
        """Signal the polling thread to stop and wait for completion."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("Attendance background poller stopped.")

    def poll_now(self) -> AttendanceSyncResult:
        """Perform a single, thread-safe sync immediately."""
        with self._lock:
            try:
                result = self.service.sync()
                self.last_polled_at = datetime.now()
                self.last_saved_count = result.saved
                self.total_saved_count += result.saved
                self.poll_count += 1
                self.last_error = None
                self.device_healthy = True

                if result.saved > 0:
                    logger.info(
                        "Auto-imported %d new attendance punch(es) (received %d total).",
                        result.saved,
                        result.received,
                    )
                    if self.on_punches_imported:
                        try:
                            self.on_punches_imported(result)
                        except Exception as callback_err:
                            logger.warning("Error in on_punches_imported callback: %s", callback_err)

                return result
            except AttendanceDeviceError as exc:
                self.last_polled_at = datetime.now()
                self.last_error = str(exc)
                self.device_healthy = False
                logger.warning("Attendance device sync failed: %s", exc)
                raise
            except Exception as exc:
                self.last_polled_at = datetime.now()
                self.last_error = str(exc)
                self.device_healthy = False
                logger.exception("Unexpected error during attendance sync: %s", exc)
                raise

    def _worker_loop(self) -> None:
        """Continuous background polling loop."""
        # Initial short pause before first poll
        self._stop_event.wait(2.0)
        while not self._stop_event.is_set():
            if self._enabled:
                try:
                    self.poll_now()
                except Exception:
                    pass  # Already logged in poll_now

            # Wait for next interval or stop signal
            self._stop_event.wait(self.interval_seconds)

    def status(self) -> dict:
        """Return structured runtime telemetry."""
        return {
            "enabled": self._enabled,
            "running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "last_polled_at": self.last_polled_at.isoformat(sep=" ", timespec="seconds") if self.last_polled_at else None,
            "last_saved_count": self.last_saved_count,
            "total_saved_count": self.total_saved_count,
            "poll_count": self.poll_count,
            "last_error": self.last_error,
            "device_healthy": self.device_healthy,
        }
