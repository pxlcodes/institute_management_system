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

# Transfers
# ---------------------------------------------------------------------------

class TransfersPage(CrudPage, AccountSelectionMixin):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.account_map = {}

        ttk.Label(self, text="Account Transfers", style="Title.TLabel").pack(anchor="w")
        form = self.create_form_dialog("Transfer Money", padding=8)
        form.pack(fill="x", pady=8)

        self.vars = {
            "date": tk.StringVar(value=today_iso()), "from": tk.StringVar(),
            "to": tk.StringVar(), "amount": tk.StringVar(value="0"),
            "charge": tk.StringVar(value="0"), "reference": tk.StringVar(),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        fb.entry("Transfer Date *", self.vars["date"])
        self.from_combo = fb.combo("From Account *", self.vars["from"], [])
        self.to_combo = fb.combo("To Account *", self.vars["to"], [])
        fb.entry("Amount *", self.vars["amount"])
        fb.entry("Transfer Charge", self.vars["charge"])
        fb.entry("Reference No.", self.vars["reference"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        ttk.Button(form, text="Transfer", command=self.save).grid(
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
                ("id", "ID", 50), ("date", "Date", 95), ("from", "From Account", 160),
                ("to", "To Account", 160), ("amount", "Amount", 100),
                ("charge", "Charge", 85), ("reference", "Reference", 110),
            ],
        )

    def save(self):
        try:
            trans_date = validate_date(self.vars["date"].get())
            from_id = self.selected_account_id(self.vars["from"].get())
            to_id = self.selected_account_id(self.vars["to"].get())
            if from_id == to_id:
                raise ValueError("From and To accounts must be different.")
            amount = parse_amount(self.vars["amount"].get(), "Amount", allow_zero=False)
            charge = parse_amount(self.vars["charge"].get() or "0", "Transfer charge")
            self.require_sufficient_balance(from_id, amount + charge)

            def callback(conn):
                cur = conn.execute(
                    """
                    INSERT INTO account_transfers
                    (transfer_date, from_account_id, to_account_id, amount,
                     transfer_charge, reference_no, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trans_date, from_id, to_id, amount, charge,
                        self.vars["reference"].get().strip(),
                        self.vars["remarks"].get().strip(),
                    ),
                )
                transfer_id = cur.lastrowid
                self.db.add_ledger(
                    conn, trans_date, from_id, "OUT", amount + charge,
                    "Account Transfer", transfer_id, "Transfer out",
                    self.vars["reference"].get().strip(), self.vars["remarks"].get().strip()
                )
                self.db.add_ledger(
                    conn, trans_date, to_id, "IN", amount,
                    "Account Transfer", transfer_id, "Transfer in",
                    self.vars["reference"].get().strip(), self.vars["remarks"].get().strip()
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
        self.vars["charge"].set("0")

    def refresh(self):
        rows = self.db.query(
            "SELECT id, account_name FROM accounts WHERE status='Active' ORDER BY account_name"
        )
        self.account_map = {f"{r['id']} - {r['account_name']}": r["id"] for r in rows}
        values = list(self.account_map)
        self.from_combo["values"] = values
        self.to_combo["values"] = values

        self.clear_tree(self.tree)
        rows = self.db.query(
            """
            SELECT tr.*, fa.account_name from_name, ta.account_name to_name
            FROM account_transfers tr
            JOIN accounts fa ON fa.id=tr.from_account_id
            JOIN accounts ta ON ta.id=tr.to_account_id
            ORDER BY tr.transfer_date DESC, tr.id DESC
            """
        )
        for r in rows:
            self.tree.insert(
                "", "end",
                values=(r["id"], r["transfer_date"], r["from_name"], r["to_name"],
                        money(r["amount"]), money(r["transfer_charge"]), r["reference_no"])
            )


# ---------------------------------------------------------------------------
# Ledger
