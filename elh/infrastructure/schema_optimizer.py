"""Versioned schema normalization and index management.

The application keeps historical accounting snapshots (amounts, names on audit
events, and ledger descriptions) intentionally.  This module only removes
master-data values that can always be obtained through an existing foreign key.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable


NORMALIZATION_VERSION = 1
NORMALIZATION_NAME = "normalize master relationships and billing items"
BILL_MONTH_GUARD_VERSION = 2
BILL_MONTH_GUARD_NAME = "enforce unique enrollment billing months"
CERTIFICATE_VERSION = 3
CERTIFICATE_NAME = "add normalized course completion certificates"
STUDENT_PROFILE_VERSION = 4
STUDENT_PROFILE_NAME = "move certificate identity data to student profiles"
APPLICATION_SETTINGS_VERSION = 5
APPLICATION_SETTINGS_NAME = "add structured settings, course ownership, and sms notifications"
CERTIFICATE_PDF_VERSION = 6
CERTIFICATE_PDF_NAME = "add direct certificate pdf outputs"
COUNTERPARTY_PAYABLE_VERSION = 7
COUNTERPARTY_PAYABLE_NAME = "add payee, vendor, and credit payable tracking"
WORK_ITEMS_VERSION = 8
WORK_ITEMS_NAME = "add staff tasks and bug report tracking"
ATTENDANCE_ALERT_REVIEW_VERSION = 9
ATTENDANCE_ALERT_REVIEW_NAME = "add attendance alert review history"
STAFF_ACCOUNT_VERSION = 10
STAFF_ACCOUNT_NAME = "add staff payment accounts and transaction statements"
LATEST_SCHEMA_VERSION = STAFF_ACCOUNT_VERSION


INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("app_users", "idx_app_users_role_status", ("role", "status")),
    ("auth_audit_log", "idx_auth_audit_occurred", ("occurred_at",)),
    ("students", "idx_students_school", ("school_id",)),
    ("students", "idx_students_status_name", ("status", "student_name")),
    ("courses", "idx_courses_status_category_name", ("status", "category", "course_name")),
    ("enrollments", "idx_enrollments_student_status", ("student_id", "status")),
    ("enrollments", "idx_enrollments_course_status", ("course_id", "status")),
    ("enrollments", "idx_enrollments_status_start", ("status", "start_date")),
    ("student_transactions", "idx_student_transactions_student_date", ("student_id", "transaction_date")),
    ("student_transactions", "idx_student_transactions_enrollment_date", ("enrollment_id", "transaction_date")),
    ("student_transactions", "idx_student_transactions_account_date", ("account_id", "transaction_date")),
    ("ledger", "idx_ledger_account_date", ("account_id", "transaction_date")),
    ("ledger", "idx_ledger_source", ("source_type", "source_id")),
    ("teacher_advances", "idx_teacher_advances_status", ("teacher_id", "status", "recovery_start_month")),
    ("salary_payouts", "idx_salary_payouts_payment_date", ("payment_date",)),
    ("income_records", "idx_income_date_account", ("income_date", "received_in_account_id")),
    ("expense_records", "idx_expense_date_account", ("expense_date", "paid_from_account_id")),
    ("expense_records", "idx_expense_counterparty_status", ("counterparty_id", "payment_status")),
    ("counterparty_payments", "idx_counterparty_payments_party_date", ("counterparty_id", "payment_date")),
    ("todo_items", "idx_todo_staff_status", ("assigned_teacher_id", "status")),
    ("todo_items", "idx_todo_status_due", ("status", "due_date")),
    ("bug_reports", "idx_bug_status_created", ("status", "created_at")),
    ("attendance_alert_reviews", "idx_attendance_alert_review_student", ("student_id", "id")),
    ("staff_payment_accounts", "idx_staff_payment_account_teacher", ("teacher_id",)),
    ("staff_payment_transactions", "idx_staff_payment_transaction_account_date", ("staff_account_id", "transaction_date")),
    ("account_transfers", "idx_transfers_date", ("transfer_date",)),
    ("device_user_mappings", "idx_device_mapping_person", ("person_type", "person_id", "status")),
    ("attendance_logs", "idx_attendance_person_time", ("person_type", "person_id", "occurred_at")),
    ("due_bills", "idx_due_bills_status_due", ("status", "due_date")),
    ("due_bills", "idx_due_bills_issue", ("issue_date",)),
    ("course_certificates", "idx_certificates_certify_date", ("certify_date",)),
    ("course_certificates", "idx_certificates_student_course", ("student_name_snapshot", "course_name_snapshot")),
    ("sms_delivery_log", "idx_sms_delivery_status_created", ("status", "created_at")),
    ("sms_delivery_log", "idx_sms_delivery_recipient_created", ("recipient", "created_at")),
)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return value


def _mysql_column_exists(db, table: str, column: str) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) total FROM information_schema.columns "
        "WHERE table_schema=? AND table_name=? AND column_name=?",
        (db.config.database_name, table, column),
    )
    return bool(row and int(row["total"]))


def _mysql_fk_names(db, table: str, column: str) -> list[str]:
    rows = db.query(
        "SELECT DISTINCT constraint_name constraint_id FROM information_schema.key_column_usage "
        "WHERE table_schema=? AND table_name=? AND column_name=? "
        "AND referenced_table_name IS NOT NULL",
        (db.config.database_name, table, column),
    )
    return [str(row["constraint_id"]) for row in rows]


def _mysql_drop_foreign_keys(db, table: str, column: str) -> None:
    table = _identifier(table)
    for name in _mysql_fk_names(db, table, column):
        db.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{_identifier(name)}`")


def _mysql_fk_exists(db, table: str, column: str, referenced_table: str) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) total FROM information_schema.key_column_usage "
        "WHERE table_schema=? AND table_name=? AND column_name=? "
        "AND referenced_table_name=?",
        (db.config.database_name, table, column, referenced_table),
    )
    return bool(row and int(row["total"]))


def _mysql_index_exists(db, table: str, columns: Iterable[str]) -> bool:
    target = ",".join(columns)
    row = db.query_one(
        "SELECT COUNT(*) total FROM ("
        "SELECT index_name,GROUP_CONCAT(column_name ORDER BY seq_in_index) indexed_columns "
        "FROM information_schema.statistics WHERE table_schema=? AND table_name=? "
        "GROUP BY index_name) indexes_for_table WHERE indexed_columns=?",
        (db.config.database_name, table, target),
    )
    return bool(row and int(row["total"]))


def _mysql_named_index_exists(db, table: str, index_name: str) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) total FROM information_schema.statistics "
        "WHERE table_schema=? AND table_name=? AND index_name=?",
        (db.config.database_name, table, index_name),
    )
    return bool(row and int(row["total"]))


def _mysql_drop_index(db, table: str, index_name: str) -> None:
    if _mysql_named_index_exists(db, table, index_name):
        db.execute(
            f"ALTER TABLE `{_identifier(table)}` DROP INDEX `{_identifier(index_name)}`"
        )


def _mysql_assert_normalizable(db) -> None:
    checks = (
        (
            "enrollments without a valid course",
            "SELECT COUNT(*) total FROM enrollments e LEFT JOIN courses c ON c.id=e.course_id "
            "WHERE c.id IS NULL",
        ),
        (
            "bills without a valid enrollment",
            "SELECT COUNT(*) total FROM due_bills b LEFT JOIN enrollments e ON e.id=b.enrollment_id "
            "WHERE e.id IS NULL",
        ),
        (
            "bill items without a valid bill",
            "SELECT COUNT(*) total FROM due_bill_items bi LEFT JOIN due_bills b ON b.id=bi.bill_id "
            "WHERE b.id IS NULL",
        ),
    )
    for label, sql in checks:
        row = db.query_one(sql)
        if row and int(row["total"]):
            raise RuntimeError(
                f"Cannot normalize schema: found {row['total']} {label}. "
                "Remove those invalid records and retry."
            )


def normalize_mysql_schema(db) -> None:
    """Apply the idempotent MySQL 3NF migration to an existing database."""
    applied = db.query_one(
        "SELECT version FROM schema_migrations WHERE version=?",
        (NORMALIZATION_VERSION,),
    )
    if applied:
        ensure_mysql_application_settings_migration(db)
        ensure_mysql_certificate_pdf_migration(db)
        ensure_mysql_counterparty_payable_migration(db)
        ensure_mysql_work_items_migration(db)
        ensure_mysql_attendance_alert_review_migration(db)
        ensure_mysql_staff_account_migration(db)
        ensure_mysql_indexes(db)
        ensure_mysql_bill_month_guard(db)
        ensure_mysql_certificate_migration(db)
        ensure_mysql_student_profile_migration(db)
        return

    _mysql_assert_normalizable(db)

    if _mysql_column_exists(db, "due_bill_items", "enrollment_id"):
        _mysql_drop_foreign_keys(db, "due_bill_items", "enrollment_id")
        _mysql_drop_index(db, "due_bill_items", "uq_enrollment_billing_month")
        db.execute("ALTER TABLE due_bill_items DROP COLUMN enrollment_id")

    if not _mysql_index_exists(db, "due_bill_items", ("bill_id", "billing_month")):
        db.execute(
            "ALTER TABLE due_bill_items ADD CONSTRAINT uq_bill_billing_month "
            "UNIQUE (bill_id,billing_month)"
        )

    for column in ("student_id", "course_id"):
        if _mysql_column_exists(db, "due_bills", column):
            _mysql_drop_foreign_keys(db, "due_bills", column)
            db.execute(f"ALTER TABLE due_bills DROP COLUMN {_identifier(column)}")

    if _mysql_column_exists(db, "enrollments", "course_name"):
        db.execute("ALTER TABLE enrollments DROP COLUMN course_name")
    db.execute("ALTER TABLE enrollments MODIFY course_id INTEGER NOT NULL")
    if not _mysql_fk_exists(db, "enrollments", "course_id", "courses"):
        db.execute(
            "ALTER TABLE enrollments ADD CONSTRAINT fk_enrollments_course "
            "FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT"
        )

    if _mysql_column_exists(db, "students", "school"):
        db.execute("ALTER TABLE students DROP COLUMN school")
    if not _mysql_fk_exists(db, "students", "school_id", "schools"):
        db.execute(
            "ALTER TABLE students ADD CONSTRAINT fk_students_school "
            "FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE SET NULL"
        )

    ensure_mysql_application_settings_migration(db)
    ensure_mysql_certificate_pdf_migration(db)
    ensure_mysql_counterparty_payable_migration(db)
    ensure_mysql_work_items_migration(db)
    ensure_mysql_attendance_alert_review_migration(db)
    ensure_mysql_staff_account_migration(db)
    ensure_mysql_indexes(db)
    ensure_mysql_bill_month_guard(db)
    ensure_mysql_certificate_migration(db)
    ensure_mysql_student_profile_migration(db)
    db.execute(
        "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
        (NORMALIZATION_VERSION, NORMALIZATION_NAME),
    )


def ensure_mysql_certificate_migration(db) -> None:
    applied = db.query_one(
        "SELECT version FROM schema_migrations WHERE version=?",
        (CERTIFICATE_VERSION,),
    )
    if not applied:
        db.execute(
            "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (CERTIFICATE_VERSION, CERTIFICATE_NAME),
        )


def ensure_mysql_student_profile_migration(db) -> None:
    definitions = (
        ("gender", "VARCHAR(20) NULL"),
        ("date_of_birth", "VARCHAR(30) NULL"),
        ("guardian_relationship", "VARCHAR(100) NULL"),
        ("photo_data", "MEDIUMBLOB NULL"),
        ("photo_mime_type", "VARCHAR(100) NULL"),
    )
    for column, definition in definitions:
        if not _mysql_column_exists(db, "students", column):
            db.execute(
                f"ALTER TABLE students ADD COLUMN `{_identifier(column)}` {definition}"
            )
    applied = db.query_one(
        "SELECT version FROM schema_migrations WHERE version=?",
        (STUDENT_PROFILE_VERSION,),
    )
    if not applied:
        db.execute(
            "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (STUDENT_PROFILE_VERSION, STUDENT_PROFILE_NAME),
        )


def ensure_mysql_application_settings_migration(db) -> None:
    definitions = (
        ("company_profile", "principal_name", "VARCHAR(255) NULL"),
        ("courses", "instructor_name", "VARCHAR(255) NULL"),
        ("settings", "category", "VARCHAR(100) NOT NULL DEFAULT 'General'"),
        ("settings", "setting_label", "VARCHAR(255) NULL"),
        ("settings", "data_type", "VARCHAR(50) NOT NULL DEFAULT 'text'"),
        ("settings", "description", "TEXT NULL"),
        ("settings", "updated_at", "DATETIME NULL"),
    )
    for table, column, definition in definitions:
        if not _mysql_column_exists(db, table, column):
            db.execute(
                f"ALTER TABLE `{_identifier(table)}` "
                f"ADD COLUMN `{_identifier(column)}` {definition}"
            )
    db.execute(
        "CREATE TABLE IF NOT EXISTS sms_event_templates ("
        "event_key VARCHAR(50) PRIMARY KEY,event_name VARCHAR(100) NOT NULL,"
        "enabled INTEGER NOT NULL DEFAULT 1,template_text TEXT NOT NULL,"
        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS sms_delivery_log ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,event_key VARCHAR(50) NOT NULL,"
        "entity_type VARCHAR(50) NOT NULL,entity_id INTEGER NOT NULL,"
        "recipient VARCHAR(30) NOT NULL,message_text TEXT NOT NULL,"
        "provider VARCHAR(30) NOT NULL,status VARCHAR(30) NOT NULL DEFAULT 'Pending',"
        "attempt_count INTEGER NOT NULL DEFAULT 0,response_code VARCHAR(50),"
        "response_message TEXT,last_attempt_at DATETIME,sent_at DATETIME,"
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "UNIQUE KEY uq_sms_event_entity(event_key,entity_type,entity_id)) ENGINE=InnoDB"
    )
    applied = db.query_one(
        "SELECT version FROM schema_migrations WHERE version=?",
        (APPLICATION_SETTINGS_VERSION,),
    )
    if not applied:
        db.execute(
            "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (APPLICATION_SETTINGS_VERSION, APPLICATION_SETTINGS_NAME),
        )


def ensure_mysql_certificate_pdf_migration(db) -> None:
    definitions = (
        ("pdf_path", "TEXT NULL"),
        ("pdf_sha256", "VARCHAR(64) NULL"),
    )
    for column, definition in definitions:
        if not _mysql_column_exists(db, "course_certificates", column):
            db.execute(
                f"ALTER TABLE course_certificates "
                f"ADD COLUMN `{_identifier(column)}` {definition}"
            )
    applied = db.query_one(
        "SELECT version FROM schema_migrations WHERE version=?",
        (CERTIFICATE_PDF_VERSION,),
    )
    if not applied:
        db.execute(
            "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (CERTIFICATE_PDF_VERSION, CERTIFICATE_PDF_NAME),
        )


def ensure_mysql_counterparty_payable_migration(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS counterparties ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,counterparty_name VARCHAR(255) NOT NULL UNIQUE,"
        "counterparty_type VARCHAR(100) NOT NULL DEFAULT 'Vendor',contact VARCHAR(50),address TEXT,"
        "status VARCHAR(50) NOT NULL DEFAULT 'Active',remarks TEXT,"
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS counterparty_payments ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,counterparty_id INTEGER NOT NULL,payment_date VARCHAR(30) NOT NULL,"
        "amount DECIMAL(14,2) NOT NULL,paid_from_account_id INTEGER NOT NULL,payment_method VARCHAR(100),"
        "reference_no VARCHAR(255),remarks TEXT,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(counterparty_id) REFERENCES counterparties(id) ON DELETE RESTRICT,"
        "FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT) ENGINE=InnoDB"
    )
    for column, definition in (
        ("counterparty_id", "INTEGER NULL"),
        ("payment_status", "VARCHAR(30) NOT NULL DEFAULT 'Paid'"),
    ):
        if not _mysql_column_exists(db, "expense_records", column):
            db.execute(f"ALTER TABLE expense_records ADD COLUMN `{column}` {definition}")
    applied = db.query_one("SELECT version FROM schema_migrations WHERE version=?", (COUNTERPARTY_PAYABLE_VERSION,))
    if not applied:
        db.execute(
            "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (COUNTERPARTY_PAYABLE_VERSION, COUNTERPARTY_PAYABLE_NAME),
        )


def ensure_mysql_work_items_migration(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS todo_items ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,title VARCHAR(255) NOT NULL,details TEXT,"
        "assigned_teacher_id INTEGER NULL,due_date VARCHAR(30),priority VARCHAR(30) NOT NULL DEFAULT 'Normal',"
        "status VARCHAR(30) NOT NULL DEFAULT 'Open',created_by_user_id INTEGER NULL,completed_at DATETIME NULL,"
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(assigned_teacher_id) REFERENCES teachers(id) ON DELETE SET NULL,"
        "FOREIGN KEY(created_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL) ENGINE=InnoDB"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS bug_reports ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,title VARCHAR(255) NOT NULL,details TEXT NOT NULL,"
        "page_name VARCHAR(100),severity VARCHAR(30) NOT NULL DEFAULT 'Normal',"
        "status VARCHAR(30) NOT NULL DEFAULT 'Open',reported_by_user_id INTEGER NULL,"
        "resolution_note TEXT,resolved_at DATETIME NULL,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(reported_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL) ENGINE=InnoDB"
    )
    applied = db.query_one("SELECT version FROM schema_migrations WHERE version=?", (WORK_ITEMS_VERSION,))
    if not applied:
        db.execute("INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)", (WORK_ITEMS_VERSION, WORK_ITEMS_NAME))


def ensure_mysql_attendance_alert_review_migration(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS attendance_alert_reviews ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,student_id INTEGER NOT NULL,review_status VARCHAR(50) NOT NULL,"
        "note TEXT,follow_up_date VARCHAR(30),reviewed_by_user_id INTEGER NULL,"
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,"
        "FOREIGN KEY(reviewed_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL) ENGINE=InnoDB"
    )
    applied = db.query_one("SELECT version FROM schema_migrations WHERE version=?", (ATTENDANCE_ALERT_REVIEW_VERSION,))
    if not applied:
        db.execute("INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)", (ATTENDANCE_ALERT_REVIEW_VERSION, ATTENDANCE_ALERT_REVIEW_NAME))


def ensure_mysql_staff_account_migration(db) -> None:
    """Create one internal payment account per staff member and backfill existing staff."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS staff_payment_accounts ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,teacher_id INTEGER NOT NULL UNIQUE,"
        "account_name VARCHAR(255) NOT NULL UNIQUE,account_number VARCHAR(100),"
        "account_holder VARCHAR(255),bank_name VARCHAR(255),status VARCHAR(50) NOT NULL DEFAULT 'Active',"
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at DATETIME NULL,"
        "FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT) ENGINE=InnoDB"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS staff_payment_transactions ("
        "id INTEGER AUTO_INCREMENT PRIMARY KEY,staff_account_id INTEGER NOT NULL,transaction_date VARCHAR(30) NOT NULL,"
        "transaction_type VARCHAR(50) NOT NULL,amount DECIMAL(14,2) NOT NULL,source_type VARCHAR(100) NOT NULL,"
        "source_id INTEGER,paid_from_account_id INTEGER NULL,reference_no VARCHAR(255),particular VARCHAR(500) NOT NULL,"
        "remarks TEXT,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(staff_account_id) REFERENCES staff_payment_accounts(id) ON DELETE RESTRICT,"
        "FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE SET NULL) ENGINE=InnoDB"
    )
    db.execute(
        "INSERT IGNORE INTO staff_payment_accounts "
        "(teacher_id,account_name,account_number,account_holder,bank_name,status) "
        "SELECT t.id,CONCAT('Staff Account - ',t.id,' - ',t.teacher_name),t.bank_account_number,"
        "t.account_holder_name,t.bank_name,t.status FROM teachers t"
    )
    db.execute(
        "INSERT INTO staff_payment_transactions "
        "(staff_account_id,transaction_date,transaction_type,amount,source_type,source_id,"
        "paid_from_account_id,reference_no,particular,remarks) "
        "SELECT spa.id,sp.payment_date,'Salary Payment',sp.net_salary,'Salary Payout',sp.id,"
        "sp.paid_from_account_id,sp.voucher_no,CONCAT('Salary payment for ',sp.salary_month),sp.remarks "
        "FROM salary_payouts sp JOIN staff_payment_accounts spa ON spa.teacher_id=sp.teacher_id "
        "WHERE NOT EXISTS (SELECT 1 FROM staff_payment_transactions tx "
        "WHERE tx.source_type='Salary Payout' AND tx.source_id=sp.id)"
    )
    db.execute(
        "INSERT INTO staff_payment_transactions "
        "(staff_account_id,transaction_date,transaction_type,amount,source_type,source_id,"
        "paid_from_account_id,reference_no,particular,remarks) "
        "SELECT spa.id,ta.advance_date,'Staff Advance',ta.amount,'Teacher Advance',ta.id,"
        "ta.paid_from_account_id,ta.reference_no,'Recoverable staff advance',ta.remarks "
        "FROM teacher_advances ta JOIN staff_payment_accounts spa ON spa.teacher_id=ta.teacher_id "
        "WHERE NOT EXISTS (SELECT 1 FROM staff_payment_transactions tx "
        "WHERE tx.source_type='Teacher Advance' AND tx.source_id=ta.id)"
    )
    applied = db.query_one("SELECT version FROM schema_migrations WHERE version=?", (STAFF_ACCOUNT_VERSION,))
    if not applied:
        db.execute("INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)", (STAFF_ACCOUNT_VERSION, STAFF_ACCOUNT_NAME))


