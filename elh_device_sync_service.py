"""Institute Device Gateway & Synchronization Service.

This service runs continuously on the Institute Admin PC to bridge
local LAN devices (ZKTeco Biometric & ESC/POS Receipt Printer) with the
remote cPanel server.

Modes of Operation:
1. HTTP Cloud Sync (Recommended):
   Communicates over HTTPS to the cPanel web app via /api/sync/* endpoints.
   No router port-forwarding or static public IP required.
2. Direct Database Sync:
   Connects directly to the cPanel MySQL database when Remote MySQL is enabled.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from elh.config import AppConfig, ROOT_DIR, load_config
from elh.hardware.attendance.zkteco import ZKTecoAttendanceDevice
from elh.hardware.printing.cloud_spool import dict_to_receipt
from elh.hardware.printing.network_escpos import NetworkEscPosPrinter
from elh.models import AttendanceEvent


def configure_service_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "device_sync.log"
    logger = logging.getLogger("elh.device_sync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


class DeviceSyncService:
    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.cloud_url = os.environ.get("ELH_CLOUD_URL", "").strip().rstrip("/")
        self.sync_token = os.environ.get("ELH_SYNC_API_TOKEN", "").strip() or (config.secret_key or "").strip()
        self.poll_interval = max(5, int(os.environ.get("ELH_ATTENDANCE_POLL_INTERVAL", "30")))
        self.print_check_interval = max(2, int(os.environ.get("ELH_PRINT_POLL_INTERVAL", "4")))
        self.last_attendance_poll = 0.0
        self.last_print_poll = 0.0
        self.running = True

        # Initialize local hardware adapters
        self.attendance_device = None
        if config.attendance_driver == "zkteco" and config.zkteco_host:
            self.attendance_device = ZKTecoAttendanceDevice(
                host=config.zkteco_host,
                port=config.zkteco_port,
                password=config.zkteco_password,
                timeout=config.zkteco_timeout_seconds,
            )

        self.pos_printer = None
        if config.pos_printer_driver == "network_escpos" and config.pos_printer_host:
            self.pos_printer = NetworkEscPosPrinter(
                host=config.pos_printer_host,
                port=config.pos_printer_port,
                width=config.pos_printer_chars_per_line,
            )

    def _http_request(self, path: str, method: str = "GET", data: dict | None = None) -> dict | None:
        if not self.cloud_url:
            return None
        url = f"{self.cloud_url}/api/sync/{path.lstrip('/')}"
        headers = {
            "User-Agent": "ELH-Institute-Device-Sync/1.0",
            "Content-Type": "application/json",
            "X-Sync-Token": self.sync_token,
        }
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            err_msg = exc.read().decode("utf-8", errors="replace")
            self.logger.error("Cloud HTTP error (%s %s): %s - %s", method, url, exc.code, err_msg)
            return None
        except Exception as exc:
            self.logger.error("Cloud connection failed (%s %s): %s", method, url, exc)
            return None

    def poll_biometric_attendance(self) -> None:
        if not self.attendance_device:
            return
        self.logger.info("Connecting to ZKTeco device at %s:%s ...", self.config.zkteco_host, self.config.zkteco_port)
        try:
            events = self.attendance_device.fetch_events()
            if not events:
                self.logger.info("No punch events retrieved from biometric machine.")
                return

            self.logger.info("Fetched %d raw punch events from biometric machine.", len(events))
            
            # Send events to cloud server if cloud_url configured
            if self.cloud_url:
                payload = {
                    "events": [
                        {
                            "device_user_id": e.device_user_id,
                            "occurred_at": e.occurred_at.isoformat(),
                            "event_type": e.event_type,
                            "device_serial": e.device_serial,
                            "verification_type": e.verification_type,
                        }
                        for e in events
                    ]
                }
                res = self._http_request("device-attendance-push", method="POST", data=payload)
                if res and res.get("ok"):
                    self.logger.info(
                        "Attendance push to cloud SUCCESS: %d received, %d saved, %d unmapped.",
                        res.get("received", 0), res.get("saved", 0), res.get("unmapped", 0)
                    )
                else:
                    self.logger.warning("Attendance push to cloud did not acknowledge success.")
            else:
                # Direct database sync mode
                from elh.infrastructure import create_database
                from elh.repositories import AttendanceRepository
                db = create_database(self.config)
                repo = AttendanceRepository(db)
                mappings = repo.mappings_for([e.device_user_id for e in events])
                saved = repo.save_events(events, mappings)
                unmapped = sum(1 for e in events if e.device_user_id not in mappings)
                self.logger.info(
                    "Direct DB Attendance sync SUCCESS: %d received, %d saved, %d unmapped.",
                    len(events), saved, unmapped
                )
        except Exception as exc:
            self.logger.error("Attendance polling cycle failed: %s", exc)

    def check_and_print_pos_spool(self) -> None:
        if not self.pos_printer:
            return

        job_info = None
        if self.cloud_url:
            res = self._http_request("pos-print-queue/pull", method="GET")
            if res and res.get("job"):
                job_info = res["job"]
        else:
            # Direct database pull
            from elh.infrastructure import create_database
            db = create_database(self.config)
            row = db.query_one(
                "SELECT id, receipt_number, customer_name, title, payload_json "
                "FROM pos_print_queue WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
            )
            if row:
                try:
                    payload = json.loads(row["payload_json"])
                    job_info = {
                        "id": row["id"],
                        "receipt_number": row["receipt_number"],
                        "customer_name": row["customer_name"],
                        "title": row["title"],
                        "payload": payload,
                    }
                except Exception as exc:
                    self.logger.error("Failed to parse local print job payload: %s", exc)

        if not job_info:
            return

        job_id = job_info["id"]
        receipt_no = job_info.get("receipt_number", "")
        self.logger.info("Found pending POS print job #%d (%s) - Printing to %s:%s ...",
                         job_id, receipt_no, self.config.pos_printer_host, self.config.pos_printer_port)
        try:
            receipt = dict_to_receipt(job_info["payload"])
            self.pos_printer.print_receipt(receipt)
            self.logger.info("POS print job #%d printed successfully!", job_id)

            if self.cloud_url:
                self._http_request(f"pos-print-queue/{job_id}/status", method="POST", data={"status": "printed"})
            else:
                from elh.infrastructure import create_database
                db = create_database(self.config)
                db.execute(
                    "UPDATE pos_print_queue SET status = 'printed', printed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (job_id,)
                )
        except Exception as exc:
            self.logger.error("Failed to print job #%d: %s", job_id, exc)
            if self.cloud_url:
                self._http_request(f"pos-print-queue/{job_id}/status", method="POST", data={"status": "failed", "error_message": str(exc)})
            else:
                from elh.infrastructure import create_database
                db = create_database(self.config)
                db.execute(
                    "UPDATE pos_print_queue SET status = 'failed', error_message = ? WHERE id = ?",
                    (str(exc), job_id)
                )

    def start(self) -> None:
        self.logger.info("=" * 60)
        self.logger.info("  ELH Institute Device Gateway Service Started")
        self.logger.info("=" * 60)
        self.logger.info("Mode: %s", "Cloud HTTP Sync (" + self.cloud_url + ")" if self.cloud_url else "Direct Remote Database")
        self.logger.info("ZKTeco Attendance Device: %s:%d (Poll every %ds)",
                         self.config.zkteco_host or "Disabled", self.config.zkteco_port, self.poll_interval)
        self.logger.info("ESC/POS Receipt Printer:  %s:%d (Check every %ds)",
                         self.config.pos_printer_host or "Disabled", self.config.pos_printer_port, self.print_check_interval)
        self.logger.info("Running live sync loop. Press Ctrl+C to stop.")

        while self.running:
            now = time.time()
            # 1. Check POS print spool queue frequently
            if now - self.last_print_poll >= self.print_check_interval:
                self.last_print_poll = now
                try:
                    self.check_and_print_pos_spool()
                except Exception as exc:
                    self.logger.error("Error in print spool worker: %s", exc)

            # 2. Poll Attendance periodically
            if now - self.last_attendance_poll >= self.poll_interval:
                self.last_attendance_poll = now
                try:
                    self.poll_biometric_attendance()
                except Exception as exc:
                    self.logger.error("Error in attendance poller worker: %s", exc)

            time.sleep(1.0)


def main() -> int:
    config = load_config()
    logger = configure_service_logging(config.log_directory)
    service = DeviceSyncService(config, logger)
    try:
        service.start()
        return 0
    except KeyboardInterrupt:
        logger.info("Service shutting down cleanly on user request.")
        return 0
    except Exception as exc:
        logger.critical("Fatal error in device sync service: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
