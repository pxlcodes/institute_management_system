"""Read-only production health checks shared by all presentation adapters."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from elh.config import AppConfig
from elh.core.backup import BackupError, BackupService
from elh.infrastructure.schema_optimizer import LATEST_SCHEMA_VERSION


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str
    detail: str


class HealthService:
    """Collect health without creating tables, running migrations, or changing data."""

    def __init__(self, config: AppConfig, database=None):
        self.config = config
        self.database = database

    def checks(self) -> list[HealthCheck]:
        return [
            self._database(),
            self._schema(),
            self._storage(),
            self._logging(),
            self._configuration(),
            self._backup(),
            self._attendance(),
            self._printer(),
            self._sms(),
        ]

    def report(self) -> dict[str, object]:
        checks = self.checks()
        return {
            "status": "healthy" if all(check.status == "ok" for check in checks) else "degraded",
            "environment": self.config.environment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": [asdict(check) for check in checks],
        }

    def _query_one(self, sql: str, params=()):
        if self.database is not None:
            return self.database.query_one(sql, params)
        if self.config.database_engine == "mysql":
            try:
                import mysql.connector
            except ImportError as exc:
                raise RuntimeError("MySQL Python driver is not installed") from exc
            connection = mysql.connector.connect(
                host=self.config.database_host,
                port=self.config.database_port,
                database=self.config.database_name,
                user=self.config.database_user,
                password=self.config.database_password,
                connection_timeout=5,
            )
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute(sql.replace("?", "%s"), tuple(params))
                return cursor.fetchone()
            finally:
                connection.close()
        with closing(sqlite3.connect(self.config.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(sql, tuple(params)).fetchone()

    def _database(self) -> HealthCheck:
        try:
            if self.config.database_engine == "mysql":
                row = self._query_one("SELECT DATABASE() AS database_name, VERSION() AS version")
                return HealthCheck(
                    "database",
                    "ok",
                    f"MySQL {row['version']} / {row['database_name']}",
                )
            row = self._query_one("PRAGMA integrity_check")
            result = row[0] if row is not None else "no result"
            return HealthCheck("database", "ok" if result == "ok" else "error", str(result))
        except Exception as exc:
            return HealthCheck("database", "error", str(exc))

    def _schema(self) -> HealthCheck:
        try:
            row = self._query_one("SELECT MAX(version) AS version FROM schema_migrations")
            version = int(row["version"] or 0)
            if version < LATEST_SCHEMA_VERSION:
                return HealthCheck(
                    "schema",
                    "warning",
                    f"Migration level {version}; required {LATEST_SCHEMA_VERSION}",
                )
            return HealthCheck("schema", "ok", f"Migration level {version} is current")
        except Exception as exc:
            return HealthCheck("schema", "warning", f"Schema metadata unavailable: {exc}")

    def _storage(self) -> HealthCheck:
        if self.config.database_engine == "mysql":
            detail = f"MySQL server: {self.config.database_host}:{self.config.database_port}"
            return HealthCheck("storage", "ok", detail)
        parent = self.config.database_path.parent
        writable = parent.exists() and os.access(parent, os.W_OK)
        return HealthCheck(
            "storage",
            "ok" if writable else "error",
            f"Database directory: {parent}",
        )

    def _logging(self) -> HealthCheck:
        directory = self.config.log_directory
        candidate = directory if directory.exists() else directory.parent
        writable = candidate.exists() and os.access(candidate, os.W_OK)
        return HealthCheck(
            "logging",
            "ok" if writable else "error",
            f"Rotating logs: {directory}",
        )

    def _configuration(self) -> HealthCheck:
        issues: list[str] = []
        status = "ok"
        if self.config.environment.lower() != "production":
            issues.append(f"Environment is {self.config.environment}, not production")
            status = "warning"
        if self.config.database_engine == "mysql" and not self.config.database_password:
            issues.append("MySQL database password is empty")
            status = "error"
        if self.config.environment.lower() == "production":
            if self.config.database_engine == "mysql" and self.config.database_user.lower() == "root":
                issues.append("Use a dedicated least-privilege MySQL account instead of root")
                status = "warning" if status != "error" else status
            if any(
                (
                    self.config.operator_password,
                    self.config.admin_password,
                    self.config.maintenance_password,
                )
            ):
                issues.append("Blank bootstrap passwords in .env after the accounts are created")
                status = "warning" if status != "error" else status
        return HealthCheck(
            "configuration",
            status,
            "; ".join(issues) if issues else "Production configuration checks passed",
        )

    def _backup(self) -> HealthCheck:
        directory = self.config.backup_directory
        pattern = "*.sql" if self.config.database_engine == "mysql" else "*.db"
        backups = list(directory.glob(pattern)) if directory.exists() else []
        if not backups:
            available, detail = BackupService(self.config).tool_status()
            suffix = "" if available else f"; {detail}"
            return HealthCheck("backup", "warning", f"No database backup found{suffix}")
        newest = max(backups, key=lambda path: path.stat().st_mtime)
        age_hours = (datetime.now().timestamp() - newest.stat().st_mtime) / 3600
        try:
            BackupService(self.config).verify(newest)
        except (BackupError, OSError) as exc:
            return HealthCheck("backup", "error", f"Latest backup failed verification: {exc}")
        status = "ok" if age_hours <= self.config.health_stale_backup_hours else "warning"
        return HealthCheck(
            "backup",
            status,
            f"Latest verified: {newest.name} ({age_hours:.1f} hours old)",
        )

    def _attendance(self) -> HealthCheck:
        try:
            from elh.hardware.factory import create_attendance_device

            ok, detail = create_attendance_device(self.config).health()
            return HealthCheck("attendance_device", "ok" if ok else "warning", detail)
        except Exception as exc:
            return HealthCheck("attendance_device", "warning", str(exc))

    def _printer(self) -> HealthCheck:
        try:
            from elh.hardware.factory import create_receipt_printer

            ok, detail = create_receipt_printer(self.config).health()
            return HealthCheck("pos_printer", "ok" if ok else "warning", detail)
        except Exception as exc:
            return HealthCheck("pos_printer", "warning", str(exc))

    def _sms(self) -> HealthCheck:
        try:
            enabled = self._query_one(
                "SELECT setting_value FROM settings WHERE setting_key='sms_enabled'"
            )
            if not enabled or str(enabled["setting_value"] or "").lower() not in {
                "1", "true", "yes", "on"
            }:
                return HealthCheck("sms_notifications", "ok", "Automatic SMS is disabled")
            provider_row = self._query_one(
                "SELECT setting_value FROM settings WHERE setting_key='sms_provider'"
            )
            provider = str(provider_row["setting_value"] or "").strip().lower()
            if provider == "aakash":
                if not self.config.aakash_sms_token.strip():
                    return HealthCheck(
                        "sms_notifications", "error", "Aakash SMS token is missing"
                    )
                endpoint = self.config.aakash_sms_endpoint
            elif provider == "sparrow":
                sender = self._query_one(
                    "SELECT setting_value FROM settings WHERE setting_key='sms_sender_id'"
                )
                if not self.config.sparrow_sms_token.strip():
                    return HealthCheck(
                        "sms_notifications", "error", "Sparrow SMS token is missing"
                    )
                if not sender or not str(sender["setting_value"] or "").strip():
                    return HealthCheck(
                        "sms_notifications", "error", "Sparrow sender ID is missing"
                    )
                endpoint = self.config.sparrow_sms_endpoint
            else:
                return HealthCheck(
                    "sms_notifications", "error", "SMS provider is invalid"
                )
            status = "ok" if endpoint.lower().startswith("https://") else "warning"
            return HealthCheck(
                "sms_notifications",
                status,
                f"{provider.title()} SMS configured at {endpoint}",
            )
        except Exception as exc:
            return HealthCheck(
                "sms_notifications", "warning", f"SMS settings unavailable: {exc}"
            )