def ensure_mysql_bill_month_guard(db) -> None:
    """Enforce the cross-table bill-month rule without a redundant column."""
    definitions = {
        "trg_due_bill_items_unique_month_insert": "INSERT",
        "trg_due_bill_items_unique_month_update": "UPDATE",
    }
    for name, event in definitions.items():
        row = db.query_one(
            "SELECT COUNT(*) total FROM information_schema.triggers "
            "WHERE trigger_schema=? AND trigger_name=?",
            (db.config.database_name, name),
        )
        if row and int(row["total"]):
            continue
        exclude_current = "AND existing.id<>OLD.id" if event == "UPDATE" else ""
        db.execute(
            f"CREATE TRIGGER `{name}` BEFORE {event} ON due_bill_items FOR EACH ROW "
            "BEGIN "
            "IF EXISTS (SELECT 1 FROM due_bill_items existing "
            "JOIN due_bills existing_bill ON existing_bill.id=existing.bill_id "
            "JOIN due_bills new_bill ON new_bill.id=NEW.bill_id "
            "WHERE existing_bill.enrollment_id=new_bill.enrollment_id "
            f"AND existing.billing_month=NEW.billing_month {exclude_current}) THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Enrollment month is already billed'; "
            "END IF; END"
        )
    applied = db.query_one(
        "SELECT version FROM schema_migrations WHERE version=?",
        (BILL_MONTH_GUARD_VERSION,),
    )
    if not applied:
        db.execute(
            "INSERT INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (BILL_MONTH_GUARD_VERSION, BILL_MONTH_GUARD_NAME),
        )


