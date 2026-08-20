from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from elh.models import CourseCertificate


class CertificatePdfRenderer:
    """Deterministic, UI-independent certificate PDF renderer."""

    PAGE_SIZE = landscape(A4)
    NAVY = colors.HexColor("#102A43")
    TEAL = colors.HexColor("#008F7A")
    SLATE = colors.HexColor("#526579")
    LIGHT = colors.HexColor("#E8F3F2")

    @staticmethod
    def _accent(value: str):
        clean = (value or "").strip()
        return colors.HexColor(clean) if re.fullmatch(r"#[0-9A-Fa-f]{6}", clean) else CertificatePdfRenderer.TEAL

    @staticmethod
    def _fit_size(text: str, font: str, maximum: float, minimum: float, width: float) -> float:
        size = maximum
        while size > minimum and stringWidth(text, font, size) > width:
            size -= 0.5
        return size

    @staticmethod
    def _photo(photo_data: bytes | None) -> bytes | None:
        if not photo_data:
            return None
        try:
            with Image.open(BytesIO(photo_data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image = ImageOps.fit(
                    image,
                    (720, 900),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.38),
                )
                result = BytesIO()
                image.save(result, "JPEG", quality=92, optimize=True)
                return result.getvalue()
        except (UnidentifiedImageError, OSError, ValueError):
            return None

    @classmethod
    def render(
        cls,
        certificate: CourseCertificate,
        photo_data: bytes | None,
        destination: Path,
        *,
        title: str = "CERTIFICATE OF COMPLETION",
        show_photo: bool = True,
        show_guardian: bool = False,
        show_date_of_birth: bool = False,
        accent_color: str = "#008F7A",
        background_path: Path | None = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        page_width, page_height = cls.PAGE_SIZE
        accent = cls._accent(accent_color)
        pdf = canvas.Canvas(
            str(destination),
            pagesize=cls.PAGE_SIZE,
            pageCompression=1,
            invariant=1,
        )
        pdf.setTitle(f"Certificate {certificate.certificate_number}")
        pdf.setAuthor(certificate.company_name)
        pdf.setSubject(f"Course completion certificate for {certificate.student_name}")
        pdf.setCreator("ELH Management System")
        pdf.setKeywords(
            f"certificate,{certificate.certificate_number},{certificate.student_name},{certificate.course_name}"
        )

        if background_path:
            if not background_path.is_file():
                raise FileNotFoundError(f"Certificate PDF background was not found: {background_path}")
            if background_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                raise ValueError("Certificate PDF background must be a PNG or JPEG image.")
            pdf.drawImage(
                ImageReader(str(background_path)),
                0,
                0,
                width=page_width,
                height=page_height,
                preserveAspectRatio=False,
                mask="auto",
            )
        else:
            pdf.setFillColor(colors.white)
            pdf.rect(0, 0, page_width, page_height, stroke=0, fill=1)
            pdf.setStrokeColor(cls.NAVY)
            pdf.setLineWidth(3.2)
            pdf.roundRect(13 * mm, 13 * mm, page_width - 26 * mm, page_height - 26 * mm, 3 * mm, stroke=1, fill=0)
            pdf.setStrokeColor(accent)
            pdf.setLineWidth(1.15)
            pdf.roundRect(17 * mm, 17 * mm, page_width - 34 * mm, page_height - 34 * mm, 2 * mm, stroke=1, fill=0)
            pdf.setFillColor(accent)
            pdf.rect(13 * mm, page_height - 23 * mm, 48 * mm, 10 * mm, stroke=0, fill=1)
            pdf.setFillColor(cls.NAVY)
            pdf.rect(page_width - 61 * mm, 13 * mm, 48 * mm, 10 * mm, stroke=0, fill=1)

        pdf.setFillColor(cls.NAVY)
        company_size = cls._fit_size(certificate.company_name, "Helvetica-Bold", 20, 13, 150 * mm)
        pdf.setFont("Helvetica-Bold", company_size)
        pdf.drawCentredString(page_width / 2, page_height - 43 * mm, certificate.company_name)

        clean_title = (title or "CERTIFICATE OF COMPLETION").strip().upper()
        title_size = cls._fit_size(clean_title, "Helvetica-Bold", 31, 20, 205 * mm)
        pdf.setFont("Helvetica-Bold", title_size)
        pdf.drawCentredString(page_width / 2, page_height - 62 * mm, clean_title)
        pdf.setStrokeColor(accent)
        pdf.setLineWidth(1.4)
        pdf.line(page_width / 2 - 38 * mm, page_height - 67 * mm, page_width / 2 + 38 * mm, page_height - 67 * mm)

        pdf.setFillColor(cls.SLATE)
        pdf.setFont("Helvetica", 9.5)
        pdf.drawCentredString(page_width / 2, page_height - 82 * mm, "THIS CERTIFICATE IS PROUDLY PRESENTED TO")

        student = certificate.student_name.upper()
        name_size = cls._fit_size(student, "Helvetica-Bold", 29, 17, 190 * mm)
        pdf.setFillColor(cls.NAVY)
        pdf.setFont("Helvetica-Bold", name_size)
        pdf.drawCentredString(page_width / 2, page_height - 103 * mm, student)

        details: list[str] = []
        if show_guardian and certificate.guardian_name:
            relationship = certificate.guardian_relationship.strip()
            details.append(f"{relationship} {certificate.guardian_name}".strip())
        if show_date_of_birth and certificate.date_of_birth:
            details.append(f"Date of Birth: {certificate.date_of_birth}")
        if details:
            pdf.setFillColor(cls.SLATE)
            pdf.setFont("Helvetica", 8.5)
            pdf.drawCentredString(page_width / 2, page_height - 111 * mm, "  |  ".join(details))

        pdf.setFillColor(cls.SLATE)
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(page_width / 2, page_height - 126 * mm, "has successfully completed the course")
        course_size = cls._fit_size(certificate.course_name, "Helvetica-Bold", 22, 14, 185 * mm)
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", course_size)
        pdf.drawCentredString(page_width / 2, page_height - 143 * mm, certificate.course_name)
        pdf.setFillColor(cls.SLATE)
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(page_width / 2, page_height - 155 * mm, f"conducted by {certificate.company_name}")

        box_width = 72 * mm
        box_height = 19 * mm
        box_x = (page_width - box_width) / 2
        box_y = 27 * mm
        pdf.setFillColor(cls.LIGHT)
        pdf.setStrokeColor(colors.HexColor("#C8DEDC"))
        pdf.setLineWidth(0.7)
        pdf.roundRect(box_x, box_y, box_width, box_height, 3 * mm, stroke=1, fill=1)
        pdf.setFillColor(cls.NAVY)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(page_width / 2, box_y + 11.2 * mm, "COURSE PERIOD")
        pdf.setFont("Helvetica", 8.5)
        pdf.drawCentredString(
            page_width / 2,
            box_y + 5.5 * mm,
            f"{certificate.course_start_date} to {certificate.course_end_date}  |  {certificate.duration_days} days",
        )

        normalized_photo = cls._photo(photo_data) if show_photo else None
        if normalized_photo:
            photo_width, photo_height = 22 * mm, 28 * mm
            photo_x = page_width - 46 * mm
            photo_y = page_height - 70 * mm
            pdf.setFillColor(colors.white)
            pdf.setStrokeColor(accent)
            pdf.setLineWidth(1.1)
            pdf.roundRect(photo_x - 1.2 * mm, photo_y - 1.2 * mm, photo_width + 2.4 * mm, photo_height + 2.4 * mm, 1.5 * mm, stroke=1, fill=1)
            pdf.drawImage(
                ImageReader(BytesIO(normalized_photo)),
                photo_x,
                photo_y,
                width=photo_width,
                height=photo_height,
                preserveAspectRatio=False,
                mask="auto",
            )

        signature_y = 31 * mm
        left_center = 69 * mm
        right_center = page_width - 69 * mm
        pdf.setStrokeColor(cls.NAVY)
        pdf.setLineWidth(0.8)
        pdf.line(left_center - 28 * mm, signature_y + 9 * mm, left_center + 28 * mm, signature_y + 9 * mm)
        pdf.line(right_center - 28 * mm, signature_y + 9 * mm, right_center + 28 * mm, signature_y + 9 * mm)
        for center, person, role in (
            (left_center, certificate.instructor_name, "Course Instructor"),
            (right_center, certificate.principal_name, "Director / Principal"),
        ):
            person_size = cls._fit_size(person, "Helvetica-Bold", 10, 7.5, 55 * mm)
            pdf.setFillColor(cls.NAVY)
            pdf.setFont("Helvetica-Bold", person_size)
            pdf.drawCentredString(center, signature_y + 3.5 * mm, person)
            pdf.setFillColor(cls.SLATE)
            pdf.setFont("Helvetica", 8)
            pdf.drawCentredString(center, signature_y - 1 * mm, role)

        pdf.setFillColor(cls.SLATE)
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(27 * mm, 19 * mm, f"Certificate No.: {certificate.certificate_number}")
        pdf.drawRightString(page_width - 27 * mm, 19 * mm, f"Certificate Date (BS): {certificate.certify_date}")
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawCentredString(page_width / 2, 19 * mm, "AUTHORIZED COURSE COMPLETION RECORD")

        pdf.showPage()
        pdf.save()

        data = destination.read_bytes()
        if len(data) < 1000 or not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise RuntimeError("The certificate PDF could not be verified after generation.")
