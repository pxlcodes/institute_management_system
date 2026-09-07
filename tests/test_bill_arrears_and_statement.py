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


class BillArrearsAndStatementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_arrears.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            operator_username="testop",
            operator_password="Operator@TestPassword2025",
            secret_key="unit-test-secret-key-arrears",
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

        # Seed student, course, enrollment, account
        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name,category,billing_type,default_fee,status) "
            "VALUES ('Science Class 10','Coaching','Monthly',1500,'Active')"
        )
        self.student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Bikash Rai', 'Class 10', '9800000001', 'Active', '2083/01/01')"
        )
        self.enrollment_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Class 10', '2083/01/01', 1500, 'Active')",
            (self.student_id, self.course_id),
        )
        self.account_id = self.db.execute(
            "INSERT INTO accounts (account_name,account_type,opening_balance,status) "
            "VALUES ('Main Cash Counter','Cash Counter',0,'Active')"
        )

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_bill_arrears_detection_and_grand_total(self):
        # Generate 3 bills: Month 1, Month 2, Month 3
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill
        bill3 = self.services.billing.generate(
            self.enrollment_id, "2083/03", "2083/03/05", "2083/03/15"
        ).bill

        # For Bill 1, there should be NO arrears
        arr1, tot1, grand1 = self.services.billing.get_bill_arrears(bill1)
        self.assertEqual(len(arr1), 0)
        self.assertEqual(tot1, Decimal("0"))
        self.assertEqual(grand1, Decimal("1500"))

        # For Bill 2, Month 1 is unpaid (Rs. 1500 arrears) -> Grand Total Rs. 3000
        arr2, tot2, grand2 = self.services.billing.get_bill_arrears(bill2)
        self.assertEqual(len(arr2), 1)
        self.assertEqual(arr2[0]["billing_period"], "2083/01")
        self.assertEqual(arr2[0]["balance"], Decimal("1500"))
        self.assertEqual(tot2, Decimal("1500"))
        self.assertEqual(grand2, Decimal("3000"))

        # For Bill 3, Month 1 and Month 2 are unpaid -> Rs. 3000 arrears -> Grand Total Rs. 4500
        arr3, tot3, grand3 = self.services.billing.get_bill_arrears(bill3)
        self.assertEqual(len(arr3), 2)
        self.assertEqual(tot3, Decimal("3000"))
        self.assertEqual(grand3, Decimal("4500"))

        # Now suppose student pays partially on Month 1 (pays Rs. 500)
        self.services.billing.pay_bills(
            [bill1.id], Decimal("500"), "2083/01/10", self.account_id, "Cash"
        )
        # Bill 1 remaining is now 1000
        arr3_after, tot3_after, grand3_after = self.services.billing.get_bill_arrears(bill3)
        self.assertEqual(len(arr3_after), 2)
        self.assertEqual(arr3_after[0]["balance"], Decimal("1000"))
        self.assertEqual(arr3_after[1]["balance"], Decimal("1500"))
        self.assertEqual(tot3_after, Decimal("2500"))
        self.assertEqual(grand3_after, Decimal("4000"))

    def test_create_pdf_and_batch_pdf_with_arrears(self):
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        # Test single bill PDF with arrears
        pdf_path = self.services.billing.create_pdf(bill2)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)

        # Test batch PDF with arrears
        batch_pdf = self.services.billing.create_batch_pdf([bill1, bill2])
        self.assertTrue(batch_pdf.exists())
        self.assertGreater(batch_pdf.stat().st_size, 1000)

    def test_consolidated_statement_pdf_generation(self):
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        # Test consolidated statement from bills
        stmt_pdf = self.services.billing.create_consolidated_statement_pdf(bills=[bill1, bill2])
        self.assertTrue(stmt_pdf.exists())
        self.assertGreater(stmt_pdf.stat().st_size, 1000)

        # Test consolidated statement from student_id
        stmt_student_pdf = self.services.billing.create_consolidated_statement_pdf(student_id=self.student_id)
        self.assertTrue(stmt_student_pdf.exists())
        self.assertGreater(stmt_student_pdf.stat().st_size, 1000)

    def test_web_endpoints_for_statement_and_bill_pdf(self):
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        # Test GET /api/bills/{id}/pdf
        status, headers, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/bills/{bill1.id}/pdf",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        self.assertIn(b"%PDF", body[:10])

        # Test GET /api/bills/consolidated-statement?bill_ids=...
        status, headers, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/bills/consolidated-statement?bill_ids={bill1.id},{bill2.id}",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        self.assertIn(b"%PDF", body[:10])

        # Test GET /api/bills/consolidated-statement?student_id=...
        status, headers, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/bills/consolidated-statement?student_id={self.student_id}",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        self.assertIn(b"%PDF", body[:10])

    def test_whatsapp_bill_notice_reflects_arrears(self):
        bill1 = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        bill2 = self.services.billing.generate(
            self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15"
        ).bill

        wa_data = self.services.notifications.build_bill_whatsapp_message(bill2.id)
        self.assertIn("Previous Arrears", wa_data["message"])
        self.assertIn("Grand Total Outstanding", wa_data["message"])
        self.assertEqual(wa_data["amount_due"], "3,000.00")


if __name__ == "__main__":
    unittest.main()
