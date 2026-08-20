"""Environment based configuration with no UI or framework dependencies."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping


def _application_root() -> Path:
    """Return the writable deployment directory in source and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT_DIR = _application_root()
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR)).resolve()
DEFAULT_ENV_FILE = ROOT_DIR / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    app_title: str = "Expert Learning Hub Management System"
    environment: str = "development"
    database_path: Path = ROOT_DIR / "elh_management.db"
    database_engine: str = "sqlite"
    database_host: str = "localhost"
    database_port: int = 3306
    database_name: str = "elhims"
    database_user: str = "root"
    database_password: str = ""
    backup_directory: Path = ROOT_DIR / "backups"
    log_directory: Path = ROOT_DIR / "logs"
    log_level: str = "INFO"
    log_max_bytes: int = 5_000_000
    log_backup_count: int = 5
    session_idle_minutes: int = 20
    mysql_dump_path: str = ""
    mysql_client_path: str = ""
    certificate_template_path: Path = RESOURCE_DIR / "elh" / "assets" / "certificate_template.docx"
    certificate_output_directory: Path = ROOT_DIR / "output" / "certificates"
    certificate_pdf_background_path: Path | None = None
    certificate_number_prefix: str = "EXP"
    certificate_default_instructor: str = ""
    certificate_default_principal: str = ""
    date_format: str = "%Y/%m/%d"
    currency_symbol: str = "Rs."
    window_width: int = 1420
    window_height: int = 860
    min_window_width: int = 1100
    min_window_height: int = 700
    allow_negative_balance: bool = False
    seed_demo_data: bool = False
    health_stale_backup_hours: int = 168
    attendance_driver: str = "disabled"
    zkteco_host: str = ""
    zkteco_port: int = 4370
    zkteco_password: int = 0
    zkteco_timeout_seconds: int = 10
    pos_printer_driver: str = "disabled"
    pos_printer_host: str = ""
    pos_printer_port: int = 9100
    pos_printer_chars_per_line: int = 42
    aakash_sms_token: str = ""
    aakash_sms_endpoint: str = "https://sms.aakashsms.com/sms/v3/send"
    sparrow_sms_token: str = ""
    sparrow_sms_endpoint: str = "https://api.sparrowsms.com/v2/sms/"
    operator_username: str = "operator"
    operator_password: str = "Operator@2025"
    admin_username: str = "admin"
    admin_password: str = "Admin@2025"
    maintenance_username: str = "maintenance"
    maintenance_password: str = "Maintenance@2025"

    def public_values(self) -> dict[str, str]:
        """Serializable values suitable for an admin/configuration API."""
        result: dict[str, str] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            result[item.name] = "" if value is None else str(value)
        return result


