from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm

logger = logging.getLogger("elh.core.payment_qr")


@dataclass
class PaymentQrData:
    provider: str = "Fonepay"
    merchant_id: str = ""
    merchant_name: str = ""
    account_number: str = ""
    bank_code: str = ""
    account_type: str = ""
    amount: Decimal | float = 0
    bill_number: str = ""
    student_name: str = ""
    purpose: str = "Institute Tuition Fee"
    instructions: str = "Scan to Pay via Fonepay / eSewa / Mobile Banking"
    image_path: str = ""
    qr_payload: str = ""


class PaymentQrEngine:
    """Engine to generate standardized digital payment QR payloads for Nepali payment gateways."""

    @staticmethod
    def crc16_ccitt(data: str) -> str:
        """Compute standard EMVCo CRC16-CCITT checksum."""
        crc = 0xFFFF
        for ch in data.encode("ascii", errors="ignore"):
            crc ^= (ch << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return f"{crc:04X}"

    @classmethod
    def parse_emvco_tlv(cls, raw: str) -> dict[str, str]:
        """Parse raw EMVCo Tag-Length-Value payload into dictionary."""
        i = 0
        res: dict[str, str] = {}
        s = raw.strip()
        while i + 4 <= len(s):
            tag = s[i:i+2]
            try:
                length = int(s[i+2:i+4])
            except ValueError:
                break
            val = s[i+4:i+4+length]
            res[tag] = val
            i += 4 + length
        return res

    @classmethod
    def build_dynamic_emvco(
        cls,
        base_emvco: str,
        amount: Decimal | float = 0,
        bill_number: str = "",
        student_name: str = "",
        purpose: str = "",
    ) -> str:
        """Construct scannable dynamic EMVCo payload from a base merchant QR code string."""
        tlv = cls.parse_emvco_tlv(base_emvco)
        if not tlv or "00" not in tlv:
            return base_emvco

        amt = float(amount or 0)
        bill_no = "".join(ch for ch in str(bill_number or "") if 32 <= ord(ch) <= 126).strip()
        student = "".join(ch for ch in str(student_name or "") if 32 <= ord(ch) <= 126).strip()
        purp = "".join(ch for ch in str(purpose or "") if 32 <= ord(ch) <= 126).strip()

        # Remove old CRC if present
        tlv.pop("63", None)

        # Tag 01: Point of Initiation (12 = Dynamic QR with fixed amount / ref)
        if amt > 0 or bill_no:
            tlv["01"] = "12"

        # Tag 54: Transaction Amount
        if amt > 0:
            tlv["54"] = f"{amt:.2f}"

        # Tag 62: Additional Data Field Template (Bill no, reference, purpose, terminal)
        sub_62: dict[str, str] = {}
        if "62" in tlv:
            sub_62 = cls.parse_emvco_tlv(tlv["62"])
        if bill_no:
            sub_62["01"] = bill_no[:25]
        if student:
            sub_62["05"] = student[:25]
        if purp:
            sub_62["08"] = purp[:25]

        rebuilt_62 = "".join(f"{k}{len(v):02d}{v}" for k, v in sorted(sub_62.items()))
        if rebuilt_62:
            tlv["62"] = rebuilt_62

        payload_body = "".join(f"{k}{len(tlv[k]):02d}{tlv[k]}" for k in sorted(tlv.keys()))
        payload_to_crc = payload_body + "6304"
        crc = cls.crc16_ccitt(payload_to_crc)
        return payload_to_crc + crc

    @classmethod
    def build_fonepay_emvco(
        cls,
        merchant_id: str = "2222520021039149",
        merchant_name: str = "EXPERT LEARNING HUB",
        city: str = "PATHARI BRANC",
        terminal_id: str = "2162508",
        pan: str = "4271420021039148",
    ) -> str:
        """Construct official static Fonepay EMVCo QR code string recognized by all mobile banking apps."""
        m_name = (merchant_name or "EXPERT LEARNING HUB")[:25].upper()
        m_city = (city or "PATHARI BRANC")[:15].upper()
        tag_26_val = f"0011fonepay.com07{len(merchant_id):02d}{merchant_id}11011"
        tag_26 = f"26{len(tag_26_val):02d}{tag_26_val}"
        tag_62_val = f"07{len(terminal_id):02d}{terminal_id}" if terminal_id else ""
        tag_62 = f"62{len(tag_62_val):02d}{tag_62_val}" if tag_62_val else ""

        body = (
            "000201010211"
            f"02{len(pan):02d}{pan}"
            + tag_26
            + "52048299"
            + "5303524"
            + "5802NP"
            + f"59{len(m_name):02d}{m_name}"
            + f"60{len(m_city):02d}{m_city}"
            + tag_62
            + "6304"
        )
        crc = cls.crc16_ccitt(body)
        return body + crc

    @classmethod
    def build_payload(cls, data: PaymentQrData) -> str:
        """Construct standard scannable digital payment payload for Fonepay, eSewa, Khalti, or Banking."""
        amt = float(data.amount or 0)
        bill_no = (data.bill_number or "").strip()
        m_id = (data.merchant_id or "").strip()
        m_name = (data.merchant_name or "EXPERT LEARNING HUB").strip()
        student = (data.student_name or "").strip()
        acc = (data.account_number or m_id).strip()
        provider = (data.provider or "Fonepay").strip()

        # 1. If an exact merchant QR string (EMVCo) is saved in the account/settings, use it with dynamic amount/remarks
        if data.qr_payload and data.qr_payload.strip().startswith("000201"):
            base = data.qr_payload.strip()
            if amt > 0 or bill_no:
                return cls.build_dynamic_emvco(
                    base,
                    amount=amt,
                    bill_number=bill_no,
                    student_name=student,
                    purpose=data.purpose,
                )
            return base

        if provider.lower() == "esewa":
            # eSewa Digital QuickPay payload standard
            if m_id or acc:
                return f"https://esewa.com.np/#/quick-pay?rc={m_id or acc}&am={amt:.2f}&pid={bill_no}&su={student or data.purpose}"
            return f"esewa://pay?amt={amt:.2f}&ref={bill_no}&name={m_name}"

        elif provider.lower() == "khalti":
            if m_id or acc:
                return f"https://khalti.com/pay?merchant={m_id or acc}&amount={amt:.2f}&ref={bill_no}&student={student}"
            return f"khalti://pay?amount={amt:.2f}&ref={bill_no}"

        elif provider.lower() in ("fonepay", "phonepay", "bank", "bank transfer"):
            # Official Fonepay EMVCo Standee Payload (Scannable by all Nepali mobile banking apps)
            mid = "2222520021039149" if ("08000300919240000001" in acc or not m_id) else (m_id or acc)
            base = cls.build_fonepay_emvco(
                merchant_id=mid,
                merchant_name=m_name,
                city="PATHARI BRANC",
                terminal_id="2162508",
            )
            if amt > 0 or bill_no:
                return cls.build_dynamic_emvco(
                    base,
                    amount=amt,
                    bill_number=bill_no,
                    student_name=student,
                    purpose=data.purpose,
                )
            return base

        else:
            # Universal / Bank Transfer EMVCo Payload Representation
            bc_text = f"|BANK:{data.bank_code}" if data.bank_code else ""
            return (
                f"PAYMENT:{provider.upper()}{bc_text}|TO:{m_name}|ACC:{acc}|"
                f"AMT:{amt:.2f}|REF:{bill_no}|NAME:{student}"
            )

    @classmethod
    def build_reportlab_drawing(cls, data: PaymentQrData, size_mm: float = 35.0) -> Drawing:
        """Create a vector ReportLab Drawing flowable containing the QR code with high-contrast quiet zone."""
        from reportlab.graphics.shapes import Rect
        from reportlab.lib import colors

        payload = cls.build_payload(data)
        size_pt = size_mm * mm
        qr = QrCodeWidget(payload, barLevel="M", barBorder=4)
        qr.barWidth = size_pt
        qr.barHeight = size_pt
        qr.barBorder = 4
        qr.barLevel = "M"  # 15% error correction for optimal camera recognition

        drawing = Drawing(size_pt, size_pt)
        drawing.add(Rect(0, 0, size_pt, size_pt, fillColor=colors.white, strokeColor=None))
        drawing.add(qr)
        return drawing

    @classmethod
    def build_reportlab_flowable(cls, data: PaymentQrData, size_mm: float = 35.0):
        """Return a ReportLab flowable: custom merchant QR image if exists on disk and valid, otherwise vector QR Drawing."""
        size_pt = size_mm * mm
        if data.image_path:
            candidate = Path(data.image_path).expanduser().resolve()
            if candidate.is_file():
                try:
                    # Sanity-check that custom image is not an unreadable/invalid payload or raw json
                    try:
                        import zxingcpp
                        from PIL import Image as PILImage
                        with PILImage.open(candidate) as c_img:
                            scanned = zxingcpp.read_barcodes(c_img)
                            if scanned:
                                raw_txt = scanned[0].text.strip()
                                if raw_txt.startswith("{") and "accountNumber" in raw_txt:
                                    logger.warning(
                                        "Custom QR image '%s' contains raw JSON instead of standard EMVCo payload. Falling back to vector QR.",
                                        candidate,
                                    )
                                    return cls.build_reportlab_drawing(data, size_mm=size_mm)
                    except Exception:
                        pass

                    from reportlab.platypus import Image
                    return Image(str(candidate), width=size_pt, height=size_pt)
                except Exception as exc:
                    logger.warning("Failed loading custom QR image '%s': %s", candidate, exc)
        return cls.build_reportlab_drawing(data, size_mm=size_mm)

    @classmethod
    def build_escpos_bytes(cls, data: PaymentQrData, module_size: int = 5) -> bytes:
        """Generate binary ESC/POS 2D barcode commands for thermal receipt printers."""
        payload = cls.build_payload(data)
        data_bytes = payload.encode("utf-8", errors="replace")
        length = len(data_bytes) + 3
        len_l = length & 0xFF
        len_h = (length >> 8) & 0xFF
        size_byte = bytes([max(2, min(16, int(module_size)))])

        return (
            b"\x1b\x61\x01"
            + b"\x1d(k\x04\x001A2\x00"
            + b"\x1d(k\x03\x001C" + size_byte
            + b"\x1d(k\x03\x001E1"
            + b"\x1d(k" + bytes([len_l, len_h]) + b"1P0" + data_bytes
            + b"\x1d(k\x03\x001Q0"
            + b"\x1b\x61\x00"
        )

    @classmethod
    def build_escpos_raster(
        cls,
        payload_or_data: str | PaymentQrData,
        printer_chars: int = 42,
        module_size: int | None = None,
        border_modules: int = 4,
    ) -> bytes:
        """Generate universal ESC/POS raster bit image (GS v 0) with guaranteed quiet zone and centered alignment."""
        if isinstance(payload_or_data, PaymentQrData):
            payload = cls.build_payload(payload_or_data)
        else:
            payload = str(payload_or_data or "").strip()

        if not payload:
            return b""

        # 80mm printers (>= 40 chars/line): 576 dots printable width
        # 58mm printers (< 40 chars/line): 384 dots printable width
        if printer_chars >= 40:
            target_dots = 576
            default_mod_size = 5
        else:
            target_dots = 384
            default_mod_size = 4

        mod_size = module_size or default_mod_size

        qr = QrCodeWidget(payload, barLevel="M", barBorder=border_modules)
        qr.draw()
        modules = qr.qr.modules
        n = len(modules)

        total_modules = n + 2 * border_modules
        qr_dots = total_modules * mod_size

        line_dots = max(target_dots, ((qr_dots + 7) // 8) * 8)
        line_dots = ((line_dots + 7) // 8) * 8
        bytes_per_line = line_dots // 8

        left_margin_dots = max(0, (line_dots - qr_dots) // 2)
        total_height_dots = qr_dots

        raster_bytes = bytearray()

        for r_mod in range(-border_modules, n + border_modules):
            is_module_row = (0 <= r_mod < n)
            row_data = modules[r_mod] if is_module_row else None

            for _ in range(mod_size):
                row_bits = [0] * line_dots
                if is_module_row and row_data:
                    for c_mod in range(n):
                        if row_data[c_mod]:
                            start_dot = left_margin_dots + (c_mod + border_modules) * mod_size
                            for dx in range(mod_size):
                                if start_dot + dx < line_dots:
                                    row_bits[start_dot + dx] = 1

                for b_idx in range(bytes_per_line):
                    byte_val = 0
                    for bit in range(8):
                        dot_idx = b_idx * 8 + bit
                        if dot_idx < line_dots and row_bits[dot_idx]:
                            byte_val |= (1 << (7 - bit))
                    raster_bytes.append(byte_val)

        xL = bytes_per_line & 0xFF
        xH = (bytes_per_line >> 8) & 0xFF
        yL = total_height_dots & 0xFF
        yH = (total_height_dots >> 8) & 0xFF

        return (
            b"\x1b\x61\x01"
            + bytes([0x1D, 0x76, 0x30, 0x00, xL, xH, yL, yH])
            + bytes(raster_bytes)
            + b"\x1b\x61\x00"
            + b"\n"
        )

    @classmethod
    def from_settings(
        cls,
        settings_service: Any,
        amount: Decimal | float,
        bill_number: str,
        student_name: str = "",
        purpose: str = "Tuition Fee",
    ) -> PaymentQrData | None:
        """Construct PaymentQrData from application runtime settings if enabled."""
        if not settings_service:
            return None
        enabled = settings_service.get_bool("payment_qr_enabled", True)
        if not enabled:
            return None

        provider = settings_service.get("payment_qr_provider", "Fonepay") or "Fonepay"
        merchant_id = settings_service.get("payment_qr_merchant_id", "")
        merchant_name = settings_service.get("payment_qr_merchant_name", "") or settings_service.get("app_title", "Expert Learning Hub")
        account_number = settings_service.get("payment_qr_account_number", "")
        bank_code = settings_service.get("payment_qr_bank_code", "")
        account_type = ""
        instructions = settings_service.get(
            "payment_qr_instructions", "Scan with Fonepay / eSewa / Mobile Banking to Pay"
        )
        image_path = settings_service.get("payment_qr_image_path", "")
        qr_payload = settings_service.get("payment_qr_raw_payload", "")

        db = getattr(settings_service, "db", None) or getattr(settings_service, "store", None)
        if db:
            try:
                acc_row = db.query_one(
                    "SELECT * FROM accounts WHERE is_billing_default=1 AND status='Active' LIMIT 1"
                )
                if acc_row:
                    if acc_row["account_number"]:
                        account_number = str(acc_row["account_number"])
                    if "bank_code" in acc_row.keys() and acc_row["bank_code"]:
                        bank_code = str(acc_row["bank_code"])
                    if "account_type" in acc_row.keys() and acc_row["account_type"]:
                        account_type = str(acc_row["account_type"])
                    if "qr_payload" in acc_row.keys() and acc_row["qr_payload"]:
                        qr_payload = str(acc_row["qr_payload"]).strip()
                    if acc_row["account_name"] or acc_row["account_holder"]:
                        merchant_name = str(acc_row["account_holder"] or acc_row["account_name"])
                    if "phonepay" in str(acc_row["account_name"] or "").lower() or "fonepay" in str(acc_row["account_name"] or "").lower() or bank_code:
                        provider = "Fonepay"
            except Exception:
                pass

        return PaymentQrData(
            provider=provider,
            merchant_id=merchant_id,
            merchant_name=merchant_name,
            account_number=account_number,
            bank_code=bank_code,
            account_type=account_type,
            amount=amount,
            bill_number=bill_number,
            student_name=student_name,
            purpose=purpose,
            instructions=instructions,
            image_path=image_path,
            qr_payload=qr_payload,
        )
