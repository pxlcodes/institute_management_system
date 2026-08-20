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

# Student Transactions
# ---------------------------------------------------------------------------

class StudentTransactionsPage(CrudPage, AccountSelectionMixin, PaymentProofMixin):
    proof_kind="student"
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.student_map = {}
        self.enrollment_map = {}
        self.account_map = {}

        ttk.Label(self, text="Student Account Transactions", style="Title.TLabel").pack(anchor="w")
        form = self.create_form_dialog("Transaction", padding=8)
        form.pack(fill="x", pady=8)

        self.vars = {
            "student": tk.StringVar(),
            "enrollment": tk.StringVar(),
            "date": tk.StringVar(value=today_iso()),
            "type": tk.StringVar(value="Payment Received"),
            "particular": tk.StringVar(value="Fee payment"),
            "charge": tk.StringVar(value="0"),
            "payment": tk.StringVar(value="0"),
            "discount": tk.StringVar(value="0"),
            "account": tk.StringVar(),
            "method": tk.StringVar(value="Cash"),
            "receipt": tk.StringVar(),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.student_combo = fb.combo(
            "Student *", self.vars["student"], [], searchable=True
        )
        self.student_combo.bind("<<ComboboxSelected>>", lambda e: self.load_enrollments())
        self.enroll_combo = fb.combo(
            "Enrollment", self.vars["enrollment"], [], searchable=True
        )
        fb.entry("Date *", self.vars["date"])
        fb.combo(
            "Transaction Type",
            self.vars["type"],
            ["Admission Fee", "Monthly Fee", "Exam Fee", "Other Charge",
             "Payment Received", "Discount", "Refund", "Adjustment"],
        )
        fb.entry("Particular *", self.vars["particular"])
        fb.entry("Charge Amount", self.vars["charge"])
        fb.entry("Payment Amount", self.vars["payment"])
        fb.entry("Discount Amount", self.vars["discount"])
        self.account_combo = fb.combo("Payment Account", self.vars["account"], [])
        fb.combo("Payment Method", self.vars["method"], ["Cash", "Bank", "Wallet", "Other"])
        fb.entry("Receipt No.", self.vars["receipt"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form, style="Form.TFrame")
        buttons.grid(row=0, column=2, rowspan=12, padx=15, sticky="n")
        ttk.Button(buttons, text="Save Transaction", command=self.save).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear", command=self.clear).pack(fill="x", pady=3)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("date", "Date", 95), ("student", "Student", 160),
                ("type", "Type", 120), ("particular", "Particular", 170),
                ("charge", "Charge", 90), ("payment", "Payment", 90),
                ("discount", "Discount", 90), ("account", "Account", 140),
            ],
        )
        self.add_payment_proof_buttons(self)

    def load_students(self):
        rows = self.db.query("SELECT id, student_name FROM students ORDER BY student_name")
        self.student_map = {f"{r['id']} - {r['student_name']}": r["id"] for r in rows}
        self.student_combo["values"] = list(self.student_map)

    def load_enrollments(self):
        student_id = self.student_map.get(self.vars["student"].get())
        if not student_id:
            self.enroll_combo["values"] = []
            return
        rows = self.db.query(
            "SELECT e.id,c.course_name,e.start_date "
            "FROM enrollments e JOIN courses c ON c.id=e.course_id "
            "WHERE e.student_id=? ORDER BY e.start_date DESC",
            (student_id,),
        )
        self.enrollment_map = {
            f"{r['id']} - {r['course_name']} ({r['start_date']})": r["id"] for r in rows
        }
        self.enroll_combo["values"] = list(self.enrollment_map)
        self.vars["enrollment"].set("")

    def save(self):
        try:
            student_id = self.student_map.get(self.vars["student"].get())
            if not student_id:
                raise ValueError("Please select a student.")
            enrollment_id = self.enrollment_map.get(self.vars["enrollment"].get())
            trans_date = validate_date(self.vars["date"].get())
            particular = self.vars["particular"].get().strip()
            if not particular:
                raise ValueError("Particular is required.")

            charge = parse_amount(self.vars["charge"].get() or "0", "Charge")
            payment = parse_amount(self.vars["payment"].get() or "0", "Payment")
            discount = parse_amount(self.vars["discount"].get() or "0", "Discount")
            if charge == 0 and payment == 0 and discount == 0:
                raise ValueError("Enter a charge, payment or discount amount.")

            account_id = None
            if payment > 0 or self.vars["type"].get() == "Refund":
                account_id = self.selected_account_id(self.vars["account"].get())

            if self.vars["type"].get() == "Refund" and payment > 0:
                self.require_sufficient_balance(account_id, payment)

            def callback(conn):
                cur = conn.execute(
                    """
                    INSERT INTO student_transactions
                    (student_id, enrollment_id, transaction_date, transaction_type,
                     particular, charge_amount, payment_amount, discount_amount,
                     account_id, payment_method, receipt_no, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student_id, enrollment_id, trans_date, self.vars["type"].get(),
                        particular, charge, payment, discount, account_id,
                        self.vars["method"].get(), self.vars["receipt"].get().strip(),
                        self.vars["remarks"].get().strip(),
                    ),
                )
                trans_id = cur.lastrowid
                if account_id and payment > 0:
                    direction = "OUT" if self.vars["type"].get() == "Refund" else "IN"
                    self.db.add_ledger(
                        conn, trans_date, account_id, direction, payment,
                        "Student Transaction", trans_id, particular,
                        self.vars["receipt"].get().strip(), self.vars["remarks"].get().strip(),
                    )
            self.db.transaction(callback)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def clear(self):
        for var in self.vars.values():
            var.set("")
        self.vars["date"].set(today_iso())
        self.vars["type"].set("Payment Received")
        self.vars["particular"].set("Fee payment")
        self.vars["charge"].set("0")
        self.vars["payment"].set("0")
        self.vars["discount"].set("0")
        self.vars["method"].set("Cash")

    def refresh(self):
        self.load_students()
        self.load_accounts_into(self.account_combo)
        self.clear_tree(self.tree)
        rows = self.db.query(
            """
            SELECT st.*, s.student_name, a.account_name
            FROM student_transactions st
            JOIN students s ON s.id=st.student_id
            LEFT JOIN accounts a ON a.id=st.account_id
            ORDER BY st.transaction_date DESC, st.id DESC
            """
        )
        for r in rows:
            self.tree.insert(
                "", "end",
                values=(r["id"], r["transaction_date"], r["student_name"],
                        r["transaction_type"], r["particular"], money(r["charge_amount"]),
                        money(r["payment_amount"]), money(r["discount_amount"]),
                        r["account_name"] or "")
            )


# ---------------------------------------------------------------------------
# Teachers
