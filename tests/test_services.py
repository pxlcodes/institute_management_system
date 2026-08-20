from __future__ import annotations

import unittest
import tempfile
from hashlib import sha256
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import nepali_datetime as nepali
from PIL import Image

from elh.hardware.attendance.disabled import DisabledAttendanceDevice
from elh.hardware.printing.network_escpos import NetworkEscPosPrinter
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.services.auth import (
    AuthService,
    hash_login_password,
    password_needs_rehash,
    verify_login_password,
)
from pathlib import Path
from elh.models import (
    AttendanceDeviceUser,
    AttendanceEvent,
    CertificateIssueRequest,
    Receipt,
    ReceiptLine,
    Student,
)
from elh.repositories import (
    AttendanceRepository,
    BillingRepository,
    CertificateRepository,
    StudentRepository,
)
from elh.services.attendance import AttendanceService
from elh.services.billing import BillingService
from elh.services.certificates import CertificateService
from elh.services.people import StudentService
from elh.services.enrollments import EnrollmentService
from elh.services.notifications import NotificationService
from elh.core.settings import SettingsService
from elh.integrations.sms.aakash import AakashSmsProvider
from elh.integrations.sms.base import SmsProviderResponse
from elh.integrations.sms.sparrow import SparrowSmsProvider
from elh.config import AppConfig
from elh.hardware.factory import create_receipt_printer
from elh.hardware.printing.network_escpos import NetworkEscPosPrinter


class FakeAttendanceRepository:
    def __init__(self):
        self.events = []

    def mappings_for(self, device_user_ids):
        return {}

    def save_events(self, events, mappings):
        self.events.extend((event, mappings.get(event.device_user_id)) for event in events)
        return len(events)


class FakeDevice:
    def fetch_events(self):
        return [AttendanceEvent("42", datetime(2026, 8, 7, 8, 30))]

    def fetch_users(self):
        return [
            AttendanceDeviceUser(
                device_user_id="42",
                name="Device User Name",
                uid=7,
                privilege="0",
                card_number="1234",
                device_serial="ZK-TEST",
            )
        ]


class RecordingNotifications:
    def __init__(self):
        self.calls = []

    def notify(self, event_key, entity_type, entity_id, recipient, context, **_kwargs):
        self.calls.append((event_key, entity_type, entity_id, recipient, context))
        return len(self.calls)


