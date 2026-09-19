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
from elh.hardware.printing.network_escpos import NetworkEscPosPrinter
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

    def test_student_dues_summary_and_filtering(self):
        # Create second student and enrollment
        student2_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Sita Sharma', 'Class 10', '9800000002', 'Active', '2083/01/01')"
        )
        enr2_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Class 10', '2083/01/01', 1200, 'Active')",
            (student2_id, self.course_id),
        )

        # Student 1: 2 unpaid bills
        b1 = self.services.billing.generate(self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15").bill
        b2 = self.services.billing.generate(self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15").bill

        # Student 2: 1 paid bill, 1 unpaid bill
        b3 = self.services.billing.generate(enr2_id, "2083/01", "2083/01/05", "2083/01/15").bill
        self.services.billing.pay_bills(
            [b3.id], Decimal("1200"), "2083/01/10", self.account_id, "Cash", "REC-001"
        )
        b4 = self.services.billing.generate(enr2_id, "2083/02", "2083/02/05", "2083/02/15").bill

        # Test service: get_student_dues_summary
        summaries = self.services.billing.get_student_dues_summary()
        self.assertEqual(len(summaries), 2)
        s1 = next(s for s in summaries if s["student_id"] == self.student_id)
        self.assertEqual(s1["student_name"], "Bikash Rai")
        self.assertEqual(s1["contact"], "9800000001")
        self.assertEqual(s1["unpaid_bills_count"], 2)
        self.assertEqual(s1["total_due"], 3000.0)

        s2 = next(s for s in summaries if s["student_id"] == student2_id)
        self.assertEqual(s2["unpaid_bills_count"], 1)
        self.assertEqual(s2["total_due"], 1200.0)

        # Test min_unpaid_months=2 (Overdue filter)
        overdue_summaries = self.services.billing.get_student_dues_summary(min_unpaid_months=2)
        self.assertEqual(len(overdue_summaries), 1)
        self.assertEqual(overdue_summaries[0]["student_id"], self.student_id)

        # Test Web API: GET /api/bills/student-dues-summary
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/bills/student-dues-summary",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        api_summaries = json.loads(body.decode("utf-8"))
        self.assertEqual(len(api_summaries), 2)

        # Test Web API: GET /api/bills?status=pending (should return 3 unpaid bills: b1, b2, b4)
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/bills?status=pending",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        pending_bills = json.loads(body.decode("utf-8"))
        self.assertEqual(len(pending_bills), 3)
        self.assertTrue(all(b["balance"] > 0 for b in pending_bills))

        # Test Web API: GET /api/bills?status=paid (should return 1 bill: b3)
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/bills?status=paid",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        paid_bills = json.loads(body.decode("utf-8"))
        self.assertEqual(len(paid_bills), 1)
        self.assertEqual(paid_bills[0]["id"], b3.id)
        self.assertEqual(paid_bills[0]["balance"], 0.0)

    def test_period_segregation_and_combined_ranges(self):
        # 1. Test segregate_period static method
        self.assertEqual(
            self.services.billing.segregate_period("2083/01 to 2083/03"),
            ["2083/01", "2083/02", "2083/03"],
        )
        self.assertEqual(
            self.services.billing.segregate_period("2083/01 - 2083/03"),
            ["2083/01", "2083/02", "2083/03"],
        )
        self.assertEqual(
            self.services.billing.segregate_period("2083/01 to 2083/03, 2083/04, 2083/05"),
            ["2083/01", "2083/02", "2083/03", "2083/04", "2083/05"],
        )
        self.assertEqual(
            self.services.billing.segregate_period("2082/11 to 2083/02"),
            ["2082/11", "2082/12", "2083/01", "2083/02"],
        )
        self.assertEqual(
            self.services.billing.segregate_period("2083/04"),
            ["2083/04"],
        )

        # 2. Test segregate_periods class method with list of periods
        self.assertEqual(
            self.services.billing.segregate_periods(["2083/01 to 2083/03", "2083/04", "2083/05"]),
            ["2083/01", "2083/02", "2083/03", "2083/04", "2083/05"],
        )

        # 3. Create a combined bill covering 2083/01 to 2083/03 plus separate bills 2083/04 and 2083/05
        gen_combined = self.services.billing.generate_combined_month_range(
            [self.enrollment_id], "2083/01", "2083/03", "2083/01/05", "2083/01/15"
        )
        self.assertEqual(len(gen_combined), 1)
        comb_bill = gen_combined[0].bill
        self.assertEqual(comb_bill.billing_period, "2083/01 to 2083/03")

        bill4 = self.services.billing.generate(
            self.enrollment_id, "2083/04", "2083/04/05", "2083/04/15"
        ).bill
        bill5 = self.services.billing.generate(
            self.enrollment_id, "2083/05", "2083/05/05", "2083/05/15"
        ).bill

        # Test get_bill_arrears includes segregated months
        arr5, tot5, grand5 = self.services.billing.get_bill_arrears(bill5)
        self.assertEqual(len(arr5), 2)  # 2 older unpaid bills (comb_bill, bill4)
        comb_arr = next(a for a in arr5 if a["bill_id"] == comb_bill.id)
        self.assertEqual(comb_arr["months"], ["2083/01", "2083/02", "2083/03"])
        self.assertEqual(comb_arr["months_display"], "2083/01, 2083/02, 2083/03")

        # Test get_student_dues_summary reflects segregated periods
        summaries = self.services.billing.get_student_dues_summary()
        self.assertEqual(len(summaries), 1)
        s = summaries[0]
        self.assertEqual(s["unpaid_bills_count"], 3)
        self.assertEqual(s["unpaid_months_count"], 5)
        self.assertEqual(
            s["periods"],
            ["2083/01", "2083/02", "2083/03", "2083/04", "2083/05"],
        )
        self.assertEqual(
            s["periods_display"],
            "2083/01, 2083/02, 2083/03, 2083/04, 2083/05",
        )
        self.assertEqual(
            s["raw_periods"],
            ["2083/01 to 2083/03", "2083/04", "2083/05"],
        )

        # 4. Test Web API period filtering with a sub-month of a combined bill
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/bills?period=2083/02",
                headers={"Authorization": f"Bearer {self.admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        res_bills = json.loads(body.decode("utf-8"))
        self.assertEqual(len(res_bills), 1)
        self.assertEqual(res_bills[0]["id"], comb_bill.id)
        self.assertEqual(res_bills[0]["billing_period"], "2083/01 to 2083/03")

    def test_pos_student_statement_and_bulk_print(self):
        # Create second student & enrollment
        student2_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Sita Sharma', 'Class 10', '9800000002', 'Active', '2083/01/01')"
        )
        enrollment2_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Class 10', '2083/01/01', 2000, 'Active')",
            (student2_id, self.course_id),
        )

        # Generate bills for student 1 (Bikash Rai: 2 bills)
        b1 = self.services.billing.generate(self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15").bill
        b2 = self.services.billing.generate(self.enrollment_id, "2083/02", "2083/02/05", "2083/02/15").bill

        # Generate bill for student 2 (Sita Sharma: 1 bill)
        b3 = self.services.billing.generate(enrollment2_id, "2083/01", "2083/01/05", "2083/01/15").bill

        # Capture receipts printed
        printed_receipts = []
        self.services.printing.print_receipt = printed_receipts.append

        # 1. Print POS statement for single student (student 1)
        receipt = self.services.billing.print_pos_student_statement(self.student_id)
        self.assertEqual(len(printed_receipts), 1)
        self.assertEqual(receipt.title, "STUDENT CREDIT STATEMENT")
        self.assertEqual(receipt.customer_name, "Bikash Rai")
        self.assertEqual(receipt.receipt_number, f"STMT-{self.student_id}")
        self.assertEqual(len(receipt.lines), 2)
        self.assertEqual(receipt.total, Decimal("3000"))

        # Check repository marked pos printed
        b1_db = self.db.query_one("SELECT pos_printed_at FROM due_bills WHERE id=?", (b1.id,))
        b2_db = self.db.query_one("SELECT pos_printed_at FROM due_bills WHERE id=?", (b2.id,))
        self.assertIsNotNone(b1_db["pos_printed_at"])
        self.assertIsNotNone(b2_db["pos_printed_at"])

        # 2. Bulk Print POS statements for both students
        printed_receipts.clear()
        count = self.services.billing.print_pos_student_statements([self.student_id, student2_id])
        self.assertEqual(count, 2)
        self.assertEqual(len(printed_receipts), 2)
        self.assertEqual(printed_receipts[0].customer_name, "Bikash Rai")
        self.assertEqual(printed_receipts[0].total, Decimal("3000"))
        self.assertEqual(printed_receipts[1].customer_name, "Sita Sharma")
        self.assertEqual(printed_receipts[1].total, Decimal("2000"))

        # 3. Bulk Print individual POS bills for both students (3 bills total)
        printed_receipts.clear()
        bill_count = self.services.billing.print_pos_student_bills([self.student_id, student2_id])
        self.assertEqual(bill_count, 3)
        self.assertEqual(len(printed_receipts), 3)
        self.assertEqual(printed_receipts[0].title, "DUE BILL")

        # 4. Error validation: no students selected
        with self.assertRaises(ValueError):
            self.services.billing.print_pos_student_statements([])

        with self.assertRaises(ValueError):
            self.services.billing.print_pos_student_bills([])

    def test_filter_by_class_to_print_pos_and_dues_summary(self):
        # Create student 2 in Class 9
        student2_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Gita Thapa', 'Class 9', '9800000009', 'Active', '2083/01/01')"
        )
        enrollment2_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Class 9', '2083/01/01', 1500, 'Active')",
            (student2_id, self.course_id),
        )

        # Generate bills for both students
        b_c10 = self.services.billing.generate(self.enrollment_id, "2083/04", "2083/04/05", "2083/04/15").bill
        b_c9 = self.services.billing.generate(enrollment2_id, "2083/04", "2083/04/05", "2083/04/15").bill

        # 1. Verify DueBill models have correct class_name
        self.assertEqual(b_c10.class_name, "Class 10")
        self.assertEqual(b_c9.class_name, "Class 9")

        # 2. Verify get_student_dues_summary filtered by class
        c10_summaries = self.services.billing.get_student_dues_summary(class_name="Class 10")
        self.assertTrue(all(s["class_name"] == "Class 10" for s in c10_summaries))
        self.assertTrue(any(s["student_name"] == "Bikash Rai" for s in c10_summaries))
        self.assertFalse(any(s["student_name"] == "Gita Thapa" for s in c10_summaries))

        c9_summaries = self.services.billing.get_student_dues_summary(class_name="Class 9")
        self.assertEqual(len(c9_summaries), 1)
        self.assertEqual(c9_summaries[0]["student_name"], "Gita Thapa")
        self.assertEqual(c9_summaries[0]["class_name"], "Class 9")

        # 3. Verify get_unpaid_bills_by_class
        c10_unpaid = self.services.billing.get_unpaid_bills_by_class("Class 10")
        self.assertTrue(all(getattr(b, "class_name", "") == "Class 10" for b in c10_unpaid))
        self.assertTrue(any(b.id == b_c10.id for b in c10_unpaid))
        self.assertFalse(any(b.id == b_c9.id for b in c10_unpaid))

        # 4. Verify print_pos_by_class (bills mode and statement mode)
        printed_receipts = []
        self.services.printing.print_receipt = printed_receipts.append
        if hasattr(self.app.state, "services"):
            self.app.state.services.billing.printing.print_receipt = printed_receipts.append

        res_bills = self.services.billing.print_pos_by_class("Class 9", mode="bills")
        self.assertTrue(res_bills["ok"])
        self.assertEqual(res_bills["mode"], "bills")
        self.assertEqual(res_bills["printed_count"], 1)
        self.assertEqual(len(printed_receipts), 1)
        self.assertEqual(printed_receipts[0].customer_name, "Gita Thapa")

        printed_receipts.clear()
        res_stmt = self.services.billing.print_pos_by_class("Class 9", mode="statement")
        self.assertTrue(res_stmt["ok"])
        self.assertEqual(res_stmt["mode"], "statement")
        self.assertEqual(res_stmt["printed_count"], 1)
        self.assertEqual(len(printed_receipts), 1)
        self.assertEqual(printed_receipts[0].title, "STUDENT CREDIT STATEMENT")

        # 5. Web API endpoints: GET /api/bills?class_name=Class 9
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/bills?class_name=Class%209",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        ))
        self.assertEqual(status, 200)
        web_bills = json.loads(body.decode("utf-8"))
        self.assertEqual(len(web_bills), 1)
        self.assertEqual(web_bills[0]["class_name"], "Class 9")
        self.assertEqual(web_bills[0]["student_name"], "Gita Thapa")

        # 6. Web API endpoints: GET /api/bills/student-dues-summary?class_name=Class 9
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/bills/student-dues-summary?class_name=Class%209",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        ))
        self.assertEqual(status, 200)
        web_summaries = json.loads(body.decode("utf-8"))
        self.assertEqual(len(web_summaries), 1)
        self.assertEqual(web_summaries[0]["class_name"], "Class 9")

        # 7. Web API endpoints: POST /api/bills/print-pos-by-class
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/bills/print-pos-by-class",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            body={"class_name": "Class 9", "mode": "statement"}
        ))
        self.assertEqual(status, 200)
        res_web = json.loads(body.decode("utf-8"))
        self.assertTrue(res_web["ok"])
        self.assertEqual(res_web["printed_count"], 1)

        # 8. Web API endpoints: POST /api/bills/{bill_id}/print-pos
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            f"/api/bills/{b_c9.id}/print-pos",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        ))
        self.assertEqual(status, 200)
        res_single = json.loads(body.decode("utf-8"))
        self.assertTrue(res_single["ok"])

    def test_class_in_bill_pos_and_receipt_rendering(self):
        # 1. Single Bill POS
        bill = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill
        self.assertEqual(bill.class_name, "Class 10")

        printed_receipts = []
        self.services.billing.printing.print_receipt = lambda r: printed_receipts.append(r)

        self.services.billing.print_pos(bill)
        self.assertEqual(len(printed_receipts), 1)
        receipt = printed_receipts[0]
        self.assertEqual(receipt.class_name, "Class 10")

        printer = NetworkEscPosPrinter("127.0.0.1")
        rendered = printer._render(receipt)
        self.assertIn(b"Class   : Class 10", rendered)

        # 2. Consolidated Statement POS
        stmt_receipt = self.services.billing.print_pos_student_statement(self.student_id)
        self.assertEqual(stmt_receipt.class_name, "Class 10")
        rendered_stmt = printer._render(stmt_receipt)
        self.assertIn(b"Class   : Class 10", rendered_stmt)

    def test_class_in_bill_pdf_and_statement_pdf(self):
        bill = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill

        # Single Bill PDF
        pdf_path = self.services.billing.create_pdf(bill)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)

        # Batch PDF
        batch_pdf = self.services.billing.create_batch_pdf([bill])
        self.assertTrue(batch_pdf.exists())
        self.assertGreater(batch_pdf.stat().st_size, 1000)

        # Consolidated Statement PDF
        stmt_pdf = self.services.billing.create_consolidated_statement_pdf(bills=[bill])
        self.assertTrue(stmt_pdf.exists())
        self.assertGreater(stmt_pdf.stat().st_size, 1000)

    def test_class_in_whatsapp_bill_notice(self):
        bill = self.services.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/05", "2083/01/15"
        ).bill

        wa_data = self.services.notifications.build_bill_whatsapp_message(bill.id)
        self.assertEqual(wa_data["student_name"], "Bikash Rai")
        self.assertEqual(wa_data["class_name"], "Class 10")
        self.assertIn("Class / Grade: *Class 10*", wa_data["message"])

        # Pay bill and verify payment whatsapp message includes class
        pay_result = self.services.billing.pay_bills(
            [bill.id], Decimal("1500"), "2083/01/10", self.account_id, "Cash", "REC-099"
        )
        txn_id = pay_result["transaction_ids"][0]
        pay_wa = self.services.notifications.build_payment_whatsapp_message("student", txn_id)
        self.assertEqual(pay_wa["class_name"], "Class 10")
        self.assertIn("Class / Grade: *Class 10*", pay_wa["message"])


if __name__ == "__main__":
    unittest.main()
