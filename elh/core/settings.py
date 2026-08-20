"""Persistent runtime settings independent of any presentation framework."""

from __future__ import annotations

from typing import Protocol


DEFAULT_SETTINGS = (
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
)


class SettingsStore(Protocol):
    def query(self, sql: str, params=()): ...
    def execute(self, sql: str, params=()) -> int: ...
    def executemany(self, sql: str, params) -> int: ...


class SettingsService:
    def __init__(self, store: SettingsStore):
        self.store = store

    def all(self) -> dict[str, str]:
        return {row["setting_key"]: row["setting_value"] or "" for row in self.store.query(
            "SELECT setting_key, setting_value FROM settings ORDER BY setting_key"
        )}

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
        self.store.executemany(
            "UPDATE settings SET category=?,setting_label=?,data_type=?,description=? "
            "WHERE setting_key=?",
            [
                (category, label, data_type, description, key)
                for key, _value, category, label, data_type, description in DEFAULT_SETTINGS
            ],
        )

    def get(self, key: str, default: str = "") -> str:
        rows = self.store.query(
            "SELECT setting_value FROM settings WHERE setting_key=?", (key,)
        )
        return str(rows[0]["setting_value"] or "") if rows else default

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

    def delete(self, key: str) -> None:
        self.store.execute("DELETE FROM settings WHERE setting_key = ?", (key,))
