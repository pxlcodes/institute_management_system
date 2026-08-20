from __future__ import annotations

import sqlite3
import tempfile
import unittest
import logging
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from elh.config import AppConfig, load_config, write_env
from elh.core.backup import BackupService
from elh.core.health import HealthService
from elh.core.logging_config import configure_logging
from elh.core.validation import normalize_phone, parse_amount, validate_date
from elh.ui.desktop.components import SearchableCombobox


class CoreTests(unittest.TestCase):
    def test_validation_is_ui_independent(self):
        self.assertEqual(parse_amount("1,234.567"), 1234.57)
        self.assertEqual(normalize_phone("+977123"), "+977123")
        self.assertEqual(validate_date("2083/04/22", date_format="%Y/%m/%d"), "2083/04/22")
        with self.assertRaises(ValueError):
            parse_amount("-1")

    def test_searchable_dropdown_matches_any_part_of_name(self):
        choices = ["1 - Aayan Rai", "2 - Dipshika Shrestha", "3 - Niraj Dhakal"]
        self.assertEqual(
            SearchableCombobox.matching_values(choices, "shrestha"),
            ["2 - Dipshika Shrestha"],
        )
        self.assertEqual(
            SearchableCombobox.matching_values(choices, "DHAK"),
            ["3 - Niraj Dhakal"],
        )

    def test_env_round_trip_and_process_override(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            write_env(
                {
                    "window_width": "1200",
                    "seed_demo_data": "false",
                    "session_idle_minutes": "12",
                    "certificate_pdf_background_path": "templates/background.png",
                },
                env_file,
            )
            config = load_config(env_file, {"ELH_WINDOW_WIDTH": "1300"})
            self.assertEqual(config.window_width, 1300)
            self.assertFalse(config.seed_demo_data)
            self.assertEqual(config.session_idle_minutes, 12)
            self.assertEqual(
                config.certificate_pdf_background_path,
                Path(__file__).resolve().parents[1] / "templates" / "background.png",
            )
            self.assertEqual(AppConfig().public_values()["certificate_pdf_background_path"], "")

    def test_health_report_is_structured(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "test.db"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute("CREATE TABLE sample(id INTEGER)")
                conn.commit()
            config = load_config(environ={
                "ELH_DATABASE_ENGINE": "sqlite",
                "ELH_DATABASE_PATH": str(db_path),
                "ELH_BACKUP_DIRECTORY": str(Path(folder) / "backups"),
                "ELH_ATTENDANCE_DRIVER": "disabled",
                "ELH_POS_PRINTER_DRIVER": "disabled",
            })
            report = HealthService(config).report()
            self.assertIn(report["status"], {"healthy", "degraded"})
            self.assertEqual(len(report["checks"]), 9)
            self.assertEqual(
                {check["name"] for check in report["checks"]},
                {
                    "database",
                    "schema",
                    "storage",
                    "logging",
                    "configuration",
                    "backup",
                    "attendance_device",
                    "pos_printer",
                    "sms_notifications",
                },
            )

    def test_sqlite_backup_is_verified_and_restorable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database_path = root / "live.db"
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, name TEXT)")
                connection.execute("INSERT INTO sample(name) VALUES ('original')")
                connection.commit()
            config = replace(
                AppConfig(),
                database_engine="sqlite",
                database_path=database_path,
                backup_directory=root / "backups",
            )
            service = BackupService(config)
            backup = service.create()
            self.assertTrue(backup.exists())
            self.assertTrue(backup.with_suffix(".db.sha256").exists())
            service.verify(backup)
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute("UPDATE sample SET name='changed'")
                connection.commit()
            service.restore(backup)
            with closing(sqlite3.connect(database_path)) as connection:
                value = connection.execute("SELECT name FROM sample").fetchone()[0]
            self.assertEqual(value, "original")

    def test_rotating_log_file_is_configured(self):
        with tempfile.TemporaryDirectory() as folder:
            config = replace(AppConfig(), log_directory=Path(folder))
            path = configure_logging(config)
            logging.getLogger("elh.test").warning("production log test")
            for handler in logging.getLogger().handlers:
                handler.flush()
            self.assertTrue(path.exists())
            self.assertIn("production log test", path.read_text(encoding="utf-8"))
            for handler in list(logging.getLogger().handlers):
                if getattr(handler, "_elh_log_path", None) == str(path.resolve()):
                    logging.getLogger().removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
