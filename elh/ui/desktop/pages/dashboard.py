from __future__ import annotations

import csv
import sqlite3
import tkinter as tk
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
            card.grid(row=idx // 4, column=idx % 4, padx=6, pady=6, sticky="nsew")
            ttk.Label(card,text=title,style="DashboardCardTitle.TLabel").pack(anchor="w")
            value = ttk.Label(card, text="0", style="DashboardCardValue.TLabel")
            value.pack(anchor="w",pady=(7,0))
            self.cards[key] = value

        for i in range(4):
            grid.columnconfigure(i, weight=1)

        dashboard_tabs = ttk.Notebook(self)
        dashboard_tabs.pack(fill="both", expand=True, pady=(12, 0))
        attendance_tab = ttk.Frame(dashboard_tabs, padding=4)
        accounts_tab = ttk.Frame(dashboard_tabs, padding=4)
        dashboard_tabs.add(attendance_tab, text="Attendance & Follow-up")
        dashboard_tabs.add(accounts_tab, text="Account Balances")

        ttk.Label(attendance_tab, text="Students Present Today", style="SubTitle.TLabel").pack(
            anchor="w", pady=(14, 7), padx=4
        )
        present_area = ttk.Frame(attendance_tab)
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
        self.present_tree.configure(height=4)

        ttk.Label(attendance_tab, text="Attendance Follow-up Alerts", style="SubTitle.TLabel").pack(anchor="w", pady=(14, 7), padx=4)
        alert_area = ttk.Frame(attendance_tab); alert_area.pack(fill="both", expand=True)
        self.alert_tree = CrudPage.make_tree(self, alert_area, [
            ("student", "Student", 220), ("class", "Class", 90), ("last", "Last Attendance", 155),
            ("consecutive", "No-Punch Days", 110), ("monthly", "Missing This Month", 130), ("review", "Review Status", 130), ("reason", "Review Reason", 300),
        ])
        self.alert_tree.configure(height=7)
        self.alert_tree.bind("<Double-1>", self.review_selected_alert)
        alert_actions = ttk.Frame(attendance_tab, style="Toolbar.TFrame", padding=(8, 4)); alert_actions.pack(fill="x")
        ttk.Button(alert_actions, text="Review Selected Alert", style="Accent.TButton", command=self.review_selected_alert).pack(side="left")
        ttk.Label(alert_actions, text="Double-click an alert to record contact, leave, or follow-up details.", style="Hint.TLabel").pack(side="left", padx=10)

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
        present_students = self.app.services.attendance.students_present_today()
        attendance_alerts = self.app.services.attendance.student_attendance_alerts()
        self.attendance_alerts_by_student = {int(row["student_id"]): row for row in attendance_alerts}
        self.cards["student_present"].config(text=str(len(present_students)))
        self.cards["attendance_alerts"].config(text=str(len(attendance_alerts)))
        self.cards["student_due"].config(text=money(metrics["student_due"]))
        self.cards["today_income"].config(text=money(float(metrics["today_income"]) + float(metrics["today_student"])))
        self.cards["today_expense"].config(text=money(metrics["today_expense"]))
        self.cards["cash_total"].config(text=money(total_balance))
        self.cards["salary_total"].config(text=money(metrics["salary_total"]))

        self.present_tree.delete(*self.present_tree.get_children())
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

        self.alert_tree.delete(*self.alert_tree.get_children())
        for row in attendance_alerts:
            self.alert_tree.insert("", "end", iid=f"alert-{row['student_id']}", values=(
                row["student_name"], row["class_name"], self._attendance_date(row["last_seen"]),
                row["consecutive_days"], row["monthly_missing_days"], row["review_status"], row["reason"],
            ))

        self.tree.delete(*self.tree.get_children())
        for row in accounts:
            self.tree.insert(
                "", "end",
                values=(
                    row["account_name"],
                    row["account_type"],
                    money(row["balance"]),
                    row["status"],
                ),
            )

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
        values = {"status": tk.StringVar(value=alert["review_status"] if alert["review_status"] != "Not reviewed" else "Monitoring"), "follow_up": tk.StringVar(value=alert["follow_up_date"] or ""), "note": tk.StringVar(value=alert["review_note"] or "")}
        form = ttk.Frame(shell, style="Form.TFrame"); form.pack(fill="x")
        fb = FormBuilder(form); fb.combo("Review Status *", values["status"], ["Contacted", "Monitoring", "Approved Leave", "Left Institution", "No Action Needed"]); fb.entry("Follow-up Date", values["follow_up"], width=42); fb.entry("Review Notes", values["note"], width=42)
        def save_review():
            try:
                follow_up = validate_date(values["follow_up"].get(), "Follow-up date", True)
                self.app.services.attendance.record_attendance_alert_review(student_id, values["status"].get(), values["note"].get(), follow_up, self.app.session.user_id)
                dialog.destroy(); self.refresh()
            except Exception as exc:
                messagebox.showerror("Attendance Review", str(exc), parent=dialog)
        ttk.Button(shell, text="Save Review", style="Accent.TButton", command=save_review).pack(anchor="e", pady=(12, 0))


# ---------------------------------------------------------------------------
# Students
