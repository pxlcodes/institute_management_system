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

        ttk.Label(self, text="Students Present Today", style="SubTitle.TLabel").pack(
            anchor="w", pady=(14, 7), padx=4
        )
        present_area = ttk.Frame(self)
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
        self.present_tree.configure(height=5)

        ttk.Label(self, text="Attendance Follow-up Alerts", style="SubTitle.TLabel").pack(anchor="w", pady=(18, 7), padx=4)
        alert_area = ttk.Frame(self); alert_area.pack(fill="x")
        self.alert_tree = CrudPage.make_tree(self, alert_area, [
            ("student", "Student", 220), ("class", "Class", 90), ("last", "Last Attendance", 155),
            ("consecutive", "No-Punch Days", 110), ("monthly", "Missing This Month", 130), ("reason", "Review Reason", 300),
        ])
        self.alert_tree.configure(height=5)

        ttk.Label(self, text="Account Balances", style="SubTitle.TLabel").pack(
            anchor="w", pady=(18, 7), padx=4
        )
        area = ttk.Frame(self)
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
            self.alert_tree.insert("", "end", values=(
                row["student_name"], row["class_name"], self._attendance_date(row["last_seen"]),
                row["consecutive_days"], row["monthly_missing_days"], row["reason"],
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


# ---------------------------------------------------------------------------
# Students
