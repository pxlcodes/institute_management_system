from __future__ import annotations

import logging
import os
import re
import tempfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree
from PIL import Image, ImageOps, UnidentifiedImageError

from elh.config import AppConfig
from elh.core.settings import SettingsService
from elh.core.validation import parse_nepali_date, today_iso, validate_date
from elh.models import CertificateIssueRequest, CourseCertificate
from elh.repositories import CertificateRepository
from elh.services.certificate_pdf import CertificatePdfRenderer


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WORD_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PICTURE_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_SHAPE_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
VML_NS = "urn:schemas-microsoft-com:vml"
PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {
    "w": WORD_NS,
    "a": DRAWING_NS,
    "wp": WORD_DRAWING_NS,
    "pic": PICTURE_NS,
    "r": RELATIONSHIP_NS,
    "wps": WORD_SHAPE_NS,
    "v": VML_NS,
}
W_RPR = f"{{{WORD_NS}}}rPr"
W_SZ = f"{{{WORD_NS}}}sz"
W_SZCS = f"{{{WORD_NS}}}szCs"
W_VAL = f"{{{WORD_NS}}}val"
LOGGER = logging.getLogger(__name__)


class CertificateService:
    """Issue and reproduce course certificates without depending on Tkinter."""

    HONORIFICS = ("Mr.", "Ms.", "Mx.")
    RELATIONSHIPS = ("Son of Mr.", "Daughter of Mr.", "Child of")

    def __init__(self, repository: CertificateRepository, config: AppConfig, notifications=None):
        self.repository = repository
        self.config = config
        self.notifications = notifications
        self.settings = SettingsService(repository.db)

    def available_enrollments(self):
        return self.repository.completed_enrollments_without_certificate()

    def next_certificate_number(self) -> str:
        prefix = self.settings.get(
            "certificate_number_prefix", self.config.certificate_number_prefix
        ).strip().upper()
        if not prefix or not re.fullmatch(r"[A-Z0-9-]+", prefix):
            raise ValueError("Certificate number prefix may contain letters, numbers, and hyphens only.")
        year = int(today_iso().split("/", 1)[0])
        used = set()
        pattern = re.compile(rf"^{re.escape(prefix)}-{year}-(\d+)$")
        for value in self.repository.certificate_numbers(prefix, year):
            match = pattern.fullmatch(value)
            if match:
                used.add(int(match.group(1)))
        sequence = 1
        while sequence in used:
            sequence += 1
        return f"{prefix}-{year}-{sequence:03d}"

    def issue(self, request: CertificateIssueRequest) -> CourseCertificate:
        enrollment = self.repository.enrollment(request.enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment was not found.")
        if enrollment["status"] != "Completed":
            raise ValueError("Mark the enrollment Completed before issuing its certificate.")
        if not enrollment["end_date"]:
            raise ValueError("Set the enrollment end date before issuing its certificate.")
        if self.repository.by_enrollment(request.enrollment_id):
            raise ValueError("A certificate has already been issued for this enrollment.")

        number = request.certificate_number.strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]+", number):
            raise ValueError("Certificate number may contain letters, numbers, and hyphens only.")
        if self.repository.number_exists(number):
            raise ValueError("That certificate number is already in use.")
        gender = str(enrollment["gender"] or "").strip().title()
        honorific = {"Male": "Mr.", "Female": "Ms.", "Other": "Mx."}.get(
            gender, "Mx."
        )
        guardian_relationship = str(enrollment["guardian_relationship"] or "").strip()
        raw_date_of_birth = str(enrollment["date_of_birth"] or "").strip()
        date_of_birth = validate_date(
            raw_date_of_birth,
            "Date of birth",
            allow_blank=True,
        )
        certify_date = validate_date(request.certify_date, "Certificate date")
        start = validate_date(enrollment["start_date"], "Course start date")
        end = validate_date(enrollment["end_date"], "Course end date")
        if date_of_birth and parse_nepali_date(date_of_birth) >= parse_nepali_date(start):
            raise ValueError("Date of birth must be before the course start date.")
        if parse_nepali_date(end) < parse_nepali_date(start):
            raise ValueError("Course end date cannot be before its start date.")
        if parse_nepali_date(certify_date) < parse_nepali_date(end):
            raise ValueError("Certificate date cannot be before the course end date.")
        instructor_name = (
            request.instructor_name.strip()
            or str(enrollment["course_instructor"] or "").strip()
            or self.config.certificate_default_instructor.strip()
        )
        principal_name = (
            request.principal_name.strip()
            or str(enrollment["company_principal"] or "").strip()
            or self.config.certificate_default_principal.strip()
        )
        if not instructor_name:
            raise ValueError("Course instructor is required.")
        if not principal_name:
            raise ValueError("Director/Principal is required.")

        configured_months = int(enrollment["duration_months"] or 0)
        duration_days = configured_months * 30 if configured_months > 0 else (
            parse_nepali_date(end).to_datetime_date()
            - parse_nepali_date(start).to_datetime_date()
        ).days
        clean_request = CertificateIssueRequest(
            enrollment_id=request.enrollment_id,
            certificate_number=number,
            certify_date=certify_date,
            instructor_name=instructor_name,
            principal_name=principal_name,
            remarks=request.remarks.strip(),
            created_by_user_id=request.created_by_user_id,
        )
        certificate_id = self.repository.create(
            clean_request, enrollment, duration_days, honorific
        )
        pdf_path: Path | None = None
        try:
            pdf_path = self.generate_pdf(certificate_id)
            self.repository.update_pdf(
                certificate_id,
                str(pdf_path),
                sha256(pdf_path.read_bytes()).hexdigest(),
            )
        except Exception:
            if pdf_path:
                pdf_path.unlink(missing_ok=True)
            self.repository.delete_failed_issue(certificate_id)
            raise
        try:
            document_path = self.generate_docx(certificate_id)
            self.repository.update_document_path(certificate_id, str(document_path))
        except Exception:
            LOGGER.warning(
                "Certificate %s was issued as PDF, but its optional DOCX could not be generated.",
                number,
                exc_info=True,
            )
        certificate = self.repository.get(certificate_id)
        if self.notifications:
            self.notifications.notify(
                "certificate_issued",
                "course_certificate",
                certificate_id,
                enrollment["contact"] or "",
                {
                    "student_name": certificate.student_name,
                    "course_name": certificate.course_name,
                    "certificate_number": certificate.certificate_number,
                    "certificate_date": certificate.certify_date,
                },
            )
        return certificate

    def generate_pdf(self, certificate_id: int) -> Path:
        certificate = self.repository.get(certificate_id)
        if not certificate:
            raise ValueError("Certificate record was not found.")
        output_directory = self.config.certificate_output_directory
        output_directory.mkdir(parents=True, exist_ok=True)
        safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", certificate.certificate_number)
        destination = output_directory / f"Certificate_{safe_number}.pdf"
        with tempfile.NamedTemporaryFile(
            prefix=f".{safe_number}-", suffix=".pdf", dir=output_directory, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            student_photo = self.repository.student_photo(certificate.enrollment_id)
            CertificatePdfRenderer.render(
                certificate,
                student_photo["photo_data"] if student_photo else None,
                temporary_path,
                title=self.settings.get(
                    "certificate_pdf_title", "CERTIFICATE OF COMPLETION"
                ),
                show_photo=self.settings.get_bool("certificate_pdf_show_photo", True),
                show_guardian=self.settings.get_bool(
                    "certificate_pdf_show_guardian", False
                ),
                show_date_of_birth=self.settings.get_bool(
                    "certificate_pdf_show_date_of_birth", False
                ),
                accent_color=self.settings.get(
                    "certificate_pdf_accent_color", "#008F7A"
                ),
                background_path=self.config.certificate_pdf_background_path,
            )
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return destination

    def generate_docx(self, certificate_id: int) -> Path:
        certificate = self.repository.get(certificate_id)
        if not certificate:
            raise ValueError("Certificate record was not found.")
        template = self.config.certificate_template_path
        if not template.is_file():
            raise FileNotFoundError(
                f"Certificate template was not found: {template}. "
                "Set ELH_CERTIFICATE_TEMPLATE_PATH or restore the bundled template."
            )
        output_directory = self.config.certificate_output_directory
        output_directory.mkdir(parents=True, exist_ok=True)
        safe_number = re.sub(r"[^A-Za-z0-9._-]+", "-", certificate.certificate_number)
        destination = output_directory / f"Certificate_{safe_number}.docx"
        with tempfile.NamedTemporaryFile(
            prefix=f".{safe_number}-", suffix=".docx", dir=output_directory, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            student_photo = self.repository.student_photo(certificate.enrollment_id)
            self._render_template(
                template,
                temporary_path,
                certificate,
                student_photo["photo_data"] if student_photo else None,
            )
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return destination

    def list(self):
        return self.repository.list()

    def generate(self, certificate_id: int) -> Path:
        """Compatibility alias: direct PDF is the primary certificate output."""
        return self.generate_pdf(certificate_id)

    def regenerate(self, certificate_id: int) -> Path:
        path = self.generate_pdf(certificate_id)
        self.repository.update_pdf(
            certificate_id,
            str(path),
            sha256(path.read_bytes()).hexdigest(),
        )
        return path

    def regenerate_docx(self, certificate_id: int) -> Path:
        path = self.generate_docx(certificate_id)
        self.repository.update_document_path(certificate_id, str(path))
        return path

    def get(self, certificate_id: int) -> CourseCertificate | None:
        return self.repository.get(certificate_id)

    @staticmethod
    def _paragraph_text(paragraph) -> str:
        return "".join(node.text or "" for node in paragraph.xpath(".//w:t", namespaces=NS))

    @classmethod
    def _set_existing_text(cls, paragraph, values: list[str]) -> None:
        nodes = paragraph.xpath(".//w:t", namespaces=NS)
        if len(nodes) < len(values):
            raise ValueError("Certificate template text slot has changed unexpectedly.")
        for index, node in enumerate(nodes):
            node.text = values[index] if index < len(values) else ""
            if node.text and (node.text.startswith(" ") or node.text.endswith(" ")):
                node.set(f"{{{XML_NS}}}space", "preserve")

    @staticmethod
    def _sync_text_space(node) -> None:
        space_attribute = f"{{{XML_NS}}}space"
        if node.text and (node.text.startswith(" ") or node.text.endswith(" ")):
            node.set(space_attribute, "preserve")
        elif space_attribute in node.attrib:
            del node.attrib[space_attribute]

    @classmethod
    def _replace_placeholders(cls, paragraph, replacements: dict[str, str]) -> None:
        """Fill named fields even when Word has split a token across runs."""
        for placeholder, replacement in replacements.items():
            while True:
                nodes = paragraph.xpath(".//w:t", namespaces=NS)
                pieces = [node.text or "" for node in nodes]
                combined = "".join(pieces)
                start = combined.find(placeholder)
                if start < 0:
                    break
                end = start + len(placeholder)
                cursor = 0
                start_index = end_index = -1
                start_offset = end_offset = 0
                for index, piece in enumerate(pieces):
                    next_cursor = cursor + len(piece)
                    if start_index < 0 and start < next_cursor:
                        start_index = index
                        start_offset = start - cursor
                    if end_index < 0 and end <= next_cursor:
                        end_index = index
                        end_offset = end - cursor
                        break
                    cursor = next_cursor
                if start_index < 0 or end_index < 0:
                    raise ValueError(f"Certificate field {placeholder} could not be replaced.")
                prefix = pieces[start_index][:start_offset]
                suffix = pieces[end_index][end_offset:]
                nodes[start_index].text = prefix + replacement
                if end_index == start_index:
                    nodes[start_index].text += suffix
                else:
                    for index in range(start_index + 1, end_index):
                        nodes[index].text = ""
                    nodes[end_index].text = suffix
                for index in range(start_index, end_index + 1):
                    cls._sync_text_space(nodes[index])

    @classmethod
    def _set_visible_run_sizes(cls, paragraph, half_points: int | None) -> None:
        if not half_points:
            return
        for node in paragraph.xpath(".//w:t", namespaces=NS):
            if not (node.text or ""):
                continue
            run = node.getparent()
            if run is not None and run.tag == f"{{{WORD_NS}}}r":
                cls._set_run_size(run, half_points)

    @classmethod
    def _set_indexed_text(
        cls, paragraph, replacements: dict[int, str], size: int | None = None
    ) -> None:
        """Replace text without rebuilding Word drawing or fallback runs.

        The supplied certificate uses paired DrawingML/VML text boxes. Keeping
        every original run in place is important because Word uses that exact
        structure when choosing the compatible representation.
        """
        nodes = paragraph.xpath(".//w:t", namespaces=NS)
        if not nodes or max(replacements, default=-1) >= len(nodes):
            raise ValueError("Certificate template text slot has changed unexpectedly.")
        for index, node in enumerate(nodes):
            node.text = replacements.get(index, "")
            if node.text and (node.text.startswith(" ") or node.text.endswith(" ")):
                node.set(f"{{{XML_NS}}}space", "preserve")
            elif f"{{{XML_NS}}}space" in node.attrib:
                del node.attrib[f"{{{XML_NS}}}space"]
            if size and node.text:
                run = node.getparent()
                if run is not None and run.tag == f"{{{WORD_NS}}}r":
                    cls._set_run_size(run, size)

    @staticmethod
    def _set_run_size(run, half_points: int) -> None:
        properties = run.find(W_RPR)
        if properties is None:
            properties = etree.Element(W_RPR)
            run.insert(0, properties)
        for tag in (W_SZ, W_SZCS):
            size = properties.find(tag)
            if size is None:
                size = etree.SubElement(properties, tag)
            size.set(W_VAL, str(half_points))

    @staticmethod
    def _prepare_student_photo(photo_data: bytes | None) -> bytes | None:
        """Normalize a stored student image for predictable Word rendering."""
        if not photo_data:
            return None
        try:
            with Image.open(BytesIO(photo_data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image = ImageOps.fit(
                    image,
                    (600, 674),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.38),
                )
                output = BytesIO()
                image.save(output, format="JPEG", quality=92, optimize=True)
                return output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError):
            LOGGER.warning("Skipping an unreadable student photo while generating a certificate.")
            return None

    @staticmethod
    def _next_relationship_id(relationships) -> str:
        used = {
            int(match.group(1))
            for node in relationships
            if (match := re.fullmatch(r"rId(\d+)", node.get("Id", "")))
        }
        sequence = 1
        while sequence in used:
            sequence += 1
        return f"rId{sequence}"

    @classmethod
    def _photo_drawing(
        cls,
        relationship_id: str,
        drawing_id: int,
        student_name: str,
        width: int,
        height: int,
    ):
        run = etree.Element(f"{{{WORD_NS}}}r")
        properties = etree.SubElement(run, f"{{{WORD_NS}}}rPr")
        etree.SubElement(properties, f"{{{WORD_NS}}}noProof")
        drawing = etree.SubElement(run, f"{{{WORD_NS}}}drawing")
        inline = etree.SubElement(
            drawing,
            f"{{{WORD_DRAWING_NS}}}inline",
            distT="0",
            distB="0",
            distL="0",
            distR="0",
        )
        etree.SubElement(
            inline, f"{{{WORD_DRAWING_NS}}}extent", cx=str(width), cy=str(height)
        )
        etree.SubElement(
            inline,
            f"{{{WORD_DRAWING_NS}}}effectExtent",
            l="0",
            t="0",
            r="0",
            b="0",
        )
        etree.SubElement(
            inline,
            f"{{{WORD_DRAWING_NS}}}docPr",
            id=str(drawing_id),
            name=f"Student photo {drawing_id}",
            descr=f"Student photo of {student_name}",
        )
        frame_properties = etree.SubElement(
            inline, f"{{{WORD_DRAWING_NS}}}cNvGraphicFramePr"
        )
        etree.SubElement(
            frame_properties,
            f"{{{DRAWING_NS}}}graphicFrameLocks",
            noChangeAspect="1",
        )
        graphic = etree.SubElement(inline, f"{{{DRAWING_NS}}}graphic")
        graphic_data = etree.SubElement(
            graphic,
            f"{{{DRAWING_NS}}}graphicData",
            uri="http://schemas.openxmlformats.org/drawingml/2006/picture",
        )
        picture = etree.SubElement(graphic_data, f"{{{PICTURE_NS}}}pic")
        non_visual = etree.SubElement(picture, f"{{{PICTURE_NS}}}nvPicPr")
        etree.SubElement(
            non_visual,
            f"{{{PICTURE_NS}}}cNvPr",
            id=str(drawing_id),
            name=f"Student photo {drawing_id}",
            descr=f"Student photo of {student_name}",
        )
        etree.SubElement(non_visual, f"{{{PICTURE_NS}}}cNvPicPr")
        fill = etree.SubElement(picture, f"{{{PICTURE_NS}}}blipFill")
        blip = etree.SubElement(fill, f"{{{DRAWING_NS}}}blip")
        blip.set(f"{{{RELATIONSHIP_NS}}}embed", relationship_id)
        stretch = etree.SubElement(fill, f"{{{DRAWING_NS}}}stretch")
        etree.SubElement(stretch, f"{{{DRAWING_NS}}}fillRect")
        shape = etree.SubElement(picture, f"{{{PICTURE_NS}}}spPr")
        transform = etree.SubElement(shape, f"{{{DRAWING_NS}}}xfrm")
        etree.SubElement(transform, f"{{{DRAWING_NS}}}off", x="0", y="0")
        etree.SubElement(
            transform, f"{{{DRAWING_NS}}}ext", cx=str(width), cy=str(height)
        )
        geometry = etree.SubElement(
            shape, f"{{{DRAWING_NS}}}prstGeom", prst="rect"
        )
        etree.SubElement(geometry, f"{{{DRAWING_NS}}}avLst")
        return run

    @classmethod
    def _insert_student_photo(
        cls, root, relationship_id: str, student_name: str
    ) -> int:
        targets = []
        for paragraph in root.xpath(".//w:p", namespaces=NS):
            text = cls._paragraph_text(paragraph).strip()
            inside_photo_frame = bool(
                paragraph.xpath("ancestor::w:txbxContent", namespaces=NS)
            )
            if text == "{{STUDENT_PHOTO}}" or (text == "Photo" and inside_photo_frame):
                targets.append(paragraph)
        if not targets:
            return 0

        existing_ids = [
            int(node.get("id"))
            for node in root.xpath(".//wp:docPr[@id]", namespaces=NS)
            if str(node.get("id", "")).isdigit()
        ]
        drawing_id = max(existing_ids, default=0) + 1
        replaced_text_boxes = set()
        for paragraph in targets:
            text_boxes = paragraph.xpath("ancestor::w:txbxContent[1]", namespaces=NS)
            text_box = text_boxes[0] if text_boxes else None
            if text_box is not None:
                identity = id(text_box)
                if identity in replaced_text_boxes:
                    continue
                replaced_text_boxes.add(identity)
                shape_extents = text_box.xpath(
                    "ancestor::wps:wsp[1]/wps:spPr/a:xfrm/a:ext[1]", namespaces=NS
                )
                width = int(shape_extents[0].get("cx")) if shape_extents else 707366
                height = int(shape_extents[0].get("cy")) if shape_extents else 793630
                for child in list(text_box):
                    text_box.remove(child)
                paragraph = etree.SubElement(text_box, f"{{{WORD_NS}}}p")
                body_properties = text_box.xpath(
                    "ancestor::wps:wsp[1]/wps:bodyPr[1]", namespaces=NS
                )
                if body_properties:
                    for attribute in ("lIns", "tIns", "rIns", "bIns"):
                        body_properties[0].set(attribute, "0")
                    body_properties[0].set("anchor", "ctr")
                    body_properties[0].set("anchorCtr", "1")
                vml_textboxes = text_box.xpath("ancestor::v:textbox[1]", namespaces=NS)
                if vml_textboxes:
                    vml_textboxes[0].set("inset", "0,0,0,0")
            else:
                width, height = 707366, 793630
                properties = paragraph.find(f"{{{WORD_NS}}}pPr")
                for child in list(paragraph):
                    if child is not properties:
                        paragraph.remove(child)

            paragraph_properties = paragraph.find(f"{{{WORD_NS}}}pPr")
            if paragraph_properties is None:
                paragraph_properties = etree.Element(f"{{{WORD_NS}}}pPr")
                paragraph.insert(0, paragraph_properties)
            justification = paragraph_properties.find(f"{{{WORD_NS}}}jc")
            if justification is None:
                justification = etree.SubElement(
                    paragraph_properties, f"{{{WORD_NS}}}jc"
                )
            justification.set(W_VAL, "center")
            spacing = paragraph_properties.find(f"{{{WORD_NS}}}spacing")
            if spacing is None:
                spacing = etree.SubElement(
                    paragraph_properties, f"{{{WORD_NS}}}spacing"
                )
            spacing.set(f"{{{WORD_NS}}}before", "0")
            spacing.set(f"{{{WORD_NS}}}after", "0")
            paragraph.append(
                cls._photo_drawing(
                    relationship_id,
                    drawing_id,
                    student_name,
                    width,
                    height,
                )
            )
            drawing_id += 1
        return len(replaced_text_boxes) or len(targets)

    @classmethod
    def _render_template(
        cls,
        source: Path,
        destination: Path,
        certificate: CourseCertificate,
        student_photo: bytes | None = None,
    ) -> None:
        with ZipFile(source, "r") as package:
            document_xml = package.read("word/document.xml")
            root = etree.fromstring(document_xml)
            photo_data = cls._prepare_student_photo(student_photo)
            photo_relationships = None
            photo_content_types = None
            photo_relationship_id = ""
            photo_path = f"word/media/student-photo-{certificate.id}.JPG"
            photo_inserted = False
            if photo_data:
                photo_relationships = etree.fromstring(
                    package.read("word/_rels/document.xml.rels")
                )
                photo_relationship_id = cls._next_relationship_id(photo_relationships)
                photo_inserted = bool(
                    cls._insert_student_photo(
                        root, photo_relationship_id, certificate.student_name
                    )
                )
                if photo_inserted:
                    etree.SubElement(
                        photo_relationships,
                        f"{{{PACKAGE_RELATIONSHIP_NS}}}Relationship",
                        Id=photo_relationship_id,
                        Type=(
                            "http://schemas.openxmlformats.org/officeDocument/2006/"
                            "relationships/image"
                        ),
                        Target=f"media/student-photo-{certificate.id}.JPG",
                    )
                    photo_content_types = etree.fromstring(
                        package.read("[Content_Types].xml")
                    )
                    jpeg_defaults = [
                        node
                        for node in photo_content_types
                        if node.tag == f"{{{CONTENT_TYPES_NS}}}Default"
                        and node.get("Extension", "").lower() == "jpg"
                    ]
                    if not jpeg_defaults:
                        etree.SubElement(
                            photo_content_types,
                            f"{{{CONTENT_TYPES_NS}}}Default",
                            Extension="JPG",
                            ContentType="image/jpeg",
                        )
            # DrawingML/VML compatibility shapes can place whole text boxes inside an
            # outer paragraph. Process only leaf paragraphs so a parent pass cannot
            # consume fields that must also be filled in Word's fallback representation.
            paragraphs = root.xpath(".//w:p[not(.//w:p)]", namespaces=NS)
            object_pronoun, possessive = {
                "Mr.": ("him", "his"),
                "Ms.": ("her", "her"),
                "Mx.": ("them", "their"),
            }[certificate.honorific]
            student = certificate.student_name.upper()
            guardian = certificate.guardian_name.upper()
            body_text_length = sum(
                len(value)
                for value in (
                    student,
                    guardian,
                    certificate.course_name,
                    certificate.company_name,
                )
            )
            body_size = 28 if body_text_length > 105 else None
            placeholder_values = {
                "{{CERTIFICATE_NUMBER}}": certificate.certificate_number,
                "{{CERT_NO}}": certificate.certificate_number,
                "{{HONORIFIC}}": certificate.honorific,
                "{{TITLE}}": certificate.honorific,
                "{{STUDENT_NAME}}": student,
                "{{STUDENT}}": student,
                "{{GUARDIAN_RELATIONSHIP}}": certificate.guardian_relationship,
                "{{RELATION}}": certificate.guardian_relationship,
                "{{GUARDIAN_NAME}}": guardian,
                "{{GUARDIAN}}": guardian,
                "{{DATE_OF_BIRTH}}": certificate.date_of_birth,
                "{{DOB}}": certificate.date_of_birth,
                "{{COURSE_NAME}}": certificate.course_name,
                "{{COURSE}}": certificate.course_name,
                "{{COMPANY_NAME}}": certificate.company_name,
                "{{COMPANY}}": certificate.company_name,
                "{{OBJECT_PRONOUN}}": object_pronoun,
                "{{OBJECT}}": object_pronoun,
                "{{POSSESSIVE_PRONOUN}}": possessive,
                "{{POSSESSIVE}}": possessive,
                "{{COURSE_START_DATE}}": certificate.course_start_date,
                "{{START_DATE}}": certificate.course_start_date,
                "{{COURSE_END_DATE}}": certificate.course_end_date,
                "{{END_DATE}}": certificate.course_end_date,
                "{{DURATION_DAYS}}": str(certificate.duration_days),
                "{{DAYS}}": str(certificate.duration_days),
                "{{CERTIFICATE_DATE}}": certificate.certify_date,
                "{{CERT_DATE}}": certificate.certify_date,
                "{{INSTRUCTOR_NAME}}": certificate.instructor_name,
                "{{INSTRUCTOR}}": certificate.instructor_name,
                "{{PRINCIPAL_NAME}}": certificate.principal_name,
                "{{PRINCIPAL}}": certificate.principal_name,
            }

            for paragraph in paragraphs:
                text = cls._paragraph_text(paragraph)
                if "{{" in text:
                    cls._replace_placeholders(paragraph, placeholder_values)
                    if text.startswith("This is to certify that ") or text.startswith(
                        "We congratulate "
                    ):
                        cls._set_visible_run_sizes(paragraph, body_size)
                    if (
                        text.startswith("{{HONORIFIC}}")
                        or text.startswith("{{TITLE}}")
                    ) and ("{{STUDENT_NAME}}" in text or "{{STUDENT}}" in text):
                        for node in paragraph.xpath(".//w:t", namespaces=NS):
                            if (node.text or "") == student and len(student) > 28:
                                run = node.getparent()
                                if run is not None and run.tag == f"{{{WORD_NS}}}r":
                                    cls._set_run_size(
                                        run, 34 if len(student) <= 38 else 30
                                    )
                    continue
                if text == "CERTIFICATEE":
                    cls._set_existing_text(paragraph, ["CERTIFICATE"])
                elif text.startswith("Certificate No.:"):
                    cls._set_existing_text(
                        paragraph, ["Certificate No.:", f" {certificate.certificate_number}"]
                    )
                elif text.startswith("Mr./Ms."):
                    cls._set_existing_text(paragraph, [f"{certificate.honorific} ", student])
                    name_runs = paragraph.xpath("./w:r", namespaces=NS)
                    if name_runs and len(student) > 28:
                        cls._set_run_size(name_runs[-1], 34 if len(student) <= 38 else 30)
                elif text.startswith("This is to certify that "):
                    cls._set_indexed_text(
                        paragraph,
                        {
                            0: "This is to certify that ",
                            1: f"{certificate.honorific} ",
                            2: student,
                            3: f", {certificate.guardian_relationship} ",
                            4: guardian,
                            5: ", Date of Birth ",
                            6: certificate.date_of_birth,
                            12: ", has successfully completed the ",
                            13: certificate.course_name,
                            15: " conducted by ",
                            16: certificate.company_name,
                            17: ". ",
                            19: (
                                "The recipient has successfully fulfilled all the training "
                                "requirements and demonstrated satisfactory performance throughout the course."
                            ),
                        },
                        size=body_size,
                    )
                elif text.startswith("We congratulate "):
                    cls._set_indexed_text(
                        paragraph,
                        {
                            0: "We congratulate ",
                            1: f"{certificate.honorific} ",
                            2: student,
                            4: (
                                f" on this accomplishment and wish {object_pronoun} continued success in "
                                f"{possessive} future academic, professional, and personal endeavors."
                            ),
                        },
                        size=body_size,
                    )
                elif text.startswith("Course Duration:"):
                    cls._set_existing_text(
                        paragraph,
                        [
                            "Course Duration:",
                            f" {certificate.course_start_date} To {certificate.course_end_date} "
                            f"({certificate.duration_days} Days)",
                        ],
                    )
                elif text.startswith("Certify Date:"):
                    cls._set_existing_text(
                        paragraph, ["Certificate Date: ", certificate.certify_date]
                    )
                elif text == "Adarsha Nepal":
                    cls._set_existing_text(paragraph, [certificate.instructor_name])
                elif text == "Bhim Raj Adhikari":
                    cls._set_existing_text(paragraph, [certificate.principal_name])

            updated = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone="yes"
            )
            with ZipFile(destination, "w", compression=ZIP_DEFLATED) as output:
                for item in package.infolist():
                    if photo_inserted and item.filename == photo_path:
                        continue
                    if photo_inserted and item.filename == "[Content_Types].xml":
                        output.writestr(
                            item,
                            etree.tostring(
                                photo_content_types,
                                xml_declaration=True,
                                encoding="UTF-8",
                                standalone="yes",
                            ),
                        )
                        continue
                    if photo_inserted and item.filename == "word/_rels/document.xml.rels":
                        output.writestr(
                            item,
                            etree.tostring(
                                photo_relationships,
                                xml_declaration=True,
                                encoding="UTF-8",
                                standalone="yes",
                            ),
                        )
                        continue
                    output.writestr(
                        item,
                        updated if item.filename == "word/document.xml" else package.read(item.filename),
                    )
                if photo_inserted:
                    output.writestr(photo_path, photo_data)