def load_config(
    env_file: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    """Load config from defaults, a .env file, then process environment variables."""
    path = Path(env_file) if env_file else DEFAULT_ENV_FILE
    values = _read_env_file(path)
    values.update(dict(os.environ if environ is None else environ))
    get = lambda key, default: values.get(f"ELH_{key}", str(default))
    def path_value(key: str, default: Path) -> Path:
        candidate = Path(get(key, default)).expanduser()
        return candidate if candidate.is_absolute() else ROOT_DIR / candidate

    def resource_path_value(key: str, default: Path) -> Path:
        raw = values.get(f"ELH_{key}", "").strip()
        if not raw:
            return default
        candidate = Path(raw).expanduser()
        return candidate if candidate.is_absolute() else ROOT_DIR / candidate

    def optional_resource_path_value(key: str) -> Path | None:
        raw = values.get(f"ELH_{key}", "").strip()
        if not raw:
            return None
        candidate = Path(raw).expanduser()
        return candidate if candidate.is_absolute() else ROOT_DIR / candidate

    return AppConfig(
        app_title=get("APP_TITLE", AppConfig.app_title),
        environment=get("ENVIRONMENT", AppConfig.environment),
        database_path=path_value("DATABASE_PATH", ROOT_DIR / "elh_management.db"),
        database_engine=get("DATABASE_ENGINE", AppConfig.database_engine).lower(),
        database_host=get("DATABASE_HOST", AppConfig.database_host),
        database_port=int(get("DATABASE_PORT", AppConfig.database_port)),
        database_name=get("DATABASE_NAME", AppConfig.database_name),
        database_user=get("DATABASE_USER", AppConfig.database_user),
        database_password=get("DATABASE_PASSWORD", AppConfig.database_password),
        backup_directory=path_value("BACKUP_DIRECTORY", ROOT_DIR / "backups"),
        log_directory=path_value("LOG_DIRECTORY", ROOT_DIR / "logs"),
        log_level=get("LOG_LEVEL", AppConfig.log_level).upper(),
        log_max_bytes=int(get("LOG_MAX_BYTES", AppConfig.log_max_bytes)),
        log_backup_count=int(get("LOG_BACKUP_COUNT", AppConfig.log_backup_count)),
        session_idle_minutes=max(0, int(get("SESSION_IDLE_MINUTES", AppConfig.session_idle_minutes))),
        mysql_dump_path=get("MYSQL_DUMP_PATH", AppConfig.mysql_dump_path),
        mysql_client_path=get("MYSQL_CLIENT_PATH", AppConfig.mysql_client_path),
        certificate_template_path=resource_path_value(
            "CERTIFICATE_TEMPLATE_PATH",
            RESOURCE_DIR / "elh" / "assets" / "certificate_template.docx",
        ),
        certificate_output_directory=path_value(
            "CERTIFICATE_OUTPUT_DIRECTORY", ROOT_DIR / "output" / "certificates"
        ),
        certificate_pdf_background_path=optional_resource_path_value(
            "CERTIFICATE_PDF_BACKGROUND_PATH"
        ),
        certificate_number_prefix=get(
            "CERTIFICATE_NUMBER_PREFIX", AppConfig.certificate_number_prefix
        ).strip(),
        certificate_default_instructor=get(
            "CERTIFICATE_DEFAULT_INSTRUCTOR", AppConfig.certificate_default_instructor
        ),
        certificate_default_principal=get(
            "CERTIFICATE_DEFAULT_PRINCIPAL", AppConfig.certificate_default_principal
        ),
        date_format=get("DATE_FORMAT", AppConfig.date_format),
        currency_symbol=get("CURRENCY_SYMBOL", AppConfig.currency_symbol),
        window_width=int(get("WINDOW_WIDTH", AppConfig.window_width)),
        window_height=int(get("WINDOW_HEIGHT", AppConfig.window_height)),
        min_window_width=int(get("MIN_WINDOW_WIDTH", AppConfig.min_window_width)),
        min_window_height=int(get("MIN_WINDOW_HEIGHT", AppConfig.min_window_height)),
        allow_negative_balance=_bool(get("ALLOW_NEGATIVE_BALANCE", "false")),
        seed_demo_data=_bool(get("SEED_DEMO_DATA", "false")),
        health_stale_backup_hours=int(get("HEALTH_STALE_BACKUP_HOURS", 168)),
        attendance_driver=get("ATTENDANCE_DRIVER", AppConfig.attendance_driver).lower(),
        zkteco_host=get("ZKTECO_HOST", AppConfig.zkteco_host),
        zkteco_port=int(get("ZKTECO_PORT", AppConfig.zkteco_port)),
        zkteco_password=int(get("ZKTECO_PASSWORD", AppConfig.zkteco_password)),
        zkteco_timeout_seconds=int(get("ZKTECO_TIMEOUT_SECONDS", AppConfig.zkteco_timeout_seconds)),
        pos_printer_driver=get("POS_PRINTER_DRIVER", AppConfig.pos_printer_driver).lower(),
        pos_printer_host=get("POS_PRINTER_HOST", AppConfig.pos_printer_host),
        pos_printer_port=int(get("POS_PRINTER_PORT", AppConfig.pos_printer_port)),
        pos_printer_chars_per_line=int(get("POS_PRINTER_CHARS_PER_LINE", AppConfig.pos_printer_chars_per_line)),
        aakash_sms_token=get("AAKASH_SMS_TOKEN", AppConfig.aakash_sms_token),
        aakash_sms_endpoint=get("AAKASH_SMS_ENDPOINT", AppConfig.aakash_sms_endpoint),
        sparrow_sms_token=get("SPARROW_SMS_TOKEN", AppConfig.sparrow_sms_token),
        sparrow_sms_endpoint=get("SPARROW_SMS_ENDPOINT", AppConfig.sparrow_sms_endpoint),
        operator_username=get("OPERATOR_USERNAME", AppConfig.operator_username),
        operator_password=get("OPERATOR_PASSWORD", AppConfig.operator_password),
        admin_username=get("ADMIN_USERNAME", AppConfig.admin_username),
        admin_password=get("ADMIN_PASSWORD", AppConfig.admin_password),
        maintenance_username=get("MAINTENANCE_USERNAME", AppConfig.maintenance_username),
        maintenance_password=get("MAINTENANCE_PASSWORD", AppConfig.maintenance_password),
    )


EDITABLE_ENV_KEYS = {
    "app_title": "ELH_APP_TITLE",
    "environment": "ELH_ENVIRONMENT",
    "database_path": "ELH_DATABASE_PATH",
    "database_engine": "ELH_DATABASE_ENGINE",
    "database_host": "ELH_DATABASE_HOST",
    "database_port": "ELH_DATABASE_PORT",
    "database_name": "ELH_DATABASE_NAME",
    "database_user": "ELH_DATABASE_USER",
    "database_password": "ELH_DATABASE_PASSWORD",
    "backup_directory": "ELH_BACKUP_DIRECTORY",
    "log_directory": "ELH_LOG_DIRECTORY",
    "log_level": "ELH_LOG_LEVEL",
    "log_max_bytes": "ELH_LOG_MAX_BYTES",
    "log_backup_count": "ELH_LOG_BACKUP_COUNT",
    "session_idle_minutes": "ELH_SESSION_IDLE_MINUTES",
    "mysql_dump_path": "ELH_MYSQL_DUMP_PATH",
    "mysql_client_path": "ELH_MYSQL_CLIENT_PATH",
    "certificate_template_path": "ELH_CERTIFICATE_TEMPLATE_PATH",
    "certificate_output_directory": "ELH_CERTIFICATE_OUTPUT_DIRECTORY",
    "certificate_pdf_background_path": "ELH_CERTIFICATE_PDF_BACKGROUND_PATH",
    "date_format": "ELH_DATE_FORMAT",
    "window_width": "ELH_WINDOW_WIDTH",
    "window_height": "ELH_WINDOW_HEIGHT",
    "min_window_width": "ELH_MIN_WINDOW_WIDTH",
    "min_window_height": "ELH_MIN_WINDOW_HEIGHT",
    "allow_negative_balance": "ELH_ALLOW_NEGATIVE_BALANCE",
    "seed_demo_data": "ELH_SEED_DEMO_DATA",
    "health_stale_backup_hours": "ELH_HEALTH_STALE_BACKUP_HOURS",
    "attendance_driver": "ELH_ATTENDANCE_DRIVER",
    "zkteco_host": "ELH_ZKTECO_HOST",
    "zkteco_port": "ELH_ZKTECO_PORT",
    "zkteco_password": "ELH_ZKTECO_PASSWORD",
    "zkteco_timeout_seconds": "ELH_ZKTECO_TIMEOUT_SECONDS",
    "pos_printer_driver": "ELH_POS_PRINTER_DRIVER",
    "pos_printer_host": "ELH_POS_PRINTER_HOST",
    "pos_printer_port": "ELH_POS_PRINTER_PORT",
    "pos_printer_chars_per_line": "ELH_POS_PRINTER_CHARS_PER_LINE",
    "aakash_sms_token": "ELH_AAKASH_SMS_TOKEN",
    "aakash_sms_endpoint": "ELH_AAKASH_SMS_ENDPOINT",
    "sparrow_sms_token": "ELH_SPARROW_SMS_TOKEN",
    "sparrow_sms_endpoint": "ELH_SPARROW_SMS_ENDPOINT",
    "operator_username": "ELH_OPERATOR_USERNAME",
    "operator_password": "ELH_OPERATOR_PASSWORD",
    "admin_username": "ELH_ADMIN_USERNAME",
    "admin_password": "ELH_ADMIN_PASSWORD",
    "maintenance_username": "ELH_MAINTENANCE_USERNAME",
    "maintenance_password": "ELH_MAINTENANCE_PASSWORD",
}


def write_env(updates: Mapping[str, str], env_file: Path | str | None = None) -> None:
    """Update only supported ELH keys while preserving comments and unknown values."""
    path = Path(env_file) if env_file else DEFAULT_ENV_FILE
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacements = {EDITABLE_ENV_KEYS[k]: str(v) for k, v in updates.items() if k in EDITABLE_ENV_KEYS}
    output: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else ""
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)
    if output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={value}" for key, value in replacements.items() if key not in seen)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
