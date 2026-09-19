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
        self.all_payments = []

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

        ttk.Label(filter_row, text="Class:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.filter_class_var = tk.StringVar(value="All Classes")
        self.class_combo = ttk.Combobox(
            filter_row,
            textvariable=self.filter_class_var,
            values=["All Classes"],
            state="readonly",
            width=14,
        )
        self.class_combo.pack(side="left", padx=(0, 10))
        self.class_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)

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
                ("student", "Student Name", 160),
                ("class_name", "Class", 85),
                ("contact", "Contact / Phone", 110),
                ("courses", "Enrolled Course(s)", 180),
                ("unpaid_count", "Unpaid Months", 100),
                ("periods", "Pending Periods", 160),
                ("total_due", "Total Overdue (Rs.)", 120),
            ],
        )
        self.student_tree.configure(selectmode="extended")
        self.student_tree.bind("<Double-1>", self.on_student_double_click)

        student_toolbar = ttk.Frame(self.tab_student)
        student_toolbar.pack(fill="x", pady=(6, 0))
        ttk.Button(student_toolbar, text="Select All Students", command=lambda: self.student_tree.selection_set(self.student_tree.get_children())).pack(side="left")
        ttk.Button(student_toolbar, text="Clear Selection", command=lambda: self.student_tree.selection_remove(self.student_tree.selection())).pack(side="left", padx=5)
        ttk.Button(student_toolbar, text="📄 Print Consolidated Statement", style="Accent.TButton", command=self.open_student_statement).pack(side="left", padx=(0, 4))
        ttk.Button(student_toolbar, text="💳 Settle All Dues", style="Accent.TButton", command=self.open_student_payment).pack(side="left", padx=4)
        if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False):
            ttk.Button(student_toolbar, text="💬 WhatsApp Due Notice", command=self.send_student_whatsapp).pack(side="left", padx=4)
        ttk.Button(student_toolbar, text="🔍 View Detailed Bills", command=self.view_student_bills_in_detailed_tab).pack(side="left", padx=4)
        ttk.Button(student_toolbar, text="🖨️ Print POS (Class)", style="Accent.TButton", command=self.open_print_pos_by_class_dialog).pack(side="right", padx=3)
        ttk.Button(student_toolbar, text="Batch POS Print", command=self.print_pos_students_batch).pack(side="right", padx=3)

        # Tab 2: Detailed Bills List
        self.tab_detailed = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_detailed, text="  📋 Detailed Bills List  ")

        area = ttk.Frame(self.tab_detailed)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 45),
                ("bill", "Bill No.", 140),
                ("student", "Student", 150),
                ("class_name", "Class", 85),
                ("course", "Course", 160),
                ("period", "Period", 85),
                ("issue", "Issue", 85),
                ("due", "Due", 85),
                ("amount", "Total", 85),
                ("paid", "Paid", 85),
                ("balance", "Balance", 85),
                ("status", "Status", 95),
            ],
        )
        self.tree.configure(selectmode="extended")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.open_edit_bill())

        batch = ttk.Frame(self.tab_detailed)
        batch.pack(fill="x", pady=(6, 0))
        ttk.Button(batch, text="Select All Bills", command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left")
        ttk.Button(batch, text="Clear Selection", command=lambda: self.tree.selection_remove(self.tree.selection())).pack(side="left", padx=5)
        ttk.Button(batch, text="Pay Selected Bill(s)", style="Accent.TButton", command=self.open_payment).pack(side="left", padx=8)
        ttk.Button(batch, text="✏️ Edit Bill", command=self.open_edit_bill).pack(side="left", padx=4)
        ttk.Button(batch, text="💳 View Payments", command=self.open_bill_payments).pack(side="left", padx=4)
        if self.is_admin():
            ttk.Button(batch, text="🗑️ Delete Bill", command=self.delete_selected_bill).pack(side="left", padx=4)
        ttk.Button(batch, text="📄 Consolidated Statement", command=self.open_consolidated_statement).pack(side="left", padx=4)
        if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False):
            ttk.Button(batch, text="💬 WhatsApp Bill", command=self.send_whatsapp_bill).pack(side="left", padx=4)
        ttk.Button(batch, text="Open Batch PDF", command=self.open_batch_pdf).pack(side="right", padx=3)
        ttk.Button(batch, text="Print Batch PDF", command=self.print_batch_pdf).pack(side="right", padx=3)
        ttk.Button(batch, text="🖨️ Print POS (Class)", style="Accent.TButton", command=self.open_print_pos_by_class_dialog).pack(side="right", padx=3)
        ttk.Button(batch, text="Batch POS Print", command=self.print_pos_batch).pack(side="right", padx=3)

        # Tab 3: Payment Records & Receipts
        self.tab_payments = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(self.tab_payments, text="  💳 Payment Records & Receipts  ")

        pay_area = ttk.Frame(self.tab_payments)
        pay_area.pack(fill="both", expand=True)
        self.payment_tree = self.make_tree(
            pay_area,
            [
                ("id", "Txn ID", 60),
                ("date", "Date", 85),
                ("student", "Student Name", 150),
                ("class_name", "Class", 80),
                ("particular", "Bill # / Particular", 220),
                ("amount", "Paid (Rs.)", 90),
                ("discount", "Discount (Rs.)", 90),
                ("account", "Account", 130),
                ("method", "Method", 80),
                ("receipt", "Receipt #", 95),
            ],
        )
        self.payment_tree.configure(selectmode="browse")
        self.payment_tree.bind("<Double-1>", lambda e: self.open_selected_payment_pdf())

        pay_toolbar = ttk.Frame(self.tab_payments)
        pay_toolbar.pack(fill="x", pady=(6, 0))
        self.del_pay_tab_btn = ttk.Button(pay_toolbar, text="🗑️ Delete Payment Record", command=self.delete_payment_from_tab)
        self.del_pay_tab_btn.pack(side="left")
        ttk.Button(pay_toolbar, text="📄 Open Receipt PDF", style="Accent.TButton", command=self.open_selected_payment_pdf).pack(side="left", padx=4)
        ttk.Button(pay_toolbar, text="🖨️ Print Receipt", command=self.print_selected_payment_receipt).pack(side="left", padx=4)
        if getattr(self.app.services, "settings", None) and self.app.services.settings.get_bool("whatsapp_enabled", False):
            ttk.Button(pay_toolbar, text="💬 WhatsApp Receipt", command=self.send_selected_payment_whatsapp).pack(side="left", padx=4)
        ttk.Button(pay_toolbar, text="🔄 Refresh Payments", command=self.refresh_payments_tab).pack(side="right", padx=3)

    def on_filter_changed(self, *_args):
        self.apply_filters()

    def reset_filters(self):
        self.filter_status_var.set("Pending Dues Only (Credit)")
        self.filter_class_var.set("All Classes")
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
        self.all_payments = self.app.services.billing.list_payment_records(limit=1000)

        classes = ["All Classes"]
        db_classes = self.db.query(
            "SELECT DISTINCT COALESCE(cl.level_name, s.class_name) AS cname "
            "FROM students s "
            "LEFT JOIN class_levels cl ON cl.id = s.class_level_id "
            "WHERE COALESCE(cl.level_name, s.class_name) IS NOT NULL "
            "  AND COALESCE(cl.level_name, s.class_name) <> '' "
            "ORDER BY cname"
        )
        for r in db_classes:
            if r["cname"] and r["cname"] not in classes:
                classes.append(r["cname"])
        self.class_combo["values"] = classes

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
        class_choice = self.filter_class_var.get()
        period_choice = self.filter_period_var.get()
        search_kw = self.search_var.get().strip().lower()

        # 1. Update Student Credit Summary Tree
        min_months = 2 if "2+" in status_choice else 1
        summaries = self.app.services.billing.get_student_dues_summary(
            min_unpaid_months=min_months,
            search=search_kw,
            class_name="" if class_choice == "All Classes" else class_choice,
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
                    s.get("class_name") or "—",
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

            # Class filter
            if class_choice != "All Classes":
                b_class = getattr(b, "class_name", "") or ""
                if b_class.strip().lower() != class_choice.strip().lower():
                    continue

            # Period filter
            if period_choice != "All Periods":
                seg_list = self.app.services.billing.segregate_period(b.billing_period)
                if b.billing_period != period_choice and period_choice not in seg_list:
                    continue

            # Search filter
            if search_kw:
                seg_str = " ".join(self.app.services.billing.segregate_period(b.billing_period))
                match_content = f"{b.bill_number} {b.student_name} {getattr(b, 'class_name', '')} {b.course_name} {getattr(b, 'contact', '')} {b.billing_period} {seg_str}".lower()
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
                    getattr(b, "class_name", "") or "—",
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

        # 3. Update Payment Records Tree
        self.clear_tree(self.payment_tree)
        filtered_payments = []
        tot_pay_amt = Decimal("0")
        for p in getattr(self, "all_payments", []):
            if class_choice != "All Classes":
                p_class = str(p.get("class_name") or "")
                if p_class.strip().lower() != class_choice.strip().lower():
                    continue

            if period_choice != "All Periods":
                p_date = str(p.get("transaction_date") or "")
                p_part = str(p.get("particular") or "")
                if period_choice not in p_date and period_choice not in p_part:
                    continue

            if search_kw:
                p_match = f"{p['id']} {p.get('student_name', '')} {p.get('class_name', '')} {p.get('particular', '')} {p.get('receipt_no', '')} {p.get('account_name', '')}".lower()
                if search_kw not in p_match:
                    continue

            filtered_payments.append(p)
            amt = Decimal(str(p.get("payment_amount") or 0))
            tot_pay_amt += amt
            disc = Decimal(str(p.get("discount_amount") or 0))
            self.payment_tree.insert(
                "",
                "end",
                values=(
                    p["id"],
                    p.get("transaction_date") or "—",
                    p.get("student_name") or "—",
                    p.get("class_name") or "—",
                    p.get("particular") or p.get("remarks") or "—",
                    money(amt),
                    money(disc),
                    p.get("account_name") or "—",
                    p.get("payment_method") or "—",
                    p.get("receipt_no") or "—",
                ),
            )

        if hasattr(self, "del_pay_tab_btn"):
            if self.is_admin():
                self.del_pay_tab_btn.configure(text="🗑️ Delete Payment Record", state="normal")
            else:
                self.del_pay_tab_btn.configure(text="🔒 Delete Payment (Admin Only)", state="disabled")

        self.summary_label.configure(
            text=f"Defaulters: {len(summaries)} · Due: {money(total_credit_due)} | Bills: {len(filtered_bills)} | Payments: {len(filtered_payments)}"
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

    def selected_student_ids(self) -> list[int]:
        selected = self.student_tree.selection()
        if not selected:
            raise ValueError("Select one or more students first.")
        return [int(self.student_tree.item(item, "values")[0]) for item in selected]

    def on_student_double_click(self, _event=None):
        self.open_student_statement()

    def open_student_statement(self):
        sel = self.student_tree.selection()
        if not sel:
            messagebox.showwarning("Select Student", "Please select one or more students from the list first.", parent=self)
            return
        if len(sel) > 5 and not messagebox.askyesno("Open Statements", f"This will generate and open statements for {len(sel)} students.\nDo you wish to continue?", parent=self):
            return
        try:
            for item_id in sel:
                item = self.student_tree.item(item_id)
                student_id = int(item["values"][0])
                path = self.app.services.billing.create_consolidated_statement_pdf(student_id=student_id)
                os.startfile(path)
        except Exception as exc:
            self.show_error(exc)

    def open_student_payment(self):
        sel = self.student_tree.selection()
        if not sel:
            messagebox.showwarning("Select Student", "Please select a student from the list first.", parent=self)
            return
        if len(sel) > 1:
            messagebox.showwarning("Single Student Only", "Payment settlement can only be processed for one student at a time.\nPlease select a single student.", parent=self)
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
        if len(sel) > 1:
            messagebox.showwarning("Single Student Only", "WhatsApp notice can only be previewed and sent to one student at a time.\nPlease select a single student.", parent=self)
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

    def print_pos_students_batch(self):
        try:
            student_ids = self.selected_student_ids()
        except Exception as exc:
            self.show_error(exc)
            return

        total_bills_count = 0
        total_due_amount = Decimal("0")
        for sid in student_ids:
            bills = self.app.services.billing.repository.get_unpaid_bills_for_student(sid)
            total_bills_count += len(bills)
            total_due_amount += sum(max(Decimal("0"), b.total_amount - b.paid_amount) for b in bills)

        if total_bills_count == 0:
            messagebox.showinfo("No Dues", "The selected student(s) have no unpaid dues.", parent=self)
            return

        num_students = len(student_ids)
        dialog = tk.Toplevel(self)
        dialog.title(f"Batch POS Print ({num_students} Student{'s' if num_students > 1 else ''})")
        dialog.geometry("520x330")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(
            content,
            text="🖨️ Bulk POS Printing — Student Credit",
            font=("Segoe UI", 12, "bold"),
            foreground="#102A43",
        ).pack(anchor="w", pady=(0, 4))

        summary_text = (
            f"Selected: {num_students} student(s) · {total_bills_count} unpaid bill(s)\n"
            f"Total Overdue: {money(total_due_amount)}"
        )
        ttk.Label(content, text=summary_text, font=("Segoe UI", 9), foreground="#0369A1").pack(anchor="w", pady=(0, 12))

        ttk.Label(content, text="Select POS Receipt Format:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))

        mode_var = tk.StringVar(value="statement")
        r1 = ttk.Radiobutton(
            content,
            text=f"📄 Consolidated Statements ({num_students} receipt{'s' if num_students > 1 else ''})\n    1 summary slip per student with all overdue months, total balance & QR.",
            variable=mode_var,
            value="statement",
        )
        r1.pack(anchor="w", pady=4)

        r2 = ttk.Radiobutton(
            content,
            text=f"🧾 Individual Due Bills ({total_bills_count} receipt{'s' if total_bills_count > 1 else ''})\n    Separate slip for each pending monthly due bill.",
            variable=mode_var,
            value="bills",
        )
        r2.pack(anchor="w", pady=4)

        button_box = ttk.Frame(content)
        button_box.pack(fill="x", side="bottom", pady=(16, 0))

        def execute_print():
            dialog.destroy()
            try:
                mode = mode_var.get()
                if mode == "statement":
                    printed_count = self.app.services.billing.print_pos_student_statements(student_ids)
                    messagebox.showinfo(
                        "Batch Printed",
                        f"Sent {printed_count} student consolidated statement(s) to the POS printer.",
                        parent=self,
                    )
                else:
                    printed_count = self.app.services.billing.print_pos_student_bills(student_ids)
                    messagebox.showinfo(
                        "Batch Printed",
                        f"Sent {printed_count} individual due bill(s) to the POS printer.",
                        parent=self,
                    )
            except Exception as err:
                self.show_error(err)

        ttk.Button(button_box, text="🖨️ Send to POS Printer", style="Accent.TButton", command=execute_print).pack(side="left")
        ttk.Button(button_box, text="Cancel", command=dialog.destroy).pack(side="right")

    def open_print_pos_by_class_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("🖨️ Print Bill POS by Class")
        dialog.geometry("540x390")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(
            content,
            text="🖨️ Filter & Print POS Bills by Class",
            font=("Segoe UI", 12, "bold"),
            foreground="#102A43",
        ).pack(anchor="w", pady=(0, 4))

        ttk.Label(
            content,
            text="Print thermal POS receipts for all unpaid students in a selected class/grade.",
            font=("Segoe UI", 9),
            foreground="#475569",
        ).pack(anchor="w", pady=(0, 10))

        form = ttk.Frame(content)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Select Class / Grade:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))

        current_class = self.filter_class_var.get()
        class_options = list(self.class_combo["values"])
        if not class_options:
            class_options = ["All Classes"]
        dlg_class_var = tk.StringVar(value=current_class if current_class in class_options else class_options[0])

        class_dropdown = ttk.Combobox(form, textvariable=dlg_class_var, values=class_options, state="readonly", width=24)
        class_dropdown.grid(row=0, column=1, sticky="w", pady=4)

        stats_card = ttk.LabelFrame(content, text="Class Summary (Unpaid Dues)", padding=10)
        stats_card.pack(fill="x", pady=(4, 10))

        stats_label = ttk.Label(stats_card, text="", font=("Segoe UI", 9, "bold"), foreground="#0369A1", justify="left")
        stats_label.pack(anchor="w")

        def update_stats(*_args):
            sel_class = dlg_class_var.get()
            unpaid_bills = self.app.services.billing.get_unpaid_bills_by_class(
                "" if sel_class == "All Classes" else sel_class
            )
            s_ids = {b.student_id for b in unpaid_bills}
            tot_due = sum(max(Decimal("0"), b.total_amount - b.paid_amount) for b in unpaid_bills)
            stats_label.configure(
                text=f"Target: {sel_class}\n"
                     f"• Unpaid Students: {len(s_ids)}\n"
                     f"• Pending Unpaid Bills: {len(unpaid_bills)}\n"
                     f"• Total Balance Overdue: {money(tot_due)}"
            )

        class_dropdown.bind("<<ComboboxSelected>>", update_stats)
        update_stats()

        ttk.Label(content, text="Select POS Receipt Format:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        mode_var = tk.StringVar(value="statement")
        r1 = ttk.Radiobutton(
            content,
            text="📄 Consolidated Statements (1 summary slip per student with all overdue months & QR)",
            variable=mode_var,
            value="statement",
        )
        r1.pack(anchor="w", pady=3)
        r2 = ttk.Radiobutton(
            content,
            text="🧾 Individual Due Bills (Separate slip for each pending monthly due bill)",
            variable=mode_var,
            value="bills",
        )
        r2.pack(anchor="w", pady=3)

        btn_box = ttk.Frame(content)
        btn_box.pack(fill="x", side="bottom", pady=(12, 0))

        def execute_print():
            sel_class = dlg_class_var.get()
            chosen_mode = mode_var.get()
            dialog.destroy()
            try:
                res = self.app.services.billing.print_pos_by_class(
                    "" if sel_class == "All Classes" else sel_class,
                    mode=chosen_mode,
                )
                fmt_name = "statement(s)" if res["mode"] == "statement" else "bill receipt(s)"
                messagebox.showinfo(
                    "POS Print Completed",
                    f"Successfully sent {res['printed_count']} {fmt_name} for Class '{res['class_name']}' ({res['student_count']} student(s)) to the POS printer.",
                    parent=self,
                )
                self.refresh()
            except Exception as err:
                self.show_error(err)

        ttk.Button(btn_box, text="🖨️ Send to POS Printer", style="Accent.TButton", command=execute_print).pack(side="left")
        ttk.Button(btn_box, text="Cancel", command=dialog.destroy).pack(side="right")

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
        student_class = getattr(bills[0], "class_name", "") or ""
        is_multi = len(bills) > 1

        dialog = tk.Toplevel(self)
        dialog.title(f"Combined Payment ({len(bills)} Bills)" if is_multi else "Quick Bill Payment")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)

        class_tag = f" ({student_class})" if student_class else ""
        panel_title = f"{student_name}{class_tag} — {len(bills)} Bills Combined" if is_multi else f"{student_name}{class_tag} - {bills[0].bill_number}"
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
            class_str = f"    Class: {student_class}" if student_class else ""
            ttk.Label(panel, text=f"Course: {bills[0].course_name}{class_str}    Period: {bills[0].billing_period}").grid(row=cur_row, column=0, columnspan=2, sticky="w", pady=(0, 8))
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

    def is_admin(self) -> bool:
        role = getattr(getattr(self.app, "session", None), "role", "")
        return role in ("super_admin", "admin") or self.can("administration.manage")

    def refresh_payments_tab(self):
        self.all_payments = self.app.services.billing.list_payment_records(limit=1000)
        self.apply_filters()

    def selected_payment_id(self) -> int:
        sel = self.payment_tree.selection()
        if not sel:
            raise ValueError("Select a payment record first.")
        return int(self.payment_tree.item(sel[0], "values")[0])

    def open_selected_payment_pdf(self):
        try:
            pid = self.selected_payment_id()
            path = self.app.services.reports.payment_proof_pdf("student", pid)
            os.startfile(Path(path))
        except Exception as exc:
            self.show_error(exc)

    def print_selected_payment_receipt(self):
        try:
            pid = self.selected_payment_id()
            path = self.app.services.reports.payment_proof_pdf("student", pid)
            os.startfile(Path(path), "print")
        except Exception as exc:
            self.show_error(exc)

    def send_selected_payment_whatsapp(self):
        try:
            pid = self.selected_payment_id()
            self.send_whatsapp_payment_receipt(pid)
        except Exception as exc:
            self.show_error(exc)

    def delete_payment_from_tab(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied", "Only administrators are authorized to delete payment records.", parent=self)
            return
        sel = self.payment_tree.selection()
        if not sel:
            messagebox.showwarning("Select Payment", "Please select a payment record to delete from the list.", parent=self)
            return
        item = self.payment_tree.item(sel[0])
        txn_id = int(item["values"][0])
        date_str = str(item["values"][1])
        student_name = str(item["values"][2])
        part_str = str(item["values"][4])
        paid_str = str(item["values"][5])
        disc_str = str(item["values"][6])
        receipt_str = str(item["values"][9])

        confirm_msg = (
            f"⚠️ ARE YOU SURE YOU WANT TO DELETE THIS PAYMENT RECORD?\n\n"
            f"• Payment Record ID: #{txn_id}\n"
            f"• Date: {date_str}\n"
            f"• Student: {student_name}\n"
            f"• Paid Amount: {paid_str}\n"
            f"• Discount: {disc_str}\n"
            f"• Receipt #: {receipt_str}\n"
            f"• Particular: {part_str}\n\n"
            f"Deleting this payment record will:\n"
            f"1. Reverse this payment amount and restore the balance on the associated due bill(s).\n"
            f"2. Reverse the credit entry from the cash/bank account ledger.\n"
            f"3. Restore the student's overdue credit dues.\n"
            f"4. Log this event in the system administrative audit log.\n\n"
            f"This action CANNOT be undone. Proceed?"
        )
        if not messagebox.askyesno("Confirm Delete Payment (Admin Access)", confirm_msg, icon="warning", parent=self):
            return

        try:
            actor = getattr(self.app.session, "username", "admin")
            actor_id = getattr(self.app.session, "user_id", None)
            actor_role = getattr(self.app.session, "role", "admin")
            res = self.app.services.billing.delete_payment(
                transaction_id=txn_id,
                actor_user_id=actor_id,
                actor_username=actor,
                actor_role=actor_role,
            )
            self.app.refresh_all()
            messagebox.showinfo(
                "Payment Deleted",
                f"Payment record #{txn_id} was successfully deleted.\n\n"
                f"• Reverted Payment: Rs. {res['reverted_payment']:,.2f}\n"
                f"• Reverted Discount: Rs. {res['reverted_discount']:,.2f}\n"
                f"Bills and financial ledgers have been updated.",
                parent=self,
            )
        except Exception as err:
            self.show_error(err)

    def delete_selected_bill(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied", "Only administrators are authorized to delete bills.", parent=self)
            return
        try:
            bill = self.selected_bill()
        except Exception:
            messagebox.showinfo("Selection Required", "Please select a bill to delete.", parent=self)
            return

        is_paid = bill.paid_amount > Decimal("0")
        if is_paid:
            msg = (
                f"⚠️ ADMINISTRATOR WARNING: DELETE PAID BILL\n\n"
                f"Bill #{bill.bill_number} for {bill.student_name} has recorded payments of Rs. {bill.paid_amount:,.2f}!\n\n"
                f"Deleting this bill will automatically:\n"
                f"• Permanently delete the bill and its line items\n"
                f"• Revert and remove all associated payment transactions\n"
                f"• Reverse matching General Ledger entries\n"
                f"• Recalculate student account balances\n\n"
                f"Are you sure you want to permanently delete this PAID bill?"
            )
        else:
            msg = f"Are you sure you want to permanently delete unpaid bill #{bill.bill_number} for {bill.student_name}?"

        if not messagebox.askyesno("Confirm Delete Bill", msg, icon="warning", parent=self):
            return

        try:
            user = getattr(self.app, "current_user", None)
            role = getattr(user, "role", "admin") if user else "admin"
            username = getattr(user, "username", "admin") if user else "admin"
            uid = getattr(user, "user_id", None) if user else None
            res = self.app.services.billing.delete_bill(
                bill_id=bill.id,
                actor_user_id=uid,
                actor_username=username,
                actor_role=role,
                force_paid=True,
            )
            self.refresh()
            rev_info = f"\nReverted {len(res.get('reverted_payments', []))} payment transaction(s)." if is_paid else ""
            messagebox.showinfo("Deleted", f"Bill #{bill.bill_number} was successfully deleted.{rev_info}", parent=self)
        except Exception as err:
            messagebox.showerror("Error", str(err), parent=self)

    def open_bill_payments(self):
        try:
            bill = self.selected_bill()
        except Exception as exc:
            self.show_error(exc)
            return

        payments = self.app.services.billing.get_payments_for_bill(bill.id)

        dialog = tk.Toplevel(self)
        dialog.title(f"Payment Records — Bill {bill.bill_number} ({bill.student_name})")
        dialog.geometry("820x520")
        dialog.minsize(700, 420)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        top = ttk.Frame(dialog, padding=14)
        top.pack(fill="both", expand=True)

        # Header info
        hdr = ttk.Frame(top)
        hdr.pack(fill="x", pady=(0, 8))
        ttk.Label(
            hdr,
            text=f"💳 Payment Records for Bill: {bill.bill_number}",
            font=("Segoe UI", 12, "bold"),
            foreground="#102A43",
        ).pack(anchor="w")
        class_str = f"  |  Class: {getattr(bill, 'class_name', '')}" if getattr(bill, "class_name", "") else ""
        sub_text = (
            f"Student: {bill.student_name}{class_str}  |  Course: {bill.course_name}  |  Period: {bill.billing_period}\n"
            f"Total Bill: {money(bill.total_amount)}  |  Paid: {money(bill.paid_amount)}  |  "
            f"Balance Due: {money(max(Decimal('0'), bill.total_amount - bill.paid_amount))}  |  Status: {bill.status}"
        )
        ttk.Label(hdr, text=sub_text, font=("Segoe UI", 9), foreground="#334155").pack(anchor="w", pady=(2, 0))

        # Payments table
        tree_area = ttk.Frame(top)
        tree_area.pack(fill="both", expand=True, pady=6)
        pay_tree = ttk.Treeview(
            tree_area,
            columns=("id", "date", "receipt", "paid", "discount", "method", "account", "particular"),
            show="headings",
        )
        for col_id, col_name, col_w in [
            ("id", "ID", 45),
            ("date", "Date", 90),
            ("receipt", "Receipt #", 95),
            ("paid", "Paid (Rs.)", 90),
            ("discount", "Discount", 80),
            ("method", "Method", 80),
            ("account", "Account", 130),
            ("particular", "Particular / Remarks", 200),
        ]:
            pay_tree.heading(col_id, text=col_name)
            pay_tree.column(col_id, width=col_w, anchor="w")

        p_scroll = ttk.Scrollbar(tree_area, orient="vertical", command=pay_tree.yview)
        pay_tree.configure(yscrollcommand=p_scroll.set)
        pay_tree.pack(side="left", fill="both", expand=True)
        p_scroll.pack(side="right", fill="y")

        def populate_tree():
            for item in pay_tree.get_children():
                pay_tree.delete(item)
            nonlocal payments
            payments = self.app.services.billing.get_payments_for_bill(bill.id)
            for p in payments:
                pay_tree.insert(
                    "", "end",
                    values=(
                        p["id"],
                        p.get("transaction_date") or "—",
                        p.get("receipt_no") or "—",
                        money(Decimal(str(p.get("payment_amount") or 0))),
                        money(Decimal(str(p.get("discount_amount") or 0))),
                        p.get("payment_method") or "—",
                        p.get("account_name") or "—",
                        p.get("particular") or p.get("remarks") or "—",
                    ),
                )

        populate_tree()

        # Action bar
        btn_bar = ttk.Frame(top, padding=(0, 8))
        btn_bar.pack(fill="x", side="bottom")

        def delete_selected_payment():
            if not self.is_admin():
                messagebox.showerror("Access Denied", "Only administrators are authorized to delete payment records.", parent=dialog)
                return
            sel = pay_tree.selection()
            if not sel:
                messagebox.showwarning("Select Payment", "Please select a payment record to delete.", parent=dialog)
                return
            item = pay_tree.item(sel[0])
            txn_id = int(item["values"][0])
            paid_str = str(item["values"][3])
            receipt_str = str(item["values"][2])

            confirm_msg = (
                f"⚠️ ARE YOU SURE YOU WANT TO DELETE THIS PAYMENT RECORD?\n\n"
                f"• Payment Record ID: #{txn_id}\n"
                f"• Amount: {paid_str}\n"
                f"• Receipt #: {receipt_str}\n"
                f"• Target Bill: {bill.bill_number}\n\n"
                f"Deleting this payment will:\n"
                f"1. Reverse this payment amount and restore the balance on Bill {bill.bill_number}.\n"
                f"2. Reverse the corresponding credit entry in the cash/bank account ledger.\n"
                f"3. Restore the student's overdue balance.\n"
                f"4. Log this administrative event in the audit trail.\n\n"
                f"This action CANNOT be undone. Proceed?"
            )
            if not messagebox.askyesno("Confirm Delete Payment (Admin Access)", confirm_msg, icon="warning", parent=dialog):
                return

            try:
                actor = getattr(self.app.session, "username", "admin")
                actor_id = getattr(self.app.session, "user_id", None)
                actor_role = getattr(self.app.session, "role", "admin")
                res = self.app.services.billing.delete_payment(
                    transaction_id=txn_id,
                    actor_user_id=actor_id,
                    actor_username=actor,
                    actor_role=actor_role,
                )
                self.app.refresh_all()
                dialog.destroy()
                messagebox.showinfo(
                    "Payment Deleted",
                    f"Payment record #{txn_id} was successfully deleted.\n\n"
                    f"• Reverted Payment: Rs. {res['reverted_payment']:,.2f}\n"
                    f"• Reverted Discount: Rs. {res['reverted_discount']:,.2f}\n"
                    f"Bill and financial ledgers have been updated.",
                    parent=self,
                )
            except Exception as err:
                messagebox.showerror("Error Deleting Payment", str(err), parent=dialog)

        def open_receipt_pdf():
            sel = pay_tree.selection()
            if not sel:
                messagebox.showwarning("Select Payment", "Please select a payment record first.", parent=dialog)
                return
            txn_id = int(pay_tree.item(sel[0])["values"][0])
            try:
                path = self.app.services.reports.payment_proof_pdf("student", txn_id)
                os.startfile(Path(path))
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        def print_receipt():
            sel = pay_tree.selection()
            if not sel:
                messagebox.showwarning("Select Payment", "Please select a payment record first.", parent=dialog)
                return
            txn_id = int(pay_tree.item(sel[0])["values"][0])
            try:
                path = self.app.services.reports.payment_proof_pdf("student", txn_id)
                os.startfile(Path(path), "print")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dialog)

        if self.is_admin():
            del_btn = ttk.Button(btn_bar, text="🗑️ Delete Payment Record", command=delete_selected_payment)
            del_btn.pack(side="left", padx=3)
        else:
            del_btn = ttk.Button(btn_bar, text="🔒 Delete Payment (Admin Only)", state="disabled")
            del_btn.pack(side="left", padx=3)

        ttk.Button(btn_bar, text="📄 Open Receipt PDF", command=open_receipt_pdf).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="🖨️ Print Receipt", command=print_receipt).pack(side="left", padx=3)
        ttk.Button(btn_bar, text="Close", command=dialog.destroy).pack(side="right", padx=3)

    def open_edit_bill(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Select Bill", "Please select a bill from the list to edit.", parent=self)
            return
        item_id = selection[0]
        values = self.tree.item(item_id, "values")
        bill_id = int(values[0])
        bill = self.app.services.billing.repository.get(bill_id)
        if not bill:
            messagebox.showerror("Error", f"Bill #{bill_id} was not found.", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Due Bill #{bill.id} ({bill.bill_number})")
        dialog.geometry("620x700")
        dialog.minsize(540, 560)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        top = ttk.Frame(dialog, padding=16)
        top.pack(fill="both", expand=True)

        ttk.Label(top, text=f"Edit Bill: {bill.bill_number}", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 4))
        class_str = getattr(bill, "class_name", "") or "—"
        ttk.Label(top, text=f"Student: {bill.student_name}  |  Course: {bill.course_name}  |  Class: {class_str}", foreground="#475569").pack(anchor="w", pady=(0, 10))

        form_frame = ttk.Frame(top)
        form_frame.pack(fill="x")

        period_var = tk.StringVar(value=bill.billing_period)
        issue_var = tk.StringVar(value=bill.issue_date)
        due_var = tk.StringVar(value=bill.due_date)
        subtotal_var = tk.StringVar(value=f"{bill.subtotal:.2f}")
        discount_var = tk.StringVar(value=f"{bill.discount:.2f}")
        remarks_var = tk.StringVar(value=getattr(bill, "remarks", "") or "")

        fb = FormBuilder(form_frame)
        fb.entry("Billing Period (YYYY/MM) *", period_var)
        fb.entry("Issue Date (YYYY/MM/DD) *", issue_var)
        fb.entry("Due Date (YYYY/MM/DD) *", due_var)
        fb.entry("Subtotal / Fee (Rs.) *", subtotal_var)
        fb.entry("Discount (Rs.)", discount_var)
        fb.entry("Remarks", remarks_var)

        calc_box = ttk.LabelFrame(top, text="Payment & Balance Preview", padding=10)
        calc_box.pack(fill="x", pady=8)

        total_lbl = ttk.Label(calc_box, text="", font=("Segoe UI", 10, "bold"))
        total_lbl.pack(anchor="w")
        paid_lbl = ttk.Label(calc_box, text=f"Paid Amount: {money(bill.paid_amount)}", foreground="#059669")
        paid_lbl.pack(anchor="w")
        balance_lbl = ttk.Label(calc_box, text="", font=("Segoe UI", 10, "bold"))
        balance_lbl.pack(anchor="w")
        status_lbl = ttk.Label(calc_box, text="", font=("Segoe UI", 9))
        status_lbl.pack(anchor="w")

        def update_calc(*_):
            try:
                sub = parse_amount(subtotal_var.get() or "0")
                disc = parse_amount(discount_var.get() or "0")
                tot = max(Decimal("0"), sub - disc)
                bal = max(Decimal("0"), tot - bill.paid_amount)
                if bill.paid_amount >= tot and tot > 0:
                    st = "Paid"
                    clr = "#059669"
                elif bill.paid_amount > 0:
                    st = "Partially Paid"
                    clr = "#D97706"
                else:
                    st = "Due"
                    clr = "#DC2626"

                total_lbl.config(text=f"Total Bill Amount: {money(tot)}")
                balance_lbl.config(text=f"Remaining Balance Due: {money(bal)}", foreground=clr)
                status_lbl.config(text=f"Updated Status will be: {st}", foreground=clr)
            except Exception:
                pass

        subtotal_var.trace_add("write", update_calc)
        discount_var.trace_add("write", update_calc)
        update_calc()

        # Recorded Payments Subpanel
        pay_records = self.app.services.billing.get_payments_for_bill(bill.id)
        if pay_records:
            p_box = ttk.LabelFrame(top, text=f"Recorded Payments on this Bill ({len(pay_records)})", padding=6)
            p_box.pack(fill="both", expand=True, pady=(4, 8))
            p_cols = [("id", "ID", 45), ("date", "Date", 85), ("receipt", "Receipt", 85), ("paid", "Paid (Rs.)", 85), ("method", "Method", 75), ("account", "Account", 110)]
            p_tree = self.make_tree(p_box, p_cols, height=min(4, len(pay_records)))
            for pr in pay_records:
                p_tree.insert("", "end", values=(pr["id"], pr.get("transaction_date") or "—", pr.get("receipt_no") or "—", money(Decimal(str(pr.get("payment_amount") or 0))), pr.get("payment_method") or "—", pr.get("account_name") or "—"))
            if self.is_admin():
                p_bar = ttk.Frame(p_box)
                p_bar.pack(fill="x", pady=(4, 0))
                def delete_pay_from_edit():
                    sel = p_tree.selection()
                    if not sel:
                        messagebox.showwarning("Select Payment", "Please select a payment record from the list above.", parent=dialog)
                        return
                    txn_id = int(p_tree.item(sel[0])["values"][0])
                    paid_val = str(p_tree.item(sel[0])["values"][3])
                    if not messagebox.askyesno(
                        "Confirm Delete Payment (Admin Access)",
                        f"Are you sure you want to delete payment #{txn_id} of {paid_val}?\n\n"
                        f"This will revert the paid amount on Bill {bill.bill_number}, reverse the ledger credit entry, and restore student dues.\n\n"
                        f"Proceed?",
                        icon="warning",
                        parent=dialog,
                    ):
                        return
                    try:
                        actor = getattr(self.app.session, "username", "admin")
                        actor_id = getattr(self.app.session, "user_id", None)
                        actor_role = getattr(self.app.session, "role", "admin")
                        self.app.services.billing.delete_payment(
                            transaction_id=txn_id,
                            actor_user_id=actor_id,
                            actor_username=actor,
                            actor_role=actor_role,
                        )
                        dialog.destroy()
                        self.app.refresh_all()
                        messagebox.showinfo("Payment Deleted", f"Payment #{txn_id} deleted and bill balance restored.", parent=self)
                    except Exception as err:
                        messagebox.showerror("Error", str(err), parent=dialog)
                ttk.Button(p_bar, text="🗑️ Delete Selected Payment", command=delete_pay_from_edit).pack(side="left")

        btn_row = ttk.Frame(top)
        btn_row.pack(fill="x", pady=(10, 0))

        def save_changes():
            try:
                sub = parse_amount(subtotal_var.get() or "0", "Subtotal")
                disc = parse_amount(discount_var.get() or "0", "Discount")
                self.app.services.billing.update_bill(
                    bill_id=bill.id,
                    billing_period=period_var.get().strip(),
                    issue_date=issue_var.get().strip(),
                    due_date=due_var.get().strip(),
                    subtotal=sub,
                    discount=disc,
                    remarks=remarks_var.get().strip(),
                )
                dialog.destroy()
                self.refresh()
                messagebox.showinfo("Success", f"Bill #{bill.id} updated successfully!", parent=self)
            except Exception as exc:
                messagebox.showerror("Update Error", str(exc), parent=dialog)

        ttk.Button(btn_row, text="Cancel", command=dialog.destroy).pack(side="left")

        if self.is_admin():
            def delete_bill_action():
                is_paid = bill.paid_amount > Decimal("0")
                if is_paid:
                    msg = (
                        f"⚠️ ADMINISTRATOR WARNING: DELETE PAID BILL\n\n"
                        f"Bill #{bill.bill_number} has recorded payments of Rs. {bill.paid_amount:,.2f}!\n\n"
                        f"Deleting this bill will automatically:\n"
                        f"• Permanently delete the bill and its line items\n"
                        f"• Revert and remove all associated payment transactions\n"
                        f"• Reverse matching General Ledger entries\n"
                        f"• Recalculate student account balances\n\n"
                        f"Are you sure you want to permanently delete this PAID bill?"
                    )
                else:
                    msg = f"Are you sure you want to permanently delete unpaid due bill #{bill.bill_number}?"

                if not messagebox.askyesno("Confirm Delete Bill", msg, icon="warning", parent=dialog):
                    return
                try:
                    user = getattr(self.app, "current_user", None)
                    role = getattr(user, "role", "admin") if user else "admin"
                    username = getattr(user, "username", "admin") if user else "admin"
                    uid = getattr(user, "user_id", None) if user else None
                    res = self.app.services.billing.delete_bill(
                        bill_id=bill.id,
                        actor_user_id=uid,
                        actor_username=username,
                        actor_role=role,
                        force_paid=True,
                    )
                    dialog.destroy()
                    self.refresh()
                    rev_info = f"\nReverted {len(res.get('reverted_payments', []))} payment transaction(s)." if is_paid else ""
                    messagebox.showinfo("Deleted", f"Bill #{bill.bill_number} was successfully deleted.{rev_info}", parent=self)
                except Exception as err:
                    messagebox.showerror("Error", str(err), parent=dialog)
            ttk.Button(btn_row, text="🗑️ Delete Bill", command=delete_bill_action).pack(side="left", padx=(6, 0))

        ttk.Button(btn_row, text="💾 Save Changes", style="Accent.TButton", command=save_changes).pack(side="right")

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
        class_str = f" [{data['class_name']}]" if data.get("class_name") else ""
        dialog.title(f"WhatsApp Due Bill - {data['student_name']}{class_str} ({data['bill_number']})")
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
        separate_bills = tk.BooleanVar(value=True)
        fb=FormBuilder(top);fb.entry("Start Month (YYYY/MM) *",start_month);fb.entry("End Month (YYYY/MM) *",end_month);fb.entry("Issue Date *",issue);fb.entry("Due Date *",due);fb.entry("Remarks",remarks)
        fb.check("Bill Format", separate_bills, "Generate separate bill for each month")
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
                if separate_bills.get():
                    results=self.app.services.billing.generate_month_range(ids,start_month.get(),end_month.get(),validate_date(issue.get(),"Issue date"),validate_date(due.get(),"Due date"),remarks.get())
                    label_type="Separate monthly student bills"
                else:
                    results=self.app.services.billing.generate_combined_month_range(ids,start_month.get(),end_month.get(),validate_date(issue.get(),"Issue date"),validate_date(due.get(),"Due date"),remarks.get())
                    label_type="Combined student bills"
                created=sum(1 for result in results if result.created);existing=len(results)-created;not_started=len(ids)-len(results)
                dialog.destroy();self.refresh();messagebox.showinfo("Batch Complete",f"{label_type} generated: {created}\nAlready billed or paid (skipped): {existing}\nNot yet enrolled for selected months (skipped): {not_started}\nStudents/enrollments selected: {len(ids)}",parent=self)
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

