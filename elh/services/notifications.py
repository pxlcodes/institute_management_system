from __future__ import annotations

import logging
import re
import secrets
import sqlite3
import threading
from decimal import Decimal
from string import Formatter

from elh.config import AppConfig
from elh.core.settings import SettingsService
from elh.integrations.sms import create_sms_provider


SMS_EVENT_TEMPLATES = (
    (
        "registration",
        "Student Registration",
        "Dear {student_name}, your registration at {company_name} is complete on {joining_date}.",
    ),
    (
        "enrollment",
        "Course Enrollment",
        "Dear {student_name}, you are enrolled in {course_name} from {start_date}. Fee: {currency_symbol} {fee}.",
    ),
    (
        "due_bill",
        "Due Bill Generated",
        "Dear {student_name}, bill {bill_number} for {currency_symbol} {amount} is due by {due_date}. {company_name}",
    ),
    (
        "bill_payment",
        "Bill Payment Received",
        "Dear {student_name}, payment of {currency_symbol} {amount} was received on {payment_date}. Balance: {currency_symbol} {balance}. {company_name}",
    ),
    (
        "certificate_issued",
        "Certificate Issued",
        "Dear {student_name}, certificate {certificate_number} for {course_name} was issued on {certificate_date}. {company_name}",
    ),
    (
        "attendance_absence",
        "Student Absence Alert",
        "Dear Parent/Guardian, {student_name} has not recorded attendance on {attendance_date}. Please contact {company_name} if this is due to leave or an attendance issue.",
    ),
)

COMMON_TEMPLATE_FIELDS = {
    "company_name",
    "company_phone",
    "principal_name",
    "currency_symbol",
}
SMS_EVENT_FIELDS = {
    "registration": COMMON_TEMPLATE_FIELDS | {"student_name", "joining_date"},
    "enrollment": COMMON_TEMPLATE_FIELDS
    | {"student_name", "course_name", "start_date", "fee"},
    "due_bill": COMMON_TEMPLATE_FIELDS
    | {
        "student_name",
        "course_name",
        "bill_number",
        "amount",
        "due_date",
        "period",
    },
    "bill_payment": COMMON_TEMPLATE_FIELDS
    | {
        "student_name",
        "course_name",
        "bill_number",
        "amount",
        "discount",
        "balance",
        "payment_date",
    },
    "certificate_issued": COMMON_TEMPLATE_FIELDS
    | {
        "student_name",
        "course_name",
        "certificate_number",
        "certificate_date",
    },
    "attendance_absence": COMMON_TEMPLATE_FIELDS | {"student_name", "attendance_date"},
}


