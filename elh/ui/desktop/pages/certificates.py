from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from elh.models import CertificateIssueRequest
from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import today_iso


class CertificatesPage(CrudPage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id: int | None = None
        self.enrollment_map: dict[str, int] = {}
        self.enrollment_rows: dict[int, object] = {}

        ttk.Label(self, text="Course Completion Certificates", style="Title.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            self,
            text="Issue a print-ready PDF for a completed enrollment; an editable DOCX is optional.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 3))

        form = self.create_form_dialog(
            "Certificate", padding=10, hint_text="Double-click a row to open the certificate"
        )
        form.pack(fill="x", pady=8)
        self.vars = {
            "enrollment": tk.StringVar(),
            "number": tk.StringVar(),
            "date": tk.StringVar(value=today_iso()),
            "instructor": tk.StringVar(),
            "principal": tk.StringVar(value=self._company_principal()),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.enrollment_combo = fb.combo(
            "Completed Enrollment *", self.vars["enrollment"], [], searchable=True, width=48
        )
        self.enrollment_combo.bind("<<ComboboxSelected>>", self._enrollment_selected, add="+")
        fb.entry("Certificate Number *", self.vars["number"])
        fb.entry("Certificate Date *", self.vars["date"])
        fb.entry("Remarks", self.vars["remarks"])
        self.enrollment_summary = ttk.Label(form, text="", style="FormValue.TLabel")
        self.enrollment_summary.grid(row=fb.row, column=0, columnspan=2, sticky="w", padx=5, pady=8)
        form.columnconfigure(1, weight=1)
        buttons = ttk.Frame(form, style="Form.TFrame")
        buttons.grid(row=0, column=2, rowspan=8, padx=15, sticky="n")
        ttk.Button(
            buttons,
            text="Issue Certificate",
            style="Accent.TButton",
            command=self.issue,
        ).pack(fill="x", pady=3)

        ttk.Button(self.page_toolbar, text="Open PDF", command=self.open_selected).pack(
            side="left", padx=4
        )
        ttk.Button(
            self.page_toolbar, text="Print PDF", command=self.print_selected
        ).pack(side="left", padx=4)
        ttk.Button(
            self.page_toolbar, text="Regenerate PDF", command=self.regenerate_selected
        ).pack(side="left", padx=4)
        ttk.Button(
            self.page_toolbar, text="Open DOCX", command=self.open_docx_selected
        ).pack(side="left", padx=4)
        ttk.Button(
            self.page_toolbar, text="Regenerate DOCX", command=self.regenerate_docx_selected
        ).pack(side="left", padx=4)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 55),
                ("number", "Certificate No.", 145),
                ("student", "Student", 190),
                ("course", "Course", 180),
                ("period", "Course Period", 190),
                ("days", "Days", 65),
                ("date", "Certificate Date", 115),
                ("instructor", "Instructor", 150),
                ("pdf", "PDF", 165),
                ("document", "Editable DOCX", 165),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.open_selected)

    def _enrollment_selected(self, _event=None):
        enrollment_id = self.enrollment_map.get(self.vars["enrollment"].get())
        row = self.enrollment_rows.get(enrollment_id) if enrollment_id else None
        if not row:
            self.enrollment_summary.configure(text="")
            return
        self.vars["instructor"].set(
            (row["course_instructor"] or "").strip()
            or self.app.app_config.certificate_default_instructor
        )
        self.vars["principal"].set(
            (row["company_principal"] or "").strip() or self._company_principal()
        )
        self.enrollment_summary.configure(
            text=(
                f"Student profile — Gender: {row['gender'] or 'Not set'}    "
                f"DOB: {row['date_of_birth'] or 'Not set'}    "
                f"Guardian: {row['guardian_relationship'] or ''} "
                f"{row['parent_name'] or 'Not set'}    "
                f"Course: {row['start_date']} to {row['end_date']}    "
                f"Instructor: {row['course_instructor'] or 'Not set'}    "
                f"Principal: {row['company_principal'] or 'Not set'}"
            )
        )

    def clear(self):
        self.selected_id = None
        self.vars["enrollment"].set("")
        self.vars["date"].set(today_iso())
        self.vars["remarks"].set("")
        self.vars["instructor"].set("")
        self.vars["principal"].set(self._company_principal())
        try:
            self.vars["number"].set(self.app.services.certificates.next_certificate_number())
        except Exception:
            self.vars["number"].set("")
        self.enrollment_summary.configure(text="")

    def _company_principal(self) -> str:
        row = self.db.query_one(
            "SELECT principal_name FROM company_profile WHERE id=1"
        )
        return (
            str(row["principal_name"] or "").strip() if row else ""
        ) or self.app.app_config.certificate_default_principal

    def issue(self):
        try:
            enrollment_id = self.enrollment_map.get(self.vars["enrollment"].get())
            if not enrollment_id:
                raise ValueError("Select a completed enrollment.")
            certificate = self.app.services.certificates.issue(
                CertificateIssueRequest(
                    enrollment_id=enrollment_id,
                    certificate_number=self.vars["number"].get(),
                    certify_date=self.vars["date"].get(),
                    instructor_name=self.vars["instructor"].get(),
                    principal_name=self.vars["principal"].get(),
                    remarks=self.vars["remarks"].get(),
                    created_by_user_id=self.app.session.user_id,
                )
            )
            self.app.auth_service.record_event(
                self.app.session,
                "certificate_issued",
                True,
                f"Issued {certificate.certificate_number} for enrollment {enrollment_id}",
            )
            self.hide_form_dialog()
            self.refresh()
            messagebox.showinfo(
                "Certificate Issued",
                f"Certificate {certificate.certificate_number} was created as PDF:\n"
                f"{certificate.pdf_path}\n\n"
                f"Editable DOCX: {certificate.document_path or 'Not generated'}",
                parent=self,
            )
            os.startfile(Path(certificate.pdf_path))
        except Exception as exc:
            self.show_error(exc)

    def on_select(self, _event=None):
        selected = self.tree.selection()
        self.selected_id = int(self.tree.item(selected[0], "values")[0]) if selected else None

    def selected_certificate(self):
        if not self.selected_id:
            raise ValueError("Select a certificate first.")
        certificate = self.app.services.certificates.get(self.selected_id)
        if not certificate:
            raise ValueError("Certificate record was not found.")
        return certificate

    def _pdf_for_selected(self, regenerate_missing: bool = True) -> Path:
        certificate = self.selected_certificate()
        path = Path(certificate.pdf_path) if certificate.pdf_path else Path()
        if not path.is_file():
            if not regenerate_missing:
                raise FileNotFoundError("The certificate PDF is missing.")
            path = self.app.services.certificates.regenerate(certificate.id)
        return path

    def _docx_for_selected(self, regenerate_missing: bool = True) -> Path:
        certificate = self.selected_certificate()
        path = Path(certificate.document_path) if certificate.document_path else Path()
        if not path.is_file():
            if not regenerate_missing:
                raise FileNotFoundError("The editable certificate DOCX is missing.")
            path = self.app.services.certificates.regenerate_docx(certificate.id)
        return path

    def open_selected(self, _event=None):
        try:
            os.startfile(self._pdf_for_selected())
        except Exception as exc:
            self.show_error(exc)

    def print_selected(self):
        try:
            os.startfile(self._pdf_for_selected(), "print")
        except Exception as exc:
            self.show_error(exc)

    def regenerate_selected(self):
        try:
            path = self.app.services.certificates.regenerate(self.selected_certificate().id)
            self.refresh()
            messagebox.showinfo("Regenerated", f"Certificate PDF recreated at:\n{path}", parent=self)
        except Exception as exc:
            self.show_error(exc)

    def open_docx_selected(self):
        try:
            os.startfile(self._docx_for_selected())
        except Exception as exc:
            self.show_error(exc)

    def regenerate_docx_selected(self):
        try:
            path = self.app.services.certificates.regenerate_docx(
                self.selected_certificate().id
            )
            self.refresh()
            messagebox.showinfo(
                "Regenerated", f"Editable certificate DOCX recreated at:\n{path}", parent=self
            )
        except Exception as exc:
            self.show_error(exc)

    def refresh(self):
        available = self.app.services.certificates.available_enrollments()
        self.enrollment_rows = {int(row["enrollment_id"]): row for row in available}
        self.enrollment_map = {
            f"{row['student_name']} - {row['course_name']} ({row['end_date']})": int(
                row["enrollment_id"]
            )
            for row in available
        }
        self.enrollment_combo.set_values(self.enrollment_map)
        self.clear_tree(self.tree)
        for row in self.app.services.certificates.list():
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["certificate_number"],
                    row["student_name_snapshot"],
                    row["course_name_snapshot"],
                    f"{row['course_start_date']} to {row['course_end_date']}",
                    row["duration_days"],
                    row["certify_date"],
                    row["instructor_name"],
                    Path(row["pdf_path"]).name if row["pdf_path"] else "Missing",
                    Path(row["document_path"]).name if row["document_path"] else "Missing",
                ),
            )
        if not self.form_dialog or self.form_dialog.state() == "withdrawn":
            self.clear()
