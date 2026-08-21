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
from elh.ui.desktop.pages.attendance_selection import (
    attendance_user_choices,
    selected_attendance_device,
)

# Teachers
# ---------------------------------------------------------------------------

class TeachersPage(CrudPage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id = None
        self.attendance_user_map: dict[str, str] = {}
        ttk.Label(self, text="Staff Records", style="Title.TLabel").pack(anchor="w")

        form = self.create_form_dialog("Staff Details", padding=8)
        form.pack(fill="x", pady=8)
        keys = [
            "name", "staff_type", "contact", "address", "email", "qualification", "subject",
            "joined", "salary_type", "basic_salary", "bank_no", "holder",
            "bank", "attendance", "status", "remarks"
        ]
        self.vars = {k: tk.StringVar() for k in keys}
        self.vars["joined"].set(today_iso())
        self.vars["staff_type"].set("Teaching")
        self.vars["salary_type"].set("Monthly Salary")
        self.vars["basic_salary"].set("0")
        self.vars["status"].set("Active")

        fb = FormBuilder(form)
        fb.entry("Staff Name *", self.vars["name"])
        fb.combo("Staff Type *", self.vars["staff_type"], ["Teaching", "Non-Teaching"])
        self.attendance_combo = fb.combo(
            "Attendance Device User (optional)",
            self.vars["attendance"],
            [],
            searchable=True,
        )
        fb.entry("Contact", self.vars["contact"])
        fb.entry("Address", self.vars["address"])
        fb.entry("Email", self.vars["email"])
        fb.entry("Qualification", self.vars["qualification"])
        fb.entry("Subject", self.vars["subject"])
        fb.entry("Joined Date *", self.vars["joined"])
        fb.combo(
            "Salary Type", self.vars["salary_type"],
            ["Monthly Salary", "Hourly Salary", "Per Class Payment",
             "Percentage Based", "Fixed Contract"]
        )
        fb.entry("Basic Salary / Rate", self.vars["basic_salary"])
        fb.entry("Bank Account No.", self.vars["bank_no"])
        fb.entry("Account Holder", self.vars["holder"])
        fb.entry("Bank Name", self.vars["bank"])
        fb.combo("Status", self.vars["status"], ["Active", "Inactive"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form, style="Form.TFrame")
        buttons.grid(row=0, column=2, rowspan=16, padx=15, sticky="n")
        ttk.Button(buttons, text="Save New", command=self.save).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Update", command=self.update).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Delete", command=self.delete).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear", command=self.clear).pack(fill="x", pady=3)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("name", "Staff Name", 170), ("staff_type", "Staff Type", 110), ("contact", "Contact", 110),
                ("subject", "Subject", 130), ("joined", "Joined", 95),
                ("type", "Salary Type", 130), ("salary", "Basic Salary", 100),
                ("attendance", "Attendance User", 180),
                ("status", "Status", 80),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        ttk.Button(
            self.page_toolbar,
            text="Staff Payment Summary",
            command=self.show_payment_summary,
        ).pack(side="left", padx=4)

    def values(self):
        if not self.vars["name"].get().strip():
            raise ValueError("Staff name is required.")
        return (
            self.vars["name"].get().strip(),
            self.vars["staff_type"].get(),
            normalize_phone(self.vars["contact"].get()),
            self.vars["address"].get().strip(),
            self.vars["email"].get().strip(),
            self.vars["qualification"].get().strip(),
            self.vars["subject"].get().strip(),
            validate_date(self.vars["joined"].get(), "Joined date"),
            self.vars["salary_type"].get(),
            parse_amount(self.vars["basic_salary"].get() or "0", "Basic salary"),
            self.vars["bank_no"].get().strip(),
            self.vars["holder"].get().strip(),
            self.vars["bank"].get().strip(),
            self.vars["status"].get(),
            self.vars["remarks"].get().strip(),
        )

    def save(self):
        try:
            device_user_id = selected_attendance_device(
                self.vars["attendance"].get(), self.attendance_user_map
            )
            teacher_id = self.db.execute(
                """
                INSERT INTO teachers
                (teacher_name, staff_type, contact, address, email, qualification, subject,
                 joined_date, salary_type, basic_salary, bank_account_number,
                 account_holder_name, bank_name, status, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self.values(),
            )
            self.app.services.attendance.assign_person_device(
                "teacher", teacher_id, device_user_id
            )
            self.app.services.staff_finance.sync_account(teacher_id)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def update(self):
        if not self.selected_id:
            return
        try:
            device_user_id = selected_attendance_device(
                self.vars["attendance"].get(), self.attendance_user_map
            )
            self.db.execute(
                """
                UPDATE teachers SET teacher_name=?, staff_type=?, contact=?, address=?, email=?,
                qualification=?, subject=?, joined_date=?, salary_type=?,
                basic_salary=?, bank_account_number=?, account_holder_name=?,
                bank_name=?, status=?, remarks=? WHERE id=?
                """,
                self.values() + (self.selected_id,),
            )
            self.app.services.attendance.assign_person_device(
                "teacher", self.selected_id, device_user_id
            )
            self.app.services.staff_finance.sync_account(self.selected_id)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def delete(self):
        if self.selected_id and self.confirm_delete():
            try:
                self.db.execute("DELETE FROM teachers WHERE id=?", (self.selected_id,))
                self.clear()
                self.app.refresh_all()
            except sqlite3.IntegrityError:
                self.show_error(ValueError("This staff member has payroll records and cannot be deleted."))

    def clear(self):
        self.selected_id = None
        for var in self.vars.values():
            var.set("")
        self.vars["joined"].set(today_iso())
        self.vars["staff_type"].set("Teaching")
        self.vars["salary_type"].set("Monthly Salary")
        self.vars["basic_salary"].set("0")
        self.vars["status"].set("Active")
        self.vars["attendance"].set("")
        if hasattr(self, "attendance_combo"):
            self.attendance_user_map, _current = attendance_user_choices(
                self.app, "teacher"
            )
            self.attendance_combo["values"] = list(self.attendance_user_map)

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        row_id = int(self.tree.item(selected[0], "values")[0])
        r = self.db.query_one("SELECT * FROM teachers WHERE id=?", (row_id,))
        if not r:
            return
        self.selected_id = row_id
        self.attendance_user_map, current_attendance = attendance_user_choices(
            self.app, "teacher", row_id
        )
        self.attendance_combo["values"] = list(self.attendance_user_map)
        mapping = {
            "name": "teacher_name", "staff_type": "staff_type", "contact": "contact", "address": "address",
            "email": "email", "qualification": "qualification", "subject": "subject",
            "joined": "joined_date", "salary_type": "salary_type",
            "basic_salary": "basic_salary", "bank_no": "bank_account_number",
            "holder": "account_holder_name", "bank": "bank_name",
            "status": "status", "remarks": "remarks",
        }
        for key, db_key in mapping.items():
            self.vars[key].set(r[db_key] if r[db_key] is not None else "")
        self.vars["attendance"].set(current_attendance)
        self.show_form_dialog()

    def refresh(self):
        self.attendance_user_map, _current = attendance_user_choices(self.app, "teacher")
        self.attendance_combo["values"] = list(self.attendance_user_map)
        self.clear_tree(self.tree)
        rows = self.db.query("""
            SELECT t.*,m.device_user_id,u.device_name
            FROM teachers t
            LEFT JOIN (
                SELECT person_id,MIN(id) mapping_id FROM device_user_mappings
                WHERE person_type='teacher' AND status='Active' GROUP BY person_id
            ) selected_mapping ON selected_mapping.person_id=t.id
            LEFT JOIN device_user_mappings m ON m.id=selected_mapping.mapping_id
            LEFT JOIN attendance_device_users u ON u.device_user_id=m.device_user_id
            ORDER BY t.teacher_name
        """)
        for r in rows:
            attendance_user = ""
            if r["device_user_id"]:
                attendance_user = f"{r['device_user_id']} - {r['device_name'] or 'Unnamed'}"
            self.tree.insert(
                "", "end",
                values=(r["id"], r["teacher_name"], r["staff_type"], r["contact"], r["subject"],
                        r["joined_date"], r["salary_type"], money(r["basic_salary"]),
                        attendance_user, r["status"])
            )

    def show_payment_summary(self):
        if not self.selected_id:
            messagebox.showwarning("Staff Payment Summary", "Select a staff member first.", parent=self)
            return
        staff = self.db.query_one("SELECT teacher_name FROM teachers WHERE id=?", (self.selected_id,))
        summary = self.db.query_one(
            """
            SELECT
              COALESCE((SELECT SUM(net_salary) FROM salary_payouts WHERE teacher_id=?),0) salary_paid,
              COALESCE((SELECT SUM(amount) FROM teacher_advances WHERE teacher_id=?),0) advances_paid,
              COALESCE((SELECT SUM(recovered_amount) FROM teacher_advances WHERE teacher_id=?),0) advances_recovered
            """,
            (self.selected_id, self.selected_id, self.selected_id),
        )
        outstanding = float(summary["advances_paid"]) - float(summary["advances_recovered"])
        account, transactions = self.app.services.staff_finance.statement(self.selected_id)
        dialog = tk.Toplevel(self)
        dialog.title("Staff Payment Account Statement")
        dialog.transient(self.winfo_toplevel())
        dialog.minsize(860, 470)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        bank_detail = " | ".join(
            value for value in (account["bank_name"], account["account_holder"], account["account_number"]) if value
        ) or "No receiving bank details saved"
        ttk.Label(shell, text=f"{staff['teacher_name']} — {account['account_name']}", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(shell, text=f"Receiving details: {bank_detail}", style="Hint.TLabel").pack(anchor="w", pady=(2, 8))
        ttk.Label(
            shell,
            text=(f"Salary paid: {money(summary['salary_paid'])}    |    "
                  f"Advances paid: {money(summary['advances_paid'])}    |    "
                  f"Advance outstanding: {money(outstanding)}"),
            style="FormValue.TLabel",
        ).pack(anchor="w", pady=(0, 10))
        area = ttk.Frame(shell); area.pack(fill="both", expand=True)
        tree = self.make_tree(area, [
            ("date", "Date", 110), ("type", "Transaction", 150), ("amount", "Amount", 120),
            ("from", "Paid From", 160), ("reference", "Reference", 120), ("particular", "Particular", 250),
        ])
        for transaction in transactions:
            tree.insert("", "end", values=(
                transaction["transaction_date"], transaction["transaction_type"],
                money(transaction["amount"]), transaction["paid_from"] or "",
                transaction["reference_no"] or "", transaction["particular"],
            ))
        ttk.Button(shell, text="Close", command=dialog.destroy).pack(anchor="e", pady=(10, 0))
        dialog.grab_set()


# ---------------------------------------------------------------------------
# Teacher Advances