class NotificationService:
    """Persistent, non-blocking SMS outbox shared by desktop and future web UIs."""

    def __init__(self, db, config: AppConfig):
        self.db = db
        self.config = config
        self.settings = SettingsService(db)
        self._dispatch_lock = threading.Lock()
        self._worker_guard = threading.Lock()
        self._worker_running = False
        self.ensure_defaults()

    def ensure_defaults(self) -> None:
        self.settings.ensure_defaults()
        existing = {
            row["event_key"]
            for row in self.db.query("SELECT event_key FROM sms_event_templates")
        }
        missing = [template for template in SMS_EVENT_TEMPLATES if template[0] not in existing]
        if missing:
            self.db.executemany(
                "INSERT INTO sms_event_templates "
                "(event_key,event_name,enabled,template_text) VALUES (?,?,1,?)",
                missing,
            )

    @staticmethod
    def normalize_recipient(value: str) -> str:
        digits = re.sub(r"\D", "", value or "")
        if len(digits) == 13 and digits.startswith("977"):
            digits = digits[3:]
        if len(digits) != 10 or not digits.startswith("9"):
            raise ValueError("SMS recipient must be a valid 10-digit Nepal mobile number.")
        return digits

    @staticmethod
    def render(template: str, context: dict[str, object]) -> str:
        fields = {
            field_name
            for _literal, field_name, _format, _conversion in Formatter().parse(template)
            if field_name
        }
        missing = sorted(field for field in fields if field not in context)
        if missing:
            raise ValueError(f"SMS template field is unavailable: {missing[0]}")
        message = template.format_map({key: str(value) for key, value in context.items()}).strip()
        if not message:
            raise ValueError("SMS message cannot be blank.")
        if len(message) > 500:
            raise ValueError("SMS message cannot exceed 500 characters.")
        return message

    @staticmethod
    def validate_template(event_key: str, template: str) -> None:
        try:
            fields = {
                field_name
                for _literal, field_name, _format, _conversion in Formatter().parse(template)
                if field_name
            }
        except ValueError as exc:
            raise ValueError("SMS template contains unmatched braces.") from exc
        unknown = sorted(fields - SMS_EVENT_FIELDS.get(event_key, set()))
        if unknown:
            raise ValueError(f"Unsupported field for this event: {{{unknown[0]}}}")
        if not template.strip():
            raise ValueError("SMS template cannot be blank.")
        if len(template.strip()) > 500:
            raise ValueError("SMS template cannot exceed 500 characters.")

    def company_context(self) -> dict[str, str]:
        row = self.db.query_one(
            "SELECT company_name,phone,principal_name FROM company_profile WHERE id=1"
        )
        return {
            "company_name": (row["company_name"] if row else None) or self.config.app_title,
            "company_phone": (row["phone"] if row else None) or "",
            "principal_name": (row["principal_name"] if row else None) or "",
            "currency_symbol": self.settings.get("currency_symbol", self.config.currency_symbol),
        }

    def validate_provider_configuration(self) -> str:
        provider = self.settings.get("sms_provider", "aakash").strip().lower()
        if provider == "aakash":
            if not self.config.aakash_sms_token.strip():
                raise ValueError("Aakash SMS token is not configured in .env.")
        elif provider == "sparrow":
            if not self.config.sparrow_sms_token.strip():
                raise ValueError("Sparrow SMS token is not configured in .env.")
            if not self.settings.get("sms_sender_id", "").strip():
                raise ValueError(
                    "Sparrow SMS sender ID is not configured in SMS & Notifications."
                )
        else:
            raise ValueError("SMS provider must be Aakash or Sparrow.")
        return provider

    @staticmethod
    def _money(value) -> str:
        return f"{Decimal(str(value or 0)):,.2f}"

    def student_event_history(self, student_id: int) -> dict[str, object]:
        student = self.db.query_one(
            "SELECT id,student_name,contact,joining_date FROM students WHERE id=?",
            (student_id,),
        )
        if not student:
            raise ValueError("Student was not found.")
        events: list[dict[str, object]] = [
            {
                "event_key": "registration",
                "source_type": "student",
                "source_id": int(student["id"]),
                "event_name": "Registration",
                "reference": f"Student #{student['id']}",
                "event_date": student["joining_date"],
                "details": "Student registration",
                "context": {
                    "student_name": student["student_name"],
                    "joining_date": student["joining_date"],
                },
            }
        ]
        for row in self.db.query(
            "SELECT e.id,e.start_date,e.monthly_fee,e.status,c.course_name "
            "FROM enrollments e JOIN courses c ON c.id=e.course_id "
            "WHERE e.student_id=? ORDER BY e.start_date,e.id",
            (student_id,),
        ):
            events.append(
                {
                    "event_key": "enrollment",
                    "source_type": "enrollment",
                    "source_id": int(row["id"]),
                    "event_name": "Enrollment",
                    "reference": row["course_name"],
                    "event_date": row["start_date"],
                    "details": f"{row['status']} | Fee {self._money(row['monthly_fee'])}",
                    "context": {
                        "student_name": student["student_name"],
                        "course_name": row["course_name"],
                        "start_date": row["start_date"],
                        "fee": self._money(row["monthly_fee"]),
                    },
                }
            )
        for row in self.db.query(
            "SELECT b.id,b.bill_number,b.billing_period,b.issue_date,b.due_date,"
            "b.total_amount,b.status,c.course_name "
            "FROM due_bills b JOIN enrollments e ON e.id=b.enrollment_id "
            "JOIN courses c ON c.id=e.course_id WHERE e.student_id=? "
            "ORDER BY b.issue_date,b.id",
            (student_id,),
        ):
            events.append(
                {
                    "event_key": "due_bill",
                    "source_type": "due_bill",
                    "source_id": int(row["id"]),
                    "event_name": "Due Bill",
                    "reference": row["bill_number"],
                    "event_date": row["issue_date"],
                    "details": f"{row['status']} | {self._money(row['total_amount'])}",
                    "context": {
                        "student_name": student["student_name"],
                        "course_name": row["course_name"],
                        "bill_number": row["bill_number"],
                        "amount": self._money(row["total_amount"]),
                        "due_date": row["due_date"],
                        "period": row["billing_period"],
                    },
                }
            )
        for row in self.db.query(
            "SELECT st.id,st.transaction_date,st.payment_amount,st.discount_amount,"
            "st.receipt_no,st.particular,c.course_name,b.bill_number,b.total_amount,"
            "b.paid_amount FROM student_transactions st "
            "LEFT JOIN enrollments e ON e.id=st.enrollment_id "
            "LEFT JOIN courses c ON c.id=e.course_id "
            "LEFT JOIN due_bills b ON b.bill_number="
            "REPLACE(st.particular,'Payment for bill ','') "
            "WHERE st.student_id=? AND st.transaction_type='Payment Received' "
            "ORDER BY st.transaction_date,st.id",
            (student_id,),
        ):
            bill_number = row["bill_number"] or str(row["particular"]).replace(
                "Payment for bill ", ""
            )
            balance = max(
                Decimal("0"),
                Decimal(str(row["total_amount"] or 0))
                - Decimal(str(row["paid_amount"] or 0)),
            )
            events.append(
                {
                    "event_key": "bill_payment",
                    "source_type": "student_transaction",
                    "source_id": int(row["id"]),
                    "event_name": "Bill Payment",
                    "reference": row["receipt_no"] or bill_number,
                    "event_date": row["transaction_date"],
                    "details": f"Paid {self._money(row['payment_amount'])}",
                    "context": {
                        "student_name": student["student_name"],
                        "course_name": row["course_name"] or "",
                        "bill_number": bill_number,
                        "amount": self._money(row["payment_amount"]),
                        "discount": self._money(row["discount_amount"]),
                        "balance": self._money(balance),
                        "payment_date": row["transaction_date"],
                    },
                }
            )
        for row in self.db.query(
            "SELECT cc.id,cc.certificate_number,cc.certify_date,cc.course_name_snapshot "
            "FROM course_certificates cc JOIN enrollments e ON e.id=cc.enrollment_id "
            "WHERE e.student_id=? ORDER BY cc.certify_date,cc.id",
            (student_id,),
        ):
            events.append(
                {
                    "event_key": "certificate_issued",
                    "source_type": "course_certificate",
                    "source_id": int(row["id"]),
                    "event_name": "Certificate Issued",
                    "reference": row["certificate_number"],
                    "event_date": row["certify_date"],
                    "details": row["course_name_snapshot"],
                    "context": {
                        "student_name": student["student_name"],
                        "course_name": row["course_name_snapshot"],
                        "certificate_number": row["certificate_number"],
                        "certificate_date": row["certify_date"],
                    },
                }
            )
        events.sort(
            key=lambda event: (str(event["event_date"] or ""), str(event["event_name"]))
        )
        return {
            "student_id": int(student["id"]),
            "student_name": student["student_name"],
            "contact": student["contact"] or "",
            "events": events,
        }

    def queue_student_events(
        self,
        student_id: int,
        event_refs: list[tuple[str, int]],
        recipient: str = "",
        *,
        asynchronous: bool = True,
    ) -> list[int]:
        if not event_refs:
            raise ValueError("Select at least one student event.")
        provider = self.validate_provider_configuration()
        history = self.student_event_history(student_id)
        clean_recipient = self.normalize_recipient(recipient or str(history["contact"]))
        available = {
            (str(event["event_key"]), int(event["source_id"])): event
            for event in history["events"]
        }
        selected = []
        for reference in dict.fromkeys(event_refs):
            event = available.get((str(reference[0]), int(reference[1])))
            if not event:
                raise ValueError("A selected event no longer exists for this student.")
            selected.append(event)
        prepared: list[tuple[dict[str, object], str]] = []
        for event in selected:
            template = self.db.query_one(
                "SELECT template_text FROM sms_event_templates WHERE event_key=?",
                (event["event_key"],),
            )
            if not template:
                raise ValueError(f"SMS template was not found for {event['event_name']}.")
            message = self.render(
                template["template_text"],
                {**self.company_context(), **event["context"]},
            )
            prepared.append((event, message))
        log_ids: list[int] = []
        for event, message in prepared:
            for _attempt in range(5):
                try:
                    log_id = self.db.execute(
                        "INSERT INTO sms_delivery_log "
                        "(event_key,entity_type,entity_id,recipient,message_text,provider,status) "
                        "VALUES (?,?,?,?,?,?,'Pending')",
                        (
                            event["event_key"],
                            f"manual_{event['source_type']}"[:50],
                            secrets.randbelow(2_000_000_000) + 1,
                            clean_recipient,
                            message,
                            provider,
                        ),
                    )
                    log_ids.append(log_id)
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                raise RuntimeError("Could not allocate a manual SMS delivery record.")
        if asynchronous:
            self.dispatch_async()
        else:
            for log_id in log_ids:
                self.dispatch(log_id)
        return log_ids

    def notify(
        self,
        event_key: str,
        entity_type: str,
        entity_id: int,
        recipient: str,
        context: dict[str, object],
        *,
        asynchronous: bool = True,
    ) -> int | None:
        if not self.settings.get_bool("sms_enabled", False):
            return None
        template = self.db.query_one(
            "SELECT enabled,template_text FROM sms_event_templates WHERE event_key=?",
            (event_key,),
        )
        if not template or not int(template["enabled"]):
            return None
        provider = self.settings.get("sms_provider", "aakash").strip().lower()
        clean_recipient = re.sub(r"\D", "", recipient or "")[-13:]
        message = ""
        try:
            clean_recipient = self.normalize_recipient(recipient)
            message = self.render(
                template["template_text"],
                {**self.company_context(), **context},
            )
            log_id = self.db.execute(
                "INSERT INTO sms_delivery_log "
                "(event_key,entity_type,entity_id,recipient,message_text,provider,status) "
                "VALUES (?,?,?,?,?,?,'Pending')",
                (event_key, entity_type, entity_id, clean_recipient, message, provider),
            )
        except sqlite3.IntegrityError:
            existing = self.db.query_one(
                "SELECT id FROM sms_delivery_log "
                "WHERE event_key=? AND entity_type=? AND entity_id=?",
                (event_key, entity_type, entity_id),
            )
            return int(existing["id"]) if existing else None
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "SMS event %s was not queued: %s", event_key, exc
            )
            try:
                return self.db.execute(
                    "INSERT INTO sms_delivery_log "
                    "(event_key,entity_type,entity_id,recipient,message_text,provider,status,"
                    "response_message) VALUES (?,?,?,?,?,?,'Skipped',?)",
                    (
                        event_key,
                        entity_type,
                        entity_id,
                        clean_recipient,
                        message,
                        provider,
                        str(exc)[:1000],
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self.db.query_one(
                    "SELECT id FROM sms_delivery_log "
                    "WHERE event_key=? AND entity_type=? AND entity_id=?",
                    (event_key, entity_type, entity_id),
                )
                return int(existing["id"]) if existing else None
        if asynchronous:
            self.dispatch_async(log_id)
        else:
            self.dispatch(log_id)
        return log_id

    def absence_sms_details(self, student_id: int, attendance_date: str) -> dict[str, str]:
        """Prepare the dashboard's manual absence alert without sending it yet."""
        student = self.db.query_one(
            "SELECT student_name,contact FROM students WHERE id=?", (student_id,)
        )
        if not student:
            raise ValueError("Student was not found.")
        template = self.db.query_one(
            "SELECT template_text FROM sms_event_templates WHERE event_key='attendance_absence'"
        )
        if not template:
            raise ValueError("The attendance absence SMS template was not found.")
        return {
            "student_name": str(student["student_name"]),
            "contact": str(student["contact"] or ""),
            "message": self.render(
                template["template_text"],
                {**self.company_context(), "student_name": student["student_name"], "attendance_date": attendance_date},
            ),
        }

    def queue_absence_sms(
        self, student_id: int, attendance_date: str, recipient: str = "", *, asynchronous: bool = True
    ) -> int:
        """Queue a manual attendance-absence SMS and retain it in the delivery log."""
        details = self.absence_sms_details(student_id, attendance_date)
        provider = self.validate_provider_configuration()
        clean_recipient = self.normalize_recipient(recipient or details["contact"])
        for _attempt in range(5):
            try:
                log_id = self.db.execute(
                    "INSERT INTO sms_delivery_log "
                    "(event_key,entity_type,entity_id,recipient,message_text,provider,status) "
                    "VALUES ('attendance_absence','manual_student_absence',?,?,?,?, 'Pending')",
                    (
                        secrets.randbelow(2_000_000_000) + 1,
                        clean_recipient,
                        details["message"],
                        provider,
                    ),
                )
                if asynchronous:
                    self.dispatch_async()
                else:
                    self.dispatch(log_id)
                return log_id
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("Could not allocate an absence SMS delivery record.")

    def queue_absence_sms_batch(
        self, student_ids: list[int], attendance_date: str, *, asynchronous: bool = True
    ) -> tuple[list[int], list[str]]:
        """Queue one personalised absence SMS per selected student.

        Invalid or missing contacts are skipped and returned with a reason; valid
        recipients are still queued rather than losing the entire batch.
        """
        provider = self.validate_provider_configuration()
        queued: list[int] = []
        skipped: list[str] = []
        for student_id in dict.fromkeys(int(value) for value in student_ids):
            try:
                details = self.absence_sms_details(student_id, attendance_date)
                recipient = self.normalize_recipient(details["contact"])
            except Exception as exc:
                skipped.append(f"Student #{student_id}: {exc}")
                continue
            for _attempt in range(5):
                try:
                    log_id = self.db.execute(
                        "INSERT INTO sms_delivery_log "
                        "(event_key,entity_type,entity_id,recipient,message_text,provider,status) "
                        "VALUES ('attendance_absence','manual_student_absence',?,?,?,?, 'Pending')",
                        (
                            secrets.randbelow(2_000_000_000) + 1,
                            recipient, details["message"], provider,
                        ),
                    )
                    queued.append(log_id)
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                skipped.append(f"{details['student_name']}: could not allocate a delivery record")
        if queued:
            if asynchronous:
                self.dispatch_async()
            else:
                for log_id in queued:
                    self.dispatch(log_id)
        return queued, skipped

    def send_test(self, recipient: str, message: str) -> int:
        clean_recipient = self.normalize_recipient(recipient)
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("Enter a test message.")
        if len(clean_message) > 500:
            raise ValueError("SMS message cannot exceed 500 characters.")
        provider = self.settings.get("sms_provider", "aakash").strip().lower()
        log_id = self.db.execute(
            "INSERT INTO sms_delivery_log "
            "(event_key,entity_type,entity_id,recipient,message_text,provider,status) "
            "VALUES ('test','test',?,?,?,?, 'Pending')",
            (secrets.randbelow(2_000_000_000) + 1, clean_recipient, clean_message, provider),
        )
        self.dispatch(log_id)
        return log_id

    def dispatch_async(self, log_id: int | None = None) -> None:
        del log_id
        with self._worker_guard:
            if self._worker_running:
                return
            self._worker_running = True
        thread = threading.Thread(
            target=self._run_worker,
            daemon=True,
            name="elh-sms-dispatch",
        )
        thread.start()

    def _run_worker(self) -> None:
        try:
            while self.dispatch_pending():
                pass
        finally:
            with self._worker_guard:
                self._worker_running = False
            if self.db.query_one(
                "SELECT id FROM sms_delivery_log WHERE status='Pending' LIMIT 1"
            ):
                self.dispatch_async()

    def dispatch_pending(self, limit: int = 20) -> int:
        rows = self.db.query(
            "SELECT id FROM sms_delivery_log WHERE status='Pending' "
            "ORDER BY created_at,id LIMIT ?",
            (limit,),
        )
        for row in rows:
            self.dispatch(int(row["id"]))
        return len(rows)

    def dispatch(self, log_id: int) -> None:
        with self._dispatch_lock:
            row = self.db.query_one(
                "SELECT * FROM sms_delivery_log WHERE id=?", (log_id,)
            )
            if not row or row["status"] == "Sent":
                return
            try:
                timeout = max(2, min(60, self.settings.get_int("sms_timeout_seconds", 10)))
                provider = create_sms_provider(
                    row["provider"],
                    self.config,
                    self.settings.get("sms_sender_id", ""),
                    timeout,
                )
                response = provider.send(row["recipient"], row["message_text"])
                status = "Sent" if response.success else "Failed"
                self.db.execute(
                    "UPDATE sms_delivery_log SET status=?,attempt_count=attempt_count+1,"
                    "response_code=?,response_message=?,last_attempt_at=CURRENT_TIMESTAMP,"
                    "sent_at=CASE WHEN ?='Sent' THEN CURRENT_TIMESTAMP ELSE sent_at END "
                    "WHERE id=?",
                    (status, response.code, response.message, status, log_id),
                )
            except Exception as exc:
                self.db.execute(
                    "UPDATE sms_delivery_log SET status='Failed',attempt_count=attempt_count+1,"
                    "response_message=?,last_attempt_at=CURRENT_TIMESTAMP WHERE id=?",
                    (str(exc)[:1000], log_id),
                )
                logging.getLogger(__name__).warning("SMS delivery failed: %s", exc)

    def retry(self, log_id: int, asynchronous: bool = True) -> None:
        row = self.db.query_one(
            "SELECT status FROM sms_delivery_log WHERE id=?", (log_id,)
        )
        if not row:
            raise ValueError("SMS delivery record was not found.")
        if row["status"] != "Failed":
            raise ValueError("Only failed gateway deliveries can be retried.")
        self.db.execute(
            "UPDATE sms_delivery_log SET status='Pending' WHERE id=?", (log_id,)
        )
        if asynchronous:
            self.dispatch_async(log_id)
        else:
            self.dispatch(log_id)

    def recent(self, limit: int = 100):
        return self.db.query(
            "SELECT id,event_key,recipient,provider,status,attempt_count,response_message,created_at "
            "FROM sms_delivery_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
