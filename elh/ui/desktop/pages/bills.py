from __future__ import annotations
import os
import tkinter as tk
from decimal import Decimal
from pathlib import Path
from tkinter import messagebox, ttk
from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import add_days, current_month, money, parse_amount, today_iso, validate_date


class DueBillsPage(CrudPage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.enrollment_map = {}
        self.selected_bill_id = None
        self.all_bills = []

        ttk.Label(self, text="Student Due Bills & Credit Management", style="Title.TLabel").pack(anchor="w")

        # Top Bill Generation Form
        form = self.create_form_dialog("Generate Bill", padding=8)
        form.pack(fill="x", pady=(4, 6))
        self.vars = {
            "enrollment": tk.StringVar(),
            "period": tk.StringVar(value=current_month()),
            "issue": tk.StringVar(value=today_iso()),
            "due": tk.StringVar(value=add_days(today_iso(), 7)),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.enrollment_combo = fb.combo("Enrollment *", self.vars["enrollment"], [], searchable=True)
        fb.entry("Billing Period *", self.vars["period"])
        fb.entry("Issue Date *", self.vars["issue"])
        fb.entry("Due Date *", self.vars["due"])
        fb.entry("Remarks", self.vars["remarks"])
        actions = ttk.Frame(form, style="Form.TFrame")
        actions.grid(row=0, column=2, rowspan=5, padx=12, sticky="n")
        ttk.Button(actions, text="Generate Due Bill", command=self.generate).pack(fill="x", pady=2)
        ttk.Button(actions, text="⚡ Auto-Invoicing...", style="Accent.TButton", command=self.open_auto_invoicing).pack(fill="x", pady=2)
        ttk.Button(actions, text="Generate Multiple...", command=self.open_bulk_generator).pack(fill="x", pady=2)
        ttk.Button(actions, text="Create / Open PDF", command=self.create_pdf).pack(fill="x", pady=2)
        ttk.Button(actions, text="Print PDF (Normal Printer)", command=self.print_pdf).pack(fill="x", pady=2)
        ttk.Button(actions, text="Print POS Receipt", command=self.print_pos).pack(fill="x", pady=2)
        if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False):
            ttk.Button(actions, text="💬 WhatsApp Bill", style="Accent.TButton", command=self.send_whatsapp_bill).pack(fill="x", pady=2)

        # Quick Filter & Search Bar
        filter_box = ttk.LabelFrame(self, text="Filter & Quick Search", padding=(8, 4))
        filter_box.pack(fill="x", pady=(0, 6))

        filter_row = ttk.Frame(filter_box)
        filter_row.pack(fill="x")

        ttk.Label(filter_row, text="Status Filter:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.filter_status_var = tk.StringVar(value="Pending Dues Only (Credit)")
        self.status_combo = ttk.Combobox(
            filter_row,
            textvariable=self.filter_status_var,
            values=["Pending Dues Only (Credit)", "Overdue (2+ Months)", "Fully Paid", "All Bills"],
            state="readonly",
            width=22,
        )
        self.status_combo.pack(side="left", padx=(0, 10))
        self.status_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)

        ttk.Label(filter_row, text="Period:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.filter_period_var = tk.StringVar(value="All Periods")
        self.period_combo = ttk.Combobox(
            filter_row,
            textvariable=self.filter_period_var,
            values=["All Periods"],
            state="readonly",
            width=13,
        )
        self.period_combo.pack(side="left", padx=(0, 10))
        self.period_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)

        ttk.Label(filter_row, text="🔍 Search:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_filter_changed)
        search_entry = ttk.Entry(filter_row, textvariable=self.search_var, width=22)
        search_entry.pack(side="left", padx=(0, 8))

        ttk.Button(filter_row, text="Reset Filters", command=self.reset_filters).pack(side="left", padx=(0, 10))

        self.summary_label = ttk.Label(filter_row, text="", font=("Segoe UI", 9, "bold"), foreground="#0369A1")
        self.summary_label.pack(side="right")

        # Two-Tab Notebook: 1. Student Credit / Defaulters Summary  2. Detailed Bills List
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Student Credit / Defaulters Summary
        self.tab_student = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_student, text="  👥 Student Credit Summary (Defaulters)  ")

        student_area = ttk.Frame(self.tab_student)
        student_area.pack(fill="both", expand=True)
        self.student_tree = self.make_tree(
            student_area,
            [
                ("id", "Student ID", 65),
                ("student", "Student Name", 170),
                ("contact", "Contact / Phone", 110),
                ("courses", "Enrolled Course(s)", 200),
                ("unpaid_count", "Unpaid Months", 100),
                ("periods", "Pending Periods", 180),
                ("total_due", "Total Overdue (Rs.)", 125),
            ],
        )
        self.student_tree.configure(selectmode="browse")
        self.student_tree.bind("<Double-1>", self.on_student_double_click)

        student_toolbar = ttk.Frame(self.tab_student)
        student_toolbar.pack(fill="x", pady=(6, 0))
        ttk.Button(student_toolbar, text="📄 Print Consolidated Statement", style="Accent.TButton", command=self.open_student_statement).pack(side="left", padx=(0, 6))
        ttk.Button(student_toolbar, text="💳 Settle All Dues", style="Accent.TButton", command=self.open_student_payment).pack(side="left", padx=4)
        if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False):
            ttk.Button(student_toolbar, text="💬 WhatsApp Due Notice", command=self.send_student_whatsapp).pack(side="left", padx=4)
        ttk.Button(student_toolbar, text="🔍 View Detailed Bills", command=self.view_student_bills_in_detailed_tab).pack(side="left", padx=6)
        ttk.Label(student_toolbar, text="💡 Double-click a student to print their consolidated statement", font=("Segoe UI", 8, "italic"), foreground="#64748B").pack(side="right")

        # Tab 2: Detailed Bills List
        self.tab_detailed = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_detailed, text="  📋 Detailed Bills List  ")

        area = ttk.Frame(self.tab_detailed)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 45),
                ("bill", "Bill No.", 150),
                ("student", "Student", 160),
                ("course", "Course", 170),
                ("period", "Period", 85),
                ("issue", "Issue", 90),
                ("due", "Due", 90),
                ("amount", "Total", 90),
                ("paid", "Paid", 90),
                ("balance", "Balance", 90),
                ("status", "Status", 100),
            ],
        )
        self.tree.configure(selectmode="extended")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        batch = ttk.Frame(self.tab_detailed)
        batch.pack(fill="x", pady=(6, 0))
        ttk.Button(batch, text="Select All Bills", command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left")
        ttk.Button(batch, text="Clear Selection", command=lambda: self.tree.selection_remove(self.tree.selection())).pack(side="left", padx=5)
        ttk.Button(batch, text="Pay Selected Bill(s)", style="Accent.TButton", command=self.open_payment).pack(side="left", padx=8)
        ttk.Button(batch, text="📄 Consolidated Statement", command=self.open_consolidated_statement).pack(side="left", padx=4)
        if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False):
            ttk.Button(batch, text="💬 WhatsApp Bill", command=self.send_whatsapp_bill).pack(side="left", padx=4)
        ttk.Button(batch, text="Open Batch PDF", command=self.open_batch_pdf).pack(side="right", padx=3)
        ttk.Button(batch, text="Print Batch PDF", command=self.print_batch_pdf).pack(side="right", padx=3)
        ttk.Button(batch, text="Batch POS Print", command=self.print_pos_batch).pack(side="right", padx=3)

    def on_filter_changed(self, *_args):
        self.apply_filters()

    def reset_filters(self):
        self.filter_status_var.set("Pending Dues Only (Credit)")
        self.filter_period_var.set("All Periods")
        self.search_var.set("")
        self.apply_filters()

    def refresh(self):
        rows = self.db.query(
            "SELECT e.id,s.student_name,c.course_name FROM enrollments e "
            "JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id "
            "WHERE e.status='Active' ORDER BY s.student_name,c.course_name"
        )
        self.enrollment_map = {f"{r['student_name']} - {r['course_name']} (#{r['id']})": r["id"] for r in rows}
        self.enrollment_combo["values"] = list(self.enrollment_map)

        self.all_bills = self.app.services.billing.repository.list()
        all_periods = set()
        for b in self.all_bills:
            if b.billing_period:
                all_periods.add(b.billing_period)
                for p in self.app.services.billing.segregate_period(b.billing_period):
                    all_periods.add(p)
        periods = sorted(all_periods, reverse=True)
        self.period_combo["values"] = ["All Periods", *periods]
        self.apply_filters()

    def apply_filters(self):
        status_choice = self.filter_status_var.get()
        period_choice = self.filter_period_var.get()
        search_kw = self.search_var.get().strip().lower()

        # 1. Update Student Credit Summary Tree
        min_months = 2 if "2+" in status_choice else 1
        summaries = self.app.services.billing.get_student_dues_summary(
            min_unpaid_months=min_months,
            search=search_kw,
        )
        self.clear_tree(self.student_tree)
        total_credit_due = Decimal("0")
        for s in summaries:
            total_credit_due += Decimal(str(s["total_due"]))
            months_count = s.get("unpaid_months_count", s["unpaid_bills_count"])
            bills_count = s["unpaid_bills_count"]
            months_text = (
                f"{months_count} month(s)"
                if months_count == bills_count
                else f"{months_count} month(s) ({bills_count} bills)"
            )
            self.student_tree.insert(
                "",
                "end",
                values=(
                    s["student_id"],
                    s["student_name"],
                    s["contact"] or "—",
                    s["course_name"],
                    months_text,
                    s["periods_display"],
                    money(Decimal(str(s["total_due"]))),
                ),
            )

        # 2. Update Detailed Bills Tree
        self.clear_tree(self.tree)
        multi_unpaid_students = {
            s["student_id"] for s in summaries
            if max(s.get("unpaid_months_count", s["unpaid_bills_count"]), s["unpaid_bills_count"]) >= 2
        }

        filtered_bills = []
        for b in self.all_bills:
            rem = b.total_amount - b.paid_amount
            # Status filter
            if "Pending" in status_choice and rem <= Decimal("0"):
                continue
            if "Overdue" in status_choice and b.student_id not in multi_unpaid_students:
                continue
            if "Fully Paid" in status_choice and rem > Decimal("0"):
                continue

            # Period filter
            if period_choice != "All Periods":
                seg_list = self.app.services.billing.segregate_period(b.billing_period)
                if b.billing_period != period_choice and period_choice not in seg_list:
                    continue

            # Search filter
            if search_kw:
                seg_str = " ".join(self.app.services.billing.segregate_period(b.billing_period))
                match_content = f"{b.bill_number} {b.student_name} {b.course_name} {getattr(b, 'contact', '')} {b.billing_period} {seg_str}".lower()
                if search_kw not in match_content:
                    continue

            filtered_bills.append(b)
            seg = self.app.services.billing.segregate_period(b.billing_period)
            period_val = f"{b.billing_period} ({', '.join(seg)})" if len(seg) > 1 else b.billing_period
            self.tree.insert(
                "",
                "end",
                values=(
                    b.id,
                    b.bill_number,
                    b.student_name,
                    b.course_name,
                    period_val,
                    b.issue_date,
                    b.due_date,
                    money(b.total_amount),
                    money(b.paid_amount),
                    money(rem),
                    b.status,
                ),
            )

        self.summary_label.configure(
            text=f"Credit Defaulters: {len(summaries)} student(s) · Total Due: {money(total_credit_due)} | Bills Listed: {len(filtered_bills)}"
        )

    def generate(self):
        try:
            enrollment_id = self.enrollment_map.get(self.vars["enrollment"].get())
            if not enrollment_id:
                raise ValueError("Please select an enrollment.")
            result = self.app.services.billing.generate(
                enrollment_id,
                self.vars["period"].get(),
                validate_date(self.vars["issue"].get(), "Issue date"),
                validate_date(self.vars["due"].get(), "Due date"),
                self.vars["remarks"].get(),
            )
            self.selected_bill_id = result.bill.id
            self.refresh()
            messagebox.showinfo(
                "Bill Generated" if result.created else "Already Generated",
                f"Bill {result.bill.bill_number}\nAmount due: {money(result.bill.total_amount)}"
                if result.created
                else f"A bill already exists for this enrollment and period:\n{result.bill.bill_number}",
                parent=self,
            )
        except Exception as exc:
            self.show_error(exc)

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self.selected_bill_id = int(self.tree.item(selected[0], "values")[0])

    def on_student_double_click(self, _event=None):
        self.open_student_statement()

    def open_student_statement(self):
        sel = self.student_tree.selection()
        if not sel:
            messagebox.showwarning("Select Student", "Please select a student from the list first.", parent=self)
            return
        item = self.student_tree.item(sel[0])
        student_id = int(item["values"][0])
        try:
            path = self.app.services.billing.create_consolidated_statement_pdf(student_id=student_id)
            os.startfile(path)
        except Exception as exc:
            self.show_error(exc)

    def open_student_payment(self):
        sel = self.student_tree.selection()
        if not sel:
            messagebox.showwarning("Select Student", "Please select a student from the list first.", parent=self)
            return
        item = self.student_tree.item(sel[0])
        student_id = int(item["values"][0])
        bills = self.app.services.billing.repository.get_unpaid_bills_for_student(student_id)
        if not bills:
            messagebox.showinfo("Settled", "This student has no pending unpaid bills.", parent=self)
            return
        self._launch_payment_dialog(bills)

    def view_student_bills_in_detailed_tab(self):
        sel = self.student_tree.selection()
        if not sel:
            messagebox.showwarning("Select Student", "Please select a student from the list first.", parent=self)
            return
        item = self.student_tree.item(sel[0])
        student_name = str(item["values"][1])
        self.search_var.set(student_name)
        self.notebook.select(self.tab_detailed)

    def send_student_whatsapp(self):
        sel = self.student_tree.selection()
        if not sel:
            messagebox.showwarning("Select Student", "Please select a student from the list first.", parent=self)
            return
        item = self.student_tree.item(sel[0])
        student_id = int(item["values"][0])
        bills = self.app.services.billing.repository.get_unpaid_bills_for_student(student_id)
        if not bills:
            messagebox.showinfo("Settled", "This student has no pending unpaid bills.", parent=self)
            return
        latest_bill = bills[-1]
        self.selected_bill_id = latest_bill.id
        self.send_whatsapp_bill()

    def selected_bill(self):
        if not self.selected_bill_id:
            raise ValueError("Select or generate a bill first.")
        return self.app.services.billing.repository.get(self.selected_bill_id)

    def selected_bills(self):
        selected = self.tree.selection()
        if not selected:
            raise ValueError("Select one or more bills first.")
        return [self.app.services.billing.repository.get(int(self.tree.item(item, "values")[0])) for item in selected]

    def open_payment(self):
        try:
            bills = self.selected_bills()
        except Exception:
            try:
                bills = [self.selected_bill()]
            except Exception as exc:
                self.show_error(exc)
                return

        if not bills:
            self.show_error(ValueError("Select at least one bill to pay."))
            return
        self._launch_payment_dialog(bills)

    def _launch_payment_dialog(self, bills):
        student_names = {b.student_name for b in bills}
        if len(student_names) > 1:
            self.show_error(ValueError("All selected bills must belong to the same student for a combined payment.\nPlease select bills belonging to a single student."))
            return

        total_remaining = sum(max(Decimal("0"), b.total_amount - b.paid_amount) for b in bills)
        if total_remaining <= 0:
            self.show_error(ValueError("All selected bills are already fully paid."))
            return

        accounts = self.db.query("SELECT id,account_name,account_type FROM accounts WHERE status='Active' ORDER BY account_name")
        account_map = {f"{r['account_name']} ({r['account_type']})": r["id"] for r in accounts}
        if not account_map:
            self.show_error(ValueError("Create an active payment account first."))
            return

        student_name = bills[0].student_name
        is_multi = len(bills) > 1

        dialog = tk.Toplevel(self)
        dialog.title(f"Combined Payment ({len(bills)} Bills)" if is_multi else "Quick Bill Payment")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)

        panel_title = f"{student_name} — {len(bills)} Bills Combined" if is_multi else f"{student_name} - {bills[0].bill_number}"
        panel = ttk.LabelFrame(dialog, text=panel_title, padding=14)
        panel.pack(fill="both", expand=True, padx=12, pady=12)

        cur_row = 0
        if is_multi:
            bill_summary_lines = []
            for b in bills:
                b_rem = max(Decimal("0"), b.total_amount - b.paid_amount)
                bill_summary_lines.append(f"• {b.bill_number} ({b.billing_period}): Due {money(b_rem)}")
            ttk.Label(panel, text="\n".join(bill_summary_lines), justify="left").grid(row=cur_row, column=0, columnspan=2, sticky="w", pady=(0, 6))
            cur_row += 1
        else:
            ttk.Label(panel, text=f"Course: {bills[0].course_name}    Period: {bills[0].billing_period}").grid(row=cur_row, column=0, columnspan=2, sticky="w", pady=(0, 8))
            cur_row += 1

        ttk.Label(panel, text=f"Total balance due: {money(total_remaining)}", style="Card.TLabel").grid(row=cur_row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        cur_row += 1

        ttk.Label(panel, text="💡 Payment automatically settles older bills first.\nAny extra amount is credited as student advance.", foreground="#0369A1", font=("Segoe UI", 8, "italic")).grid(row=cur_row, column=0, columnspan=2, sticky="w", pady=(0, 10))
        cur_row += 1

        values = {
            "amount": tk.StringVar(value=str(total_remaining)),
            "discount": tk.StringVar(value="0"),
            "date": tk.StringVar(value=today_iso()),
            "account": tk.StringVar(value=next(iter(account_map))),
            "method": tk.StringVar(value="Cash"),
            "receipt": tk.StringVar(),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(panel, start_row=cur_row)
        fb.entry("Payment Amount *", values["amount"])
        fb.entry("Discount Amount", values["discount"])
        fb.entry("Payment Date *", values["date"])
        fb.combo("Payment Account *", values["account"], account_map)
        fb.combo("Payment Method", values["method"], ["Cash", "Bank", "Wallet", "Other"])
        fb.entry("Receipt No.", values["receipt"])
        fb.entry("Remarks", values["remarks"])

        def save_payment():
            try:
                amount = parse_amount(values["amount"].get() or "0", "Payment")
                discount = parse_amount(values["discount"].get() or "0", "Discount")
                pay_date = validate_date(values["date"].get(), "Payment date")
                acc_id = account_map.get(values["account"].get())
                method = values["method"].get()
                receipt = values["receipt"].get().strip()
                remarks = values["remarks"].get().strip()

                result = self.app.services.billing.pay_bills(
                    [b.id for b in bills],
                    amount,
                    pay_date,
                    acc_id,
                    method,
                    receipt,
                    remarks,
                    discount,
                    allow_advance=True,
                )
                dialog.destroy()
                self.app.refresh_all()

                settled_count = len(result.get("updated_bills", []))
                adv = result.get("advance_amount", Decimal("0"))
                adv_msg = f"\nAdvance credit recorded: {money(adv)} (Surplus)" if adv > 0 else ""
                info_msg = (
                    f"Payment: {money(amount)}\n"
                    f"Discount: {money(discount)}\n"
                    f"Bills settled / updated: {settled_count}{adv_msg}"
                )

                first_txn_id = result.get("transaction_ids", [None])[0]
                wa_enabled = getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False)
                if wa_enabled:
                    ans = messagebox.askyesno("Payment Saved", f"{info_msg}\n\nWould you like to send a payment receipt via WhatsApp?", parent=self)
                    if ans and first_txn_id:
                        self.send_whatsapp_payment_receipt(first_txn_id)
                else:
                    sms_note = "\n\nAutomated SMS receipt has been queued." if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("sms_enabled", False) else ""
                    messagebox.showinfo("Payment Saved", f"{info_msg}{sms_note}", parent=self)
            except Exception as exc:
                messagebox.showerror("Payment Error", str(exc), parent=dialog)

        ttk.Button(panel, text="Receive Payment", style="Accent.TButton", command=save_payment).grid(row=fb.row, column=1, sticky="e", pady=(12, 0))

    def create_pdf(self):
        try:
            path=self.app.services.billing.create_pdf(self.selected_bill());os.startfile(path)
        except Exception as exc:self.show_error(exc)
    def print_pdf(self):
        try:
            bill=self.selected_bill();path=Path(bill.pdf_path) if bill.pdf_path else self.app.services.billing.create_pdf(bill)
            os.startfile(path,"print")
        except Exception as exc:self.show_error(exc)
    def print_pos(self):
        try:self.app.services.billing.print_pos(self.selected_bill());messagebox.showinfo("Printed","Bill sent to the configured POS printer.",parent=self)
        except Exception as exc:self.show_error(exc)
    def open_batch_pdf(self):
        try:path=self.app.services.billing.create_batch_pdf(self.selected_bills());os.startfile(path)
        except Exception as exc:self.show_error(exc)
    def print_batch_pdf(self):
        try:path=self.app.services.billing.create_batch_pdf(self.selected_bills());os.startfile(path,"print")
        except Exception as exc:self.show_error(exc)
    def print_pos_batch(self):
        try:
            bills=self.selected_bills();self.app.services.billing.print_pos_many(bills);messagebox.showinfo("Batch Printed",f"Sent {len(bills)} bills to the POS printer.",parent=self)
        except Exception as exc:self.show_error(exc)

    def open_consolidated_statement(self):
        try:
            bills = self.selected_bills()
        except Exception:
            try:
                bills = [self.selected_bill()]
            except Exception as exc:
                self.show_error(exc)
                return

        if not bills:
            self.show_error(ValueError("Select at least one bill first."))
            return

        student_names = {b.student_name for b in bills}
        if len(student_names) > 1:
            self.show_error(ValueError("All selected bills must belong to the same student to generate a consolidated statement."))
            return

        try:
            path = self.app.services.billing.create_consolidated_statement_pdf(bills)
            os.startfile(path)
        except Exception as exc:
            self.show_error(exc)

    def send_whatsapp_bill(self):
        try:
            bill = self.selected_bill()
        except Exception as exc:
            self.show_error(exc)
            return

        notif_svc = getattr(self.app.services, "notifications", None)
        if not notif_svc:
            self.show_error(ValueError("Notification service is not available."))
            return

        try:
            data = notif_svc.build_bill_whatsapp_message(bill.id)
        except Exception as exc:
            self.show_error(exc)
            return

        import webbrowser
        from tkinter import scrolledtext

        dialog = tk.Toplevel(self)
        dialog.title(f"WhatsApp Due Bill - {data['student_name']} ({data['bill_number']})")
        dialog.geometry("640x560")
        dialog.minsize(560, 480)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        top = ttk.LabelFrame(dialog, text="WhatsApp Due Bill Notice", padding=12)
        top.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        rec_frame = ttk.Frame(top)
        rec_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(rec_frame, text="Mobile Number: *", font=("Segoe UI", 9, "bold")).pack(side="left")
        phone_var = tk.StringVar(value=data["recipient"])
        phone_entry = ttk.Entry(rec_frame, textvariable=phone_var, width=24, font=("Segoe UI", 10))
        phone_entry.pack(side="left", padx=8)
        ttk.Label(rec_frame, text=f"Due: Rs. {data['amount_due']}", font=("Segoe UI", 9, "bold"), foreground="#0284C7").pack(side="right")

        ttk.Label(top, text="Message Preview (Editable):").pack(anchor="w", pady=(0, 4))
        msg_text = scrolledtext.ScrolledText(top, wrap="word", height=12, font=("Segoe UI", 9))
        msg_text.pack(fill="both", expand=True, pady=(0, 8))
        msg_text.insert("1.0", data["message"])

        status_lbl = ttk.Label(top, text="", foreground="#15803D", font=("Segoe UI", 9, "bold"))
        status_lbl.pack(anchor="w")

        btn_bar = ttk.Frame(dialog, padding=(12, 8))
        btn_bar.pack(fill="x", side="bottom")

        def open_click_to_chat():
            phone = phone_var.get().strip()
            body = msg_text.get("1.0", "end-1c").strip()
            if not phone:
                messagebox.showerror("Error", "Please enter a valid mobile number.", parent=dialog)
                return
            try:
                wa_url = notif_svc.build_whatsapp_link(phone, body)
                webbrowser.open(wa_url)
                status_lbl.config(text="✓ Opened in WhatsApp! You can send the message now.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def send_via_api():
            phone = phone_var.get().strip()
            body = msg_text.get("1.0", "end-1c").strip()
            if not phone:
                messagebox.showerror("Error", "Please enter a valid mobile number.", parent=dialog)
                return
            try:
                resp = notif_svc.send_whatsapp(phone, body)
                if resp.success:
                    status_lbl.config(text=f"✓ Sent via automated API! (ID: {resp.message_id or 'OK'})")
                    messagebox.showinfo("Success", f"WhatsApp message sent successfully!\n\nMessage ID: {resp.message_id}", parent=dialog)
                else:
                    messagebox.showerror("Gateway Error", f"{resp.message}\n\nTip: You can use 'Open WhatsApp' instead.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def copy_message():
            dialog.clipboard_clear()
            dialog.clipboard_append(msg_text.get("1.0", "end-1c").strip())
            status_lbl.config(text="✓ Message copied to clipboard!")

        def open_pdf_file():
            try:
                pdf_path = self.app.services.billing.create_pdf(bill)
                os.startfile(pdf_path)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        ttk.Button(btn_bar, text="🚀 Open WhatsApp (Web / App)", style="Accent.TButton", command=open_click_to_chat).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="⚡ Send via API", command=send_via_api).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="📋 Copy Text", command=copy_message).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="📂 Open PDF Bill", command=open_pdf_file).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="Close", command=dialog.destroy).pack(side="right", padx=3)

    def send_whatsapp_payment_receipt(self, payment_record_id: int):
        notif_svc = getattr(self.app.services, "notifications", None)
        if not notif_svc:
            return

        try:
            data = notif_svc.build_payment_whatsapp_message("student", payment_record_id)
        except Exception:
            return

        import webbrowser
        from tkinter import scrolledtext

        dialog = tk.Toplevel(self)
        dialog.title(f"WhatsApp Payment Receipt - {data['student_name']} ({data['receipt_number']})")
        dialog.geometry("640x520")
        dialog.minsize(540, 440)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        top = ttk.LabelFrame(dialog, text="WhatsApp Payment Receipt", padding=12)
        top.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        rec_frame = ttk.Frame(top)
        rec_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(rec_frame, text="Mobile Number: *", font=("Segoe UI", 9, "bold")).pack(side="left")
        phone_var = tk.StringVar(value=data["recipient"])
        phone_entry = ttk.Entry(rec_frame, textvariable=phone_var, width=24, font=("Segoe UI", 10))
        phone_entry.pack(side="left", padx=8)
        ttk.Label(rec_frame, text=f"Paid: Rs. {data['amount_paid']}", font=("Segoe UI", 9, "bold"), foreground="#16A34A").pack(side="right")

        ttk.Label(top, text="Message Preview (Editable):").pack(anchor="w", pady=(0, 4))
        msg_text = scrolledtext.ScrolledText(top, wrap="word", height=10, font=("Segoe UI", 9))
        msg_text.pack(fill="both", expand=True, pady=(0, 8))
        msg_text.insert("1.0", data["message"])

        status_lbl = ttk.Label(top, text="", foreground="#15803D", font=("Segoe UI", 9, "bold"))
        status_lbl.pack(anchor="w")

        btn_bar = ttk.Frame(dialog, padding=(12, 8))
        btn_bar.pack(fill="x", side="bottom")

        def open_click_to_chat():
            phone = phone_var.get().strip()
            body = msg_text.get("1.0", "end-1c").strip()
            if not phone:
                messagebox.showerror("Error", "Please enter a valid mobile number.", parent=dialog)
                return
            try:
                wa_url = notif_svc.build_whatsapp_link(phone, body)
                webbrowser.open(wa_url)
                status_lbl.config(text="✓ Opened in WhatsApp! You can send the receipt now.")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def send_via_api():
            phone = phone_var.get().strip()
            body = msg_text.get("1.0", "end-1c").strip()
            if not phone:
                messagebox.showerror("Error", "Please enter a valid mobile number.", parent=dialog)
                return
            try:
                resp = notif_svc.send_whatsapp(phone, body)
                if resp.success:
                    status_lbl.config(text=f"✓ Sent via automated API! (ID: {resp.message_id or 'OK'})")
                    messagebox.showinfo("Success", f"WhatsApp receipt sent successfully!\n\nMessage ID: {resp.message_id}", parent=dialog)
                else:
                    messagebox.showerror("Gateway Error", f"{resp.message}\n\nTip: You can use 'Open WhatsApp' instead.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def copy_message():
            dialog.clipboard_clear()
            dialog.clipboard_append(msg_text.get("1.0", "end-1c").strip())
            status_lbl.config(text="✓ Message copied to clipboard!")

        ttk.Button(btn_bar, text="🚀 Open WhatsApp (Web / App)", style="Accent.TButton", command=open_click_to_chat).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="⚡ Send via API", command=send_via_api).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="📋 Copy Text", command=copy_message).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="Close", command=dialog.destroy).pack(side="right", padx=3)

    def open_bulk_generator(self):
        dialog=tk.Toplevel(self);dialog.title("Generate Bills for Multiple Students");dialog.geometry("840x700");dialog.minsize(760,620);dialog.transient(self.winfo_toplevel());dialog.grab_set()
        top=ttk.Frame(dialog,padding=10);top.pack(fill="x")
        start_month=tk.StringVar(value=self.vars["period"].get());end_month=tk.StringVar(value=self.vars["period"].get());issue=tk.StringVar(value=self.vars["issue"].get());due=tk.StringVar(value=self.vars["due"].get());remarks=tk.StringVar()
        fb=FormBuilder(top);fb.entry("Start Month (YYYY/MM) *",start_month);fb.entry("End Month (YYYY/MM) *",end_month);fb.entry("Issue Date *",issue);fb.entry("Due Date *",due);fb.entry("Remarks",remarks)
        ttk.Label(dialog,text="Select students/enrollments (Ctrl or Shift for multiple selection)").pack(anchor="w",padx=10)
        area=ttk.Frame(dialog,padding=(10,4));area.pack(fill="both",expand=True)
        tree=ttk.Treeview(area,columns=("id","student","course","start","fee"),show="headings",selectmode="extended")
        for key,title,width in (("id","Enrollment ID",90),("student","Student",190),("course","Course",190),("start","Start Date",100),("fee","Fee",90)):
            tree.heading(key,text=title);tree.column(key,width=width,anchor="w")
        ybar=ttk.Scrollbar(area,orient="vertical",command=tree.yview);tree.configure(yscrollcommand=ybar.set);tree.pack(side="left",fill="both",expand=True);ybar.pack(side="right",fill="y")
        rows=self.db.query("SELECT e.id,s.student_name,c.course_name,e.start_date,e.monthly_fee FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id WHERE e.status='Active' ORDER BY s.student_name,c.course_name")
        for row in rows:tree.insert("","end",values=(row["id"],row["student_name"],row["course_name"],row["start_date"],money(row["monthly_fee"])))
        buttons=ttk.Frame(dialog,padding=10);buttons.pack(fill="x")
        ttk.Button(buttons,text="Select All",command=lambda:tree.selection_set(tree.get_children())).pack(side="left")
        ttk.Button(buttons,text="Clear Selection",command=lambda:tree.selection_remove(tree.selection())).pack(side="left",padx=5)
        def generate_batch():
            try:
                ids=[int(tree.item(item,"values")[0]) for item in tree.selection()]
                results=self.app.services.billing.generate_combined_month_range(ids,start_month.get(),end_month.get(),validate_date(issue.get(),"Issue date"),validate_date(due.get(),"Due date"),remarks.get())
                created=sum(1 for result in results if result.created);existing=len(results)-created;not_started=len(ids)-len(results)
                dialog.destroy();self.refresh();messagebox.showinfo("Batch Complete",f"Combined student bills generated: {created}\nAlready billed or paid (skipped): {existing}\nNot yet enrolled for selected months (skipped): {not_started}\nStudents/enrollments selected: {len(ids)}",parent=self)
            except Exception as exc:messagebox.showerror("Batch Error",str(exc),parent=dialog)
        ttk.Button(buttons,text="Generate Selected Bills",command=generate_batch).pack(side="right")
        buttons.pack_configure(side="bottom",before=area,pady=(4,0))

    def open_auto_invoicing(self):
        service = getattr(self.app.services, "recurring_billing", None)
        if not service:
            messagebox.showerror("Error", "Recurring billing service is not available.", parent=self)
            return

        cfg = service.get_config()
        dialog = tk.Toplevel(self)
        dialog.title("Automated Monthly Recurring Invoicing")
        dialog.geometry("940x690")
        dialog.minsize(820, 590)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        header_frame = ttk.Frame(dialog, padding=(16, 12, 16, 6))
        header_frame.pack(fill="x")
        ttk.Label(
            header_frame,
            text="⚡ Automated Monthly Recurring Invoicing",
            font=("Segoe UI Variable Display", 15, "bold"),
            foreground="#102A43",
        ).pack(anchor="w")
        ttk.Label(
            header_frame,
            text="Automatically evaluate, verify, and issue monthly recurring dues for all active students.",
            font=("Segoe UI", 9),
            foreground="#64748B",
        ).pack(anchor="w", pady=(2, 0))

        # Status Banner
        banner = ttk.Frame(dialog, padding=(16, 6))
        banner.pack(fill="x")
        status_label = ttk.Label(
            banner,
            text=f"Auto-Billing Daemon: {'ENABLED' if cfg['enabled'] else 'DISABLED'}  |  Last Run Month: {cfg['last_run_month'] or 'None'}  |  Last Run: {cfg['last_run_at'] or 'Never'}",
            font=("Segoe UI", 9, "bold"),
            foreground="#008F7A" if cfg["enabled"] else "#64748B",
        )
        status_label.pack(anchor="w")

        # Controls & Form
        ctrl = ttk.LabelFrame(dialog, text="Invoicing Parameters", padding=10)
        ctrl.pack(fill="x", padx=16, pady=6)

        target_month_var = tk.StringVar(value=current_month())
        issue_date_var = tk.StringVar(value=today_iso())
        due_days_var = tk.StringVar(value=str(cfg["due_days"]))
        due_date_var = tk.StringVar(value=add_days(today_iso(), cfg["due_days"]))
        send_sms_var = tk.BooleanVar(value=cfg["auto_sms"])
        enabled_daemon_var = tk.BooleanVar(value=cfg["enabled"])
        remarks_var = tk.StringVar(value="Automated monthly recurring invoice")

        def recalculate_due_date(*_args):
            try:
                days = int(due_days_var.get())
                due_date_var.set(add_days(issue_date_var.get(), days))
            except Exception:
                pass

        due_days_var.trace_add("write", recalculate_due_date)
        issue_date_var.trace_add("write", recalculate_due_date)

        f_grid = ttk.Frame(ctrl)
        f_grid.pack(fill="x")

        ttk.Label(f_grid, text="Billing Month (YYYY/MM) *").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(f_grid, textvariable=target_month_var, width=14).grid(row=0, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(f_grid, text="Issue Date *").grid(row=0, column=2, sticky="w", padx=4, pady=3)
        ttk.Entry(f_grid, textvariable=issue_date_var, width=14).grid(row=0, column=3, sticky="w", padx=4, pady=3)

        ttk.Label(f_grid, text="Due Days *").grid(row=0, column=4, sticky="w", padx=4, pady=3)
        ttk.Entry(f_grid, textvariable=due_days_var, width=8).grid(row=0, column=5, sticky="w", padx=4, pady=3)

        ttk.Label(f_grid, text="Due Date").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(f_grid, textvariable=due_date_var, width=14).grid(row=1, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(f_grid, text="Remarks").grid(row=1, column=2, sticky="w", padx=4, pady=3)
        ttk.Entry(f_grid, textvariable=remarks_var, width=32).grid(row=1, column=3, columnspan=3, sticky="ew", padx=4, pady=3)

        opts_frame = ttk.Frame(ctrl)
        opts_frame.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(opts_frame, text="Send SMS notification on generation", variable=send_sms_var).pack(side="left", padx=4)
        ttk.Checkbutton(opts_frame, text="Enable background auto-invoicing on startup/schedule", variable=enabled_daemon_var).pack(side="left", padx=16)

        # Unbilled Students Preview Table
        preview_frame = ttk.LabelFrame(dialog, text="Pending Unbilled Students Preview", padding=8)
        preview_frame.pack(fill="both", expand=True, padx=16, pady=6)

        summary_label = ttk.Label(preview_frame, text="Loading preview...", font=("Segoe UI", 9, "bold"))
        summary_label.pack(anchor="w", pady=(0, 4))

        tree_wrap = ttk.Frame(preview_frame)
        tree_wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            tree_wrap,
            columns=("eid", "student", "course", "level", "contact", "start", "fee", "estimated"),
            show="headings",
        )
        for k, t, w in (
            ("eid", "ID", 45),
            ("student", "Student Name", 160),
            ("course", "Course", 160),
            ("level", "Class", 80),
            ("contact", "Contact", 105),
            ("start", "Start Date", 90),
            ("fee", "Monthly Fee", 90),
            ("estimated", "Estimated Due", 100),
        ):
            tree.heading(k, text=t)
            tree.column(k, width=w, anchor="w")

        sbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sbar.set)
        tree.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")

        def refresh_preview():
            for item in tree.get_children():
                tree.delete(item)
            try:
                prev = service.preview(target_month_var.get().strip())
                unbilled = prev["unbilled_enrollments"]
                total = prev["total_estimated_amount"]
                summary_label.configure(
                    text=f"Month: {prev['target_month']}  |  Pending Students to Invoice: {len(unbilled)}  |  Total Estimated Invoicing: {self.app.services.billing.currency_symbol} {total:,.2f}"
                )
                for u in unbilled:
                    tree.insert(
                        "",
                        "end",
                        values=(
                            u["enrollment_id"],
                            u["student_name"],
                            u["course_name"],
                            u["level"],
                            u["contact"],
                            u["start_date"],
                            money(u["monthly_fee"]),
                            money(u["estimated_amount"]),
                        ),
                    )
            except Exception as e:
                summary_label.configure(text=f"Preview error: {e}")

        target_month_var.trace_add("write", lambda *_args: refresh_preview())
        refresh_preview()

        # Action Buttons
        bot_bar = ttk.Frame(dialog, padding=(16, 10))
        bot_bar.pack(fill="x")

        def save_config_action():
            try:
                service.update_config(
                    enabled=enabled_daemon_var.get(),
                    due_days=int(due_days_var.get()),
                    auto_sms=send_sms_var.get(),
                )
                status_label.configure(
                    text=f"Auto-Billing Daemon: {'ENABLED' if enabled_daemon_var.get() else 'DISABLED'}  |  Last Run Month: {service.get_config()['last_run_month'] or 'None'}  |  Last Run: {service.get_config()['last_run_at'] or 'Never'}",
                    foreground="#008F7A" if enabled_daemon_var.get() else "#64748B",
                )
                messagebox.showinfo("Saved", "Auto-invoicing configuration saved successfully.", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def execute_auto_billing():
            month = target_month_var.get().strip()
            try:
                prev = service.preview(month)
            except Exception as e:
                messagebox.showerror("Validation Error", str(e), parent=dialog)
                return

            if not prev["unbilled_enrollments"]:
                messagebox.showinfo("Up to Date", f"All active students are already invoiced for {month}.", parent=dialog)
                return

            count = prev["unbilled_count"]
            amt = prev["total_estimated_amount"]
            if not messagebox.askyesno(
                "Confirm Auto-Invoicing",
                f"Generate recurring monthly due bills for {count} active student(s) for month {month}?\n\nTotal Invoiced Amount: {self.app.services.billing.currency_symbol} {amt:,.2f}",
                parent=dialog,
            ):
                return

            try:
                service.update_config(
                    enabled=enabled_daemon_var.get(),
                    due_days=int(due_days_var.get()),
                    auto_sms=send_sms_var.get(),
                )
                actor = getattr(getattr(self.app, "session", None), "username", "operator")
                res = service.run_auto_billing(
                    target_month=month,
                    issue_date=issue_date_var.get().strip(),
                    due_date=due_date_var.get().strip(),
                    send_sms=send_sms_var.get(),
                    remarks=remarks_var.get().strip(),
                    actor_username=actor,
                )
                self.refresh()
                refresh_preview()
                status_label.configure(
                    text=f"Auto-Billing Daemon: {'ENABLED' if enabled_daemon_var.get() else 'DISABLED'}  |  Last Run Month: {res.target_month}  |  Last Run: {res.executed_at}",
                    foreground="#008F7A" if enabled_daemon_var.get() else "#64748B",
                )
                messagebox.showinfo(
                    "Auto-Invoicing Completed",
                    f"Recurring Monthly Billing Complete for {res.target_month}:\n\n"
                    f"• Bills Created: {res.bills_created}\n"
                    f"• Bills Skipped / Already Invoiced: {res.bills_skipped}\n"
                    f"• Total Amount Invoiced: {self.app.services.billing.currency_symbol} {res.total_invoiced_amount:,.2f}\n"
                    f"• SMS Notifications Queued: {res.sms_queued_count}",
                    parent=dialog,
                )
            except Exception as e:
                messagebox.showerror("Auto-Invoicing Error", str(e), parent=dialog)

        ttk.Button(bot_bar, text="🔄 Refresh Preview", command=refresh_preview).pack(side="left")
        ttk.Button(bot_bar, text="Save Settings", command=save_config_action).pack(side="left", padx=8)
        ttk.Button(bot_bar, text="⚡ Run Auto-Invoicing Now", style="Accent.TButton", command=execute_auto_billing).pack(side="right")
        ttk.Button(bot_bar, text="Close", command=dialog.destroy).pack(side="right", padx=6)