def ensure_mysql_indexes(db) -> None:
    for table, name, columns in INDEXES:
        if _mysql_index_exists(db, table, columns):
            continue
        column_sql = ",".join(f"`{_identifier(column)}`" for column in columns)
        db.execute(
            f"CREATE INDEX `{_identifier(name)}` ON `{_identifier(table)}` ({column_sql})"
        )


def _sqlite_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({_identifier(table)})")}


def normalize_sqlite_schema(path) -> None:
    """Normalize a legacy SQLite file; fresh files already use the canonical DDL."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        has_migrations = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()[0]
        if not has_migrations:
            return
        columns = {
            table: _sqlite_columns(connection, table)
            for table in ("students", "enrollments", "due_bills", "due_bill_items")
        }
        legacy = any(
            column in columns[table]
            for table, column in (
                ("students", "school"),
                ("enrollments", "course_name"),
                ("due_bills", "student_id"),
                ("due_bills", "course_id"),
                ("due_bill_items", "enrollment_id"),
            )
        )
        if legacy:
            invalid = connection.execute(
                "SELECT COUNT(*) FROM enrollments e LEFT JOIN courses c ON c.id=e.course_id "
                "WHERE c.id IS NULL"
            ).fetchone()[0]
            if invalid:
                raise RuntimeError(
                    f"Cannot normalize schema: found {invalid} enrollments without a valid course."
                )
            connection.executescript(
                """
                BEGIN;
                CREATE TABLE students_normalized (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT NOT NULL,
                  class_name TEXT, school_id INTEGER, contact TEXT, gender TEXT,
                  date_of_birth TEXT, parent_name TEXT, guardian_relationship TEXT,
                  photo_data BLOB, photo_mime_type TEXT,
                  joining_date TEXT NOT NULL, address TEXT, status TEXT NOT NULL DEFAULT 'Active',
                  remarks TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(school_id) REFERENCES schools(id) ON DELETE SET NULL
                );
                INSERT INTO students_normalized
                  (id,student_name,class_name,school_id,contact,gender,date_of_birth,parent_name,guardian_relationship,photo_data,photo_mime_type,joining_date,address,status,remarks,created_at)
                  SELECT id,student_name,class_name,school_id,contact,gender,date_of_birth,parent_name,guardian_relationship,photo_data,photo_mime_type,joining_date,address,status,remarks,created_at FROM students;

                CREATE TABLE enrollments_normalized (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
                  course_id INTEGER NOT NULL, level TEXT, start_date TEXT NOT NULL, end_date TEXT,
                  monthly_fee REAL NOT NULL DEFAULT 0, admission_fee REAL NOT NULL DEFAULT 0,
                  discount REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Active',
                  remarks TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE RESTRICT,
                  FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
                );
                INSERT INTO enrollments_normalized
                  (id,student_id,course_id,level,start_date,end_date,monthly_fee,admission_fee,discount,status,remarks,created_at)
                  SELECT id,student_id,course_id,level,start_date,end_date,monthly_fee,admission_fee,discount,status,remarks,created_at FROM enrollments;

                CREATE TABLE due_bills_normalized (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, bill_number TEXT NOT NULL UNIQUE,
                  enrollment_id INTEGER NOT NULL, billing_period TEXT NOT NULL,
                  issue_date TEXT NOT NULL, due_date TEXT NOT NULL, subtotal REAL NOT NULL,
                  discount REAL NOT NULL DEFAULT 0, total_amount REAL NOT NULL,
                  paid_amount REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Due',
                  pdf_path TEXT, pos_printed_at TEXT, remarks TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(enrollment_id,billing_period),
                  FOREIGN KEY(enrollment_id) REFERENCES enrollments(id) ON DELETE RESTRICT
                );
                INSERT INTO due_bills_normalized
                  (id,bill_number,enrollment_id,billing_period,issue_date,due_date,subtotal,discount,total_amount,paid_amount,status,pdf_path,pos_printed_at,remarks,created_at)
                  SELECT id,bill_number,enrollment_id,billing_period,issue_date,due_date,subtotal,discount,total_amount,paid_amount,status,pdf_path,pos_printed_at,remarks,created_at FROM due_bills;

                CREATE TABLE due_bill_items_normalized (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, bill_id INTEGER NOT NULL,
                  billing_month TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(bill_id,billing_month),
                  FOREIGN KEY(bill_id) REFERENCES due_bills(id) ON DELETE CASCADE
                );
                INSERT INTO due_bill_items_normalized
                  (id,bill_id,billing_month,description,amount,created_at)
                  SELECT id,bill_id,billing_month,description,amount,created_at FROM due_bill_items;

                DROP TABLE due_bill_items;
                DROP TABLE due_bills;
                DROP TABLE enrollments;
                DROP TABLE students;
                ALTER TABLE students_normalized RENAME TO students;
                ALTER TABLE enrollments_normalized RENAME TO enrollments;
                ALTER TABLE due_bills_normalized RENAME TO due_bills;
                ALTER TABLE due_bill_items_normalized RENAME TO due_bill_items;
                COMMIT;
                """
            )

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS staff_payment_accounts (
              id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id INTEGER NOT NULL UNIQUE,
              account_name TEXT NOT NULL UNIQUE, account_number TEXT, account_holder TEXT,
              bank_name TEXT, status TEXT NOT NULL DEFAULT 'Active',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT,
              FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS staff_payment_transactions (
              id INTEGER PRIMARY KEY AUTOINCREMENT, staff_account_id INTEGER NOT NULL,
              transaction_date TEXT NOT NULL, transaction_type TEXT NOT NULL, amount REAL NOT NULL,
              source_type TEXT NOT NULL, source_id INTEGER, paid_from_account_id INTEGER,
              reference_no TEXT, particular TEXT NOT NULL, remarks TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(staff_account_id) REFERENCES staff_payment_accounts(id) ON DELETE RESTRICT,
              FOREIGN KEY(paid_from_account_id) REFERENCES accounts(id) ON DELETE SET NULL
            );
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO staff_payment_accounts "
            "(teacher_id,account_name,account_number,account_holder,bank_name,status) "
            "SELECT id,'Staff Account - ' || id || ' - ' || teacher_name,bank_account_number,"
            "account_holder_name,bank_name,status FROM teachers"
        )
        connection.execute(
            """
            INSERT INTO staff_payment_transactions
              (staff_account_id,transaction_date,transaction_type,amount,source_type,source_id,
               paid_from_account_id,reference_no,particular,remarks)
            SELECT spa.id,sp.payment_date,'Salary Payment',sp.net_salary,'Salary Payout',sp.id,
                   sp.paid_from_account_id,sp.voucher_no,'Salary payment for ' || sp.salary_month,sp.remarks
            FROM salary_payouts sp JOIN staff_payment_accounts spa ON spa.teacher_id=sp.teacher_id
            WHERE NOT EXISTS (
              SELECT 1 FROM staff_payment_transactions tx
              WHERE tx.source_type='Salary Payout' AND tx.source_id=sp.id
            )
            """
        )
        connection.execute(
            """
            INSERT INTO staff_payment_transactions
              (staff_account_id,transaction_date,transaction_type,amount,source_type,source_id,
               paid_from_account_id,reference_no,particular,remarks)
            SELECT spa.id,ta.advance_date,'Staff Advance',ta.amount,'Teacher Advance',ta.id,
                   ta.paid_from_account_id,ta.reference_no,'Recoverable staff advance',ta.remarks
            FROM teacher_advances ta JOIN staff_payment_accounts spa ON spa.teacher_id=ta.teacher_id
            WHERE NOT EXISTS (
              SELECT 1 FROM staff_payment_transactions tx
              WHERE tx.source_type='Teacher Advance' AND tx.source_id=ta.id
            )
            """
        )

        for table, name, columns_used in INDEXES:
            columns_sql = ",".join(_identifier(column) for column in columns_used)
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {_identifier(name)} "
                f"ON {_identifier(table)} ({columns_sql})"
            )
        connection.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS trg_due_bill_items_unique_month_insert
            BEFORE INSERT ON due_bill_items
            WHEN EXISTS (
              SELECT 1 FROM due_bill_items existing
              JOIN due_bills existing_bill ON existing_bill.id=existing.bill_id
              JOIN due_bills new_bill ON new_bill.id=NEW.bill_id
              WHERE existing_bill.enrollment_id=new_bill.enrollment_id
                AND existing.billing_month=NEW.billing_month
            )
            BEGIN
              SELECT RAISE(ABORT,'Enrollment month is already billed');
            END;
            CREATE TRIGGER IF NOT EXISTS trg_due_bill_items_unique_month_update
            BEFORE UPDATE OF bill_id,billing_month ON due_bill_items
            WHEN EXISTS (
              SELECT 1 FROM due_bill_items existing
              JOIN due_bills existing_bill ON existing_bill.id=existing.bill_id
              JOIN due_bills new_bill ON new_bill.id=NEW.bill_id
              WHERE existing_bill.enrollment_id=new_bill.enrollment_id
                AND existing.billing_month=NEW.billing_month
                AND existing.id<>OLD.id
            )
            BEGIN
              SELECT RAISE(ABORT,'Enrollment month is already billed');
            END;
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (NORMALIZATION_VERSION, NORMALIZATION_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (BILL_MONTH_GUARD_VERSION, BILL_MONTH_GUARD_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (CERTIFICATE_VERSION, CERTIFICATE_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (STUDENT_PROFILE_VERSION, STUDENT_PROFILE_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (APPLICATION_SETTINGS_VERSION, APPLICATION_SETTINGS_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (CERTIFICATE_PDF_VERSION, CERTIFICATE_PDF_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (COUNTERPARTY_PAYABLE_VERSION, COUNTERPARTY_PAYABLE_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (WORK_ITEMS_VERSION, WORK_ITEMS_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (ATTENDANCE_ALERT_REVIEW_VERSION, ATTENDANCE_ALERT_REVIEW_NAME),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version,migration_name) VALUES (?,?)",
            (STAFF_ACCOUNT_VERSION, STAFF_ACCOUNT_NAME),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.close()
