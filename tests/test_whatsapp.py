from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from elh.config import AppConfig
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.integrations.whatsapp import (
    GenericWhatsAppGatewayProvider,
    MetaWhatsAppCloudProvider,
    WhatsAppResponse,
    build_whatsapp_click_to_chat_url,
    create_whatsapp_provider,
    normalize_whatsapp_recipient,
)
from elh.services.notifications import NotificationService


from pathlib import Path
import tempfile

class TestWhatsAppIntegration(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.db_path = Path(tempfile.mktemp(suffix=".db"))
        self.db = SQLiteDatabase(self.db_path)
        self._setup_schema()
        self.notifications = NotificationService(self.db, self.config)

    def tearDown(self):
        try:
            if hasattr(self, "db_path") and self.db_path.exists():
                self.db_path.unlink()
        except Exception:
            pass

    def _setup_schema(self):
        self.db.execute(
            "INSERT OR REPLACE INTO company_profile (id, company_name, phone, principal_name) "
            "VALUES (1, 'Expert Learning Hub', '023-540000', 'Principal')"
        )
        self.db.execute(
            "INSERT INTO accounts (id, account_name, bank_name, account_number, account_type, status, is_billing_default) "
            "VALUES (1, 'EXPERT LEARNING HUB', 'Kamana Sewa Bikas Bank', '08000300919240000001', 'Bank', 'Active', 1)"
        )
        self.db.execute(
            "INSERT INTO students (id, student_name, contact, parent_name, joining_date, status) "
            "VALUES (10, 'Suman Adhikari', '9805354348', 'Hari Adhikari', '2083/05/01', 'Active')"
        )
        self.db.execute(
            "INSERT INTO courses (id, course_name, category, billing_type, default_fee, duration_months, status) "
            "VALUES (5, 'Basic English', 'Language', 'Monthly', 4000.0, 3, 'Active')"
        )
        self.db.execute(
            "INSERT INTO enrollments (id, student_id, course_id, monthly_fee, start_date, status) "
            "VALUES (100, 10, 5, 4000.0, '2083/05/01', 'Active')"
        )
        self.db.execute(
            "INSERT INTO due_bills (id, enrollment_id, bill_number, billing_period, issue_date, due_date, subtotal, discount, total_amount, paid_amount, status) "
            "VALUES (1, 100, 'ELH-BILL-001', '2083/05', '2083/05/01', '2083/05/10', 4000.0, 0.0, 4000.0, 1000.0, 'Partial')"
        )
        self.db.execute(
            "INSERT INTO student_transactions (id, student_id, enrollment_id, transaction_date, transaction_type, particular, charge_amount, payment_amount, discount_amount, account_id, payment_method, receipt_no, remarks) "
            "VALUES (1, 10, 100, '2083/05/05', 'Payment Received', 'Payment for bill ELH-BILL-001', 0, 1000.0, 0, 1, 'Cash', 'REC-001', '')"
        )

    def test_normalize_whatsapp_recipient(self):
        # 10 digits Nepal mobile
        self.assertEqual(normalize_whatsapp_recipient("9805354348"), "9779805354348")
        # Pre-formatted with country code
        self.assertEqual(normalize_whatsapp_recipient("9779805354348"), "9779805354348")
        # With symbols
        self.assertEqual(normalize_whatsapp_recipient("+977 980-535-4348"), "9779805354348")
        # Invalid number
        with self.assertRaises(ValueError):
            normalize_whatsapp_recipient("123")

    def test_build_whatsapp_click_to_chat_url(self):
        url = build_whatsapp_click_to_chat_url("9805354348", "Hello World!\nTotal: Rs. 2,000.00")
        self.assertTrue(url.startswith("https://wa.me/9779805354348?text="))
        self.assertIn("Hello%20World%21", url)
        self.assertIn("%0A", url)  # newline URL encoded

    def test_meta_whatsapp_cloud_provider_validation(self):
        # Missing credentials
        provider = MetaWhatsAppCloudProvider(phone_number_id="", access_token="")
        resp = provider.send("9805354348", "Test")
        self.assertFalse(resp.success)
        self.assertEqual(resp.code, "CONFIG_ERROR")

    def test_generic_whatsapp_gateway_validation(self):
        # Missing endpoint
        provider = GenericWhatsAppGatewayProvider(endpoint="")
        resp = provider.send("9805354348", "Test")
        self.assertFalse(resp.success)
        self.assertEqual(resp.code, "CONFIG_ERROR")

    def test_create_whatsapp_provider_factory(self):
        meta = create_whatsapp_provider("meta_cloud", config=self.config)
        self.assertIsInstance(meta, MetaWhatsAppCloudProvider)

        gateway = create_whatsapp_provider("gateway", config=self.config)
        self.assertIsInstance(gateway, GenericWhatsAppGatewayProvider)

        none_prov = create_whatsapp_provider("1-Click Web/App (Free)")
        self.assertIsNone(none_prov)

    def test_build_bill_whatsapp_message(self):
        data = self.notifications.build_bill_whatsapp_message(1)
        self.assertEqual(data["student_name"], "Suman Adhikari")
        self.assertEqual(data["bill_number"], "ELH-BILL-001")
        self.assertEqual(data["recipient"], "9805354348")
        self.assertIn("4,000.00", data["message"])
        self.assertIn("3,000.00", data["message"])  # remaining
        self.assertIn("Kamana Sewa Bikas Bank", data["message"])
        self.assertTrue(data["whatsapp_url"].startswith("https://wa.me/9779805354348"))

    def test_build_payment_whatsapp_message(self):
        data = self.notifications.build_payment_whatsapp_message("student", 1)
        self.assertEqual(data["student_name"], "Suman Adhikari")
        self.assertEqual(data["receipt_number"], "REC-001")
        self.assertEqual(data["recipient"], "9805354348")
        self.assertIn("1,000.00", data["message"])
        self.assertIn("3,000.00", data["message"])  # remaining balance
        self.assertTrue(data["whatsapp_url"].startswith("https://wa.me/9779805354348"))


if __name__ == "__main__":
    unittest.main()
