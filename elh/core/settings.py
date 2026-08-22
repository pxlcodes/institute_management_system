"""Persistent runtime settings independent of any presentation framework."""

from __future__ import annotations

from time import monotonic
from typing import Protocol


DEFAULT_SETTINGS = (
    (
        "app_title",
        "Expert Learning Hub Management System",
        "Application",
        "Application Title",
        "text",
        "Name shown in the desktop application title bar.",
    ),
    (
        "session_idle_minutes",
        "20",
        "Application",
        "Auto-lock After (minutes)",
        "integer",
        "Lock the application after this much inactivity. Set 0 to disable auto-lock.",
    ),
    (
        "window_width",
        "1420",
        "Application",
        "Window Width",
        "integer",
        "Preferred application window width in pixels.",
    ),
    (
        "window_height",
        "860",
        "Application",
        "Window Height",
        "integer",
        "Preferred application window height in pixels.",
    ),
    (
        "min_window_width",
        "1100",
        "Application",
        "Minimum Window Width",
        "integer",
        "Smallest supported application width in pixels.",
    ),
    (
        "min_window_height",
        "700",
        "Application",
        "Minimum Window Height",
        "integer",
        "Smallest supported application height in pixels.",
    ),
    (
        "allow_negative_balance",
        "false",
        "Finance",
        "Allow Negative Account Balance",
        "boolean",
        "Allow payments and expenses that exceed the selected account balance.",
    ),
    (
        "health_stale_backup_hours",
        "168",
        "Application",
        "Backup Stale After (hours)",
        "integer",
        "Show a health warning when the latest verified backup is older than this.",
    ),
    (
        "currency_symbol",
        "Rs.",
        "General",
        "Currency Symbol",
        "text",
        "Symbol used on bills, receipts, and reports.",
    ),
    (
        "certificate_number_prefix",
        "EXP",
        "Certificates",
        "Certificate Number Prefix",
        "text",
        "Prefix used when generating the next certificate number.",
    ),
    (
        "certificate_default_instructor",
        "",
        "Certificates",
        "Default Instructor",
        "text",
        "Used only when a course does not have an assigned instructor.",
    ),
    (
        "certificate_default_principal",
        "",
        "Certificates",
        "Default Principal",
        "text",
        "Used only when the company profile has no principal name.",
    ),
    (
        "certificate_pdf_title",
        "CERTIFICATE OF COMPLETION",
        "Certificates",
        "PDF Certificate Title",
        "text",
        "Heading used on directly generated certificate PDFs.",
    ),
    (
        "certificate_pdf_show_photo",
        "true",
        "Certificates",
        "Show Student Photo",
        "boolean",
        "Place the student photo on the certificate PDF when available.",
    ),
    (
        "certificate_pdf_show_guardian",
        "false",
        "Certificates",
        "Show Guardian",
        "boolean",
        "Include the saved guardian relationship and name on certificate PDFs.",
    ),
    (
        "certificate_pdf_show_date_of_birth",
        "false",
        "Certificates",
        "Show Date of Birth",
        "boolean",
        "Include the student's Nepali date of birth on certificate PDFs.",
    ),
    (
        "certificate_pdf_accent_color",
        "#008F7A",
        "Certificates",
        "PDF Accent Color",
        "text",
        "Six-digit hexadecimal accent color used by the built-in PDF design.",
    ),
    (
        "sms_enabled",
        "false",
        "Notifications",
        "Enable SMS",
        "boolean",
        "Send enabled event notifications through the selected provider.",
    ),
    (
        "sms_provider",
        "aakash",
        "Notifications",
        "SMS Provider",
        "choice",
        "Aakash SMS or Sparrow SMS.",
    ),
    (
        "sms_sender_id",
        "",
        "Notifications",
        "Sender ID",
        "text",
        "Required by Sparrow SMS; use the identity assigned by the provider.",
    ),
    (
        "sms_timeout_seconds",
        "10",
        "Notifications",
        "Gateway Timeout (seconds)",
        "integer",
        "Maximum time for one SMS gateway request.",
    ),
    (
        "attendance_consecutive_absence_days",
        "3",
        "Attendance",
        "Consecutive Absence Alert Days",
        "integer",
        "Flag an active enrolled student after this many calendar days since the last attendance punch.",
    ),
    (
        "attendance_monthly_irregular_days",
        "5",
        "Attendance",
        "Monthly Irregularity Alert Days",
        "integer",
        "Flag an active enrolled student when missing attendance days in the current Nepali month reach this number.",
    ),
)


