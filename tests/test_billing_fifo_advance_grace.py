from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.services.container import ServiceContainer
from elh.services.billing import BillingService


class BillingFifoAdvanceGraceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_billing.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            secret_key="unit-test-secret-key",
            date_format="%Y/%m/%d",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.services = ServiceContainer.build(self.config, self.db)

        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name,category,billing_type,default_fee,status) "
            "VALUES ('IELTS Master','Coaching','Monthly',3000,'Active')"
        )
        self.student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Aarav Sharma', 'Class 10', '9800000001', 'Active', '2081/01/01')"
        )
        self.account_id = self.db.execute(
            "INSERT INTO accounts (account_name,account_type,opening_balance,status) "
            "VALUES ('Main Cash Counter','Cash Counter',0,'Active')"
        )

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_5_day_grace_period_calculation(self):
        """Enrollment within the last 5 days of a Nepali month skips to next month for billing."""
        eff_start_28 = BillingService.get_effective_billing_start_month("2081/03/28", grace_days=5)
        eff_start_29 = BillingService.get_effective_billing_start_month("2081/03/29", grace_days=5)
        eff_start_30 = BillingService.get_effective_billing_start_month("2081/03/30", grace_days=5)
        self.assertEqual(eff_start_28, "2081/04")
        self.assertEqual(eff_start_29, "2081/04")
        self.assertEqual(eff_start_30, "2081/04")

        eff_start_15 = BillingService.get_effective_billing_start_month("2081/03/15", grace_days=5)
        self.assertEqual(eff_start_15, "2081/03")

    def test_generation_skips_when_effective_start_month_is_later(self):
        """Enrolling a student on 2081/03/28 will not generate a bill for 2081/03."""
        enr_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
            "VALUES (?, ?, '2081/03/28', 3000, 'Active')",
            (self.student_id, self.course_id),
        )
        with self.assertRaises(ValueError) as cm:
            self.services.billing.generate(enr_id, "2081/03", "2081/03/28", "2081/04/05")
        self.assertIn("grace", str(cm.exception).lower())

        res2 = self.services.billing.generate(enr_id, "2081/04", "2081/04/01", "2081/04/10")
        self.assertTrue(res2.created)
        self.assertEqual(res2.bill.billing_period, "2081/04")

    def test_fifo_payment_allocation(self):
        """Paying month 05 when month 04 is unpaid automatically settles month 04 first."""
        enr_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
            "VALUES (?, ?, '2081/01/01', 3000, 'Active')",
            (self.student_id, self.course_id),
        )

        b4 = self.services.billing.generate(enr_id, "2081/04", "2081/04/01", "2081/04/10").bill
        b5 = self.services.billing.generate(enr_id, "2081/05", "2081/05/01", "2081/05/10").bill

        res = self.services.billing.pay_bills(
            [b5.id],
            Decimal("3000"),
            "2081/05/05",
            self.account_id,
            "Cash",
            receipt_no="R-01",
            remarks="Pay bill",
            discount=Decimal("0"),
            enforce_fifo=True,
        )

        b4_updated = self.services.billing.repository.get(b4.id)
        b5_updated = self.services.billing.repository.get(b5.id)

        # Under FIFO, b4 (Month 04) is fully paid first, and b5 (Month 05) remains Due!
        self.assertEqual(b4_updated.status, "Paid")
        self.assertEqual(b4_updated.paid_amount, Decimal("3000"))
        self.assertEqual(b5_updated.status, "Due")
        self.assertEqual(b5_updated.paid_amount, Decimal("0"))

    def test_fifo_reconciliation_fixes_out_of_order_payments(self):
        """Reconciliation redistributes payments in FIFO order when out-of-order payments exist."""
        enr_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
            "VALUES (?, ?, '2081/01/01', 2000, 'Active')",
            (self.student_id, self.course_id),
        )

        b4 = self.services.billing.generate(enr_id, "2081/04", "2081/04/01", "2081/04/10").bill
        b5 = self.services.billing.generate(enr_id, "2081/05", "2081/05/01", "2081/05/10").bill

        # Simulate legacy out-of-order state directly in DB: b4 has 0 paid (Due), b5 has 2000 paid (Paid)
        self.db.execute("UPDATE due_bills SET paid_amount='2000', status='Paid' WHERE id=?", (b5.id,))

        b4_check = self.services.billing.repository.get(b4.id)
        b5_check = self.services.billing.repository.get(b5.id)
        self.assertEqual(b4_check.status, "Due")
        self.assertEqual(b5_check.status, "Paid")

        recon = self.services.billing.reconcile_student_billing_fifo(student_id=self.student_id)
        self.assertEqual(recon["reconciled_students"], 1)
        self.assertEqual(recon["adjusted_bills"], 2)

        # Now Month 04 must be Paid, and Month 05 must be Due
        b4_fixed = self.services.billing.repository.get(b4.id)
        b5_fixed = self.services.billing.repository.get(b5.id)
        self.assertEqual(b4_fixed.status, "Paid")
        self.assertEqual(b4_fixed.paid_amount, Decimal("2000"))
        self.assertEqual(b5_fixed.status, "Due")
        self.assertEqual(b5_fixed.paid_amount, Decimal("0"))

    def test_record_advance_payment_settles_dues_and_credits_surplus(self):
        """Direct advance payment settles outstanding bills first, then credits surplus as student advance balance."""
        enr_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
            "VALUES (?, ?, '2081/01/01', 2500, 'Active')",
            (self.student_id, self.course_id),
        )

        b1 = self.services.billing.generate(enr_id, "2081/04", "2081/04/01", "2081/04/10").bill

        res = self.services.billing.repository.record_advance_payment(
            student_id=self.student_id,
            amount=Decimal("6000"),
            payment_date="2081/04/05",
            account_id=self.account_id,
            payment_method="Cash",
            receipt_no="ADV-101",
            remarks="Tuition advance",
        )

        b1_updated = self.services.billing.repository.get(b1.id)
        self.assertEqual(b1_updated.status, "Paid")
        self.assertEqual(b1_updated.paid_amount, Decimal("2500"))

        self.assertEqual(res["total_paid"], Decimal("6000"))
        self.assertEqual(res["advance_amount"], Decimal("3500"))

        st_row = self.db.query_one(
            "SELECT transaction_type, payment_amount FROM student_transactions WHERE student_id=? AND particular LIKE '%Advance fee payment%'",
            (self.student_id,)
        )
        self.assertIsNotNone(st_row)
        self.assertEqual(Decimal(str(st_row["payment_amount"])), Decimal("3500"))

    def test_delete_unpaid_bill(self):
        """Unpaid bill can be deleted, but bill with paid amount raises ValueError."""
        enr_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
            "VALUES (?, ?, '2081/01/01', 2000, 'Active')",
            (self.student_id, self.course_id),
        )

        b = self.services.billing.generate(enr_id, "2081/08", "2081/08/01", "2081/08/10").bill
        self.services.billing.repository.delete_bill(b.id)
        self.assertIsNone(self.services.billing.repository.get(b.id))

        b2 = self.services.billing.generate(enr_id, "2081/08", "2081/08/01", "2081/08/10").bill
        self.db.execute("UPDATE due_bills SET paid_amount='500', status='Partially Paid' WHERE id=?", (b2.id,))
        with self.assertRaises(ValueError):
            self.services.billing.repository.delete_bill(b2.id)


if __name__ == "__main__":
    unittest.main()
