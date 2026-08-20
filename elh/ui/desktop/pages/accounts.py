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

# Accounts
# ---------------------------------------------------------------------------

class AccountsPage(CrudPage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id = None
        ttk.Label(self, text="Accounts", style="Title.TLabel").pack(anchor="w")

        form = self.create_form_dialog("Bank / Cash / Personal Account", padding=8)
        form.pack(fill="x", pady=8)
        self.vars = {
            "name": tk.StringVar(), "type": tk.StringVar(value="Cash Counter"),
            "bank": tk.StringVar(), "number": tk.StringVar(), "holder": tk.StringVar(),
            "opening": tk.StringVar(value="0"), "status": tk.StringVar(value="Active"),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        fb.entry("Account Name *", self.vars["name"])
        fb.combo(
            "Account Type", self.vars["type"],
            ["Cash Counter", "Bank Account", "Personal Account", "Mobile Wallet",
             "Petty Cash", "Credit Account", "Other"]
        )
        fb.entry("Bank / Provider", self.vars["bank"])
        fb.entry("Account Number", self.vars["number"])
        fb.entry("Account Holder", self.vars["holder"])
        fb.entry("Opening Balance", self.vars["opening"])
        fb.combo("Status", self.vars["status"], ["Active", "Inactive"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form, style="Form.TFrame")
        buttons.grid(row=0, column=2, rowspan=8, padx=15, sticky="n")
        ttk.Button(buttons, text="Save New", command=self.save).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Update", command=self.update).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Delete", command=self.delete).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear", command=self.clear).pack(fill="x", pady=3)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("name", "Account Name", 190), ("type", "Type", 130),
                ("bank", "Bank / Provider", 140), ("number", "Account No.", 130),
                ("opening", "Opening", 95), ("balance", "Current Balance", 110),
                ("status", "Status", 80),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def values(self):
        name = self.vars["name"].get().strip()
        if not name:
            raise ValueError("Account name is required.")
        return (
            name, self.vars["type"].get(), self.vars["bank"].get().strip(),
            self.vars["number"].get().strip(), self.vars["holder"].get().strip(),
            parse_amount(self.vars["opening"].get() or "0", "Opening balance"),
            self.vars["status"].get(), self.vars["remarks"].get().strip(),
        )

    def save(self):
        try:
            self.db.execute(
                """
                INSERT INTO accounts
                (account_name, account_type, bank_name, account_number,
                 account_holder, opening_balance, status, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self.values(),
            )
            self.clear()
            self.app.refresh_all()
        except sqlite3.IntegrityError:
            self.show_error(ValueError("Account name already exists."))
        except Exception as exc:
            self.show_error(exc)

    def update(self):
        if not self.selected_id:
            return
        try:
            self.db.execute(
                """
                UPDATE accounts SET account_name=?, account_type=?, bank_name=?,
                account_number=?, account_holder=?, opening_balance=?, status=?,
                remarks=? WHERE id=?
                """,
                self.values() + (self.selected_id,),
            )
            self.clear()
            self.app.refresh_all()
        except sqlite3.IntegrityError:
            self.show_error(ValueError("Account name already exists."))
        except Exception as exc:
            self.show_error(exc)

    def delete(self):
        if self.selected_id and self.confirm_delete():
            try:
                self.db.execute("DELETE FROM accounts WHERE id=?", (self.selected_id,))
                self.clear()
                self.app.refresh_all()
            except sqlite3.IntegrityError:
                self.show_error(ValueError("This account has transactions and cannot be deleted."))

    def clear(self):
        self.selected_id = None
        for v in self.vars.values():
            v.set("")
        self.vars["type"].set("Cash Counter")
        self.vars["opening"].set("0")
        self.vars["status"].set("Active")

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        row_id = int(self.tree.item(selected[0], "values")[0])
        r = self.db.query_one("SELECT * FROM accounts WHERE id=?", (row_id,))
        if not r:
            return
        self.selected_id = row_id
        self.vars["name"].set(r["account_name"])
        self.vars["type"].set(r["account_type"])
        self.vars["bank"].set(r["bank_name"] or "")
        self.vars["number"].set(r["account_number"] or "")
        self.vars["holder"].set(r["account_holder"] or "")
        self.vars["opening"].set(str(r["opening_balance"]))
        self.vars["status"].set(r["status"])
        self.vars["remarks"].set(r["remarks"] or "")
        self.show_form_dialog()

    def refresh(self):
        self.clear_tree(self.tree)
        for r in self.db.query("SELECT * FROM accounts ORDER BY account_name"):
            self.tree.insert(
                "", "end",
                values=(r["id"], r["account_name"], r["account_type"], r["bank_name"],
                        r["account_number"], money(r["opening_balance"]),
                        money(self.db.account_balance(r["id"])), r["status"])
            )


# ---------------------------------------------------------------------------
# Income and expense generic page
