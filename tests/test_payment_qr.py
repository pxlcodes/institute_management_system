from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from elh.config import AppConfig
from elh.core.payment_qr import PaymentQrData, PaymentQrEngine
from elh.core.settings import SettingsService
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.models import Receipt
from elh.repositories import BillingRepository
from elh.services.billing import BillingService
from elh.services.container import ServiceContainer
from elh.services.printing import PrintingService
from elh.services.reports import ReportsService
from elh.web.app import create_app


async def _run_asgi_request(
    app,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    client: tuple[str, int] = ("127.0.0.1", 50000),
) -> tuple[int, dict[str, str], bytes]:
    req_headers = []
    if headers:
        for k, v in headers.items():
            req_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    req_body = json.dumps(body).encode("utf-8") if body is not None else b""
    if body is not None and not any(k.lower() == "content-type" for k, _ in (headers or {}).items()):
        req_headers.append((b"content-type", b"application/json"))

    query_string = b""
    raw_path = path
    if "?" in path:
        raw_path, qs = path.split("?", 1)
        query_string = qs.encode("latin-1")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": raw_path,
        "raw_path": raw_path.encode("ascii"),
        "query_string": query_string,
        "headers": req_headers,
        "client": client,
        "server": ("testserver", 80),
    }

    res_status = 200
    res_headers: dict[str, str] = {}
    res_body = bytearray()

    async def receive():
        return {"type": "http.request", "body": req_body, "more_body": False}

    async def send(message):
        nonlocal res_status
        if message["type"] == "http.response.start":
            res_status = message["status"]
            for raw_k, raw_v in message.get("headers", []):
                k = raw_k.decode("latin-1").lower()
                v = raw_v.decode("latin-1")
                res_headers[k] = v
        elif message["type"] == "http.response.body":
            res_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return res_status, res_headers, bytes(res_body)


class DummyPrinter:
    def __init__(self):
        self.last_receipt = None

    def print_receipt(self, receipt: Receipt):
        self.last_receipt = receipt


class PaymentQrTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_elh.db"
        self.db = SQLiteDatabase(self.db_path, False)
        self.config = AppConfig(
            database_path=self.db_path,
            database_engine="sqlite",
            app_title="ELH Test Hub",
            currency_symbol="Rs.",
        )
        self.settings = SettingsService(self.db)
        self.settings.ensure_defaults()
        self.printer = DummyPrinter()
        self.printing = PrintingService(self.printer)
        self.billing_repo = BillingRepository(self.db)
        self.billing_service = BillingService(
            self.billing_repo, self.printing, "ELH Test Hub", "Rs.", settings=self.settings
        )
        self.reports_service = ReportsService(
            self.db, "ELH Test Hub", "Rs.", printing=self.printing, settings=self.settings
        )

        # Seed data
        self.school_id = self.db.execute(
            "INSERT INTO schools (school_name, status) VALUES ('Test School', 'Active')"
        )
        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name, category, billing_type, default_fee, duration_months, status) "
            "VALUES ('English Fluency', 'Language', 'Monthly', 4000.00, 3, 'Active')"
        )
        self.student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, joining_date, status) "
            "VALUES ('Suman Adhikari', 'Class 10', '9841234567', '2083/01/01', 'Active')"
        )
        self.enrollment_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, admission_fee, discount, status) "
            "VALUES (?, ?, 'Beginner', '2083/01/01', 4000.00, 500.00, 0.00, 'Active')",
            (self.student_id, self.course_id),
        )

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_fonepay_payload_generation(self):
        data = PaymentQrData(
            provider="Fonepay",
            merchant_id="MERCHANT123",
            merchant_name="Expert Learning Hub",
            amount=4500.00,
            bill_number="ELH-1-2083-01",
            student_name="Suman Adhikari",
        )
        payload = PaymentQrEngine.build_payload(data)
        self.assertTrue(payload.startswith("000201"))
        self.assertIn("fonepay.com", payload)
        self.assertIn("MERCHANT123", payload)

    def test_esewa_payload_generation(self):
        data = PaymentQrData(
            provider="eSewa",
            merchant_id="ESEWA_EXP_01",
            merchant_name="Expert Learning Hub",
            amount=3500.00,
            bill_number="ELH-1-2083-02",
            student_name="Suman Adhikari",
            purpose="Monthly Tuition",
        )
        payload = PaymentQrEngine.build_payload(data)
        self.assertIn("https://esewa.com.np/#/quick-pay?", payload)
        self.assertIn("rc=ESEWA_EXP_01", payload)
        self.assertIn("am=3500.00", payload)
        self.assertIn("pid=ELH-1-2083-02", payload)

    def test_khalti_and_bank_payload_generation(self):
        data_khalti = PaymentQrData(
            provider="Khalti",
            merchant_id="KHALTI_9841",
            amount=2500.00,
            bill_number="BILL-99",
        )
        payload_k = PaymentQrEngine.build_payload(data_khalti)
        self.assertIn("khalti.com/pay?", payload_k)

        data_bank = PaymentQrData(
            provider="Custom Payment",
            merchant_name="Expert Learning Hub",
            account_number="0123456789012",
            amount=5000.00,
            bill_number="BILL-100",
            student_name="Aarav",
        )
        payload_b = PaymentQrEngine.build_payload(data_bank)
        self.assertIn("PAYMENT:CUSTOM PAYMENT", payload_b)
        self.assertIn("ACC:0123456789012", payload_b)

    def test_reportlab_drawing_and_escpos_bytes(self):
        data = PaymentQrData(
            provider="Fonepay",
            merchant_id="EXP_01",
            amount=4000.0,
            bill_number="ELH-01",
        )
        # Vector drawing
        drawing = PaymentQrEngine.build_reportlab_drawing(data, size_mm=30.0)
        self.assertIsNotNone(drawing)
        self.assertGreater(drawing.width, 0)

        # ESC/POS binary command stream
        raw_bytes = PaymentQrEngine.build_escpos_bytes(data, module_size=5)
        self.assertIn(b"\x1d(k", raw_bytes)  # GS ( k
        self.assertIn(b"1P0", raw_bytes)  # Store data
        self.assertIn(b"1Q0", raw_bytes)  # Print QR

        # ESC/POS raster bit image stream (GS v 0)
        raster_bytes = PaymentQrEngine.build_escpos_raster(data, printer_chars=42)
        self.assertIn(b"\x1dv0", raster_bytes)  # GS v 0 raster header
        self.assertGreater(len(raster_bytes), 1000)

    def test_due_bill_pdf_and_pos_with_qr_code(self):
        # Configure Fonepay in settings
        self.settings.set("payment_qr_enabled", "true")
        self.settings.set("payment_qr_provider", "Fonepay")
        self.settings.set("payment_qr_merchant_id", "EXP_FONEPAY_01")
        self.settings.set("payment_qr_merchant_name", "Expert Learning Hub")

        gen_res = self.billing_service.generate(
            self.enrollment_id, "2083/01", "2083/01/01", "2083/01/08", "Term 1 bill"
        )
        bill = gen_res.bill

        # Test PDF Generation with QR
        pdf_path = Path(self.temp_dir.name) / "test_due_bill.pdf"
        self.billing_service.create_pdf(bill, output=pdf_path)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)

        # Test Batch PDF Generation
        batch_pdf_path = Path(self.temp_dir.name) / "test_batch_due_bill.pdf"
        self.billing_service.create_batch_pdf([bill], output=batch_pdf_path)
        self.assertTrue(batch_pdf_path.exists())

        # Test POS Print with QR payload
        self.billing_service.print_pos(bill)
        last_receipt = self.printer.last_receipt
        self.assertIsNotNone(last_receipt)
        self.assertTrue(last_receipt.qr_payload.startswith("000201"))
        self.assertIn("fonepay.com", last_receipt.qr_payload)
        self.assertIn("Scan to Pay (Fonepay)", last_receipt.qr_caption)

    def test_payment_proof_pdf_and_pos_with_qr(self):
        # Create an account and record payment
        acc_id = self.db.execute(
            "INSERT INTO accounts (account_name, account_type, status) VALUES ('Cash Counter', 'Cash Counter', 'Active')"
        )
        gen_res = self.billing_service.generate(
            self.enrollment_id, "2083/01", "2083/01/01", "2083/01/08"
        )
        self.billing_service.pay(
            gen_res.bill.id,
            Decimal("4500.00"),
            "2083/01/02",
            acc_id,
            "Cash",
            receipt_no="RCP-101",
        )

        txn = self.db.query_one("SELECT id FROM student_transactions ORDER BY id DESC LIMIT 1")
        txn_id = int(txn["id"])

        # Test Payment Proof PDF with verification QR
        proof_pdf = Path(self.temp_dir.name) / "test_payment_proof.pdf"
        self.reports_service.payment_proof_pdf("student", txn_id, output=proof_pdf)
        self.assertTrue(proof_pdf.exists())

        # Test Payment Proof POS Print
        self.reports_service.print_payment_pos("student", txn_id)
        last_receipt = self.printer.last_receipt
        self.assertIsNotNone(last_receipt)
        self.assertIn("VERIFIED PAYMENT RECEIPT", last_receipt.footer)

    def test_custom_qr_image_rendering(self):
        from PIL import Image as PILImage
        img_path = Path(self.temp_dir.name) / "merchant_standee_qr.png"
        dummy_img = PILImage.new("RGB", (150, 150), color=(0, 120, 215))
        dummy_img.save(img_path)

        # Set custom QR image path in settings
        self.settings.set("payment_qr_image_path", str(img_path))
        self.settings.set("payment_qr_provider", "Fonepay Standee")

        data = PaymentQrEngine.from_settings(
            self.settings, Decimal("3500.00"), "BILL-IMG-01", "Suman", "English"
        )
        self.assertIsNotNone(data)
        self.assertEqual(data.image_path, str(img_path))

        # Test build_reportlab_flowable returns an Image flowable
        flowable = PaymentQrEngine.build_reportlab_flowable(data, size_mm=32.0)
        from reportlab.platypus import Image as RLImage
        self.assertIsInstance(flowable, RLImage)

        # Test Due Bill generation with image QR
        gen_res = self.billing_service.generate(
            self.enrollment_id, "2083/02", "2083/02/01", "2083/02/08"
        )
        pdf_path = Path(self.temp_dir.name) / "test_due_bill_custom_img.pdf"
        self.billing_service.create_pdf(gen_res.bill, output=pdf_path)
        self.assertTrue(pdf_path.exists())

    def test_web_api_bill_qr_endpoint(self):
        container = ServiceContainer.build(self.config, self.db)
        app = create_app(self.config)

        gen_res = container.billing.generate(
            self.enrollment_id, "2083/01", "2083/01/01", "2083/01/08"
        )
        bill_id = gen_res.bill.id

        async def scenario():
            # Login
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/auth/login",
                body={"username": self.config.operator_username, "password": self.config.operator_password},
            )
            self.assertEqual(status, 200)
            token = json.loads(body)["token"]
            headers = {"authorization": f"Bearer {token}"}

            # Query QR endpoint
            status, _, body = await _run_asgi_request(
                app,
                "GET",
                f"/api/bills/{bill_id}/qr",
                headers=headers,
            )
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertTrue(data["enabled"])
            self.assertEqual(data["amount"], 4500.0)
            self.assertIn("payload", data)
            self.assertEqual(data["student_name"], "Suman Adhikari")

        asyncio.run(scenario())

    def test_bank_qr_account_attributes_and_default_billing_qr(self):
        container = ServiceContainer.build(self.config, self.db)
        app = create_app(self.config)

        # Create the user's specific account with bankCode and accountNumber
        acc_payload = {
            "account_name": "EXPERT LEARNING HUB",
            "account_type": "CURRENT ACCOUNT",
            "bank_name": "Kamana Sewa Bikas Bank",
            "bank_code": "KSKFNPKA",
            "account_number": "08000300919240000001",
            "account_holder": "EXPERT LEARNING HUB",
            "opening_balance": 15000.0,
            "is_billing_default": True,
            "status": "Active",
            "remarks": "Official Fonepay Bank QR Account",
        }

        async def scenario():
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/auth/login",
                body={"username": self.config.admin_username, "password": self.config.admin_password},
            )
            self.assertEqual(status, 200)
            token = json.loads(body)["token"]
            headers = {"authorization": f"Bearer {token}"}

            # Create account via API
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/accounts",
                headers=headers,
                body=acc_payload,
            )
            self.assertEqual(status, 201)
            acc_id = json.loads(body)["id"]

            # Verify account in DB
            row = self.db.query_one("SELECT * FROM accounts WHERE id=?", (acc_id,))
            self.assertEqual(row["bank_code"], "KSKFNPKA")
            self.assertEqual(row["account_number"], "08000300919240000001")
            self.assertEqual(row["account_type"], "CURRENT ACCOUNT")
            self.assertEqual(row["is_billing_default"], 1)

            # Generate Due Bill and verify PaymentQrEngine picks up the bank account
            gen_res = container.billing.generate(
                self.enrollment_id, "2083/03", "2083/03/01", "2083/03/08"
            )
            bill = gen_res.bill

            qr_data = PaymentQrEngine.from_settings(
                self.settings, bill.total_amount, bill.bill_number, bill.student_name, bill.course_name
            )
            self.assertIsNotNone(qr_data)
            self.assertEqual(qr_data.account_number, "08000300919240000001")
            self.assertEqual(qr_data.bank_code, "KSKFNPKA")

            payload = PaymentQrEngine.build_payload(qr_data)
            self.assertTrue(payload.startswith("000201"))
            self.assertIn("fonepay.com", payload)

            # Also verify via web API
            status, _, body = await _run_asgi_request(
                app,
                "GET",
                f"/api/bills/{bill.id}/qr",
                headers=headers,
            )
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertTrue(data["payload"].startswith("000201"))
            self.assertIn("fonepay.com", data["payload"])

        asyncio.run(scenario())

    def test_native_emvco_fonepay_tlv_and_dynamic_bill_qr(self):
        raw_emvco = "0002010102110216427142002103914826400011fonepay.com07162222520021039149110115204829953035245802NP5919EXPERT LEARNING HUB6013PATHARI BRANC62110707216250863041866"
        
        # Test TLV parsing
        tlv = PaymentQrEngine.parse_emvco_tlv(raw_emvco)
        self.assertEqual(tlv["00"], "01")
        self.assertEqual(tlv["59"], "EXPERT LEARNING HUB")
        self.assertEqual(tlv["60"], "PATHARI BRANC")
        self.assertEqual(tlv["53"], "524")
        self.assertEqual(tlv["63"], "1866")

        # Test CRC verification
        calculated_crc = PaymentQrEngine.crc16_ccitt(raw_emvco[:-4])
        self.assertEqual(calculated_crc, "1866")

        # Test Dynamic EMVCo QR code generation for a student bill
        dynamic_payload = PaymentQrEngine.build_dynamic_emvco(
            raw_emvco,
            amount=4500.0,
            bill_number="BILL-2083-05-001",
            student_name="Suman Adhikari",
            purpose="Tuition Fee",
        )
        self.assertTrue(dynamic_payload.startswith("000201"))
        self.assertIn("54074500.00", dynamic_payload)
        self.assertIn("EXPERT LEARNING HUB", dynamic_payload)
        self.assertIn("BILL-2083-05-001", dynamic_payload)
        self.assertIn("Suman Adhikari", dynamic_payload)

        # Verify dynamic CRC
        dynamic_tlv = PaymentQrEngine.parse_emvco_tlv(dynamic_payload)
        self.assertEqual(dynamic_tlv["01"], "12")  # Point of Initiation Method -> Dynamic
        self.assertEqual(dynamic_tlv["54"], "4500.00")
        expected_dynamic_crc = PaymentQrEngine.crc16_ccitt(dynamic_payload[:-4])
        self.assertEqual(dynamic_payload[-4:], expected_dynamic_crc)

        # Test PaymentQrEngine.build_payload with qr_payload attached to PaymentQrData
        qr_data = PaymentQrData(
            provider="Fonepay",
            merchant_name="EXPERT LEARNING HUB",
            amount=3200.0,
            bill_number="BILL-102",
            student_name="Aarav",
            qr_payload=raw_emvco,
        )
        built = PaymentQrEngine.build_payload(qr_data)
        self.assertTrue(built.startswith("000201"))
        self.assertIn("54073200.00", built)
        self.assertIn("BILL-102", built)

        # Static when amount is 0 and no bill number
        qr_data_static = PaymentQrData(
            provider="Fonepay",
            amount=0,
            bill_number="",
            qr_payload=raw_emvco,
        )
        built_static = PaymentQrEngine.build_payload(qr_data_static)
        self.assertEqual(built_static, raw_emvco)

    def test_qr_remark_set_as_bill_number(self):
        raw_emvco = "0002010102110216427142002103914826400011fonepay.com07162222520021039149110115204829953035245802NP5919EXPERT LEARNING HUB6013PATHARI BRANC62110707216250863041866"
        bill_no = "BILL-2083-05-888"

        # 1. EMVCo dynamic QR: Verify Tag 62 Subtag 08 (Purpose/Remarks) is set to bill number
        dynamic_payload = PaymentQrEngine.build_dynamic_emvco(
            raw_emvco,
            amount=3000.0,
            bill_number=bill_no,
            student_name="Nitesh Sharma",
            purpose="Monthly Tuition Fee",
        )
        tlv = PaymentQrEngine.parse_emvco_tlv(dynamic_payload)
        sub_62 = PaymentQrEngine.parse_emvco_tlv(tlv["62"])
        self.assertEqual(sub_62["01"], bill_no)  # Bill No tag
        self.assertEqual(sub_62["08"], bill_no)  # Remarks/Purpose tag

        # 2. eSewa QuickPay: Verify 'su' (subject/remark) is set to bill number
        esewa_data = PaymentQrData(
            provider="eSewa",
            merchant_id="EXP_ESEWA",
            amount=3000.0,
            bill_number=bill_no,
            student_name="Nitesh Sharma",
        )
        esewa_payload = PaymentQrEngine.build_payload(esewa_data)
        self.assertIn(f"pid={bill_no}", esewa_payload)
        self.assertIn(f"su={bill_no}", esewa_payload)

        # 3. from_settings: remarks attribute should default to bill_number
        qr_data = PaymentQrEngine.from_settings(
            self.settings, Decimal("3000.00"), bill_no, "Nitesh Sharma"
        )
        self.assertIsNotNone(qr_data)
        self.assertEqual(qr_data.remarks, bill_no)

        # 4. Web API: /api/bills/{bill_id}/qr should return remark equal to bill number
        container = ServiceContainer.build(self.config, self.db)
        app = create_app(self.config)
        gen_res = container.billing.generate(
            self.enrollment_id, "2083/04", "2083/04/01", "2083/04/08"
        )
        created_bill = gen_res.bill

        async def scenario():
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/auth/login",
                body={"username": self.config.operator_username, "password": self.config.operator_password},
            )
            self.assertEqual(status, 200)
            token = json.loads(body)["token"]
            headers = {"authorization": f"Bearer {token}"}

            status, _, body = await _run_asgi_request(
                app,
                "GET",
                f"/api/bills/{created_bill.id}/qr",
                headers=headers,
            )
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["bill_number"], created_bill.bill_number)
            self.assertEqual(data["remark"], created_bill.bill_number)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
