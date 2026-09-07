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
from elh.models import Student
from elh.services.container import ServiceContainer
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class MultiBillPaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_multi_bill.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            operator_username="testop",
            operator_password="Operator@TestPassword2025",
            secret_key="unit-test-secret-key-multi-bill",
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

        # Seed test student, course, enrollment, account
        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name,category,billing_type,default_fee,status) "
            "VALUES ('Math Coaching','Tuition','Monthly',2000,'Active')"
        )
        self.student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Suman Sharma', 'Class 10', '9812345678', 'Active', '2083/01/01')"
        )
        self.enrollment_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Class 10', '2083/01/01', 2000, 'Active')",
            (self.student_id, self.course_id),
        )
        self.account_id = self.db.execute(
            "INSERT INTO accounts (account_name,account_type,opening_balance,status) "
            "VALUES ('Main Cash Counter','Cash Counter',0,'Active')"
        )

    def tearDown(self):
        gc.collect()
        self.temp_dir.cleanup()

    def test_multi_bill_payment_settles_two_bills_in_one_shot(self):
        # Generate 2 bills for 2083/01 and 2083/02
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        self.assertEqual(bill1.total_amount, Decimal("2000"))
        self.assertEqual(bill2.total_amount, Decimal("2000"))

        # Pay exactly Rs. 4000 once covering both bills
        result = self.services.billing.pay_bills(
            [bill1.id, bill2.id],
            Decimal("4000"),
            "2083/02/10",
            self.account_id,
            "Cash",
            receipt_no="RCP-101",
            remarks="Lump sum payment for 2 months",
        )

        self.assertEqual(result["total_paid"], Decimal("4000"))
        self.assertEqual(result["advance_amount"], Decimal("0"))
        self.assertEqual(len(result["updated_bills"]), 2)

        # Verify bills are marked Paid in DB
        b1_after = self.services.billing.repository.get(bill1.id)
        b2_after = self.services.billing.repository.get(bill2.id)
        self.assertEqual(b1_after.status, "Paid")
        self.assertEqual(b1_after.paid_amount, Decimal("2000"))
        self.assertEqual(b2_after.status, "Paid")
        self.assertEqual(b2_after.paid_amount, Decimal("2000"))

        # Verify ledger entry was recorded for the full Rs. 4000
        ledger = self.db.query("SELECT * FROM ledger WHERE account_id=?", (self.account_id,))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(Decimal(str(ledger[0]["amount"])), Decimal("4000"))
        self.assertEqual(ledger[0]["direction"], "IN")

    def test_waterfall_partial_payment_clears_oldest_first(self):
        # Generate 2 bills: 2083/01 and 2083/02 (each Rs. 2000)
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        # Student pays Rs. 3500 once
        result = self.services.billing.pay_bills(
            [bill1.id, bill2.id],
            Decimal("3500"),
            "2083/02/10",
            self.account_id,
            "Bank",
            receipt_no="RCP-102",
        )

        b1_after = self.services.billing.repository.get(bill1.id)
        b2_after = self.services.billing.repository.get(bill2.id)

        # Oldest bill is fully cleared
        self.assertEqual(b1_after.status, "Paid")
        self.assertEqual(b1_after.paid_amount, Decimal("2000"))

        # Second bill is partially paid (Rs. 1500 paid, Rs. 500 remaining)
        self.assertEqual(b2_after.status, "Partially Paid")
        self.assertEqual(b2_after.paid_amount, Decimal("1500"))
        self.assertEqual(b2_after.total_amount - b2_after.paid_amount, Decimal("500"))
        self.assertEqual(result["advance_amount"], Decimal("0"))

    def test_excess_payment_credited_as_advance_surplus(self):
        # Generate 1 bill of Rs. 2000
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill

        # Student hands Rs. 5000 (Rs. 2000 for bill + Rs. 3000 advance)
        result = self.services.billing.pay_bills(
            [bill1.id],
            Decimal("5000"),
            "2083/01/10",
            self.account_id,
            "Cash",
            receipt_no="RCP-103",
        )

        self.assertEqual(result["advance_amount"], Decimal("3000"))
        b1_after = self.services.billing.repository.get(bill1.id)
        self.assertEqual(b1_after.status, "Paid")

        # Verify student_transactions contains the advance surplus entry
        txns = self.db.query(
            "SELECT * FROM student_transactions WHERE student_id=? ORDER BY id ASC",
            (self.student_id,),
        )
        self.assertEqual(len(txns), 2)
        self.assertEqual(Decimal(str(txns[0]["payment_amount"])), Decimal("2000"))
        self.assertIn("Payment for bill", txns[0]["particular"])

        self.assertEqual(Decimal(str(txns[1]["payment_amount"])), Decimal("3000"))
        self.assertIn("Advance fee payment", txns[1]["particular"])

        # Ledger should record full Rs. 5000
        ledger = self.db.query("SELECT * FROM ledger WHERE account_id=?", (self.account_id,))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(Decimal(str(ledger[0]["amount"])), Decimal("5000"))

    def test_web_api_pay_multiple_endpoint(self):
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/bills/pay-multiple",
                headers={"authorization": f"Bearer {self.admin_token}"},
                body={
                    "bill_ids": [bill1.id, bill2.id],
                    "amount": 4500.0,
                    "discount": 0.0,
                    "payment_date": "2083/02/10",
                    "account_id": self.account_id,
                    "payment_method": "Cash",
                    "receipt_no": "WEB-RCP-201",
                    "remarks": "Web combined payment with advance",
                },
            )
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data["success"])
        self.assertEqual(data["total_paid"], 4500.0)
        self.assertEqual(data["advance_amount"], 500.0)
        self.assertEqual(len(data["updated_bills"]), 2)

        # Check bills status via API
        b1_after = self.services.billing.repository.get(bill1.id)
        b2_after = self.services.billing.repository.get(bill2.id)
        self.assertEqual(b1_after.status, "Paid")
        self.assertEqual(b2_after.status, "Paid")
