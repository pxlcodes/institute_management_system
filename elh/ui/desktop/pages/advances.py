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
from elh.ui.desktop.pages.account_selection import AccountSelectionMixin
from elh.ui.desktop.pages.payment_proof import PaymentProofMixin

# Teacher Advances
# ---------------------------------------------------------------------------

class AdvancesPage(CrudPage, AccountSelectionMixin, PaymentProofMixin):
    proof_kind="advance"
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.teacher_map = {}
        self.account_map = {}

        ttk.Label(self, text="Staff Advance Payouts", style="Title.TLabel").pack(anchor="w")
        form = self.create_form_dialog("Advance Payment", padding=8)
        form.pack(fill="x", pady=8)

        self.vars = {
            "teacher": tk.StringVar(), "date": tk.StringVar(value=today_iso()),
            "amount": tk.StringVar(value="0"), "account": tk.StringVar(),
            "method": tk.StringVar(value="Cash"), "reference": tk.StringVar(),
            "recovery_method": tk.StringVar(value="Salary Deduction"),
            "recovery_month": tk.StringVar(), "monthly_deduction": tk.StringVar(value="0"),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.teacher_combo = fb.combo(
            "Staff Member *", self.vars["teacher"], [], searchable=True
        )
        fb.entry("Advance Date *", self.vars["date"])
        fb.entry("Amount *", self.vars["amount"])
        self.account_combo = fb.combo("Paid From Account *", self.vars["account"], [])
        fb.combo("Payment Method", self.vars["method"], ["Cash", "Bank", "Wallet", "Other"])
        fb.entry("Reference No.", self.vars["reference"])
        fb.combo(
            "Recovery Method", self.vars["recovery_method"],
            ["Salary Deduction", "Direct Repayment", "Other"]
        )
        fb.entry("Recovery Start Month", self.vars["recovery_month"])
        fb.entry("Monthly Deduction", self.vars["monthly_deduction"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        ttk.Button(form, text="Pay Advance", command=self.save).grid(
            row=0, column=2, padx=15, pady=3, sticky="new"
        )
        ttk.Button(form, text="Clear", command=self.clear).grid(
            row=1, column=2, padx=15, pady=3, sticky="new"
        )

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("date", "Date", 95), ("teacher", "Staff Member", 170),
                ("amount", "Advance", 100), ("recovered", "Recovered", 100),
                ("remaining", "Remaining", 100), ("account", "Paid From", 140),
                ("status", "Status", 110),
            ],
        )
        self.add_payment_proof_buttons(self)

    def refresh(self):
        teachers = self.db.query(
            "SELECT id, teacher_name FROM teachers WHERE status='Active' ORDER BY teacher_name"
        )
        self.teacher_map = {f"{r['id']} - {r['teacher_name']}": r["id"] for r in teachers}
        self.teacher_combo["values"] = list(self.teacher_map)
        self.load_accounts_into(self.account_combo)

        self.clear_tree(self.tree)
        rows = self.db.query(
            """
            SELECT ta.*, t.teacher_name, a.account_name
            FROM teacher_advances ta
            JOIN teachers t ON t.id=ta.teacher_id
            JOIN accounts a ON a.id=ta.paid_from_account_id
            ORDER BY ta.advance_date DESC, ta.id DESC
            """
        )
        for r in rows:
            remaining = float(r["amount"]) - float(r["recovered_amount"])
            self.tree.insert(
                "", "end",
                values=(r["id"], r["advance_date"], r["teacher_name"], money(r["amount"]),
                        money(r["recovered_amount"]), money(remaining), r["account_name"], r["status"])
            )

    def save(self):
        try:
            teacher_id = self.teacher_map.get(self.vars["teacher"].get())
            if not teacher_id:
                raise ValueError("Please select a staff member.")
            amount = parse_amount(self.vars["amount"].get(), "Advance amount", allow_zero=False)
            account_id = self.selected_account_id(self.vars["account"].get())
            self.require_sufficient_balance(account_id, amount)
            trans_date = validate_date(self.vars["date"].get())

            def callback(conn):
                cur = conn.execute(
                    """
                    INSERT INTO teacher_advances
                    (teacher_id, advance_date, amount, paid_from_account_id,
                     payment_method, reference_no, recovery_method,
                     recovery_start_month, monthly_deduction, status, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Outstanding', ?)
                    """,
                    (
                        teacher_id, trans_date, amount, account_id,
                        self.vars["method"].get(), self.vars["reference"].get().strip(),
                        self.vars["recovery_method"].get(),
                        self.vars["recovery_month"].get().strip(),
                        parse_amount(self.vars["monthly_deduction"].get() or "0", "Monthly deduction"),
                        self.vars["remarks"].get().strip(),
                    ),
                )
                self.db.add_ledger(
                    conn, trans_date, account_id, "OUT", amount,
                    "Teacher Advance", cur.lastrowid, "Teacher advance payout",
                    self.vars["reference"].get().strip(), self.vars["remarks"].get().strip()
                )
                self.app.services.staff_finance.record_payment(
                    conn, teacher_id, trans_date, "Staff Advance", amount,
                    "Teacher Advance", cur.lastrowid, account_id,
                    "Recoverable staff advance", self.vars["reference"].get().strip(),
                    self.vars["remarks"].get().strip(),
                )
            self.db.transaction(callback)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def clear(self):
        for v in self.vars.values():
            v.set("")
        self.vars["date"].set(today_iso())
        self.vars["amount"].set("0")
        self.vars["method"].set("Cash")
        self.vars["recovery_method"].set("Salary Deduction")
        self.vars["monthly_deduction"].set("0")


# ---------------------------------------------------------------------------
# Salary