class SettingsStore(Protocol):
    def query(self, sql: str, params=()): ...
    def execute(self, sql: str, params=()) -> int: ...
    def executemany(self, sql: str, params) -> int: ...


class SettingsService:
    def __init__(self, store: SettingsStore):
        self.store = store

    def _cached_values(self) -> dict[str, str]:
        """Share one short-lived settings cache across services using this DB."""
        entry = getattr(self.store, "_elh_settings_cache", None)
        now = monotonic()
        if entry and entry[0] > now:
            return entry[1]
        values = {
            row["setting_key"]: row["setting_value"] or ""
            for row in self.store.query(
                "SELECT setting_key, setting_value FROM settings ORDER BY setting_key"
            )
        }
        setattr(self.store, "_elh_settings_cache", (now + 15.0, values))
        return values

    def _invalidate_cache(self) -> None:
        try:
            delattr(self.store, "_elh_settings_cache")
        except AttributeError:
            pass

    def all(self) -> dict[str, str]:
        return dict(self._cached_values())

    def rows(self):
        return self.store.query(
            "SELECT setting_key,setting_value,category,setting_label,data_type,description "
            "FROM settings ORDER BY category,setting_label,setting_key"
        )

    def ensure_defaults(self) -> None:
        existing = {
            row["setting_key"]
            for row in self.store.query("SELECT setting_key FROM settings")
        }
        values = [definition for definition in DEFAULT_SETTINGS if definition[0] not in existing]
        if values:
            self.store.executemany(
                "INSERT INTO settings "
                "(setting_key,setting_value,category,setting_label,data_type,description) "
                "VALUES (?,?,?,?,?,?)",
                values,
            )
            self._invalidate_cache()
        self.store.executemany(
            "UPDATE settings SET category=?,setting_label=?,data_type=?,description=? "
            "WHERE setting_key=?",
            [
                (category, label, data_type, description, key)
                for key, _value, category, label, data_type, description in DEFAULT_SETTINGS
            ],
        )

    def get(self, key: str, default: str = "") -> str:
        return str(self._cached_values().get(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, "true" if default else "false")
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self.get(key, str(default)))
        except ValueError:
            return default

    def set(
        self,
        key: str,
        value: str,
        category: str | None = None,
        label: str = "",
        data_type: str = "text",
        description: str = "",
    ) -> None:
        clean_key = key.strip()
        if not clean_key or not clean_key.replace("_", "").isalnum():
            raise ValueError("Setting keys may contain letters, numbers, and underscores only.")
        exists = self.store.query("SELECT setting_key FROM settings WHERE setting_key = ?", (clean_key,))
        if exists:
            if category is None:
                self.store.execute(
                    "UPDATE settings SET setting_value=?,updated_at=CURRENT_TIMESTAMP "
                    "WHERE setting_key=?",
                    (value.strip(), clean_key),
                )
            else:
                self.store.execute(
                    "UPDATE settings SET setting_value=?,category=?,updated_at=CURRENT_TIMESTAMP "
                    "WHERE setting_key=?",
                    (value.strip(), category.strip() or "General", clean_key),
                )
        else:
            self.store.execute(
                "INSERT INTO settings "
                "(setting_key,setting_value,category,setting_label,data_type,description) "
                "VALUES (?,?,?,?,?,?)",
                (
                    clean_key,
                    value.strip(),
                    (category or "General").strip() or "General",
                    label.strip(),
                    data_type.strip() or "text",
                    description.strip(),
                ),
            )
        self._invalidate_cache()

    def delete(self, key: str) -> None:
        self.store.execute("DELETE FROM settings WHERE setting_key = ?", (key,))
        self._invalidate_cache()
