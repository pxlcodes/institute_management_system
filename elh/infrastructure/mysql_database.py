"""MySQL implementation of the database interface consumed by the application."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Optional

from elh.config import AppConfig


class MySQLDriverMissingError(RuntimeError):
    pass


def _driver():
    try:
        import mysql.connector
        return mysql.connector
    except ImportError as exc:
        raise MySQLDriverMissingError(
            "MySQL is configured but its Python driver is missing. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc


def _sql(statement: str) -> str:
    """Translate the application's DB-API placeholders to MySQL placeholders."""
    return statement.replace("?", "%s")


class TransactionConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql: str, params: Iterable[Any] = ()):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(_sql(sql), tuple(params))
        return cursor

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]):
        cursor = self.connection.cursor(dictionary=True)
        cursor.executemany(_sql(sql), [tuple(values) for values in params])
        return cursor


class MySQLDatabase:
    def __init__(self, config: AppConfig):
        self.config = config
        self.initialize()

    def _connect_raw(self):
        connector = _driver()
        return connector.connect(
            host=self.config.database_host,
            port=self.config.database_port,
            database=self.config.database_name,
            user=self.config.database_user,
            password=self.config.database_password,
            autocommit=False,
        )

    @contextmanager
    def connect(self):
        connection = self._connect_raw()
        try:
            yield TransactionConnection(connection)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            # Preserve compatibility with existing UI error handling while the
            # presentation layer is progressively split into services.
            if type(exc).__name__ == "IntegrityError":
                raise sqlite3.IntegrityError(str(exc)) from exc
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        statements = [part.strip() for part in MYSQL_SCHEMA.split(";") if part.strip()]
        with self.connect() as conn:
            for statement in statements:
                cursor = conn.execute(statement)
                cursor.close()
        self._migrate_columns()
        from .schema_optimizer import normalize_mysql_schema
        normalize_mysql_schema(self)

    def _migrate_columns(self) -> None:
        migrations = (
            ("students", "school_id", "INTEGER NULL"),
            ("enrollments", "course_id", "INTEGER NULL"),
            ("teachers", "staff_type", "VARCHAR(50) NOT NULL DEFAULT 'Teaching'"),
            ("schools", "emis_id", "VARCHAR(100) NULL UNIQUE"),
            ("salary_payouts", "attendance_days", "INTEGER NOT NULL DEFAULT 0"),
            ("salary_payouts", "working_hours", "DECIMAL(14,2) NOT NULL DEFAULT 0"),
            ("app_users", "display_name", "VARCHAR(255) NULL"),
            ("app_users", "email", "VARCHAR(255) NULL"),
            ("app_users", "must_change_password", "INTEGER NOT NULL DEFAULT 0"),
            ("app_users", "failed_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("app_users", "locked_until", "DATETIME NULL"),
            ("app_users", "password_changed_at", "DATETIME NULL"),
            ("app_users", "updated_at", "DATETIME NULL"),
            ("company_profile", "principal_name", "VARCHAR(255) NULL"),
            ("courses", "instructor_name", "VARCHAR(255) NULL"),
            ("settings", "category", "VARCHAR(100) NOT NULL DEFAULT 'General'"),
            ("settings", "setting_label", "VARCHAR(255) NULL"),
            ("settings", "data_type", "VARCHAR(50) NOT NULL DEFAULT 'text'"),
            ("settings", "description", "TEXT NULL"),
            ("settings", "updated_at", "DATETIME NULL"),
        )
        for table, column, definition in migrations:
            row = self.query_one(
                "SELECT COUNT(*) AS total FROM information_schema.columns "
                "WHERE table_schema=? AND table_name=? AND column_name=?",
                (self.config.database_name, table, column),
            )
            if not row or int(row["total"]) == 0:
                self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _seed(self) -> None:
        self.execute(
            "INSERT IGNORE INTO accounts "
            "(account_name, account_type, opening_balance, status, remarks) "
            "VALUES (?, ?, ?, ?, ?)",
            ("Main Cash Counter", "Cash Counter", 0, "Active", "Default cash account"),
        )
        if not self.config.seed_demo_data:
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
                    "INSERT IGNORE INTO schools (school_name,status) VALUES (?,'Active')",
                    (values[2],),
                )
                school_id = self.query_one(
                    "SELECT id FROM schools WHERE school_name=?", (values[2],)
                )["id"]
                self.execute(
                    "INSERT INTO students "
                    "(student_name, class_name, school_id, contact, parent_name, joining_date) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (values[0], values[1], school_id, values[3], values[4], values[5]),
                )
        self._seed_courses()

    def _seed_courses(self) -> None:
        for name, category, billing in (
            ("Tuition Course Complete", "Tuition", "Course Complete"),
            ("Tuition Monthly", "Tuition", "Monthly"),
            ("Korean Language", "Language", "Course Complete"),
        ):
            self.execute(
                "INSERT IGNORE INTO courses (course_name, category, billing_type, status) VALUES (?, ?, ?, 'Active')",
                (name, category, billing),
            )

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            result = int(cursor.lastrowid or 0)
            cursor.close()
            return result

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> int:
        values = [tuple(row) for row in params]
        if not values:
            return 0
        with self.connect() as conn:
            cursor = conn.executemany(sql, values)
            result = max(0, int(cursor.rowcount))
            cursor.close()
            return result

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        connection = self._connect_raw()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(_sql(sql), tuple(params))
            rows = list(cursor.fetchall())
            cursor.close()
            return rows
        finally:
            connection.close()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def transaction(self, callback: Callable[[TransactionConnection], Any]) -> Any:
        with self.connect() as conn:
            return callback(conn)

    def account_balance(self, account_id: int) -> float:
        row = self.query_one(
            "SELECT a.opening_balance + COALESCE(SUM(CASE WHEN l.direction='IN' "
            "THEN l.amount ELSE -l.amount END), 0) AS balance "
            "FROM accounts a LEFT JOIN ledger l ON l.account_id=a.id "
            "WHERE a.id=? GROUP BY a.id", (account_id,),
        )
        return float(row["balance"]) if row else 0.0

    def account_balances(self):
        return self.query(
            "SELECT a.*,a.opening_balance+COALESCE(SUM(CASE WHEN l.direction='IN' "
            "THEN l.amount ELSE -l.amount END),0) balance FROM accounts a "
            "LEFT JOIN ledger l ON l.account_id=a.id GROUP BY a.id ORDER BY a.account_name"
        )

    def add_ledger(self, conn: TransactionConnection, transaction_date: str, account_id: int,
                   direction: str, amount: float, source_type: str, source_id: int,
                   particular: str, reference_no: str = "", remarks: str = "") -> None:
        cursor = conn.execute(
            "INSERT INTO ledger (transaction_date, account_id, direction, amount, source_type, "
            "source_id, particular, reference_no, remarks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (transaction_date, account_id, direction, amount, source_type, source_id,
             particular, reference_no, remarks),
        )
        cursor.close()


MYSQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
 version INTEGER PRIMARY KEY, migration_name VARCHAR(255) NOT NULL,
 applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS app_users (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, username VARCHAR(100) NOT NULL UNIQUE,
 display_name VARCHAR(255), email VARCHAR(255), password_hash VARCHAR(255) NOT NULL,
 role VARCHAR(30) NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'Active',
 must_change_password INTEGER NOT NULL DEFAULT 0, failed_attempts INTEGER NOT NULL DEFAULT 0,
 locked_until DATETIME, last_login_at DATETIME, password_changed_at DATETIME,
 updated_at DATETIME,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS permissions (
 permission_key VARCHAR(100) PRIMARY KEY, permission_name VARCHAR(255) NOT NULL,
 description TEXT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS role_permissions (
 role VARCHAR(30) NOT NULL, permission_key VARCHAR(100) NOT NULL,
 PRIMARY KEY(role,permission_key),
 FOREIGN KEY(permission_key) REFERENCES permissions(permission_key) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS user_permissions (
 user_id INTEGER NOT NULL, permission_key VARCHAR(100) NOT NULL,
 allowed INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(user_id,permission_key),
 FOREIGN KEY(user_id) REFERENCES app_users(id) ON DELETE CASCADE,
 FOREIGN KEY(permission_key) REFERENCES permissions(permission_key) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS auth_audit_log (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, user_id INTEGER, username VARCHAR(100),
 event_type VARCHAR(100) NOT NULL, success INTEGER NOT NULL DEFAULT 1,
 detail TEXT, occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id) REFERENCES app_users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS company_profile (
 id INTEGER PRIMARY KEY, company_name VARCHAR(255) NOT NULL, pan_number VARCHAR(100), registration_number VARCHAR(100),
 address TEXT, phone VARCHAR(100), email VARCHAR(255), website VARCHAR(255), principal_name VARCHAR(255), report_footer TEXT,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS schools (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, school_name VARCHAR(255) NOT NULL UNIQUE, emis_id VARCHAR(100) NULL UNIQUE,
 address TEXT, contact VARCHAR(50), status VARCHAR(50) NOT NULL DEFAULT 'Active',
 remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS courses (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, course_name VARCHAR(255) NOT NULL, category VARCHAR(100) NOT NULL,
 billing_type VARCHAR(100) NOT NULL, default_fee DECIMAL(14,2) NOT NULL DEFAULT 0,
 duration_months INTEGER NOT NULL DEFAULT 0, instructor_name VARCHAR(255),
 status VARCHAR(50) NOT NULL DEFAULT 'Active', remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY uq_course_name_category(course_name, category)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS students (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, student_name VARCHAR(255) NOT NULL, class_name VARCHAR(100),
 school_id INTEGER, contact VARCHAR(50), gender VARCHAR(20), date_of_birth VARCHAR(30),
 parent_name VARCHAR(255), guardian_relationship VARCHAR(100), joining_date VARCHAR(30) NOT NULL,
 photo_data MEDIUMBLOB, photo_mime_type VARCHAR(100),
 address TEXT, status VARCHAR(50) NOT NULL DEFAULT 'Active', remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_students_school FOREIGN KEY(school_id) REFERENCES schools(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, account_name VARCHAR(255) NOT NULL UNIQUE, account_type VARCHAR(100) NOT NULL,
 bank_name VARCHAR(255), account_number VARCHAR(100), account_holder VARCHAR(255), opening_balance DECIMAL(14,2) NOT NULL DEFAULT 0,
 status VARCHAR(50) NOT NULL DEFAULT 'Active', remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS counterparties (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, counterparty_name VARCHAR(255) NOT NULL UNIQUE,
 counterparty_type VARCHAR(100) NOT NULL DEFAULT 'Vendor', contact VARCHAR(50), address TEXT,
 status VARCHAR(50) NOT NULL DEFAULT 'Active', remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS counterparty_payments (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, counterparty_id INTEGER NOT NULL,
 payment_date VARCHAR(30) NOT NULL, amount DECIMAL(14,2) NOT NULL,
 paid_from_account_id INTEGER NOT NULL, payment_method VARCHAR(100), reference_no VARCHAR(255),
 remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(counterparty_id) REFERENCES counterparties(id) ON DELETE RESTRICT,
 FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS enrollments (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, student_id INTEGER NOT NULL, course_id INTEGER NOT NULL, level VARCHAR(100),
 start_date VARCHAR(30) NOT NULL, end_date VARCHAR(30), monthly_fee DECIMAL(14,2) NOT NULL DEFAULT 0,
 admission_fee DECIMAL(14,2) NOT NULL DEFAULT 0, discount DECIMAL(14,2) NOT NULL DEFAULT 0,
 status VARCHAR(50) NOT NULL DEFAULT 'Active', remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE RESTRICT,
 CONSTRAINT fk_enrollments_course FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS course_certificates (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, certificate_number VARCHAR(100) NOT NULL UNIQUE,
 enrollment_id INTEGER NOT NULL UNIQUE, honorific VARCHAR(20) NOT NULL,
 guardian_relationship VARCHAR(100) NOT NULL, date_of_birth VARCHAR(30) NOT NULL,
 student_name_snapshot VARCHAR(255) NOT NULL, guardian_name_snapshot VARCHAR(255) NOT NULL,
 course_name_snapshot VARCHAR(255) NOT NULL, company_name_snapshot VARCHAR(255) NOT NULL,
 course_start_date VARCHAR(30) NOT NULL, course_end_date VARCHAR(30) NOT NULL,
 duration_days INTEGER NOT NULL, certify_date VARCHAR(30) NOT NULL,
 instructor_name VARCHAR(255) NOT NULL, principal_name VARCHAR(255) NOT NULL,
 document_path TEXT, pdf_path TEXT, pdf_sha256 VARCHAR(64), created_by_user_id INTEGER, remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(enrollment_id) REFERENCES enrollments(id) ON DELETE RESTRICT,
 FOREIGN KEY(created_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS ledger (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, transaction_date VARCHAR(30) NOT NULL, account_id INTEGER NOT NULL,
 direction ENUM('IN','OUT') NOT NULL, amount DECIMAL(14,2) NOT NULL, source_type VARCHAR(100) NOT NULL,
 source_id INTEGER, particular VARCHAR(500) NOT NULL, reference_no VARCHAR(255), remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS student_transactions (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, student_id INTEGER NOT NULL, enrollment_id INTEGER, transaction_date VARCHAR(30) NOT NULL,
 transaction_type VARCHAR(100) NOT NULL, particular VARCHAR(500) NOT NULL, charge_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
 payment_amount DECIMAL(14,2) NOT NULL DEFAULT 0, discount_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
 account_id INTEGER, payment_method VARCHAR(100), receipt_no VARCHAR(255), remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE RESTRICT,
 FOREIGN KEY(enrollment_id) REFERENCES enrollments(id) ON DELETE SET NULL,
 FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS teachers (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, teacher_name VARCHAR(255) NOT NULL, contact VARCHAR(50), address TEXT, email VARCHAR(255),
 qualification VARCHAR(255), subject VARCHAR(255), staff_type VARCHAR(50) NOT NULL DEFAULT 'Teaching', joined_date VARCHAR(30) NOT NULL,
 salary_type VARCHAR(100) NOT NULL DEFAULT 'Monthly Salary', basic_salary DECIMAL(14,2) NOT NULL DEFAULT 0,
 bank_account_number VARCHAR(100), account_holder_name VARCHAR(255), bank_name VARCHAR(255),
 status VARCHAR(50) NOT NULL DEFAULT 'Active', remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS teacher_advances (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, teacher_id INTEGER NOT NULL, advance_date VARCHAR(30) NOT NULL,
 amount DECIMAL(14,2) NOT NULL, paid_from_account_id INTEGER NOT NULL, payment_method VARCHAR(100), reference_no VARCHAR(255),
 recovery_method VARCHAR(100), recovery_start_month VARCHAR(30), monthly_deduction DECIMAL(14,2) NOT NULL DEFAULT 0,
 recovered_amount DECIMAL(14,2) NOT NULL DEFAULT 0, status VARCHAR(50) NOT NULL DEFAULT 'Outstanding', remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT,
 FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS salary_payouts (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, teacher_id INTEGER NOT NULL, salary_month VARCHAR(30) NOT NULL,
 basic_salary DECIMAL(14,2) NOT NULL DEFAULT 0, extra_payment DECIMAL(14,2) NOT NULL DEFAULT 0,
 bonus DECIMAL(14,2) NOT NULL DEFAULT 0, allowance DECIMAL(14,2) NOT NULL DEFAULT 0,
 advance_deduction DECIMAL(14,2) NOT NULL DEFAULT 0, other_deduction DECIMAL(14,2) NOT NULL DEFAULT 0,
 attendance_days INTEGER NOT NULL DEFAULT 0, working_hours DECIMAL(14,2) NOT NULL DEFAULT 0,
 net_salary DECIMAL(14,2) NOT NULL DEFAULT 0, payment_date VARCHAR(30) NOT NULL, paid_from_account_id INTEGER NOT NULL,
 payment_method VARCHAR(100), voucher_no VARCHAR(255), status VARCHAR(50) NOT NULL DEFAULT 'Paid', remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY uq_teacher_salary_month(teacher_id, salary_month),
 FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT,
 FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS income_records (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, income_date VARCHAR(30) NOT NULL, category VARCHAR(255) NOT NULL,
 particular VARCHAR(500) NOT NULL, amount DECIMAL(14,2) NOT NULL, received_in_account_id INTEGER NOT NULL,
 received_from VARCHAR(255), payment_method VARCHAR(100), reference_no VARCHAR(255), remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(received_in_account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS expense_records (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, expense_date VARCHAR(30) NOT NULL, category VARCHAR(255) NOT NULL,
 particular VARCHAR(500) NOT NULL, amount DECIMAL(14,2) NOT NULL, paid_from_account_id INTEGER NOT NULL,
 paid_to VARCHAR(255), counterparty_id INTEGER, payment_status VARCHAR(30) NOT NULL DEFAULT 'Paid',
 payment_method VARCHAR(100), reference_no VARCHAR(255), remarks TEXT,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS account_transfers (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, transfer_date VARCHAR(30) NOT NULL, from_account_id INTEGER NOT NULL,
 to_account_id INTEGER NOT NULL, amount DECIMAL(14,2) NOT NULL, transfer_charge DECIMAL(14,2) NOT NULL DEFAULT 0,
 reference_no VARCHAR(255), remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
 FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
 CHECK(from_account_id <> to_account_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS settings (
 setting_key VARCHAR(255) PRIMARY KEY, setting_value TEXT, category VARCHAR(100) NOT NULL DEFAULT 'General',
 setting_label VARCHAR(255), data_type VARCHAR(50) NOT NULL DEFAULT 'text', description TEXT,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS todo_items (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NOT NULL, details TEXT,
 assigned_teacher_id INTEGER NULL, due_date VARCHAR(30), priority VARCHAR(30) NOT NULL DEFAULT 'Normal',
 status VARCHAR(30) NOT NULL DEFAULT 'Open', created_by_user_id INTEGER NULL,
 completed_at DATETIME NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(assigned_teacher_id) REFERENCES teachers(id) ON DELETE SET NULL,
 FOREIGN KEY(created_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS bug_reports (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NOT NULL, details TEXT NOT NULL,
 page_name VARCHAR(100), severity VARCHAR(30) NOT NULL DEFAULT 'Normal',
 status VARCHAR(30) NOT NULL DEFAULT 'Open', reported_by_user_id INTEGER NULL,
 resolution_note TEXT, resolved_at DATETIME NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(reported_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS sms_event_templates (
 event_key VARCHAR(50) PRIMARY KEY, event_name VARCHAR(100) NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, template_text TEXT NOT NULL,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS sms_delivery_log (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, event_key VARCHAR(50) NOT NULL,
 entity_type VARCHAR(50) NOT NULL, entity_id INTEGER NOT NULL,
 recipient VARCHAR(30) NOT NULL, message_text TEXT NOT NULL,
 provider VARCHAR(30) NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'Pending',
 attempt_count INTEGER NOT NULL DEFAULT 0, response_code VARCHAR(50), response_message TEXT,
 last_attempt_at DATETIME, sent_at DATETIME,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_sms_event_entity(event_key,entity_type,entity_id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS attendance_device_users (
 device_user_id VARCHAR(100) PRIMARY KEY, device_name VARCHAR(255), device_uid INTEGER,
 privilege VARCHAR(100), card_number VARCHAR(100), device_serial VARCHAR(100),
 fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS device_user_mappings (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, device_user_id VARCHAR(100) NOT NULL UNIQUE,
 person_type ENUM('student','teacher') NOT NULL, person_id INTEGER NOT NULL,
 status VARCHAR(50) NOT NULL DEFAULT 'Active', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS attendance_logs (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, device_user_id VARCHAR(100) NOT NULL,
 person_type VARCHAR(30), person_id INTEGER, occurred_at DATETIME NOT NULL,
 event_type VARCHAR(50) NOT NULL, device_serial VARCHAR(100), verification_mode VARCHAR(100),
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_attendance_event(device_user_id, occurred_at, device_serial)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS due_bills (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, bill_number VARCHAR(100) NOT NULL UNIQUE,
 enrollment_id INTEGER NOT NULL,
 billing_period VARCHAR(30) NOT NULL, issue_date VARCHAR(30) NOT NULL, due_date VARCHAR(30) NOT NULL,
 subtotal DECIMAL(14,2) NOT NULL, discount DECIMAL(14,2) NOT NULL DEFAULT 0,
 total_amount DECIMAL(14,2) NOT NULL, paid_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
 status VARCHAR(50) NOT NULL DEFAULT 'Due', pdf_path TEXT, pos_printed_at DATETIME,
 remarks TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_enrollment_billing_period(enrollment_id,billing_period),
 FOREIGN KEY(enrollment_id) REFERENCES enrollments(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS due_bill_items (
 id INTEGER AUTO_INCREMENT PRIMARY KEY, bill_id INTEGER NOT NULL,
 billing_month VARCHAR(7) NOT NULL, description VARCHAR(255) NOT NULL,
 amount DECIMAL(14,2) NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_bill_billing_month(bill_id,billing_month),
 FOREIGN KEY(bill_id) REFERENCES due_bills(id) ON DELETE CASCADE
) ENGINE=InnoDB
"""