class ServiceTests(unittest.TestCase):
    def test_fresh_schema_is_normalized_and_indexed(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "normalized.db", False)
            with db.connect() as connection:
                columns = {
                    table: {
                        row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                    for table in ("students", "enrollments", "due_bills", "due_bill_items")
                }
                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(ledger)")
                }
                settings_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(settings)")
                }
                course_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(courses)")
                }
                company_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(company_profile)")
                }
            self.assertNotIn("school", columns["students"])
            self.assertTrue(
                {
                    "gender",
                    "date_of_birth",
                    "guardian_relationship",
                    "photo_data",
                    "photo_mime_type",
                }.issubset(columns["students"])
            )
            self.assertNotIn("course_name", columns["enrollments"])
            self.assertNotIn("student_id", columns["due_bills"])
            self.assertNotIn("course_id", columns["due_bills"])
            self.assertNotIn("enrollment_id", columns["due_bill_items"])
            self.assertIn("idx_ledger_source", indexes)
            self.assertTrue(
                {"category", "setting_label", "data_type", "description"}.issubset(
                    settings_columns
                )
            )
            self.assertIn("instructor_name", course_columns)
            self.assertIn("principal_name", company_columns)
            self.assertIsNotNone(
                db.query_one(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='sms_delivery_log'"
                )
            )
            self.assertEqual(
                int(db.query_one("SELECT MAX(version) version FROM schema_migrations")["version"]),
                9,
            )
            certificate_columns = {
                row["name"] for row in db.query("PRAGMA table_info(course_certificates)")
            }
            self.assertTrue({"pdf_path", "pdf_sha256"}.issubset(certificate_columns))
            self.assertIsNotNone(
                db.query_one(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='course_certificates'"
                )
            )

    def test_completion_certificate_is_issued_once_from_retained_template(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = SQLiteDatabase(root / "certificate.db", False)
            photo_buffer = BytesIO()
            Image.new("RGB", (240, 300), "#2A7F9E").save(photo_buffer, "PNG")
            student_photo = photo_buffer.getvalue()
            course_id = db.execute(
                "INSERT INTO courses "
                "(course_name,category,billing_type,duration_months,instructor_name,status) "
                "VALUES (?,?,?,?,?, 'Active')",
                (
                    "Basic Computer Course",
                    "Computer",
                    "Course Complete",
                    3,
                    "Adarsha Nepal",
                ),
            )
            db.execute(
                "INSERT INTO company_profile (id,company_name,principal_name) VALUES (1,?,?)",
                ("Expert Learning Hub", "Bhim Raj Adhikari"),
            )
            student_id = db.execute(
                "INSERT INTO students "
                "(student_name,contact,gender,date_of_birth,parent_name,guardian_relationship,"
                "photo_data,photo_mime_type,joining_date,status) "
                "VALUES (?,?,?,?,?,?,?,?,?,'Active')",
                (
                    "Madan Rai",
                    "9800000001",
                    "Male",
                    "2066/07/24",
                    "Devendra Rai",
                    "Son of Mr.",
                    student_photo,
                    "image/png",
                    "2083/01/12",
                ),
            )
            enrollment_id = db.execute(
                "INSERT INTO enrollments "
                "(student_id,course_id,start_date,end_date,status) VALUES (?,?,?,?,'Completed')",
                (student_id, course_id, "2083/01/12", "2083/04/11"),
            )
            template = Path(__file__).resolve().parents[1] / "elh" / "assets" / "certificate_template.docx"
            config = replace(
                AppConfig(),
                certificate_template_path=template,
                certificate_output_directory=root / "output",
            )
            notifications = RecordingNotifications()
            service = CertificateService(CertificateRepository(db), config, notifications)
            request = CertificateIssueRequest(
                enrollment_id=enrollment_id,
                certificate_number="EXP-2083-007",
                certify_date="2083/04/11",
                instructor_name="",
                principal_name="",
            )
            certificate = service.issue(request)
            document = Path(certificate.document_path)
            pdf_document = Path(certificate.pdf_path)
            self.assertTrue(document.exists())
            self.assertTrue(pdf_document.exists())
            self.assertEqual(pdf_document.suffix.lower(), ".pdf")
            pdf_data = pdf_document.read_bytes()
            self.assertTrue(pdf_data.startswith(b"%PDF-"))
            self.assertIn(b"%%EOF", pdf_data[-2048:])
            self.assertEqual(certificate.pdf_sha256, sha256(pdf_data).hexdigest())
            self.assertEqual(certificate.duration_days, 90)
            self.assertEqual(certificate.instructor_name, "Adarsha Nepal")
            self.assertEqual(certificate.principal_name, "Bhim Raj Adhikari")
            self.assertEqual(notifications.calls[0][0], "certificate_issued")
            with ZipFile(document) as package:
                xml = package.read("word/document.xml").decode("utf-8")
                certificate_files = set(package.namelist())
                relationships = package.read(
                    "word/_rels/document.xml.rels"
                ).decode("utf-8")
            self.assertIn("EXP-2083-007", xml)
            self.assertIn("Certificate Date: ", xml)
            self.assertIn("Basic Computer Course", xml)
            self.assertNotIn("CERTIFICATEE", xml)
            self.assertIn("Student photo of Madan Rai", xml)
            self.assertIn("word/media/student-photo-1.JPG", certificate_files)
            self.assertIn("media/student-photo-1.JPG", relationships)
            self.assertEqual(
                service.repository.student_photo(enrollment_id)["photo_data"],
                student_photo,
            )

            db.execute(
                "UPDATE students SET photo_data=NULL,photo_mime_type=NULL WHERE id=?",
                (student_id,),
            )
            no_photo_document = service.regenerate_docx(certificate.id)
            with ZipFile(no_photo_document) as package:
                no_photo_xml = package.read("word/document.xml").decode("utf-8")
                self.assertNotIn("word/media/student-photo-1.JPG", package.namelist())
            self.assertIn(">Photo<", no_photo_xml)
            db.execute(
                "UPDATE students SET photo_data=?,photo_mime_type=? WHERE id=?",
                (student_photo, "image/png", student_id),
            )

            field_template = (
                Path(__file__).resolve().parents[1]
                / "templates"
                / "Certificate_Template_Editable_Fields.docx"
            )
            service.config = replace(config, certificate_template_path=field_template)
            field_document = service.regenerate_docx(certificate.id)
            with ZipFile(field_document) as package:
                field_xml = package.read("word/document.xml").decode("utf-8")
                field_files = set(package.namelist())
            self.assertNotIn("{{", field_xml)
            self.assertIn("EXP-2083-007", field_xml)
            self.assertIn("Basic Computer Course", field_xml)
            self.assertIn("word/media/student-photo-1.JPG", field_files)

            service.config = replace(
                config,
                certificate_template_path=root / "missing-template.docx",
            )
            regenerated_pdf = service.regenerate(certificate.id)
            self.assertEqual(regenerated_pdf.suffix.lower(), ".pdf")
            self.assertTrue(regenerated_pdf.is_file())

            with self.assertRaisesRegex(ValueError, "already been issued"):
                service.issue(request)

    def test_student_optional_profile_and_photo_are_saved_for_later(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "student-profile.db", False)
            service = StudentService(StudentRepository(db), "%Y/%m/%d")
            student_id = service.register(
                Student(
                    id=None,
                    name="Aakriti Karki",
                    gender="female",
                    date_of_birth="2068/02/12",
                    parent_name="Sita Karki",
                    guardian_relationship="Daughter of Mr.",
                    joining_date="2083/04/24",
                    photo_data=b"\xff\xd8\xffsmall-test-photo",
                    photo_mime_type="image/jpeg",
                )
            )

            saved = service.get(student_id)
            self.assertEqual(saved.gender, "Female")
            self.assertEqual(saved.date_of_birth, "2068/02/12")
            self.assertEqual(saved.photo_data, b"\xff\xd8\xffsmall-test-photo")
            self.assertEqual(saved.photo_mime_type, "image/jpeg")

            quick_id = service.register(
                Student(id=None, name="Quick Entry", joining_date="2083/04/24")
            )
            quick = service.get(quick_id)
            self.assertEqual(quick.gender, "")
            self.assertIsNone(quick.photo_data)

    def test_registration_enrollment_billing_and_payment_emit_sms_events(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "notification-events.db", False)
            notifications = RecordingNotifications()
            student_id = StudentService(
                StudentRepository(db), "%Y/%m/%d", notifications
            ).register(
                Student(
                    id=None,
                    name="SMS Student",
                    contact="9800000002",
                    joining_date="2083/04/24",
                )
            )
            course_id = db.execute(
                "INSERT INTO courses "
                "(course_name,category,billing_type,status) VALUES (?,?,?,'Active')",
                ("SMS Course", "Computer", "Monthly"),
            )
            enrollment_id = EnrollmentService(
                db, notifications, "%Y/%m/%d"
            ).create(
                student_id,
                course_id,
                "",
                "2083/04/24",
                "",
                Decimal("2000"),
                Decimal("0"),
                Decimal("0"),
                "Active",
                "",
            )
            account_id = db.execute(
                "INSERT INTO accounts "
                "(account_name,account_type,opening_balance,status) VALUES (?,?,0,'Active')",
                ("SMS Cash", "Cash Counter"),
            )
            billing = BillingService(
                BillingRepository(db),
                None,
                "Expert Learning Hub",
                "Rs.",
                notifications,
            )
            bill = billing.generate(
                enrollment_id,
                "2083/04",
                "2083/04/24",
                "2083/04/31",
            ).bill
            billing.pay(
                bill.id,
                Decimal("500"),
                "2083/04/25",
                account_id,
                "Cash",
            )

            self.assertEqual(
                [call[0] for call in notifications.calls],
                ["registration", "enrollment", "due_bill", "bill_payment"],
            )
            certificate_id = db.execute(
                "INSERT INTO course_certificates "
                "(certificate_number,enrollment_id,honorific,guardian_relationship,date_of_birth,"
                "student_name_snapshot,guardian_name_snapshot,course_name_snapshot,"
                "company_name_snapshot,course_start_date,course_end_date,duration_days,"
                "certify_date,instructor_name,principal_name) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "SMS-2083-001",
                    enrollment_id,
                    "Mx.",
                    "Child of",
                    "",
                    "SMS Student",
                    "",
                    "SMS Course",
                    "Expert Learning Hub",
                    "2083/04/24",
                    "2083/05/24",
                    30,
                    "2083/05/24",
                    "Instructor",
                    "Principal",
                ),
            )
            manual = NotificationService(
                db, replace(AppConfig(), aakash_sms_token="manual-token")
            )
            SettingsService(db).set("sms_provider", "aakash")
            db.execute("UPDATE sms_event_templates SET enabled=0")
            history = manual.student_event_history(student_id)
            self.assertEqual(
                {event["event_key"] for event in history["events"]},
                {
                    "registration",
                    "enrollment",
                    "due_bill",
                    "bill_payment",
                    "certificate_issued",
                },
            )

            class ManualProvider:
                def send(self, _recipient, _message):
                    return SmsProviderResponse(True, "200", "queued")

            references = [
                (event["event_key"], event["source_id"])
                for event in history["events"]
            ]
            with patch(
                "elh.services.notifications.create_sms_provider",
                return_value=ManualProvider(),
            ):
                first_logs = manual.queue_student_events(
                    student_id, references, asynchronous=False
                )
                repeated_log = manual.queue_student_events(
                    student_id,
                    [("registration", student_id)],
                    asynchronous=False,
                )
            self.assertEqual(len(first_logs), 5)
            self.assertEqual(len(repeated_log), 1)
            self.assertEqual(
                db.query_one(
                    "SELECT COUNT(*) total FROM sms_delivery_log WHERE status='Sent'"
                )["total"],
                6,
            )
            self.assertTrue(certificate_id)

    def test_sms_outbox_templates_and_both_provider_adapters(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "sms-outbox.db", False)
            config = replace(AppConfig(), aakash_sms_token="a-token")
            notifications = NotificationService(db, config)
            settings = SettingsService(db)
            settings.set("sms_enabled", "true")
            settings.set("sms_provider", "aakash")

            class SuccessfulProvider:
                name = "aakash"

                def send(self, recipient, message):
                    self.recipient = recipient
                    self.message = message
                    return SmsProviderResponse(True, "200", "queued")

            provider = SuccessfulProvider()
            with patch(
                "elh.services.notifications.create_sms_provider",
                return_value=provider,
            ):
                log_id = notifications.notify(
                    "registration",
                    "student",
                    11,
                    "+977-9800000003",
                    {"student_name": "Test Student", "joining_date": "2083/04/24"},
                    asynchronous=False,
                )
            log = db.query_one("SELECT * FROM sms_delivery_log WHERE id=?", (log_id,))
            self.assertEqual(log["status"], "Sent")
            self.assertEqual(log["recipient"], "9800000003")
            self.assertIn("Test Student", log["message_text"])
            skipped_id = notifications.notify(
                "registration",
                "student",
                12,
                "",
                {"student_name": "No Mobile", "joining_date": "2083/04/24"},
                asynchronous=False,
            )
            self.assertEqual(
                db.query_one("SELECT status FROM sms_delivery_log WHERE id=?", (skipped_id,))[
                    "status"
                ],
                "Skipped",
            )

            with patch(
                "elh.integrations.sms.aakash.post_form",
                return_value=(200, {"error": False, "message": "queued"}, ""),
            ) as request:
                response = AakashSmsProvider("https://aakash.test", "token").send(
                    "9800000003", "hello"
                )
                self.assertTrue(response.success)
                self.assertEqual(request.call_args.args[1]["auth_token"], "token")

            with patch(
                "elh.integrations.sms.sparrow.post_form",
                return_value=(200, {"response_code": 200, "response": "queued"}, ""),
            ) as request:
                response = SparrowSmsProvider(
                    "https://sparrow.test", "token", "ELH"
                ).send("9800000003", "hello")
                self.assertTrue(response.success)
                self.assertEqual(request.call_args.args[1]["from"], "ELH")

    def test_normalized_bill_items_still_reject_duplicate_enrollment_months(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "bill-month-guard.db", False)
            course_id = db.execute(
                "INSERT INTO courses (course_name,category,billing_type,status) VALUES (?,?,?,'Active')",
                ("Monthly Course", "Tuition", "Monthly"),
            )
            student_id = db.execute(
                "INSERT INTO students (student_name,joining_date,status) VALUES (?,?,'Active')",
                ("Test Student", "2083/04/01"),
            )
            enrollment_id = db.execute(
                "INSERT INTO enrollments (student_id,course_id,start_date,status) VALUES (?,?,?,'Active')",
                (student_id, course_id, "2083/04/01"),
            )
            bill_ids = [
                db.execute(
                    "INSERT INTO due_bills (bill_number,enrollment_id,billing_period,issue_date,due_date,subtotal,total_amount,status) "
                    "VALUES (?,?,?,?,?,?,?,'Due')",
                    (f"B-{number}", enrollment_id, f"range-{number}", "2083/04/01", "2083/04/07", 100, 100),
                )
                for number in (1, 2)
            ]
            db.execute(
                "INSERT INTO due_bill_items (bill_id,billing_month,description,amount) VALUES (?,?,?,?)",
                (bill_ids[0], "2083/04", "Fee", 100),
            )
            with self.assertRaises(Exception):
                db.execute(
                    "INSERT INTO due_bill_items (bill_id,billing_month,description,amount) VALUES (?,?,?,?)",
                    (bill_ids[1], "2083/04", "Fee again", 100),
                )

    def test_vendor_credit_purchase_and_settlement_keep_cash_and_payable_balances(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "vendor-credit.db", False)
            bank_id = db.execute(
                "INSERT INTO accounts (account_name,account_type,opening_balance,status) VALUES (?,?,?,'Active')",
                ("Bank", "Bank Account", 1000),
            )
            payable_id = db.execute(
                "INSERT INTO accounts (account_name,account_type,opening_balance,status) VALUES (?,?,?,'Active')",
                ("Accounts Payable Clearing", "Credit Account", 0),
            )
            vendor_id = db.execute(
                "INSERT INTO counterparties (counterparty_name,counterparty_type,status) VALUES (?,?,'Active')",
                ("ABC Stationery", "Vendor"),
            )
            expense_id = db.execute(
                """INSERT INTO expense_records
                (expense_date,category,particular,amount,paid_from_account_id,counterparty_id,payment_status)
                VALUES (?,?,?,?,?,?,?)""",
                ("2083/05/01", "Stationery", "Books", 500, payable_id, vendor_id, "Credit"),
            )
            def record_credit(conn):
                db.add_ledger(conn, "2083/05/01", payable_id, "OUT", 500, "Expense", expense_id, "Books")
            db.transaction(record_credit)
            payment_id = db.execute(
                "INSERT INTO counterparty_payments (counterparty_id,payment_date,amount,paid_from_account_id) VALUES (?,?,?,?)",
                (vendor_id, "2083/05/05", 500, bank_id),
            )
            def settle_credit(conn):
                db.add_ledger(conn, "2083/05/05", bank_id, "OUT", 500, "Vendor Credit Payment", payment_id, "ABC Stationery")
                db.add_ledger(conn, "2083/05/05", payable_id, "IN", 500, "Vendor Credit Payment", payment_id, "ABC Stationery")
            db.transaction(settle_credit)
            self.assertEqual(db.account_balance(bank_id), 500)
            self.assertEqual(db.account_balance(payable_id), 0)
            due = db.query_one(
                "SELECT COALESCE(SUM(amount),0) amount FROM expense_records WHERE counterparty_id=? AND payment_status='Credit'",
                (vendor_id,),
            )
            settled = db.query_one(
                "SELECT COALESCE(SUM(amount),0) amount FROM counterparty_payments WHERE counterparty_id=?",
                (vendor_id,),
            )
            self.assertEqual(float(due["amount"]) - float(settled["amount"]), 0)

    def test_disabled_hardware_is_safe(self):
        self.assertEqual(DisabledAttendanceDevice().fetch_events(), [])
        self.assertEqual(DisabledAttendanceDevice().fetch_users(), [])

    def test_attendance_service_does_not_depend_on_zkteco_library(self):
        repository = FakeAttendanceRepository()
        result = AttendanceService(repository, FakeDevice()).sync()
        self.assertEqual((result.received, result.saved, result.unmapped), (1, 1, 1))

    def test_attendance_device_users_are_fetched_with_device_names(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = AttendanceRepository(
                SQLiteDatabase(Path(folder) / "device-users.db", False)
            )
            result = AttendanceService(repository, FakeDevice()).sync_device_users()
            rows = repository.device_users()

            self.assertEqual((result.received, result.stored), (1, 1))
            self.assertEqual(rows[0]["device_user_id"], "42")
            self.assertEqual(rows[0]["device_name"], "Device User Name")
            self.assertEqual(rows[0]["device_uid"], 7)
            self.assertEqual(rows[0]["log_count"], 0)

    def test_attendance_mapping_merges_existing_punches_and_calculates_staff_totals(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "attendance.db", False)
            staff_id = db.execute(
                "INSERT INTO teachers "
                "(teacher_name, staff_type, joined_date, salary_type, basic_salary, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("Maya Rai", "Teaching", "2083/01/01", "Monthly Salary", 0, "Active"),
            )
            repository = AttendanceRepository(db)
            repository.save_event(
                AttendanceEvent("26", datetime(2026, 8, 9, 8, 0)),
                None,
            )
            repository.save_event(
                AttendanceEvent("26", datetime(2026, 8, 9, 17, 30)),
                None,
            )

            service = AttendanceService(repository, DisabledAttendanceDevice())
            service.map_device_user("26", "teacher", staff_id)

            service.assign_person_device("teacher", staff_id, "27")
            self.assertIsNone(repository.mapping_for("26"))
            self.assertEqual(repository.mapping_for("27").person_id, staff_id)
            service.assign_person_device("teacher", staff_id, None)
            self.assertIsNone(repository.mapping_for("27"))
            service.assign_person_device("teacher", staff_id, "26")

            logs = repository.logs()
            self.assertTrue(all(row["person_id"] == staff_id for row in logs))
            totals = service.staff_totals("2026-08-09 00:00:00", "2026-08-09 23:59:59")
            self.assertEqual(totals[0]["days"], 1)
            self.assertEqual(totals[0]["punches"], 2)
            self.assertEqual(totals[0]["hours"], 9.5)

            salary_month = nepali.date.from_datetime_date(
                date(2026, 8, 9)
            ).strftime("%Y/%m")
            salary_summary = service.staff_month_summary(staff_id, salary_month)
            self.assertEqual(salary_summary["days"], 1)
            self.assertEqual(salary_summary["punches"], 2)
            self.assertEqual(salary_summary["hours"], 9.5)

    def test_student_attendance_month_totals_and_quick_enrollment_skip_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "student-attendance.db", False)
            course_id = db.execute(
                "INSERT INTO courses (course_name,category,billing_type,default_fee,status) "
                "VALUES (?,?,?,?, 'Active')",
                ("Basic Tuition", "Tuition", "Monthly", 2000),
            )
            student_ids = [
                db.execute(
                    "INSERT INTO students (student_name,class_name,joining_date,status) VALUES (?,?,?,'Active')",
                    (name, class_name, joining_date),
                )
                for name, class_name, joining_date in (
                    ("Aakriti Karki", "12", "2083/01/12"),
                    ("Bishal Rai", "10", "2083/02/18"),
                )
            ]
            repository = AttendanceRepository(db)
            service = AttendanceService(repository, DisabledAttendanceDevice())
            attendance_date = date(2026, 8, 9)
            month = nepali.date.from_datetime_date(attendance_date).strftime("%Y/%m")
            for student_id, device_id in zip(student_ids, ("501", "502")):
                service.map_device_user(device_id, "student", student_id)
                repository.save_event(AttendanceEvent(device_id, datetime(2026, 8, 9, 8, 0)), repository.mapping_for(device_id))
                repository.save_event(AttendanceEvent(device_id, datetime(2026, 8, 9, 10, 30)), repository.mapping_for(device_id))

            totals = service.student_month_totals(month)
            self.assertEqual([(row["days"], row["punches"], row["hours"]) for row in totals], [(1, 2, 2.5), (1, 2, 2.5)])

            enrollments = EnrollmentService(db, None)
            created, skipped = enrollments.create_for_attendance_students(
                student_ids, course_id,
                end_date="", monthly_fee=2000, admission_fee=0, discount=0,
            )
            self.assertEqual(len(created), 2)
            self.assertEqual(skipped, [])
            details = db.query(
                "SELECT student_id,level,start_date FROM enrollments ORDER BY student_id"
            )
            self.assertEqual(
                [(row["level"], row["start_date"]) for row in details],
                [("12", "2083/01/12"), ("10", "2083/02/18")],
            )
            created_again, skipped_again = enrollments.create_for_attendance_students(
                student_ids, course_id,
                end_date="", monthly_fee=2000, admission_fee=0, discount=0,
            )
            self.assertEqual(created_again, [])
            self.assertEqual(sorted(skipped_again), sorted(student_ids))

    def test_attendance_sync_does_not_save_the_same_device_punch_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            repository = AttendanceRepository(
                SQLiteDatabase(Path(folder) / "attendance-duplicates.db", False)
            )
            service = AttendanceService(repository, FakeDevice())
            first = service.sync()
            second = service.sync()
            self.assertEqual(first.saved, 1)
            self.assertEqual(second.saved, 0)

    def test_receipt_rendering_is_separate_from_ui(self):
        printer = NetworkEscPosPrinter("127.0.0.1")
        payload = printer._render(Receipt(
            title="ELH", receipt_number="R-1", issued_at="2026-08-07",
            lines=[ReceiptLine("Fee", Decimal("100.00"))],
        ))
        self.assertIn(b"R-1", payload)
        self.assertIn(b"100.00", payload)

    def test_billing_month_range_is_inclusive(self):
        service = BillingService.__new__(BillingService)
        calls = []
        service.generate = lambda enrollment_id, period, issue, due, remarks: calls.append((enrollment_id, period)) or period
        results = service.generate_month_range([10, 20], "2083/11", "2084/02", "2083/11/01", "2083/11/07")
        self.assertEqual(len(results), 8)
        self.assertEqual(calls[:4], [(10, "2083/11"), (10, "2083/12"), (10, "2084/01"), (10, "2084/02")])

    def test_bills_resolve_course_name_through_course_id(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "billing-course-name.db", False)
            course_id = db.execute(
                "INSERT INTO courses (course_name,category,billing_type,status) VALUES (?,?,?,'Active')",
                ("Tuition 2 Hrs", "Tuition", "Monthly"),
            )
            student_id = db.execute(
                "INSERT INTO students (student_name,joining_date,status) VALUES (?,?,'Active')",
                ("Test Student", "2083/04/01"),
            )
            enrollment_id = db.execute(
                "INSERT INTO enrollments (student_id,course_id,start_date,monthly_fee,status) "
                "VALUES (?,?,?,?,'Active')",
                (student_id, course_id, "2083/04/01", 2000),
            )
            bill_id = db.execute(
                "INSERT INTO due_bills (bill_number,enrollment_id,billing_period,"
                "issue_date,due_date,subtotal,total_amount,status) VALUES (?,?,?,?,?,?,?,'Due')",
                ("ELH-TEST", enrollment_id, "2083/04", "2083/04/27", "2083/05/03", 2000, 2000),
            )

            repository = BillingRepository(db)
            self.assertEqual(repository.enrollment(enrollment_id)["course_name"], "Tuition 2 Hrs")
            self.assertEqual(repository.get(bill_id).course_name, "Tuition 2 Hrs")

    def test_billing_month_range_rejects_reverse_range(self):
        service = BillingService.__new__(BillingService)
        with self.assertRaises(ValueError):
            service.generate_month_range([1], "2083/09", "2083/08", "2083/08/01", "2083/08/07")

    def test_billing_skips_months_before_enrollment_start(self):
        class Repository:
            def enrollments(self, enrollment_ids):
                return {1:{"start_date":"2083/05/10"}}
            def billed_months_many(self, enrollment_ids, months):return {}
            def bill_counts(self, enrollment_ids):return {}
            def get_many(self, bill_ids):return {}
        service=BillingService.__new__(BillingService);service.repository=Repository()
        results=service.generate_combined_month_range([1],"2083/01","2083/04","2083/04/24","2083/04/31")
        self.assertEqual(results,[])

    def test_single_bill_rejects_period_before_enrollment_start(self):
        class Repository:
            def enrollment(self, enrollment_id):
                return {"start_date":"2083/05/10"}
        service=BillingService.__new__(BillingService);service.repository=Repository()
        with self.assertRaisesRegex(ValueError,"enrollment starts"):
            service.generate(1,"2083/04","2083/04/24","2083/04/31")

    def test_bill_payment_normalizes_ui_float_to_decimal(self):
        class PaymentRepository:
            def record_payment(self, bill_id, amount, discount, *args):
                self.amount = amount; self.discount = discount
            def get(self, bill_id):
                return bill_id
        repository = PaymentRepository()
        service = BillingService.__new__(BillingService)
        service.repository = repository
        service.pay(7, 8000.0, "2083/04/23", 1, "Cash")
        self.assertEqual(repository.amount, Decimal("8000.0"))
        self.assertIsInstance(repository.amount, Decimal)
        self.assertEqual(repository.discount, Decimal("0"))

    def test_enabled_printer_alias_does_not_block_startup(self):
        config = replace(AppConfig(), pos_printer_driver="enabled", pos_printer_host="127.0.0.1")
        self.assertIsInstance(create_receipt_printer(config), NetworkEscPosPrinter)

    def test_role_users_authenticate_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            db=SQLiteDatabase(Path(folder)/"auth.db",False);config=AppConfig()
            auth=AuthService(db,config);auth.ensure_initial_users()
            self.assertEqual(auth.authenticate("operator",config.operator_password).role,"operator")
            self.assertEqual(auth.authenticate("admin",config.admin_password).role,"admin")
            self.assertEqual(auth.authenticate("maintenance",config.maintenance_password).role,"maintenance")
            self.assertIsNone(auth.authenticate("operator","wrong"))

    def test_user_administration_permissions_password_status_and_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "aaa.db", False)
            config = AppConfig()
            auth = AuthService(db, config)
            auth.ensure_initial_users()
            admin = auth.authenticate("admin", config.admin_password)

            user_id = auth.create_user(
                "report.user",
                "Report@1234",
                "Report User",
                "report@example.com",
                "viewer",
                "Active",
                {"dashboard.view"},
                admin,
                False,
            )
            session = auth.authenticate("report.user", "Report@1234")
            self.assertEqual(session.display_name, "Report User")
            self.assertEqual(session.permissions, frozenset({"dashboard.view"}))

            auth.update_user(
                user_id,
                "Report User",
                "report@example.com",
                "viewer",
                "Disabled",
                {"dashboard.view"},
                admin,
            )
            self.assertIsNone(auth.authenticate("report.user", "Report@1234"))

            auth.update_user(
                user_id,
                "Report User",
                "report@example.com",
                "viewer",
                "Active",
                {"dashboard.view", "reports.view"},
                admin,
            )
            auth.change_password(user_id, "Changed@1234", admin)
            self.assertIsNone(auth.authenticate("report.user", "Report@1234"))
            self.assertEqual(
                auth.authenticate("report.user", "Changed@1234").permissions,
                frozenset({"dashboard.view", "reports.view"}),
            )
            events = {row["event_type"] for row in auth.list_audit()}
            self.assertIn("user_created", events)
            self.assertIn("user_updated", events)
            self.assertIn("password_changed", events)
            self.assertIn("login", events)

    def test_failed_logins_temporarily_lock_user_until_password_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "lockout.db", False)
            config = AppConfig()
            auth = AuthService(db, config)
            auth.ensure_initial_users()
            admin = auth.authenticate("admin", config.admin_password)
            user_id = auth.create_user(
                "locked.user",
                "Locked@1234",
                "Locked User",
                "",
                "operator",
                "Active",
                None,
                admin,
                False,
            )
            for _attempt in range(auth.MAX_FAILED_ATTEMPTS):
                self.assertIsNone(auth.authenticate("locked.user", "Wrong123"))
            self.assertIsNone(auth.authenticate("locked.user", "Locked@1234"))
            auth.change_password(user_id, "Unlocked@1234", admin)
            self.assertIsNotNone(auth.authenticate("locked.user", "Unlocked@1234"))

    def test_legacy_password_hash_is_verified_and_marked_for_upgrade(self):
        legacy_format = hash_login_password(
            "Legacy@1234", salt=b"0123456789abcdef", iterations=260_000
        )
        _algorithm, _iterations, salt_hex, digest = legacy_format.split("$")
        legacy = f"pbkdf2_sha256${salt_hex}${digest}"
        current = hash_login_password("Legacy@1234", salt=b"0123456789abcdef")
        self.assertTrue(verify_login_password("Legacy@1234", legacy))
        self.assertTrue(password_needs_rehash(legacy))
        self.assertFalse(password_needs_rehash(current))

    def test_pos_receipt_feeds_paper_before_cut(self):
        printer=NetworkEscPosPrinter("127.0.0.1")
        receipt=Receipt("DUE BILL","B-1","2083/04/23","Student Name",[ReceiptLine("Tuition",Decimal("500"))],"DUE BY: 2083/04/30")
        payload=printer._render(receipt)
        self.assertIn(b"Name: Student Name",payload)
        self.assertLess(payload.index(b"DUE BY"),payload.index(b"\x1dV"))
        self.assertGreaterEqual(payload[payload.index(b"DUE BY"):payload.index(b"\x1dV")].count(b"\n"),6)


if __name__ == "__main__":
    unittest.main()
