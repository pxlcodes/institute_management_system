from __future__ import annotations

import csv
import sqlite3
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Iterable, Optional

from elh.models import Student
from elh.ui.desktop.helpers import current_month, money, normalize_phone, parse_amount, today_iso, validate_date, validate_month
from elh.ui.desktop.components import BasePage, CrudPage, FormBuilder, ScrollableFrame
from elh.ui.desktop.pages.account_selection import AccountSelectionMixin
from elh.ui.desktop.pages.payment_proof import PaymentProofMixin

# Salary
# ---------------------------------------------------------------------------

class SalaryPage(CrudPage, AccountSelectionMixin, PaymentProofMixin):
    proof_kind="salary"
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.teacher_map = {}
        self.account_map = {}

        ttk.Label(self, text="Salary Payouts", style="Title.TLabel").pack(anchor="w")
        form = self.create_form_dialog("Salary Payment", padding=8)
        form.pack(fill="x", pady=8)

        self.vars = {
            "teacher": tk.StringVar(), "month": tk.StringVar(value=current_month()),
            "attendance_days": tk.StringVar(value="0"),
            "working_hours": tk.StringVar(value="0"),
            "basic": tk.StringVar(value="0"), "extra": tk.StringVar(value="0"),
            "bonus": tk.StringVar(value="0"), "allowance": tk.StringVar(value="0"),
            "advance": tk.StringVar(value="0"), "other": tk.StringVar(value="0"),
            "date": tk.StringVar(value=today_iso()), "account": tk.StringVar(),
            "method": tk.StringVar(value="Bank"), "voucher": tk.StringVar(),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.teacher_combo = fb.combo(
            "Staff Member *", self.vars["teacher"], [], searchable=True
        )
        self.teacher_combo.bind("<<ComboboxSelected>>", self.teacher_selected)
        self.month_entry = fb.entry("Salary Month (YYYY/MM) *", self.vars["month"])
        self.month_entry.bind("<FocusOut>", lambda _event: self.calculate_attendance(silent=True))
        fb.entry("Attendance Days (optional)", self.vars["attendance_days"])
        fb.entry("Working Hours (optional)", self.vars["working_hours"])
        fb.entry("Basic Salary", self.vars["basic"])
        fb.entry("Extra Payment", self.vars["extra"])
        fb.entry("Bonus", self.vars["bonus"])
        fb.entry("Allowance", self.vars["allowance"])
        fb.entry("Advance Deduction", self.vars["advance"])
        fb.entry("Other Deduction", self.vars["other"])
        fb.entry("Payment Date *", self.vars["date"])
        self.account_combo = fb.combo("Paid From Account *", self.vars["account"], [])
        fb.combo("Payment Method", self.vars["method"], ["Cash", "Bank", "Wallet", "Other"])
        fb.entry("Voucher No.", self.vars["voucher"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        self.attendance_label = ttk.Label(
            form,
            text="Attendance reference: not calculated",
            style="Hint.TLabel",
            wraplength=300,
        )
        self.attendance_label.grid(row=0, column=2, padx=15, pady=3, sticky="w")
        self.net_label = ttk.Label(form, text="Net Salary: 0.00", style="FormValue.TLabel")
        self.net_label.grid(row=1, column=2, padx=15, pady=3, sticky="w")
        ttk.Button(
            form,
            text="Calculate Attendance",
            command=self.calculate_attendance,
        ).grid(row=2, column=2, padx=15, pady=3, sticky="ew")
        ttk.Button(
            form,
            text="Apply Attendance Estimate",
            command=self.apply_attendance_estimate,
        ).grid(row=3, column=2, padx=15, pady=3, sticky="ew")
        ttk.Button(form, text="Calculate Net", command=self.calculate_net).grid(
            row=4, column=2, padx=15, pady=3, sticky="ew"
        )
        ttk.Button(form, text="Pay Salary", command=self.save).grid(
            row=5, column=2, padx=15, pady=3, sticky="ew"
        )
        ttk.Button(form, text="Clear", command=self.clear).grid(
            row=6, column=2, padx=15, pady=3, sticky="ew"
        )

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("month", "Month", 85), ("teacher", "Staff Member", 170),
                ("days", "Present Days", 90), ("hours", "Working Hours", 95),
                ("gross", "Gross", 95), ("deduction", "Deductions", 100),
                ("net", "Net Salary", 100), ("date", "Paid Date", 95),
                ("account", "Paid From", 140),
            ],
        )
        self.add_payment_proof_buttons(self)

    def teacher_selected(self, _event=None):
        teacher_id = self.teacher_map.get(self.vars["teacher"].get())
        if teacher_id:
            row = self.db.query_one("SELECT basic_salary FROM teachers WHERE id=?", (teacher_id,))
            self.vars["basic"].set(str(row["basic_salary"]))
            self.calculate_attendance(silent=True)

    def calculate_attendance(self, _event=None, silent=False):
        try:
            teacher_id = self.teacher_map.get(self.vars["teacher"].get())
            if not teacher_id:
                raise ValueError("Please select a staff member.")
            month = validate_month(self.vars["month"].get().strip(), "Salary month")
            summary = self.app.services.attendance.staff_month_summary(teacher_id, month)
            self.vars["attendance_days"].set(str(summary["days"]))
            self.vars["working_hours"].set(f"{summary['hours']:.2f}")
            self.attendance_label.configure(
                text=(
                    f"Attendance reference: {summary['days']} present days, "
                    f"{summary['hours']:.2f} working hours, {summary['punches']} punches. "
                    f"Estimate uses {summary['calendar_days']} calendar days; it is optional."
                )
            )
            return summary
        except Exception as exc:
            if not silent:
                self.show_error(exc)
            return None

    def apply_attendance_estimate(self):
        """Offer a prorated basic salary without changing the payroll policy automatically."""
        try:
            summary = self.calculate_attendance(silent=False)
            if not summary:
                return
            entered_basic = parse_amount(self.vars["basic"].get() or "0", "Basic salary")
            if entered_basic <= 0:
                raise ValueError("Enter the full-month basic salary first.")
            estimated = round(entered_basic * summary["days"] / summary["calendar_days"], 2)
            self.vars["basic"].set(f"{estimated:.2f}")
            self.attendance_label.configure(
                text=(
                    f"Attendance estimate applied: {summary['days']} / {summary['calendar_days']} days = "
                    f"{estimated:,.2f} basic salary. You may edit this before payment."
                )
            )
            self.calculate_net()
        except Exception as exc:
            self.show_error(exc)

    def attendance_values(self) -> tuple[int, float]:
        days = parse_amount(
            self.vars["attendance_days"].get() or "0", "Attendance days"
        )
        if not float(days).is_integer():
            raise ValueError("Attendance days must be a whole number.")
        hours = parse_amount(
            self.vars["working_hours"].get() or "0", "Working hours"
        )
        return int(days), hours

    def calculate_net(self) -> float:
        try:
            basic = parse_amount(self.vars["basic"].get() or "0", "Basic salary")
            extra = parse_amount(self.vars["extra"].get() or "0", "Extra payment")
            bonus = parse_amount(self.vars["bonus"].get() or "0", "Bonus")
            allowance = parse_amount(self.vars["allowance"].get() or "0", "Allowance")
            advance = parse_amount(self.vars["advance"].get() or "0", "Advance deduction")
            other = parse_amount(self.vars["other"].get() or "0", "Other deduction")
            attendance_days, working_hours = self.attendance_values()
            net = basic + extra + bonus + allowance - advance - other
            if net < 0:
                raise ValueError("Net salary cannot be negative.")
            self.net_label.config(text=f"Net Salary: {money(net)}")
            return round(net, 2)
        except Exception as exc:
            self.show_error(exc)
            raise

    def save(self):
        try:
            teacher_id = self.teacher_map.get(self.vars["teacher"].get())
            if not teacher_id:
                raise ValueError("Please select a staff member.")
            month = self.vars["month"].get().strip()
            month=validate_month(month,"Salary month")
            basic = parse_amount(self.vars["basic"].get() or "0", "Basic salary")
            extra = parse_amount(self.vars["extra"].get() or "0", "Extra payment")
            bonus = parse_amount(self.vars["bonus"].get() or "0", "Bonus")
            allowance = parse_amount(self.vars["allowance"].get() or "0", "Allowance")
            advance = parse_amount(self.vars["advance"].get() or "0", "Advance deduction")
            other = parse_amount(self.vars["other"].get() or "0", "Other deduction")
            attendance_days, working_hours = self.attendance_values()
            net = basic + extra + bonus + allowance - advance - other
            if net < 0:
                raise ValueError("Net salary cannot be negative.")
            account_id = self.selected_account_id(self.vars["account"].get())
            self.require_sufficient_balance(account_id, net)
            pay_date = validate_date(self.vars["date"].get())

            def callback(conn):
                cur = conn.execute(
                    """
                    INSERT INTO salary_payouts
                    (teacher_id, salary_month, basic_salary, extra_payment, bonus,
                     allowance, advance_deduction, other_deduction, net_salary,
                     attendance_days, working_hours,
                     payment_date, paid_from_account_id, payment_method,
                     voucher_no, status, remarks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Paid', ?)
                    """,
                    (
                        teacher_id, month, basic, extra, bonus, allowance, advance, other,
                        net, attendance_days, working_hours, pay_date, account_id,
                        self.vars["method"].get(),
                        self.vars["voucher"].get().strip(), self.vars["remarks"].get().strip(),
                    ),
                )
                salary_id = cur.lastrowid
                self.db.add_ledger(
                    conn, pay_date, account_id, "OUT", net, "Salary Payout",
                    salary_id, f"Salary payment for {month}",
                    self.vars["voucher"].get().strip(), self.vars["remarks"].get().strip()
                )

                if advance > 0:
                    advances_cursor = conn.execute(
                        """
                        SELECT * FROM teacher_advances
                        WHERE teacher_id=? AND status IN ('Outstanding','Partially Recovered')
                        ORDER BY advance_date, id
                        """,
                        (teacher_id,),
                    )
                    advances = advances_cursor.fetchall()
                    advances_cursor.close()
                    remaining_deduction = advance
                    updates = []
                    for adv in advances:
                        if remaining_deduction <= 0:
                            break
                        outstanding = float(adv["amount"]) - float(adv["recovered_amount"])
                        applied = min(outstanding, remaining_deduction)
                        new_recovered = float(adv["recovered_amount"]) + applied
                        status = (
                            "Fully Recovered"
                            if new_recovered >= float(adv["amount"])
                            else "Partially Recovered"
                        )
                        updates.append((new_recovered, status, adv["id"]))
                        remaining_deduction -= applied
                    if updates:
                        updates_cursor = conn.executemany(
                            "UPDATE teacher_advances SET recovered_amount=?, status=? WHERE id=?",
                            updates,
                        )
                        updates_cursor.close()

            self.db.transaction(callback)
            self.clear()
            self.app.refresh_all()
        except sqlite3.IntegrityError as exc:
            self.show_error(ValueError("Salary for this staff member and month already exists."))
        except Exception as exc:
            self.show_error(exc)

    def clear(self):
        for v in self.vars.values():
            v.set("")
        self.vars["month"].set(current_month())
        self.vars["attendance_days"].set("0")
        self.vars["working_hours"].set("0")
        self.vars["basic"].set("0")
        self.vars["extra"].set("0")
        self.vars["bonus"].set("0")
        self.vars["allowance"].set("0")
        self.vars["advance"].set("0")
        self.vars["other"].set("0")
        self.vars["date"].set(today_iso())
        self.vars["method"].set("Bank")
        self.attendance_label.config(text="Attendance reference: not calculated")
        self.net_label.config(text="Net Salary: 0.00")

    def refresh(self):
        rows = self.db.query(
            "SELECT id, teacher_name FROM teachers WHERE status='Active' ORDER BY teacher_name"
        )
        self.teacher_map = {f"{r['id']} - {r['teacher_name']}": r["id"] for r in rows}
        self.teacher_combo["values"] = list(self.teacher_map)
        self.load_accounts_into(self.account_combo)

        self.clear_tree(self.tree)
        records = self.db.query(
            """
            SELECT sp.*, t.teacher_name, a.account_name
            FROM salary_payouts sp
            JOIN teachers t ON t.id=sp.teacher_id
            JOIN accounts a ON a.id=sp.paid_from_account_id
            ORDER BY sp.payment_date DESC, sp.id DESC
            """
        )
        for r in records:
            gross = r["basic_salary"] + r["extra_payment"] + r["bonus"] + r["allowance"]
            deductions = r["advance_deduction"] + r["other_deduction"]
            self.tree.insert(
                "", "end",
                values=(r["id"], r["salary_month"], r["teacher_name"],
                        r["attendance_days"], money(r["working_hours"]), money(gross),
                        money(deductions), money(r["net_salary"]), r["payment_date"],
                        r["account_name"])
            )


# ---------------------------------------------------------------------------
# Accounts
