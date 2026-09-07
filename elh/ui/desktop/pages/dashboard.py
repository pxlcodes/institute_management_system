from __future__ import annotations

import csv
import logging
import sqlite3
import tkinter as tk
import time
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Iterable, Optional

from elh.models import Student
from elh.ui.desktop.helpers import money, normalize_phone, parse_amount, today_iso, validate_date
from elh.ui.desktop.components import BasePage, CrudPage, FormBuilder, ScrollableFrame

# Dashboard
# ---------------------------------------------------------------------------

class DashboardPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.cards = {}
        self.attendance_alerts_by_student = {}
        self.absent_students_by_student = {}
        self.payment_alerts_by_bill = {}
        self.show_suppressed_alerts = False
        self.show_suppressed_payment_alerts = False
        self._attendance_cache = None
        self._attendance_after_id = None
        self._attendance_generation = 0
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(8, 4))
        labels = [
            ("students", "Total Students"),
            ("teachers", "Total Staff"),
            ("enrollments", "Active Enrollments"),
            ("student_present", "Students Present Today"),
            ("attendance_alerts", "Attendance Alerts"),
            ("student_due", "Student Outstanding"),
            ("today_income", "Today's Income"),
            ("today_expense", "Today's Expense"),
            ("cash_total", "Total Account Balance"),
            ("salary_total", "Total Salary Paid"),
        ]
        for idx, (key, title) in enumerate(labels):
            card = ttk.Frame(grid, style="DashboardCard.TFrame", padding=(16, 13))
            card.grid(row=idx // 5, column=idx % 5, padx=6, pady=6, sticky="nsew")
            ttk.Label(card,text=title,style="DashboardCardTitle.TLabel").pack(anchor="w")
            value = ttk.Label(card, text="0", style="DashboardCardValue.TLabel")
            value.pack(anchor="w",pady=(7,0))
            self.cards[key] = value

        for i in range(5):
            grid.columnconfigure(i, weight=1)

        dashboard_tabs = ttk.Notebook(self)
        dashboard_tabs.pack(fill="both", expand=True, pady=(12, 0))
        attendance_tab = ttk.Frame(dashboard_tabs, padding=4)
        payment_tab = ttk.Frame(dashboard_tabs, padding=4)
        present_tab = ttk.Frame(dashboard_tabs, padding=4)
        absent_tab = ttk.Frame(dashboard_tabs, padding=4)
        not_enrolled_tab = ttk.Frame(dashboard_tabs, padding=4)
        accounts_tab = ttk.Frame(dashboard_tabs, padding=4)
        dashboard_tabs.add(attendance_tab, text="Attendance & Follow-up")
        dashboard_tabs.add(payment_tab, text="Payment Alerts & Follow-up")
        dashboard_tabs.add(present_tab, text="Students Present Today")
        dashboard_tabs.add(absent_tab, text="Students Absent Today")
        dashboard_tabs.add(not_enrolled_tab, text="Punched, Not Enrolled")
        dashboard_tabs.add(accounts_tab, text="Account Balances")

        ttk.Label(attendance_tab, text="Attendance Follow-up Alerts", style="SubTitle.TLabel").pack(anchor="w", pady=(8, 7), padx=4)
        alert_area = ttk.Frame(attendance_tab); alert_area.pack(fill="both", expand=True)
        self.alert_tree = CrudPage.make_tree(self, alert_area, [
            ("student", "Student", 220), ("class", "Class", 90), ("last", "Last Attendance", 155),
            ("consecutive", "No-Punch Days", 110), ("monthly", "Missing This Month", 130), ("review", "Review Status", 130), ("reason", "Review Reason", 300),
        ])
        self.alert_tree.print_title = "ATTENDANCE FOLLOW-UP ALERTS"
        self.alert_tree.configure(height=8)
        self.alert_tree.bind("<Double-1>", self.review_selected_alert)
        alert_actions = ttk.Frame(attendance_tab, style="Toolbar.TFrame", padding=(8, 4)); alert_actions.pack(fill="x")
        ttk.Button(alert_actions, text="Review Selected Alert", style="Accent.TButton", command=self.review_selected_alert).pack(side="left")
        ttk.Button(alert_actions, text="Suppress Follow-up...", command=self.suppress_selected_alert).pack(side="left", padx=(6, 0))
        self.suppressed_toggle = ttk.Button(alert_actions, text="Show Suppressed", command=self.toggle_suppressed_alerts)
        self.suppressed_toggle.pack(side="left", padx=(6, 0))
        ttk.Label(alert_actions, text="Suppress keeps an audit record; a resume date brings it back automatically.", style="Hint.TLabel").pack(side="left", padx=10)

        ttk.Label(payment_tab, text="Overdue Payment Alerts & Follow-up", style="SubTitle.TLabel").pack(anchor="w", pady=(8, 7), padx=4)
        payment_area = ttk.Frame(payment_tab); payment_area.pack(fill="both", expand=True)
        self.payment_tree = CrudPage.make_tree(self, payment_area, [
            ("student", "Student", 200), ("class", "Class", 80), ("bill", "Bill #", 130),
            ("course", "Course", 150), ("due", "Due Date", 95), ("overdue", "Overdue", 80),
            ("balance", "Balance Due", 100), ("review", "Follow-up Status", 130),
            ("follow_up", "Follow-up Date", 105), ("note", "Notes", 220),
        ])
        self.payment_tree.print_title = "OVERDUE PAYMENT ALERTS"
        self.payment_tree.configure(height=8)
        self.payment_tree.bind("<Double-1>", self.review_selected_payment_alert)
        payment_actions = ttk.Frame(payment_tab, style="Toolbar.TFrame", padding=(8, 4)); payment_actions.pack(fill="x")
        ttk.Button(payment_actions, text="Review / Follow-up Selected...", style="Accent.TButton", command=self.review_selected_payment_alert).pack(side="left")
        ttk.Button(payment_actions, text="Suppress Follow-up...", command=self.suppress_selected_payment_alert).pack(side="left", padx=(6, 0))
        self.suppressed_payment_toggle = ttk.Button(payment_actions, text="Show Suppressed", command=self.toggle_suppressed_payment_alerts)
        self.suppressed_payment_toggle.pack(side="left", padx=(6, 0))
        ttk.Label(payment_actions, text="Suppress hides the alert until the resume follow-up date.", style="Hint.TLabel").pack(side="left", padx=10)

        ttk.Label(present_tab, text="Students Present Today", style="SubTitle.TLabel").pack(
            anchor="w", pady=(8, 7), padx=4
        )
        present_area = ttk.Frame(present_tab)
        present_area.pack(fill="x")
        self.present_tree = CrudPage.make_tree(
            self,
            present_area,
            [
                ("name", "Student", 240),
                ("class", "Class", 100),
                ("punches", "Punches", 90),
                ("first", "First Punch", 170),
                ("last", "Last Punch", 170),
            ],
        )
        self.present_tree.print_title = "STUDENTS PRESENT TODAY"
        self.present_tree.configure(height=9)

        ttk.Label(absent_tab, text="Students Absent Today", style="SubTitle.TLabel").pack(
            anchor="w", pady=(8, 2), padx=4
        )
        ttk.Label(
            absent_tab,
            text="Active enrolled students with no attendance punch today. “Not linked” means no attendance-device user is attached.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 7), padx=4)
        absent_actions = ttk.Frame(absent_tab, style="Toolbar.TFrame", padding=(8, 4))
        absent_actions.pack(fill="x", pady=(0, 6))
        ttk.Button(
            absent_actions, text="SMS Selected Absent Student", style="Accent.TButton",
            command=self.send_selected_absence_sms,
        ).pack(side="left")
        ttk.Button(
            absent_actions, text="Bulk SMS Selected", command=self.send_bulk_absence_sms,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            absent_actions, text="Print Absent List (POS)", command=self.print_absent_students_pos,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            absent_actions, text="Mark Selected Present...", style="Accent.TButton",
            command=self.mark_selected_absent_present,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(
            absent_actions, text="Use Ctrl/Shift to select several students. Double-click sends to one student.",
            style="Hint.TLabel",
        ).pack(side="left", padx=10)
        absent_area = ttk.Frame(absent_tab)
        absent_area.pack(fill="x")
        self.absent_tree = CrudPage.make_tree(
            self,
            absent_area,
            [
                ("name", "Student", 220), ("class", "Class", 90), ("courses", "Course(s)", 220),
                ("contact", "Contact", 125), ("last", "Last Attendance", 155),
                ("device", "Device", 110),
            ],
        )
        self.absent_tree.print_title = "STUDENTS ABSENT TODAY"
        self.absent_tree.configure(height=8, selectmode="extended")
        self.absent_tree.bind("<Double-1>", self.send_selected_absence_sms)

        ttk.Label(not_enrolled_tab, text="Students Punched but Not Enrolled", style="SubTitle.TLabel").pack(anchor="w", pady=(8, 2), padx=4)
        ttk.Label(not_enrolled_tab, text="Active students with one or more attendance punches and no active course enrollment.", style="Hint.TLabel").pack(anchor="w", pady=(0, 7), padx=4)
        not_enrolled_actions = ttk.Frame(not_enrolled_tab, style="Toolbar.TFrame", padding=(8, 4)); not_enrolled_actions.pack(fill="x", pady=(0, 6))
        ttk.Button(not_enrolled_actions, text="Assign Enrollment...", style="Accent.TButton", command=self.assign_punched_students).pack(side="left")
        ttk.Label(not_enrolled_actions, text="Select one or more students, then assign their course.", style="Hint.TLabel").pack(side="left", padx=10)
        not_enrolled_area = ttk.Frame(not_enrolled_tab); not_enrolled_area.pack(fill="x")
        self.not_enrolled_tree = CrudPage.make_tree(self, not_enrolled_area, [
            ("name", "Student", 220), ("class", "Class", 90), ("contact", "Contact", 125),
            ("punches", "Punches", 90), ("first", "First Punch", 160), ("last", "Last Punch", 160),
        ])
        self.not_enrolled_tree.print_title = "STUDENTS PUNCHED BUT NOT ENROLLED"
        self.not_enrolled_tree.configure(height=8, selectmode="extended")

        ttk.Label(accounts_tab, text="Account Balances", style="SubTitle.TLabel").pack(
            anchor="w", pady=(18, 7), padx=4
        )
        area = ttk.Frame(accounts_tab)
        area.pack(fill="both", expand=True)
        self.tree = CrudPage.make_tree(
            self,
            area,
            [
                ("name", "Account", 220),
                ("type", "Type", 130),
                ("balance", "Balance", 130),
                ("status", "Status", 90),
            ],
        )
        self.tree.print_title = "ACCOUNT BALANCES"

    def refresh(self) -> None:
        today = today_iso()
        metrics = self.db.query_one(
            "SELECT "
            "(SELECT COUNT(*) FROM students) students,"
            "(SELECT COUNT(*) FROM teachers) teachers,"
            "(SELECT COUNT(*) FROM enrollments WHERE status='Active') enrollments,"
            "(SELECT COALESCE(SUM(charge_amount-payment_amount-discount_amount),0) FROM student_transactions) student_due,"
            "(SELECT COALESCE(SUM(amount),0) FROM income_records WHERE income_date=?) today_income,"
            "(SELECT COALESCE(SUM(payment_amount),0) FROM student_transactions WHERE transaction_date=?) today_student,"
            "(SELECT COALESCE(SUM(amount),0) FROM expense_records WHERE expense_date=?) today_expense,"
            "(SELECT COALESCE(SUM(net_salary),0) FROM salary_payouts) salary_total",
            (today, today, today),
        )
        accounts = self.db.account_balances()
        total_balance = sum(float(row["balance"]) for row in accounts)

        self.cards["students"].config(text=str(metrics["students"]))
        self.cards["teachers"].config(text=str(metrics["teachers"]))
        self.cards["enrollments"].config(text=str(metrics["enrollments"]))
        self.cards["student_due"].config(text=money(metrics["student_due"]))
        self.cards["today_income"].config(text=money(float(metrics["today_income"]) + float(metrics["today_student"])))
        self.cards["today_expense"].config(text=money(metrics["today_expense"]))
        self.cards["cash_total"].config(text=money(total_balance))
        self.cards["salary_total"].config(text=money(metrics["salary_total"]))

        CrudPage.clear_tree(self.tree)
        for row in accounts:
            self.tree.insert(
                "", "end",
                values=(
                    row["account_name"], row["account_type"], money(row["balance"]), row["status"],
                ),
            )
        self._schedule_attendance_refresh()

    def invalidate_cache(self) -> None:
        self._attendance_cache = None

    def _schedule_attendance_refresh(self) -> None:
        """Draw the page first; attendance analysis is the expensive dashboard work."""
        self._attendance_generation += 1
        if self._attendance_after_id is not None:
            try:
                self.after_cancel(self._attendance_after_id)
            except tk.TclError:
                pass
            self._attendance_after_id = None
        if self._attendance_cache and time.monotonic() - self._attendance_cache[0] < 15:
            self._render_attendance(*self._attendance_cache[1:])
            return
        generation = self._attendance_generation
        self._attendance_after_id = self.after(25, lambda: self._load_attendance(generation))

    def _load_attendance(self, generation: int) -> None:
        self._attendance_after_id = None
        if generation != self._attendance_generation:
            return
        try:
            present_students = self.app.services.attendance.students_present_today()
            absent_students = self.app.services.attendance.students_absent_today()
            punched_not_enrolled = self.app.services.attendance.students_punched_not_enrolled()
            attendance_alerts = self.app.services.attendance.student_attendance_alerts(
                include_suppressed=self.show_suppressed_alerts,
            )
            payment_alerts = self.app.services.billing.payment_alerts(
                include_suppressed=self.show_suppressed_payment_alerts,
            )
            if generation != self._attendance_generation:
                return
            self._attendance_cache = (time.monotonic(), present_students, absent_students, punched_not_enrolled, attendance_alerts, payment_alerts)
            self._render_attendance(present_students, absent_students, punched_not_enrolled, attendance_alerts, payment_alerts)
        except Exception:
            logging.getLogger(__name__).exception("Dashboard attendance refresh failed")

    def _render_attendance(self, present_students, absent_students, punched_not_enrolled, attendance_alerts, payment_alerts=None) -> None:
        self.attendance_alerts_by_student = {int(row["student_id"]): row for row in attendance_alerts}
        self.absent_students_by_student = {int(row["id"]): row for row in absent_students}
        if payment_alerts is not None:
            self.payment_alerts_by_bill = {int(row["bill_id"]): row for row in payment_alerts}
            CrudPage.clear_tree(self.payment_tree)
            for row in payment_alerts:
                self.payment_tree.insert(
                    "",
                    "end",
                    iid=f"payment-{row['bill_id']}",
                    values=(
                        row["student_name"],
                        row["class_name"] or "",
                        row["bill_number"],
                        row["course_name"],
                        row["due_date"],
                        f"{row['days_overdue']} d",
                        money(row["balance"]),
                        row["review_status"],
                        row["follow_up_date"] or "-",
                        row["review_note"] or "",
                    ),
                )
        self.cards["student_present"].config(text=str(len(present_students)))
        self.cards["attendance_alerts"].config(text=str(len(attendance_alerts)))

        CrudPage.clear_tree(self.present_tree)
        for row in present_students:
            self.present_tree.insert(
                "",
                "end",
                values=(
                    row["student_name"],
                    row["class_name"] or "",
                    row["punches"],
                    self._attendance_time(row["first_seen"]),
                    self._attendance_time(row["last_seen"]),
                ),
            )

        CrudPage.clear_tree(self.absent_tree)
        for row in absent_students:
            self.absent_tree.insert(
                "", "end", iid=f"absent-{row['id']}", values=(
                    row["student_name"], row["class_name"] or "", row["courses"] or "",
                    row["contact"] or "", self._attendance_date(row["last_seen"]),
                    row["device_status"],
                ),
            )

        CrudPage.clear_tree(self.not_enrolled_tree)
        for row in punched_not_enrolled:
            self.not_enrolled_tree.insert("", "end", iid=f"not-enrolled-{row['id']}", values=(
                row["student_name"], row["class_name"] or "", row["contact"] or "", row["punches"],
                self._attendance_date(row["first_seen"]), self._attendance_date(row["last_seen"]),
            ))

        CrudPage.clear_tree(self.alert_tree)
        for row in attendance_alerts:
            self.alert_tree.insert("", "end", iid=f"alert-{row['student_id']}", values=(
                row["student_name"], row["class_name"], self._attendance_date(row["last_seen"]),
                row["consecutive_days"], row["monthly_missing_days"], row["review_status"], row["reason"],
            ))


    @staticmethod
    def _attendance_time(value) -> str:
        if not value:
            return ""
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return timestamp.strftime("%H:%M:%S")

    @staticmethod
    def _attendance_date(value) -> str:
        if not value: return "No attendance yet"
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return timestamp.strftime("%Y-%m-%d %H:%M")

    def review_selected_alert(self, _event=None):
        selected = self.alert_tree.selection()
        if not selected:
            messagebox.showinfo("Attendance Alert", "Select an attendance alert first.", parent=self)
            return
        try:
            student_id = int(str(selected[0]).removeprefix("alert-"))
        except ValueError:
            return
        alert = self.attendance_alerts_by_student.get(student_id)
        if not alert:
            return
        dialog = tk.Toplevel(self); dialog.title("Review Attendance Alert"); dialog.transient(self.winfo_toplevel()); dialog.grab_set()
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame"); shell.pack(fill="both", expand=True)
        details = (
            f"Student: {alert['student_name']}   |   Class: {alert['class_name'] or '-'}\n"
            f"Parent/Guardian: {alert['parent_name'] or '-'}   |   Contact: {alert['contact'] or '-'}\n"
            f"Active course(s): {alert['courses'] or '-'}\n"
            f"Last attendance: {self._attendance_date(alert['last_seen'])}\n"
            f"Alert: {alert['reason']}"
        )
        ttk.Label(shell, text=details, style="Form.TLabel", justify="left").pack(anchor="w", pady=(0, 10))
        if alert["review_status"] != "Not reviewed":
            ttk.Label(shell, text=f"Previous review: {alert['review_status']} by {alert['reviewer'] or 'Unknown'}; follow up {alert['follow_up_date'] or '-'}\n{alert['review_note'] or ''}", style="Hint.TLabel", justify="left", wraplength=620).pack(anchor="w", pady=(0, 10))
        initial_status = alert["review_status"]
        if initial_status in {"Not reviewed", "Suppressed", "Suppression expired"}:
            initial_status = "Monitoring"
        values = {"status": tk.StringVar(value=initial_status), "follow_up": tk.StringVar(value=alert["follow_up_date"] or ""), "note": tk.StringVar(value=alert["review_note"] or "")}
        form = ttk.Frame(shell, style="Form.TFrame"); form.pack(fill="x")
        fb = FormBuilder(form); fb.combo("Review Status *", values["status"], ["Contacted", "Monitoring", "Approved Leave", "Left Institution", "No Action Needed"]); fb.entry("Follow-up Date", values["follow_up"], width=42); fb.entry("Review Notes", values["note"], width=42)
        def save_review():
            try:
                follow_up = validate_date(values["follow_up"].get(), "Follow-up date", True)
                self.app.services.attendance.record_attendance_alert_review(student_id, values["status"].get(), values["note"].get(), follow_up, self.app.session.user_id)
                dialog.destroy(); self.invalidate_cache(); self.refresh()
            except Exception as exc:
                messagebox.showerror("Attendance Review", str(exc), parent=dialog)
        ttk.Button(shell, text="Save Review", style="Accent.TButton", command=save_review).pack(anchor="e", pady=(12, 0))

    def _selected_alert(self):
        selected = self.alert_tree.selection()
        if not selected:
            messagebox.showinfo("Attendance Follow-up", "Select an attendance alert first.", parent=self)
            return None
        try:
            return self.attendance_alerts_by_student.get(
                int(str(selected[0]).removeprefix("alert-"))
            )
        except ValueError:
            return None

    def toggle_suppressed_alerts(self) -> None:
        self.show_suppressed_alerts = not self.show_suppressed_alerts
        self.suppressed_toggle.configure(
            text="Hide Suppressed" if self.show_suppressed_alerts else "Show Suppressed"
        )
        self.invalidate_cache()
        self.refresh()

    def suppress_selected_alert(self) -> None:
        alert = self._selected_alert()
        if not alert:
            return
        if alert.get("suppressed"):
            messagebox.showinfo(
                "Attendance Follow-up", "This follow-up is already suppressed.", parent=self,
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Suppress Attendance Follow-up")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=f"Suppress follow-up — {alert['student_name']}", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="The alert will be hidden from normal follow-up. Add a resume date to show it again automatically; leave it blank to keep it suppressed until restored manually.",
            style="Hint.TLabel", wraplength=560, justify="left",
        ).pack(anchor="w", pady=(3, 12))
        values = {"reason": tk.StringVar(), "resume": tk.StringVar()}
        form = ttk.Frame(shell, style="Form.TFrame")
        form.pack(fill="x")
        builder = FormBuilder(form)
        builder.entry("Suppression Reason *", values["reason"], width=46)
        builder.entry("Resume Follow-up Date (BS)", values["resume"], width=46)
        actions = ttk.Frame(shell, style="Form.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")

        def save_suppression():
            try:
                reason = values["reason"].get().strip()
                if not reason:
                    raise ValueError("Enter a reason for suppressing this follow-up.")
                resume = validate_date(values["resume"].get(), "Resume follow-up date", True)
                self.app.services.attendance.record_attendance_alert_review(
                    alert["student_id"], "Suppressed", reason, resume,
                    self.app.session.user_id,
                )
                dialog.destroy()
                self.invalidate_cache()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("Suppress Follow-up", str(exc), parent=dialog)

        ttk.Button(actions, text="Suppress", style="Accent.TButton", command=save_suppression).pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

    def _selected_payment_alert(self):
        selected = self.payment_tree.selection()
        if not selected:
            messagebox.showinfo("Payment Alert", "Select a payment alert first.", parent=self)
            return None
        try:
            return self.payment_alerts_by_bill.get(
                int(str(selected[0]).removeprefix("payment-"))
            )
        except ValueError:
            return None

    def toggle_suppressed_payment_alerts(self) -> None:
        self.show_suppressed_payment_alerts = not self.show_suppressed_payment_alerts
        self.suppressed_payment_toggle.configure(
            text="Hide Suppressed" if self.show_suppressed_payment_alerts else "Show Suppressed"
        )
        self.invalidate_cache()
        self.refresh()

    def review_selected_payment_alert(self, _event=None):
        alert = self._selected_payment_alert()
        if not alert:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Review Payment Alert / Follow-up")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        details = (
            f"Student: {alert['student_name']}   |   Class: {alert['class_name'] or '-'}\n"
            f"Bill #: {alert['bill_number']}   |   Course: {alert['course_name']}\n"
            f"Due date: {alert['due_date']} ({alert['days_overdue']} days overdue)\n"
            f"Balance due: Rs. {money(alert['balance'])}"
        )
        ttk.Label(shell, text=details, style="Form.TLabel", justify="left").pack(anchor="w", pady=(0, 10))
        if alert["review_status"] != "Not reviewed":
            ttk.Label(
                shell,
                text=f"Previous review: {alert['review_status']} by {alert['reviewer'] or 'Unknown'}; follow-up {alert['follow_up_date'] or '-'}\n{alert['review_note'] or ''}",
                style="Hint.TLabel", justify="left", wraplength=580,
            ).pack(anchor="w", pady=(0, 10))
        initial_status = alert["review_status"]
        if initial_status in {"Not reviewed", "Suppression expired"}:
            initial_status = "Promise to Pay"
        values = {
            "status": tk.StringVar(value=initial_status),
            "follow_up": tk.StringVar(value=alert["follow_up_date"] or ""),
            "note": tk.StringVar(value=alert["review_note"] or ""),
        }
        form = ttk.Frame(shell, style="Form.TFrame")
        form.pack(fill="x")
        fb = FormBuilder(form)
        fb.combo(
            "Review Status *", values["status"],
            ["Suppressed", "Promise to Pay", "Parent Contacted", "Payment Plan", "Dispute / Under Review", "Monitoring", "No Action Needed"],
        )
        fb.entry("Follow-up Date (BS)", values["follow_up"], width=42)
        fb.entry("Notes", values["note"], width=42)

        def save_review():
            try:
                follow_up = validate_date(values["follow_up"].get(), "Follow-up date", True)
                self.app.services.billing.record_payment_alert_review(
                    alert["bill_id"], values["status"].get(), values["note"].get(), follow_up, self.app.session.user_id,
                )
                dialog.destroy()
                self.invalidate_cache()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("Payment Review", str(exc), parent=dialog)

        ttk.Button(shell, text="Save Follow-up", style="Accent.TButton", command=save_review).pack(anchor="e", pady=(12, 0))

    def suppress_selected_payment_alert(self) -> None:
        alert = self._selected_payment_alert()
        if not alert:
            return
        if alert.get("suppressed"):
            messagebox.showinfo("Payment Follow-up", "This alert is already suppressed.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Suppress Payment Alert")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=f"Suppress payment follow-up — {alert['student_name']} ({alert['bill_number']})", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="The alert will be hidden from the active dashboard. Add a resume follow-up date to restore it automatically when due.",
            style="Hint.TLabel", wraplength=560, justify="left",
        ).pack(anchor="w", pady=(3, 12))
        values = {"reason": tk.StringVar(), "resume": tk.StringVar()}
        form = ttk.Frame(shell, style="Form.TFrame")
        form.pack(fill="x")
        builder = FormBuilder(form)
        builder.entry("Suppression Reason / Notes *", values["reason"], width=46)
        builder.entry("Resume Follow-up Date (BS)", values["resume"], width=46)
        actions = ttk.Frame(shell, style="Form.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")

        def save_suppression():
            try:
                reason = values["reason"].get().strip()
                if not reason:
                    raise ValueError("Enter a reason for suppressing this follow-up.")
                resume = validate_date(values["resume"].get(), "Resume follow-up date", True)
                self.app.services.billing.record_payment_alert_review(
                    alert["bill_id"], "Suppressed", reason, resume, self.app.session.user_id,
                )
                dialog.destroy()
                self.invalidate_cache()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("Suppress Payment Follow-up", str(exc), parent=dialog)

        ttk.Button(actions, text="Suppress", style="Accent.TButton", command=save_suppression).pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

    def send_selected_absence_sms(self, _event=None):
        selected = self.absent_tree.selection()
        if not selected:
            messagebox.showinfo("Absence SMS", "Select an absent student first.", parent=self)
            return
        try:
            student_id = int(str(selected[0]).removeprefix("absent-"))
        except ValueError:
            return
        if student_id not in self.absent_students_by_student:
            messagebox.showerror("Absence SMS", "Refresh the dashboard and select the student again.", parent=self)
            return
        absence_date = today_iso()
        try:
            details = self.app.services.notifications.absence_sms_details(student_id, absence_date)
        except Exception as exc:
            self.show_error(exc)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Send Absence SMS")
        dialog.transient(self.winfo_toplevel())
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=f"Absence SMS — {details['student_name']}", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(shell, text=f"Absent date: {absence_date}", style="Hint.TLabel").pack(anchor="w", pady=(0, 10))
        recipient = tk.StringVar(value=details["contact"])
        recipient_row = ttk.Frame(shell, style="Form.TFrame"); recipient_row.pack(fill="x", pady=(0, 8))
        ttk.Label(recipient_row, text="Mobile Number").pack(side="left")
        ttk.Entry(recipient_row, textvariable=recipient, width=25).pack(side="left", padx=10)
        ttk.Label(shell, text="Message Preview", style="FormValue.TLabel").pack(anchor="w")
        ttk.Label(shell, text=details["message"], style="Hint.TLabel", justify="left", wraplength=520).pack(anchor="w", pady=(2, 12))
        actions = ttk.Frame(shell, style="Form.TFrame"); actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right", padx=3)

        def queue_sms():
            try:
                self.app.services.notifications.queue_absence_sms(student_id, absence_date, recipient.get())
                dialog.destroy()
                messagebox.showinfo(
                    "Absence SMS Queued",
                    "The absence alert was queued. Check SMS & Notifications for its delivery result.",
                    parent=self,
                )
            except Exception as exc:
                messagebox.showerror("Absence SMS", str(exc), parent=dialog)

        ttk.Button(actions, text="Queue SMS", style="Accent.TButton", command=queue_sms).pack(side="right", padx=3)
        dialog.grab_set()

    def send_bulk_absence_sms(self):
        selected = self.absent_tree.selection()
        if not selected:
            messagebox.showinfo("Bulk Absence SMS", "Select one or more absent students first.", parent=self)
            return
        student_ids = []
        for item_id in selected:
            try:
                student_id = int(str(item_id).removeprefix("absent-"))
            except ValueError:
                continue
            if student_id in self.absent_students_by_student:
                student_ids.append(student_id)
        if not student_ids:
            messagebox.showerror("Bulk Absence SMS", "Refresh the dashboard and select the students again.", parent=self)
            return
        absence_date = today_iso()
        if not messagebox.askyesno(
            "Bulk Absence SMS",
            f"Queue a personalised absence SMS for {len(student_ids)} selected student(s) for {absence_date}?\n\n"
            "Students with an invalid or missing mobile number will be skipped.",
            parent=self,
        ):
            return
        try:
            queued, skipped = self.app.services.notifications.queue_absence_sms_batch(student_ids, absence_date)
            message = f"Queued {len(queued)} absence SMS message(s)."
            if skipped:
                message += f"\n\nSkipped {len(skipped)} student(s) with contact or delivery-record issues."
            message += "\n\nCheck SMS & Notifications for delivery results."
            messagebox.showinfo("Bulk Absence SMS", message, parent=self)
        except Exception as exc:
            self.show_error(exc)

    def print_absent_students_pos(self) -> None:
        students = list(self.absent_students_by_student.values())
        try:
            self.app.services.reports.print_absent_students_pos(students)
            messagebox.showinfo(
                "Absent List Printed",
                f"Sent {len(students)} absent student(s) to the configured POS printer.",
                parent=self,
            )
        except Exception as exc:
            self.show_error(exc)

    def mark_selected_absent_present(self) -> None:
        selected = self.absent_tree.selection()
        if not selected:
            messagebox.showinfo("Mark Present", "Select one or more absent students first.", parent=self)
            return
        student_ids = [int(str(item).removeprefix("absent-")) for item in selected]
        dialog = tk.Toplevel(self)
        dialog.title("Mark Selected Students Present")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Mark Students Present", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text=f"{len(student_ids)} selected student(s) will be marked present for {today_iso()}. "
                 "Use this only when the attendance device missed a valid punch.",
            style="Hint.TLabel", wraplength=560, justify="left",
        ).pack(anchor="w", pady=(0, 10))
        values = {
            "time": tk.StringVar(value=datetime.now().strftime("%I:%M %p").lstrip("0")),
            "reason": tk.StringVar(value="Device attendance missed"),
        }
        form = ttk.Frame(shell, style="Form.TFrame"); form.pack(fill="x")
        builder = FormBuilder(form)
        builder.entry("Attendance Time *", values["time"], width=38)
        builder.entry("Reason *", values["reason"], width=38)
        actions = ttk.Frame(shell, style="Form.TFrame"); actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")

        def save_manual_present():
            try:
                created = 0
                already_recorded = 0
                for student_id in student_ids:
                    if self.app.services.attendance.mark_manual_present(
                        "student", student_id, today_iso(), values["time"].get(), values["reason"].get(),
                    ):
                        created += 1
                    else:
                        already_recorded += 1
                dialog.destroy()
                self.app.refresh_all()
                summary = f"Marked present: {created}"
                if already_recorded:
                    summary += f"\nAlready recorded: {already_recorded}"
                messagebox.showinfo("Manual Attendance", summary, parent=self)
            except Exception as exc:
                messagebox.showerror("Manual Attendance", str(exc), parent=dialog)

        ttk.Button(actions, text="Mark Present", style="Accent.TButton", command=save_manual_present).pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

    def assign_punched_students(self) -> None:
        selected = self.not_enrolled_tree.selection()
        if not selected:
            messagebox.showinfo("Assign Enrollment", "Select one or more students first.", parent=self)
            return
        student_ids = [int(str(item).removeprefix("not-enrolled-")) for item in selected]
        page = self.app.pages.get("Enrollments")
        if not page:
            self.show_error(ValueError("Enrollment module is unavailable for this user."))
            return
        page.open_selected_students_enrollment(student_ids)


# ---------------------------------------------------------------------------
# Students
