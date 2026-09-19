from __future__ import annotations

import asyncio
import gc
import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.services.container import ServiceContainer
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class DeletePaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_del_payment.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            operator_username="testop",
            operator_password="Operator@TestPassword2025",
            secret_key="unit-test-secret-key-del-pay",
            date_format="%Y/%m/%d",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.services = ServiceContainer.build(self.config, self.db)
        self.app = create_app(self.config)

        # Login as admin
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "testadmin", "password": "Admin@TestPassword2025"},
            )
        )
        self.assertEqual(status, 200)
        self.admin_token = json.loads(body.decode("utf-8"))["token"]

        # Login as operator (non-admin)
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "testop", "password": "Operator@TestPassword2025"},
            )
        )
        self.assertEqual(status, 200)
        self.operator_token = json.loads(body.decode("utf-8"))["token"]

        # Seed master data
        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name,category,billing_type,default_fee,status) "
            "VALUES ('English Speaking','Language','Monthly',2500,'Active')"
        )
        self.student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Rohan Adhikari', 'Grade 11', '9841000000', 'Active', '2083/01/01')"
        )
        self.enrollment_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Grade 11', '2083/01/01', 2500, 'Active')",
            (self.student_id, self.course_id),
        )
        self.account_id = self.db.execute(
            "INSERT INTO accounts (account_name,account_type,opening_balance,status) "
            "VALUES ('Nabil Bank','Bank',0,'Active')"
        )

    def tearDown(self):
        self.app = None
        self.services = None
        self.db = None
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_admin_can_delete_single_bill_payment(self):
        # 1. Generate bill for Rs. 2500
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        )
        bill = gen_res.bill
        self.assertEqual(bill.total_amount, Decimal("2500"))
        self.assertEqual(bill.status, "Due")

        # 2. Record payment of Rs. 2500
        pay_res = self.services.billing.pay_bill(
            bill.id,
            Decimal("2500"),
            "2083/01/10",
            self.account_id,
            "Bank",
            receipt_no="RCP-DEL-001",
            remarks="Full tuition payment",
        )
        txn_id = pay_res["transaction_id"]
        self.assertIsNotNone(txn_id)

        # Check state after payment
        updated_bill = self.services.billing.get(bill.id)
        self.assertEqual(updated_bill.status, "Paid")
        self.assertEqual(updated_bill.paid_amount, Decimal("2500"))

        self.assertEqual(self.db.account_balance(self.account_id), 2500.0)

        ledger_rows = self.db.query(
            "SELECT * FROM ledger WHERE source_type = 'Student Transaction' AND source_id = ?",
            (txn_id,),
        )
        self.assertEqual(len(ledger_rows), 1)
        self.assertEqual(Decimal(str(ledger_rows[0]["amount"])), Decimal("2500"))

        # Add a dummy SMS log to verify cleanup
        self.db.execute(
            "INSERT INTO sms_delivery_log (event_key, entity_type, entity_id, recipient, message_text, provider, status) "
            "VALUES ('payment.received', 'student_transaction', ?, '9841000000', 'Payment received', 'sparrow', 'Delivered')",
            (txn_id,),
        )

        # 3. Delete payment as administrator
        del_res = self.services.billing.delete_payment(
            transaction_id=txn_id,
            actor_user_id=1,
            actor_username="testadmin",
            actor_role="admin",
        )
        self.assertTrue(del_res["success"])
        self.assertEqual(del_res["reverted_payment"], 2500.0)

        # 4. Verify bill state reverted
        reverted_bill = self.services.billing.get(bill.id)
        self.assertEqual(reverted_bill.paid_amount, Decimal("0"))
        self.assertEqual(reverted_bill.status, "Due")
        self.assertEqual(reverted_bill.total_amount, Decimal("2500"))

        # 5. Verify transaction deleted
        txns = self.db.query("SELECT * FROM student_transactions WHERE id = ?", (txn_id,))
        self.assertEqual(len(txns), 0)

        # 6. Verify ledger row removed and account balance reverted
        ledger_after = self.db.query(
            "SELECT * FROM ledger WHERE source_type = 'Student Transaction' AND source_id = ?",
            (txn_id,),
        )
        self.assertEqual(len(ledger_after), 0)

        self.assertEqual(self.db.account_balance(self.account_id), 0.0)

        # 7. Verify SMS log removed
        sms_logs = self.db.query(
            "SELECT * FROM sms_delivery_log WHERE entity_type = 'student_transaction' AND entity_id = ?",
            (txn_id,),
        )
        self.assertEqual(len(sms_logs), 0)

        # 8. Verify audit log entry
        audit_logs = self.db.query(
            "SELECT * FROM auth_audit_log WHERE event_type = 'payment.delete'",
        )
        self.assertGreaterEqual(len(audit_logs), 1)
        self.assertIn(f"#{txn_id}", audit_logs[-1]["detail"])

    def test_admin_delete_payment_with_discount_restores_bill_totals(self):
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        )
        bill = gen_res.bill
        self.assertEqual(bill.total_amount, Decimal("2500"))

        # Pay Rs. 2000 with Rs. 500 discount
        pay_res = self.services.billing.pay_bill(
            bill.id,
            Decimal("2000"),
            "2083/02/10",
            self.account_id,
            "Cash",
            discount=Decimal("500"),
            receipt_no="RCP-DEL-002",
        )
        txn_id = pay_res["transaction_id"]

        paid_bill = self.services.billing.get(bill.id)
        self.assertEqual(paid_bill.status, "Paid")
        self.assertEqual(paid_bill.paid_amount, Decimal("2000"))
        self.assertEqual(paid_bill.discount, Decimal("500"))
        self.assertEqual(paid_bill.total_amount, Decimal("2000"))

        # Delete payment as super_admin
        del_res = self.services.billing.delete_payment(
            transaction_id=txn_id,
            actor_user_id=1,
            actor_username="superadmin",
            actor_role="super_admin",
        )
        self.assertTrue(del_res["success"])
        self.assertEqual(del_res["reverted_discount"], 500.0)

        # Bill total should be restored back to Rs. 2500 with 0 discount
        reverted_bill = self.services.billing.get(bill.id)
        self.assertEqual(reverted_bill.total_amount, Decimal("2500"))
        self.assertEqual(reverted_bill.discount, Decimal("0"))
        self.assertEqual(reverted_bill.paid_amount, Decimal("0"))
        self.assertEqual(reverted_bill.status, "Due")

    def test_non_admin_cannot_delete_payment(self):
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/03", "2083/03/05", "2083/03/15"
        )
        bill = gen_res.bill

        pay_res = self.services.billing.pay_bill(
            bill.id,
            Decimal("1000"),
            "2083/03/10",
            self.account_id,
            "Cash",
            receipt_no="RCP-DEL-003",
        )
        txn_id = pay_res["transaction_id"]

        # Attempt to delete as 'operator' or 'accountant'
        with self.assertRaises(PermissionError):
            self.services.billing.delete_payment(
                transaction_id=txn_id,
                actor_user_id=2,
                actor_username="testop",
                actor_role="operator",
            )

        with self.assertRaises(PermissionError):
            self.services.billing.delete_payment(
                transaction_id=txn_id,
                actor_user_id=3,
                actor_username="testaccountant",
                actor_role="accountant",
            )

        # Payment should NOT have been deleted
        txns = self.db.query("SELECT * FROM student_transactions WHERE id = ?", (txn_id,))
        self.assertEqual(len(txns), 1)

    def test_api_due_bill_payment_endpoints_and_admin_security(self):
        # 1. Generate bill and pay
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/04", "2083/04/05", "2083/04/15"
        )
        bill = gen_res.bill

        pay_res = self.services.billing.pay_bill(
            bill.id,
            Decimal("1500"),
            "2083/04/10",
            self.account_id,
            "Bank",
            receipt_no="RCP-API-001",
        )
        txn_id = pay_res["transaction_id"]

        # 2. Query GET /api/due-bills/{bill_id}/payments
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/due-bills/{bill.id}/payments",
                headers={"authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("payments", data)
        self.assertEqual(len(data["payments"]), 1)
        self.assertEqual(data["payments"][0]["id"], txn_id)
        self.assertEqual(data["payments"][0]["receipt_no"], "RCP-API-001")

        # 3. Query GET /api/student-payments
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/student-payments",
                headers={"authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        all_payments = json.loads(body.decode("utf-8"))["payments"]
        self.assertTrue(any(p["id"] == txn_id for p in all_payments))

        # 4. Non-admin operator attempts DELETE -> 403 Forbidden
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "DELETE",
                f"/api/due-bills/{bill.id}/payments/{txn_id}",
                headers={"authorization": f"Bearer {self.operator_token}"},
            )
        )
        self.assertEqual(status, 403)
        err_msg = json.loads(body.decode("utf-8"))["detail"]
        self.assertIn("Only administrators are authorized", err_msg)

        # 5. Administrator deletes payment -> 200 OK
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "DELETE",
                f"/api/due-bills/{bill.id}/payments/{txn_id}",
                headers={"authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        resp = json.loads(body.decode("utf-8"))
        self.assertTrue(resp["success"])
        self.assertEqual(resp["transaction_id"], txn_id)

        # 6. Verify payments endpoint now returns empty list for the bill
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/due-bills/{bill.id}/payments",
                headers={"authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(len(data["payments"]), 0)

        # Bill status reverted to Due
        bill_check = self.services.billing.get(bill.id)
        self.assertEqual(bill_check.status, "Due")
        self.assertEqual(bill_check.paid_amount, Decimal("0"))

    def test_admin_can_delete_paid_bill_and_revert_financial_events(self):
        # 1. Generate bill for 2083/05
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/05", "2083/05/05", "2083/05/15"
        )
        bill = gen_res.bill
        self.assertEqual(bill.total_amount, Decimal("2500"))

        # 2. Record payment of Rs. 2500
        pay_res = self.services.billing.pay_bill(
            bill.id,
            Decimal("2500"),
            "2083/05/10",
            self.account_id,
            "Cash",
            receipt_no="RCP-PAID-BILL-01",
            remarks="Payment to be deleted along with bill",
        )
        txn_id = pay_res["transaction_id"]

        self.assertEqual(self.db.account_balance(self.account_id), 2500.0)
        self.assertEqual(len(self.db.query("SELECT * FROM student_transactions WHERE id = ?", (txn_id,))), 1)
        self.assertEqual(len(self.db.query("SELECT * FROM ledger WHERE source_type = 'Student Transaction' AND source_id = ?", (txn_id,))), 1)

        # 3. Delete the paid bill as administrator
        del_res = self.services.billing.delete_bill(
            bill_id=bill.id,
            actor_user_id=1,
            actor_username="testadmin",
            actor_role="admin",
            force_paid=True,
        )
        self.assertTrue(del_res["success"])
        self.assertEqual(del_res["deleted_paid_amount"], 2500.0)
        self.assertEqual(len(del_res["reverted_payments"]), 1)

        # 4. Verify bill is deleted
        self.assertIsNone(self.services.billing.get(bill.id))

        # 5. Verify associated student transaction and ledger entries are deleted
        self.assertEqual(len(self.db.query("SELECT * FROM student_transactions WHERE id = ?", (txn_id,))), 0)
        self.assertEqual(len(self.db.query("SELECT * FROM ledger WHERE source_type = 'Student Transaction' AND source_id = ?", (txn_id,))), 0)

        # 6. Verify account balance reverted to 0
        self.assertEqual(self.db.account_balance(self.account_id), 0.0)

        # 7. Verify audit log entry
        audit_logs = self.db.query("SELECT * FROM auth_audit_log WHERE event_type = 'bill.delete'")
        self.assertGreaterEqual(len(audit_logs), 1)
        self.assertIn(f"#{bill.bill_number}", audit_logs[-1]["detail"])

    def test_non_admin_cannot_delete_paid_bill(self):
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/06", "2083/06/05", "2083/06/15"
        )
        bill = gen_res.bill

        self.services.billing.pay_bill(
            bill.id,
            Decimal("1200"),
            "2083/06/10",
            self.account_id,
            "Bank",
            receipt_no="RCP-PAID-BILL-02",
        )

        # Operator role must be rejected
        with self.assertRaises(PermissionError):
            self.services.billing.delete_bill(
                bill_id=bill.id,
                actor_user_id=2,
                actor_username="testop",
                actor_role="operator",
                force_paid=True,
            )

        # Via API: operator attempting to delete paid bill gets 403
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "DELETE",
                f"/api/due-bills/{bill.id}",
                headers={"authorization": f"Bearer {self.operator_token}"},
            )
        )
        self.assertEqual(status, 403)
        err_msg = json.loads(body.decode("utf-8"))["detail"]
        self.assertIn("Only administrators are authorized", err_msg)

        # Bill still exists
        self.assertIsNotNone(self.services.billing.get(bill.id))

    def test_api_admin_can_delete_paid_bill(self):
        gen_res = self.services.billing.generate(
            self.enrollment_id, "2083/07", "2083/07/05", "2083/07/15"
        )
        bill = gen_res.bill

        self.services.billing.pay_bill(
            bill.id,
            Decimal("2500"),
            "2083/07/10",
            self.account_id,
            "Bank",
            receipt_no="RCP-API-PAID-BILL",
        )

        # Admin deletes paid bill via API
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "DELETE",
                f"/api/due-bills/{bill.id}",
                headers={"authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data["success"])
        self.assertEqual(data["deleted_paid_amount"], 2500.0)

        # Verify bill deleted
        self.assertIsNone(self.services.billing.get(bill.id))
        self.assertEqual(self.db.account_balance(self.account_id), 0.0)


if __name__ == "__main__":
    unittest.main()
