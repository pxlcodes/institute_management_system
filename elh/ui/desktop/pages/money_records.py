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

# Income and expense generic page
# ---------------------------------------------------------------------------

class MoneyRecordPage(CrudPage, AccountSelectionMixin):
    mode = "income"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.account_map = {}
        self.counterparty_map: dict[str, int] = {}
        title = "Income Records" if self.mode == "income" else "Expense Records"
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")

        form = self.create_form_dialog(title[:-1], padding=8)
        form.pack(fill="x", pady=8)
        self.vars = {
            "date": tk.StringVar(value=today_iso()),
            "category": tk.StringVar(),
            "particular": tk.StringVar(),
            "amount": tk.StringVar(value="0"),
            "account": tk.StringVar(),
            "party": tk.StringVar(),
            "counterparty": tk.StringVar(),
            "payment_status": tk.StringVar(value="Paid"),
            "method": tk.StringVar(value="Cash"),
            "reference": tk.StringVar(),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        fb.entry("Date *", self.vars["date"])
        categories = (
            ["Student Fee", "Admission Fee", "Registration Fee", "Training Income",
             "Sale of Materials", "Donation", "Interest Income", "Other Income"]
            if self.mode == "income"
            else ["Teacher Salary", "Teacher Advance", "Office Rent", "Electricity",
                  "Internet", "Stationery", "Printing", "Advertisement", "Maintenance",
                  "Transportation", "Equipment Purchase", "Bank Charge", "Other Expense"]
        )
        fb.combo("Category *", self.vars["category"], categories, state="normal")
        fb.entry("Particular *", self.vars["particular"])
        fb.entry("Amount *", self.vars["amount"])
        account_label = "Received In Account *" if self.mode == "income" else "Paid From Account *"
        self.account_combo = fb.combo(account_label, self.vars["account"], [])
        party_label = "Received From" if self.mode == "income" else "Paid To"
        fb.entry(party_label, self.vars["party"])
        if self.mode == "expense":
            self.counterparty_combo = fb.combo(
                "Payee / Vendor Account", self.vars["counterparty"], [], searchable=True
            )
            status_combo = fb.combo("Payment Status", self.vars["payment_status"], ["Paid", "Credit"])
            status_combo.bind("<<ComboboxSelected>>", self.payment_status_changed, add="+")
        fb.combo("Payment Method", self.vars["method"], ["Cash", "Bank", "Wallet", "Other"])
        fb.entry("Reference No.", self.vars["reference"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        ttk.Button(form, text=f"Save {title[:-1]}", command=self.save).grid(
            row=0, column=2, padx=15, pady=3, sticky="new"
        )
        ttk.Button(form, text="Clear", command=self.clear).grid(
            row=1, column=2, padx=15, pady=3, sticky="new"
        )
        if self.mode == "expense":
            ttk.Button(self.page_toolbar, text="Manage Payees / Vendors", command=self.manage_counterparties).pack(side="left", padx=4)
            ttk.Button(self.page_toolbar, text="Pay Vendor Credit", style="Accent.TButton", command=self.pay_credit).pack(side="left", padx=4)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("date", "Date", 95), ("category", "Category", 140),
                ("particular", "Particular", 190), ("amount", "Amount", 100),
                ("account", "Account", 150), ("party", party_label, 140),
                ("reference", "Reference", 100),
            ],
        )

    def save(self):
        try:
            record_date = validate_date(self.vars["date"].get())
            category = self.vars["category"].get().strip()
            particular = self.vars["particular"].get().strip()
            if not category or not particular:
                raise ValueError("Category and particular are required.")
            amount = parse_amount(self.vars["amount"].get(), "Amount", allow_zero=False)
            payment_status = self.vars["payment_status"].get() if self.mode == "expense" else "Paid"
            if self.mode == "expense" and payment_status == "Credit":
                if not self.vars["counterparty"].get() in self.counterparty_map:
                    raise ValueError("Select a Payee / Vendor Account for a credit purchase.")
                account_id = self.payable_account_id()
            else:
                account_id = self.selected_account_id(self.vars["account"].get())
            if self.mode == "expense" and payment_status == "Paid":
                self.require_sufficient_balance(account_id, amount)

            table = "income_records" if self.mode == "income" else "expense_records"
            account_field = (
                "received_in_account_id" if self.mode == "income" else "paid_from_account_id"
            )
            party_field = "received_from" if self.mode == "income" else "paid_to"
            source = "Income" if self.mode == "income" else "Expense"
            direction = "IN" if self.mode == "income" else "OUT"

            def callback(conn):
                if self.mode == "expense":
                    cur = conn.execute(
                        """
                        INSERT INTO expense_records
                        (expense_date,category,particular,amount,paid_from_account_id,paid_to,
                         counterparty_id,payment_status,payment_method,reference_no,remarks)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            record_date, category, particular, amount, account_id,
                            self.vars["party"].get().strip(),
                            self.counterparty_map.get(self.vars["counterparty"].get()),
                            payment_status, self.vars["method"].get(),
                            self.vars["reference"].get().strip(), self.vars["remarks"].get().strip(),
                        ),
                    )
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO income_records
                        (income_date,category,particular,amount,received_in_account_id,
                         received_from,payment_method,reference_no,remarks)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record_date, category, particular, amount, account_id,
                            self.vars["party"].get().strip(), self.vars["method"].get(),
                            self.vars["reference"].get().strip(), self.vars["remarks"].get().strip(),
                        ),
                    )
                self.db.add_ledger(
                    conn, record_date, account_id, direction, amount, source,
                    cur.lastrowid, particular, self.vars["reference"].get().strip(),
                    self.vars["remarks"].get().strip()
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
        self.vars["payment_status"].set("Paid")

    def refresh(self):
        self.load_accounts_into(self.account_combo)
        if self.mode == "expense":
            self.load_counterparties()
        self.clear_tree(self.tree)
        if self.mode == "income":
            rows = self.db.query(
                """
                SELECT r.*, a.account_name
                FROM income_records r JOIN accounts a ON a.id=r.received_in_account_id
                ORDER BY income_date DESC, r.id DESC
                """
            )
            for r in rows:
                self.tree.insert(
                    "", "end",
                    values=(r["id"], r["income_date"], r["category"], r["particular"],
                            money(r["amount"]), r["account_name"], r["received_from"],
                            r["reference_no"])
                )
        else:
            rows = self.db.query(
                """
                SELECT r.*, a.account_name, COALESCE(c.counterparty_name,r.paid_to,'') payee_name
                FROM expense_records r JOIN accounts a ON a.id=r.paid_from_account_id
                LEFT JOIN counterparties c ON c.id=r.counterparty_id
                ORDER BY expense_date DESC, r.id DESC
                """
            )
            for r in rows:
                self.tree.insert(
                    "", "end",
                    values=(r["id"], r["expense_date"], r["category"], r["particular"],
                            money(r["amount"]), r["account_name"], r["payee_name"],
                            r["reference_no"])
                )

    def payable_account_id(self) -> int:
        row = self.db.query_one("SELECT id FROM accounts WHERE account_name='Accounts Payable Clearing'")
        if row:
            return int(row["id"])
        return int(self.db.execute(
            "INSERT INTO accounts (account_name,account_type,opening_balance,status,remarks) VALUES (?,?,?,?,?)",
            ("Accounts Payable Clearing", "Credit Account", 0, "Active", "System account for vendor credit purchases"),
        ))

    def load_counterparties(self):
        rows = self.db.query(
            "SELECT id,counterparty_name,counterparty_type FROM counterparties "
            "WHERE status='Active' ORDER BY counterparty_name"
        )
        self.counterparty_map = {
            f"{row['counterparty_name']} [{row['counterparty_type']}] (ID: {row['id']})": int(row["id"])
            for row in rows
        }
        self.counterparty_combo.set_values(self.counterparty_map)

    def payment_status_changed(self, _event=None):
        if self.vars["payment_status"].get() == "Credit":
            account_id = self.payable_account_id()
            self.load_accounts_into(self.account_combo)
            label = next((key for key, value in self.account_map.items() if value == account_id), "Accounts Payable Clearing")
            self.vars["account"].set(label)

    def manage_counterparties(self):
        dialog = tk.Toplevel(self)
        dialog.title("Payees & Vendors")
        dialog.transient(self.winfo_toplevel())
        dialog.minsize(760, 470)
        shell = ttk.Frame(dialog, padding=12, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        values = {key: tk.StringVar() for key in ("name", "type", "contact", "address", "remarks")}
        values["type"].set("Vendor")
        form = ttk.Frame(shell, style="Form.TFrame")
        form.pack(fill="x")
        fb = FormBuilder(form)
        fb.entry("Name *", values["name"])
        fb.combo("Type", values["type"], ["Vendor", "Landlord", "Staff", "Other"])
        fb.entry("Contact", values["contact"])
        fb.entry("Address", values["address"])
        fb.entry("Remarks", values["remarks"])
        def add_party():
            name = values["name"].get().strip()
            if not name:
                messagebox.showerror("Payee / Vendor", "Name is required.", parent=dialog); return
            try:
                self.db.execute(
                    "INSERT INTO counterparties (counterparty_name,counterparty_type,contact,address,status,remarks) VALUES (?,?,?,?, 'Active',?)",
                    (name, values["type"].get(), values["contact"].get().strip(), values["address"].get().strip(), values["remarks"].get().strip()),
                )
                for value in values.values(): value.set("")
                values["type"].set("Vendor")
                refresh_parties()
                self.load_counterparties()
            except sqlite3.IntegrityError:
                messagebox.showerror("Payee / Vendor", "A payee or vendor with this name already exists.", parent=dialog)
        ttk.Button(form, text="Add Payee / Vendor", style="Accent.TButton", command=add_party).grid(row=0, column=2, padx=12, sticky="n")
        table = ttk.Frame(shell); table.pack(fill="both", expand=True, pady=(12, 0))
        tree = ttk.Treeview(table, columns=("name", "type", "paid", "credit", "balance"), show="headings")
        for key, title, width in (("name", "Payee / Vendor", 240), ("type", "Type", 100), ("paid", "Paid", 110), ("credit", "Credit Purchases", 130), ("balance", "Credit Due", 110)):
            tree.heading(key, text=title); tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        def refresh_parties():
            tree.delete(*tree.get_children())
            rows = self.db.query("""
                SELECT c.*,COALESCE((SELECT SUM(e.amount) FROM expense_records e WHERE e.counterparty_id=c.id AND e.payment_status='Paid'),0) paid,
                COALESCE((SELECT SUM(e.amount) FROM expense_records e WHERE e.counterparty_id=c.id AND e.payment_status='Credit'),0) credit,
                COALESCE((SELECT SUM(p.amount) FROM counterparty_payments p WHERE p.counterparty_id=c.id),0) settled
                FROM counterparties c ORDER BY c.counterparty_name
            """)
            for row in rows:
                due = float(row["credit"])-float(row["settled"])
                tree.insert("", "end", values=(row["counterparty_name"], row["counterparty_type"], money(float(row["paid"])+float(row["settled"])), money(row["credit"]), money(due)))
        refresh_parties()
        ttk.Button(shell, text="Close", command=dialog.destroy).pack(anchor="e", pady=(8, 0))
        dialog.grab_set()

    def pay_credit(self):
        if not self.counterparty_map:
            self.show_error(ValueError("Add a Payee / Vendor first.")); return
        dialog = tk.Toplevel(self); dialog.title("Pay Vendor Credit"); dialog.transient(self.winfo_toplevel())
        form = ttk.Frame(dialog, padding=12, style="Form.TFrame"); form.pack(fill="both", expand=True)
        values = {"party": tk.StringVar(), "amount": tk.StringVar(value="0"), "date": tk.StringVar(value=today_iso()), "account": tk.StringVar(), "method": tk.StringVar(value="Cash"), "reference": tk.StringVar(), "remarks": tk.StringVar()}
        fb = FormBuilder(form)
        fb.combo("Payee / Vendor *", values["party"], list(self.counterparty_map), searchable=True)
        fb.entry("Amount *", values["amount"]); fb.entry("Payment Date *", values["date"])
        account_combo = fb.combo("Paid From Account *", values["account"], [])
        self.load_accounts_into(account_combo)
        fb.combo("Payment Method", values["method"], ["Cash", "Bank", "Wallet", "Other"]); fb.entry("Reference No.", values["reference"]); fb.entry("Remarks", values["remarks"])
        def save_payment():
            try:
                counterparty_id = self.counterparty_map.get(values["party"].get())
                if not counterparty_id: raise ValueError("Select a Payee / Vendor.")
                amount = parse_amount(values["amount"].get(), "Amount", allow_zero=False)
                account_id = self.selected_account_id(values["account"].get())
                self.require_sufficient_balance(account_id, amount)
                payable_id = self.payable_account_id()
                due = self.db.query_one("SELECT COALESCE(SUM(e.amount),0)-COALESCE((SELECT SUM(p.amount) FROM counterparty_payments p WHERE p.counterparty_id=?),0) due FROM expense_records e WHERE e.counterparty_id=? AND e.payment_status='Credit'", (counterparty_id,counterparty_id))
                if amount > float(due["due"]): raise ValueError(f"Payment exceeds credit due of {money(due['due'])}.")
                payment_date = validate_date(values["date"].get())
                def callback(conn):
                    cur = conn.execute("INSERT INTO counterparty_payments (counterparty_id,payment_date,amount,paid_from_account_id,payment_method,reference_no,remarks) VALUES (?,?,?,?,?,?,?)", (counterparty_id,payment_date,amount,account_id,values["method"].get(),values["reference"].get().strip(),values["remarks"].get().strip()))
                    payment_id = cur.lastrowid
                    self.db.add_ledger(conn,payment_date,account_id,"OUT",amount,"Vendor Credit Payment",payment_id,values["party"].get(),values["reference"].get().strip(),values["remarks"].get().strip())
                    self.db.add_ledger(conn,payment_date,payable_id,"IN",amount,"Vendor Credit Payment",payment_id,values["party"].get(),values["reference"].get().strip(),values["remarks"].get().strip())
                self.db.transaction(callback); dialog.destroy(); self.app.refresh_all()
            except Exception as exc: messagebox.showerror("Credit Payment", str(exc), parent=dialog)
        ttk.Button(form, text="Pay Credit", style="Accent.TButton", command=save_payment).grid(row=0,column=2,rowspan=2,padx=12,sticky="n")
        dialog.grab_set()


class IncomePage(MoneyRecordPage):
    mode = "income"


class ExpensePage(MoneyRecordPage):
    mode = "expense"


# ---------------------------------------------------------------------------
# Transfers
