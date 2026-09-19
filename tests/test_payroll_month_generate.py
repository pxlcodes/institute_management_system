import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from dataclasses import replace

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class PayrollMonthGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_payroll.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="payrolladmin",
            admin_password="Admin@Password12345",
            secret_key="secret-key-for-payroll-tests-999",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.app = create_app(self.config)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _login(self):
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/auth/login",
            body={"username": "payrolladmin", "password": "Admin@Password12345"}
        ))
        self.assertEqual(status, 200)
        return json.loads(body.decode("utf-8"))["token"]

    def test_generate_payroll_of_month_and_regenerate_and_edit(self):
        token = self._login()
        headers = {"authorization": f"Bearer {token}"}

        # 1. Setup account
        acc_id = self.db.execute(
            "INSERT INTO accounts (account_name, account_type, opening_balance, status) "
            "VALUES ('Primary Bank', 'Bank', 500000.0, 'Active')"
        )

        # 2. Setup teachers: 1 per class, 1 monthly
        t_per_class = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, salary_type, basic_salary, status) "
            "VALUES ('Teacher Ram', '9811111111', '2083/01/01', 'Per Class Payment', 400.0, 'Active')"
        )
        t_monthly = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, salary_type, basic_salary, status) "
            "VALUES ('Teacher Sita', '9822222222', '2083/01/01', 'Monthly Salary', 25000.0, 'Active')"
        )

        # 3. Add advance for Teacher Sita with monthly deduction
        self.db.execute(
            "INSERT INTO teacher_advances (teacher_id, advance_date, amount, paid_from_account_id, monthly_deduction, recovered_amount, status) "
            "VALUES (?, '2083/04/15', 5000.0, ?, 2000.0, 0.0, 'Outstanding')",
            (t_monthly, acc_id),
        )

        # 4. Generate Payroll for month 2083/05 as Draft
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/salary/generate-month",
            headers=headers,
            body={
                "salary_month": "2083/05",
                "paid_from_account_id": acc_id,
                "payment_date": "2083/05/25",
                "payment_method": "Bank",
                "status": "Draft",
                "overwrite": True,
            }
        ))
        self.assertEqual(status, 200)
        res = json.loads(body.decode("utf-8"))
        self.assertGreaterEqual(res["created"], 2)
        self.assertEqual(res["month"], "2083/05")

        # 5. Verify Draft records exist in GET /api/salary?month=2083/05
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/salary?month=2083/05",
            headers=headers,
        ))
        self.assertEqual(status, 200)
        payouts = json.loads(body.decode("utf-8"))
        self.assertEqual(len(payouts), 2)
        payout_by_tid = {p["teacher_id"]: p for p in payouts}
        self.assertIn(t_per_class, payout_by_tid)
        self.assertIn(t_monthly, payout_by_tid)

        sita_payout = payout_by_tid[t_monthly]
        self.assertEqual(sita_payout["status"], "Draft")
        self.assertEqual(float(sita_payout["basic_salary"]), 25000.0)
        self.assertEqual(float(sita_payout["advance_deduction"]), 2000.0)
        self.assertEqual(float(sita_payout["net_salary"]), 23000.0)

        # 6. Test Edit: Update Teacher Ram's payout record (add bonus and extra pay)
        ram_payout = payout_by_tid[t_per_class]
        ram_payout_id = ram_payout["id"]
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "PUT",
            f"/api/salary/{ram_payout_id}",
            headers=headers,
            body={
                "basic_salary": 8000.0,
                "extra_payment": 1200.0,
                "bonus": 1000.0,
                "allowance": 500.0,
                "advance_deduction": 0.0,
                "other_deduction": 200.0,
                "attendance_days": 20,
                "working_hours": 60.0,
                "class_count": 20,
                "payment_date": "2083/05/28",
                "paid_from_account_id": acc_id,
                "payment_method": "Bank",
                "voucher_no": "VOUCH-RAM-01",
                "status": "Draft",
                "remarks": "Manual adjustment for term bonus",
            }
        ))
        self.assertEqual(status, 200)
        updated_ram = json.loads(body.decode("utf-8"))
        # 8000 + 1200 + 1000 + 500 - 200 = 10500
        self.assertEqual(float(updated_ram["net_salary"]), 10500.0)
        self.assertEqual(updated_ram["remarks"], "Manual adjustment for term bonus")

        # 7. Test Regenerate for single staff member
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            f"/api/salary/{ram_payout_id}/regenerate",
            headers=headers,
        ))
        self.assertEqual(status, 200)
        regen_ram = json.loads(body.decode("utf-8"))
        self.assertEqual(regen_ram["id"], ram_payout_id)

        # 8. Test Disburse Month Drafts
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/salary/disburse-month",
            headers=headers,
            body={
                "salary_month": "2083/05",
                "paid_from_account_id": acc_id,
                "payment_date": "2083/05/30",
                "payment_method": "Bank",
                "voucher_no": "BATCH-05",
            }
        ))
        self.assertEqual(status, 200)
        disburse_res = json.loads(body.decode("utf-8"))
        self.assertEqual(disburse_res["disbursed_count"], 2)

        # 9. Verify that both payouts are now 'Paid'
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/salary?month=2083/05&status=Paid",
            headers=headers,
        ))
        self.assertEqual(status, 200)
        paid_list = json.loads(body.decode("utf-8"))
        self.assertEqual(len(paid_list), 2)
        for p in paid_list:
            self.assertEqual(p["status"], "Paid")

        # 10. Verify Payslip PDF generation for Paid payout
        status, _, _ = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            f"/api/salary/{ram_payout_id}/payslip/pdf",
            headers=headers,
        ))
        self.assertEqual(status, 200)

        # 11. Test Delete salary payout
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "DELETE",
            f"/api/salary/{ram_payout_id}",
            headers=headers,
        ))
        self.assertEqual(status, 200)

        # Verify only 1 remains for month
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/salary?month=2083/05",
            headers=headers,
        ))
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body.decode("utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
