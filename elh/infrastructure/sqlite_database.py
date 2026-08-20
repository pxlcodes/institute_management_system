"""SQLite database adapter used for lightweight/offline deployments."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from elh.infrastructure.mysql_database import MYSQL_SCHEMA


def _sqlite_schema() -> str:
    """Produce equivalent SQLite DDL from the canonical cross-adapter schema."""
    schema = MYSQL_SCHEMA
    schema = re.sub(r"\) ENGINE=InnoDB", ")", schema)
    schema = re.sub(r"INTEGER AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", schema)
    schema = re.sub(r"DECIMAL\(14,2\)", "REAL", schema)
    schema = re.sub(r"VARCHAR\(\d+\)", "TEXT", schema)
    schema = re.sub(r"ENUM\([^)]*\)", "TEXT", schema)
    schema = schema.replace("DATETIME", "TEXT")
    schema = re.sub(r"UNIQUE KEY \w+\(([^)]+)\)", r"UNIQUE(\1)", schema)
    return schema


class SQLiteDatabase:
    def __init__(self, path: Path, seed_demo_data: bool = True):
        self.path = path
        self.seed_demo_data = seed_demo_data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(_sqlite_schema())
            migrations = (
                ("students", "school_id", "INTEGER"),
                ("students", "gender", "TEXT"),
                ("students", "date_of_birth", "TEXT"),
                ("students", "guardian_relationship", "TEXT"),
                ("students", "photo_data", "BLOB"),
                ("students", "photo_mime_type", "TEXT"),
                ("enrollments", "course_id", "INTEGER"),
                ("teachers", "staff_type", "TEXT NOT NULL DEFAULT 'Teaching'"),
                ("schools", "emis_id", "TEXT"),
                ("salary_payouts", "attendance_days", "INTEGER NOT NULL DEFAULT 0"),
                ("salary_payouts", "working_hours", "REAL NOT NULL DEFAULT 0"),
                ("app_users", "display_name", "TEXT"),
                ("app_users", "email", "TEXT"),
                ("app_users", "must_change_password", "INTEGER NOT NULL DEFAULT 0"),
                ("app_users", "failed_attempts", "INTEGER NOT NULL DEFAULT 0"),
                ("app_users", "locked_until", "TEXT"),
                ("app_users", "password_changed_at", "TEXT"),
                ("app_users", "updated_at", "TEXT"),
                ("company_profile", "principal_name", "TEXT"),
                ("courses", "instructor_name", "TEXT"),
                ("course_certificates", "pdf_path", "TEXT"),
                ("course_certificates", "pdf_sha256", "TEXT"),
                ("expense_records", "counterparty_id", "INTEGER"),
                ("expense_records", "payment_status", "TEXT NOT NULL DEFAULT 'Paid'"),
                ("settings", "category", "TEXT NOT NULL DEFAULT 'General'"),
                ("settings", "setting_label", "TEXT"),
                ("settings", "data_type", "TEXT NOT NULL DEFAULT 'text'"),
                ("settings", "description", "TEXT"),
                ("settings", "updated_at", "TEXT"),
            )
            for table, column, definition in migrations:
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if column not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        from .schema_optimizer import normalize_sqlite_schema
        normalize_sqlite_schema(self.path)

    def _seed(self) -> None:
        self.execute(
            "INSERT OR IGNORE INTO accounts "
            "(account_name, account_type, opening_balance, status, remarks) VALUES (?, ?, ?, ?, ?)",
            ("Main Cash Counter", "Cash Counter", 0, "Active", "Default cash account"),
        )
        if not self.seed_demo_data:
            self._seed_courses()
            return
        row = self.query_one("SELECT COUNT(*) AS total FROM students")
        if row and int(row["total"]) == 0:
            for values in (
                ("Rihan Limbu", "8", "Redstar", "9816326471", "Rita Rai", "2083/03/03"),
                ("Dipshika Shrestha", "8", "Bhupu", "9829320917", "Sapana Shrestha", "2083/02/18"),
                ("Beg Bahadur Budhathoki", "8", "Bhupu", "9819345818", "Sushila Adhikari", "2083/02/18"),
            ):
                self.execute(
                    "INSERT OR IGNORE INTO schools (school_name,status) VALUES (?,'Active')",
                    (values[2],),
                )
                school_id = self.query_one(
                    "SELECT id FROM schools WHERE school_name=?", (values[2],)
                )["id"]
                self.execute(
                    "INSERT INTO students "
                    "(student_name,class_name,school_id,contact,parent_name,joining_date) "
                    "VALUES (?,?,?,?,?,?)",
                    (values[0], values[1], school_id, values[3], values[4], values[5]),
                )
        self._seed_courses()

    def _seed_courses(self) -> None:
        for values in (
            ("Tuition Course Complete", "Tuition", "Course Complete"),
            ("Tuition Monthly", "Tuition", "Monthly"),
            ("Korean Language", "Language", "Course Complete"),
        ):
            self.execute(
                "INSERT OR IGNORE INTO courses (course_name, category, billing_type, status) VALUES (?, ?, ?, 'Active')",
                values,
            )

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self.connect() as connection:
            cursor = connection.execute(sql, tuple(params))
            return int(cursor.lastrowid or 0)

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> int:
        values = [tuple(row) for row in params]
        if not values:
            return 0
        with self.connect() as connection:
            cursor = connection.executemany(sql, values)
            return max(0, int(cursor.rowcount))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute(sql, tuple(params)).fetchall())

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def transaction(self, callback: Callable[[sqlite3.Connection], Any]) -> Any:
        with self.connect() as connection:
            return callback(connection)

    def account_balance(self, account_id: int) -> float:
        row = self.query_one(
            "SELECT a.opening_balance + COALESCE(SUM(CASE WHEN l.direction='IN' THEN l.amount "
            "ELSE -l.amount END), 0) AS balance FROM accounts a "
            "LEFT JOIN ledger l ON l.account_id=a.id WHERE a.id=? GROUP BY a.id",
            (account_id,),
        )
        return float(row["balance"]) if row else 0.0

    def account_balances(self):
        return self.query(
            "SELECT a.*,a.opening_balance+COALESCE(SUM(CASE WHEN l.direction='IN' "
            "THEN l.amount ELSE -l.amount END),0) balance FROM accounts a "
            "LEFT JOIN ledger l ON l.account_id=a.id GROUP BY a.id ORDER BY a.account_name"
        )

    def add_ledger(self, connection: sqlite3.Connection, transaction_date: str,
                   account_id: int, direction: str, amount: float, source_type: str,
                   source_id: int, particular: str, reference_no: str = "",
                   remarks: str = "") -> None:
        connection.execute(
            "INSERT INTO ledger (transaction_date, account_id, direction, amount, source_type, "
            "source_id, particular, reference_no, remarks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (transaction_date, account_id, direction, amount, source_type, source_id,
             particular, reference_no, remarks),
        )
