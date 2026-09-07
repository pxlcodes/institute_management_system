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
        ttk.Label(self, text="Accounts & Payment Gateways", style="Title.TLabel").pack(anchor="w")

        form = self.create_form_dialog("Bank / Fonepay / Cash Account", padding=8)
        form.pack(fill="x", pady=8)
        self.vars = {
            "name": tk.StringVar(), "type": tk.StringVar(value="Cash Counter"),
            "bank": tk.StringVar(), "bank_code": tk.StringVar(), "number": tk.StringVar(),
            "holder": tk.StringVar(), "opening": tk.StringVar(value="0"),
            "is_billing_default": tk.BooleanVar(value=False),
            "qr_payload": tk.StringVar(),
            "status": tk.StringVar(value="Active"), "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        fb.entry("Account Name *", self.vars["name"])
        fb.combo(
            "Account Type", self.vars["type"],
            ["CURRENT ACCOUNT", "SAVINGS ACCOUNT", "Cash Counter", "Bank Account",
             "Mobile Wallet / Fonepay", "Personal Account", "Petty Cash", "Credit Account", "Other"]
        )
        fb.entry("Bank / Provider", self.vars["bank"])
        fb.entry("Bank Code (Fonepay/QR)", self.vars["bank_code"])
        fb.entry("Account Number", self.vars["number"])
        fb.entry("Account Holder", self.vars["holder"])
        fb.entry("Fonepay QR String (Optional)", self.vars["qr_payload"])
        fb.check("Use as Default Billing QR", self.vars["is_billing_default"])
        fb.entry("Opening Balance", self.vars["opening"])
        fb.combo("Status", self.vars["status"], ["Active", "Inactive"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form, style="Form.TFrame")
        buttons.grid(row=0, column=2, rowspan=12, padx=15, sticky="n")
        ttk.Button(buttons, text="Save New", command=self.save).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Update", command=self.update).pack(fill="x", pady=3)
        ttk.Button(buttons, text="⭐ Set as Default QR", style="Accent.TButton", command=self.set_default_billing_qr).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Delete", command=self.delete).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear", command=self.clear).pack(fill="x", pady=3)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 45), ("name", "Account Name", 180), ("type", "Type", 120),
                ("bank", "Bank / Provider", 120), ("bank_code", "Bank Code", 90),
                ("number", "Account No.", 140), ("qr_default", "Billing QR", 85),
                ("opening", "Opening", 85), ("balance", "Current Balance", 100),
                ("status", "Status", 70),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def values(self):
        name = self.vars["name"].get().strip()
        if not name:
            raise ValueError("Account name is required.")
        return (
            name, self.vars["type"].get(), self.vars["bank"].get().strip(),
            self.vars["bank_code"].get().strip(), self.vars["number"].get().strip(),
            self.vars["holder"].get().strip(),
            parse_amount(self.vars["opening"].get() or "0", "Opening balance"),
            1 if self.vars["is_billing_default"].get() else 0,
            self.vars["qr_payload"].get().strip(),
            self.vars["status"].get(), self.vars["remarks"].get().strip(),
        )

    def _sync_qr_settings_if_default(self, account_id: int):
        r = self.db.query_one("SELECT * FROM accounts WHERE id=?", (account_id,))
        if not r or not ("is_billing_default" in r.keys() and r["is_billing_default"]):
            return
        from elh.core.settings import SettingsService
        settings = SettingsService(self.db)
        if r["account_number"]:
            settings.set("payment_qr_account_number", str(r["account_number"]))
            settings.set("payment_qr_merchant_id", str(r["account_number"]))
        if "bank_code" in r.keys() and r["bank_code"]:
            settings.set("payment_qr_bank_code", str(r["bank_code"]))
        if "qr_payload" in r.keys() and r["qr_payload"]:
            settings.set("payment_qr_raw_payload", str(r["qr_payload"]).strip())
        merchant_label = str(r["account_holder"] or r["account_name"] or "").strip()
        if merchant_label:
            settings.set("payment_qr_merchant_name", merchant_label)

    def save(self):
        try:
            if self.vars["is_billing_default"].get():
                self.db.execute("UPDATE accounts SET is_billing_default=0")
            acc_id = self.db.execute(
                """
                INSERT INTO accounts
                (account_name, account_type, bank_name, bank_code, account_number,
                 account_holder, opening_balance, is_billing_default, qr_payload, status, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self.values(),
            )
            self._sync_qr_settings_if_default(acc_id)
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
            if self.vars["is_billing_default"].get():
                self.db.execute("UPDATE accounts SET is_billing_default=0 WHERE id != ?", (self.selected_id,))
            self.db.execute(
                """
                UPDATE accounts SET account_name=?, account_type=?, bank_name=?,
                bank_code=?, account_number=?, account_holder=?, opening_balance=?,
                is_billing_default=?, qr_payload=?, status=?, remarks=? WHERE id=?
                """,
                self.values() + (self.selected_id,),
            )
            self._sync_qr_settings_if_default(self.selected_id)
            self.clear()
            self.app.refresh_all()
        except sqlite3.IntegrityError:
            self.show_error(ValueError("Account name already exists."))
        except Exception as exc:
            self.show_error(exc)

    def set_default_billing_qr(self):
        if not self.selected_id:
            messagebox.showwarning("Default Billing QR", "Please select an account first.", parent=self)
            return
        try:
            self.db.execute("UPDATE accounts SET is_billing_default=0")
            self.db.execute("UPDATE accounts SET is_billing_default=1 WHERE id=?", (self.selected_id,))
            self._sync_qr_settings_if_default(self.selected_id)
            acc = self.db.query_one("SELECT * FROM accounts WHERE id=?", (self.selected_id,))
            acc_name = acc["account_name"] if acc else "Selected Account"
            messagebox.showinfo(
                "Default Billing QR",
                f"'{acc_name}' is now set as the active Billing QR account across all student bills and receipts.",
                parent=self,
            )
            self.refresh()
            self.app.refresh_all()
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
            if isinstance(v, tk.BooleanVar):
                v.set(False)
            else:
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
        self.vars["bank_code"].set(r["bank_code"] or "")
        self.vars["number"].set(r["account_number"] or "")
        self.vars["holder"].set(r["account_holder"] or "")
        self.vars["qr_payload"].set((r["qr_payload"] or "") if "qr_payload" in r.keys() else "")
        is_default = ("is_billing_default" in r.keys() and bool(r["is_billing_default"]))
        self.vars["is_billing_default"].set(is_default)
        self.vars["opening"].set(str(r["opening_balance"]))
        self.vars["status"].set(r["status"])
        self.vars["remarks"].set(r["remarks"] or "")
        self.show_form_dialog()

    def refresh(self):
        self.clear_tree(self.tree)
        for r in self.db.query("SELECT * FROM accounts ORDER BY is_billing_default DESC, account_name"):
            qr_label = "⭐ Active QR" if ("is_billing_default" in r.keys() and r["is_billing_default"]) else "-"
            self.tree.insert(
                "", "end",
                values=(
                    r["id"], r["account_name"], r["account_type"], r["bank_name"] or "",
                    r["bank_code"] or "", r["account_number"] or "", qr_label,
                    money(r["opening_balance"]), money(self.db.account_balance(r["id"])),
                    r["status"],
                ),
            )


# ---------------------------------------------------------------------------
# Income and expense generic page
