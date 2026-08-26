from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import nepali_datetime as nepali

from elh.ui.desktop.components import BasePage, FormBuilder
from elh.ui.desktop.helpers import open_or_print_pdf, today_iso, validate_date


class ReportsPage(BasePage):
    """A compact report chooser; table pages print their own current view."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="Reports & Printing", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Choose one report, then open its PDF or send it to the normal printer. "
                 "For searched, sorted, or filtered tables, use “Print current table” on that module.",
            style="Hint.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(2, 14))
        card = ttk.LabelFrame(self, text="Report Period (Nepali BS)", padding=12)
        card.pack(fill="x")
        self.start = tk.StringVar(value=today_iso())
        self.end = tk.StringVar(value=today_iso())
        form = FormBuilder(card)
        form.entry("Start Date *", self.start)
        form.entry("End Date *", self.end)

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, pady=16)
        finance = ttk.Frame(tabs, padding=18)
        academic = ttk.Frame(tabs, padding=18)
        attendance = ttk.Frame(tabs, padding=18)
        people = ttk.Frame(tabs, padding=18)
        tabs.add(finance, text="Finance & Payments")
        tabs.add(academic, text="Academic")
        tabs.add(attendance, text="Attendance")
        tabs.add(people, text="People & Staff")
        self._report_selector(finance, "Finance report", {
            "Paid Student Transactions": "paid", "Account Ledger": "ledger",
        }, "The selected date period is used for finance reports.")
        self._build_academic(academic)
        self._report_selector(attendance, "Attendance report", {
            "Attending Device Users Not Registered": "unregistered",
            "Students Punched but Not Enrolled": "punched_not_enrolled",
        }, "Find device users not linked to ELH, or registered students who have attendance but no active course.")
        self._report_selector(people, "People report", {"Staff Register": "staff"},
                              "A current staff register for administrative and payroll review.")

    def _report_selector(self, parent, label, choices, description):
        ttk.Label(parent, text=description, style="Hint.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(0, 12))
        card = ttk.LabelFrame(parent, text="Choose report", padding=12)
        card.pack(anchor="w", fill="x")
        value = tk.StringVar(value=next(iter(choices)))
        form = FormBuilder(card)
        form.combo(label, value, list(choices), searchable=len(choices) > 4, width=48)
        actions = ttk.Frame(card, style="Form.TFrame")
        actions.grid(row=0, column=2, padx=(14, 0), sticky="ns")
        ttk.Button(actions, text="Open PDF", style="Accent.TButton", command=lambda: self.run(choices[value.get()], False)).pack(fill="x", pady=(0, 6))
        ttk.Button(actions, text="Print", command=lambda: self.run(choices[value.get()], True)).pack(fill="x")

    def _build_academic(self, parent):
        ttk.Label(parent, text="Select a report. Student and enrollment registers can be limited by class, school, and status.", style="Hint.TLabel", wraplength=800, justify="left").pack(anchor="w", pady=(0, 12))
        card = ttk.LabelFrame(parent, text="Academic report", padding=12)
        card.pack(anchor="w", fill="x")
        self.academic_report = tk.StringVar(value="Student Register")
        self.report_class = tk.StringVar(value="All classes")
        self.report_school = tk.StringVar(value="All schools")
        self.report_status = tk.StringVar(value="All")
        classes = self.db.query("SELECT id,level_name FROM class_levels WHERE status='Active' ORDER BY level_name")
        schools = self.db.query("SELECT id,school_name FROM schools WHERE status='Active' ORDER BY school_name")
        self.report_class_map = {"All classes": None, **{str(row["level_name"]): int(row["id"]) for row in classes}}
        self.report_school_map = {"All schools": None, **{f"{row['school_name']} (ID: {row['id']})": int(row["id"]) for row in schools}}
        form = FormBuilder(card)
        form.combo("Report", self.academic_report, ["Student Register", "Enrollment Register", "Class & School Analysis", "Weekly Class Routine"], width=42)
        form.combo("Class / Level", self.report_class, self.report_class_map, searchable=True, width=42)
        form.combo("School", self.report_school, self.report_school_map, searchable=True, width=42)
        form.combo("Status", self.report_status, ["All", "Active", "Inactive"], width=42)
        actions = ttk.Frame(card, style="Form.TFrame")
        actions.grid(row=0, column=2, rowspan=4, padx=(14, 0), sticky="ns")
        ttk.Button(actions, text="Open PDF", style="Accent.TButton", command=lambda: self.run(self._academic_kind(), False)).pack(fill="x", pady=(0, 6))
        ttk.Button(actions, text="Print", command=lambda: self.run(self._academic_kind(), True)).pack(fill="x")

    def _academic_kind(self) -> str:
        return {
            "Student Register": "filtered_students", "Enrollment Register": "enrollments",
            "Class & School Analysis": "analysis", "Weekly Class Routine": "routine",
        }[self.academic_report.get()]

    def run(self, kind, print_now):
        try:
            start = validate_date(self.start.get(), "Start date")
            end = validate_date(self.end.get(), "End date")
            if end < start:
                raise ValueError("End date cannot be earlier than start date.")
            service = self.app.services.reports
            if kind in {"unregistered", "punched_not_enrolled"}:
                start_at = nepali.date(*map(int, start.split("/"))).to_datetime_date().isoformat() + " 00:00:00"
                end_at = nepali.date(*map(int, end.split("/"))).to_datetime_date().isoformat() + " 23:59:59"
                path = service.unregistered_attendance_pdf(start_at, end_at, start, end) if kind == "unregistered" else service.punched_not_enrolled_pdf(start_at, end_at, start, end)
            elif kind == "filtered_students":
                path = service.student_register_pdf(self.report_class_map.get(self.report_class.get()), self.report_school_map.get(self.report_school.get()), status=self.report_status.get())
            elif kind == "enrollments":
                path = service.enrollment_register_pdf(self.report_status.get())
            else:
                path = {
                    "paid": service.paid_transactions_pdf(start, end), "ledger": service.ledger_pdf(start, end),
                    "analysis": service.class_school_analysis_pdf(), "routine": service.routine_pdf(),
                    "staff": service.staff_register_pdf(),
                }[kind]
            if not open_or_print_pdf(path, print_now):
                messagebox.showinfo(
                    "Report Opened",
                    "Windows does not have a direct PDF print action. The report was opened; use its Print command.",
                    parent=self,
                )
        except Exception as exc:
            messagebox.showerror("Report Error", str(exc), parent=self)
