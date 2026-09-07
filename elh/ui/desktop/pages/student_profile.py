from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from PIL import Image, ImageOps, ImageTk

from elh.ui.desktop.helpers import open_or_print_pdf


class StudentProfileDialog(tk.Toplevel):
    """Rich 360-degree Student Profile & Dossier Viewer with ReportLab PDF printing."""

    def __init__(
        self,
        parent: tk.Widget,
        app: Any,
        student_id: int,
        on_edit_requested: Callable[[int], None] | None = None,
        on_sms_requested: Callable[[int], None] | None = None,
        on_enroll_requested: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.student_id = student_id
        self.on_edit_requested = on_edit_requested
        self.on_sms_requested = on_sms_requested
        self.on_enroll_requested = on_enroll_requested

        self._tk_photo: ImageTk.PhotoImage | None = None
        self.profile: dict[str, Any] = {}

        self.title("Student Profile")
        self.configure(background="#EEF3F8")
        self.transient(parent.winfo_toplevel())
        self.minsize(980, 700)

        # Main container
        self.main_container = ttk.Frame(self, padding=12)
        self.main_container.pack(fill="both", expand=True)

        if not self.load_data():
            self.destroy()
            return

        self._build_ui()
        self._center_window(1040, 740)
        self.focus_set()

    def _center_window(self, width: int, height: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(width, sw - 40)
        h = min(height, sh - 60)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def load_data(self) -> bool:
        """Fetch fresh profile data from StudentService."""
        try:
            self.profile = self.app.services.students.get_profile(self.student_id)
            student_name = self.profile["student"].get("student_name", "Student")
            self.title(f"Student Profile - {student_name} (#{self.student_id})")
            return True
        except Exception as exc:
            messagebox.showerror("Profile Error", f"Failed to load student profile: {exc}", parent=self)
            return False

    def reload(self) -> None:
        """Refresh profile data and rebuild the interface."""
        if not self.load_data():
            return
        for widget in self.main_container.winfo_children():
            widget.destroy()
        self._build_ui()

    def _build_ui(self) -> None:
        student = self.profile["student"]
        financials = self.profile["financials"]
        attendance = self.profile["attendance"]

        # ==================== 1. TOP HEADER HERO CARD ====================
        header_card = tk.Frame(self.main_container, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1)
        header_card.pack(fill="x", pady=(0, 10))

        header_inner = ttk.Frame(header_card, style="Header.TFrame", padding=12)
        header_inner.pack(fill="both", expand=True)

        # 1A. Photo Area
        photo_container = tk.Frame(
            header_inner,
            width=110,
            height=132,
            bg="#F1F5F9",
            highlightbackground="#94A3B8",
            highlightthickness=1,
        )
        photo_container.pack_propagate(False)
        photo_container.pack(side="left", padx=(0, 16), pady=2)
        self._render_photo(photo_container, student)

        # 1B. Bio & Identity Info (Center)
        bio_frame = ttk.Frame(header_inner, style="Header.TFrame")
        bio_frame.pack(side="left", fill="both", expand=True)

        # Name & Status Badge row
        title_row = ttk.Frame(bio_frame, style="Header.TFrame")
        title_row.pack(fill="x", anchor="w", pady=(0, 4))

        student_name = student.get("student_name", "Student")
        name_label = ttk.Label(title_row, text=student_name, style="HeaderTitle.TLabel")
        name_label.pack(side="left", padx=(0, 10))

        status_text = student.get("status", "Active")
        status_bg = "#DCFCE7" if status_text == "Active" else "#FEE2E2"
        status_fg = "#15803D" if status_text == "Active" else "#B91C1C"
        badge = tk.Label(
            title_row,
            text=f"● {status_text.upper()}",
            font=("Segoe UI", 9, "bold"),
            bg=status_bg,
            fg=status_fg,
            padx=8,
            pady=2,
            relief="flat",
        )
        badge.pack(side="left")

        # Identity Grid Details
        grid_frame = ttk.Frame(bio_frame, style="Header.TFrame")
        grid_frame.pack(fill="x", anchor="w", pady=(2, 0))

        cls_name = student.get("class_level_name") or student.get("class_name") or "Unassigned"
        school_name = student.get("school_name") or "None"
        contact = student.get("contact") or "None"
        parent = f"{student.get('parent_name') or 'None'} ({student.get('guardian_relationship') or 'Guardian'})"
        dob = student.get("date_of_birth") or "-"
        gender = student.get("gender") or "-"
        joining = student.get("joining_date") or "-"
        address = student.get("address") or "-"
        device_str = f"User #{student.get('device_user_id')}" if student.get("device_user_id") else "Not Mapped"
        if student.get("device_user_name"):
            device_str += f" ({student['device_user_name']})"

        details_left = [
            ("Student ID:", f"#{student.get('id')}"),
            ("Class / Level:", cls_name),
            ("School / Inst.:", school_name),
            ("Primary Contact:", contact),
        ]
        details_right = [
            ("Parent / Guardian:", parent),
            ("DOB & Gender:", f"{dob} | {gender}"),
            ("Joining Date:", joining),
            ("Biometric Device:", device_str),
        ]

        for r_idx, (label, val) in enumerate(details_left):
            ttk.Label(grid_frame, text=label, font=("Segoe UI", 9, "bold"), style="HeaderMeta.TLabel").grid(
                row=r_idx, column=0, sticky="w", padx=(0, 6), pady=1
            )
            ttk.Label(grid_frame, text=val, font=("Segoe UI", 9), style="HeaderMeta.TLabel").grid(
                row=r_idx, column=1, sticky="w", padx=(0, 20), pady=1
            )

        for r_idx, (label, val) in enumerate(details_right):
            ttk.Label(grid_frame, text=label, font=("Segoe UI", 9, "bold"), style="HeaderMeta.TLabel").grid(
                row=r_idx, column=2, sticky="w", padx=(0, 6), pady=1
            )
            ttk.Label(grid_frame, text=val, font=("Segoe UI", 9), style="HeaderMeta.TLabel").grid(
                row=r_idx, column=3, sticky="w", pady=1
            )

        # 1C. Actions Area (Right)
        actions_frame = ttk.Frame(header_inner, style="Header.TFrame")
        actions_frame.pack(side="right", fill="y", padx=(10, 0))

        ttk.Button(
            actions_frame,
            text="🖨 Print / Export PDF",
            style="Accent.TButton",
            command=lambda: self.export_pdf(print_now=False),
        ).pack(fill="x", pady=2)

        ttk.Button(
            actions_frame,
            text="🖨 Direct Print",
            command=lambda: self.export_pdf(print_now=True),
        ).pack(fill="x", pady=2)

        ttk.Button(
            actions_frame,
            text="✏ Edit Details",
            command=self._handle_edit,
        ).pack(fill="x", pady=2)

        ttk.Button(
            actions_frame,
            text="✉ Send SMS",
            command=self._handle_sms,
        ).pack(fill="x", pady=2)

        ttk.Button(
            actions_frame,
            text="🔄 Refresh",
            command=self.reload,
        ).pack(fill="x", pady=2)

        # ==================== 2. KPI METRICS ROW ====================
        kpi_frame = ttk.Frame(self.main_container)
        kpi_frame.pack(fill="x", pady=(0, 10))
        for i in range(4):
            kpi_frame.columnconfigure(i, weight=1)

        total_due = financials["total_due"]
        due_color = "#DC2626" if total_due > 0 else "#15803D"
        due_label = f"Rs. {total_due:,.2f}"
        due_sub = "Clear / All Paid" if total_due == 0 else f"{len(financials['due_bills'])} bill(s) pending"

        active_count = len(self.profile["active_enrollments"])
        prev_count = len(self.profile["previous_enrollments"])
        enroll_val = f"{active_count} Active"
        enroll_sub = f"{prev_count} Previous / Completed"

        c_month = attendance.get("current_month", "-")
        days_pres = attendance.get("days_present_month", 0)
        punches_pres = attendance.get("total_punches_month", 0)
        att_val = f"{days_pres} Days Present"
        att_sub = f"{punches_pres} punches ({c_month}) • {attendance.get('lifetime_days', 0)} lifetime"

        tot_paid = financials["total_paid"]
        tot_billed = financials["total_billed"]
        fin_val = f"Rs. {tot_paid:,.2f}"
        fin_sub = f"Billed: Rs. {tot_billed:,.2f} | Disc: Rs. {financials['total_discount']:,.2f}"

        self._create_kpi_card(kpi_frame, 0, "OUTSTANDING DUE", due_label, due_sub, due_color)
        self._create_kpi_card(kpi_frame, 1, "COURSES ENROLLED", enroll_val, enroll_sub, "#0284C7")
        self._create_kpi_card(kpi_frame, 2, f"ATTENDANCE ({c_month})", att_val, att_sub, "#059669")
        self._create_kpi_card(kpi_frame, 3, "TOTAL PAID TO DATE", fin_val, fin_sub, "#183B56")

        # ==================== 3. TABBED NOTEBOOK ====================
        notebook = ttk.Notebook(self.main_container)
        notebook.pack(fill="both", expand=True)

        tab_enrollments = ttk.Frame(notebook, padding=8)
        tab_finance = ttk.Frame(notebook, padding=8)
        tab_attendance = ttk.Frame(notebook, padding=8)
        tab_other = ttk.Frame(notebook, padding=8)

        notebook.add(tab_enrollments, text="  📚 Course Enrollments  ")
        notebook.add(tab_finance, text="  💳 Account & Payments  ")
        notebook.add(tab_attendance, text="  🕒 Attendance Record  ")
        notebook.add(tab_other, text="  📜 Certificates & Logs  ")

        self._build_enrollments_tab(tab_enrollments)
        self._build_finance_tab(tab_finance)
        self._build_attendance_tab(tab_attendance)
        self._build_other_tab(tab_other)

        # ==================== 4. BOTTOM ACTION FOOTER ====================
        footer = ttk.Frame(self.main_container)
        footer.pack(fill="x", pady=(8, 0))

        ttk.Label(
            footer,
            text=f"Address: {address} • Registered: {joining}",
            style="Hint.TLabel",
        ).pack(side="left", padx=4)

        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(
            footer,
            text="➕ Assign Course...",
            command=self._handle_enroll,
        ).pack(side="right", padx=4)
        ttk.Button(
            footer,
            text="🖨 Export Profile PDF",
            style="Accent.TButton",
            command=lambda: self.export_pdf(print_now=False),
        ).pack(side="right", padx=4)

    def _create_kpi_card(
        self, parent: ttk.Frame, col: int, title: str, value: str, subtitle: str, value_color: str
    ) -> None:
        card = tk.Frame(
            parent,
            bg="#FFFFFF",
            highlightbackground="#CBD5E1",
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=4)

        tk.Label(
            card,
            text=title,
            font=("Segoe UI", 8, "bold"),
            fg="#64748B",
            bg="#FFFFFF",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            card,
            text=value,
            font=("Segoe UI Variable Display", 15, "bold"),
            fg=value_color,
            bg="#FFFFFF",
            anchor="w",
        ).pack(fill="x", pady=(2, 1))

        tk.Label(
            card,
            text=subtitle,
            font=("Segoe UI", 8),
            fg="#64748B",
            bg="#FFFFFF",
            anchor="w",
        ).pack(fill="x")

    def _render_photo(self, container: tk.Frame, student: dict[str, Any]) -> None:
        photo_bytes = student.get("photo_data")
        if photo_bytes:
            try:
                pil_img = Image.open(BytesIO(photo_bytes)).convert("RGB")
                pil_img = ImageOps.fit(pil_img, (110, 132), Image.Resampling.LANCZOS)
                self._tk_photo = ImageTk.PhotoImage(pil_img)
                lbl = tk.Label(container, image=self._tk_photo, bg="#FFFFFF")
                lbl.pack(fill="both", expand=True)
                return
            except Exception:
                pass

        # Fallback placeholder
        canvas = tk.Canvas(container, width=110, height=132, bg="#F1F5F9", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        name = student.get("student_name", "Student")
        initials = "".join(part[0].upper() for part in name.split()[:2]) or "ST"
        canvas.create_oval(30, 22, 80, 72, fill="#CBD5E1", outline="")
        canvas.create_text(55, 47, text=initials, fill="#FFFFFF", font=("Segoe UI Variable Display", 15, "bold"))
        canvas.create_text(55, 92, text="No Photo", fill="#64748B", font=("Segoe UI", 8, "bold"))
        canvas.create_text(55, 108, text="Recorded", fill="#94A3B8", font=("Segoe UI", 7))

    def _build_enrollments_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # 1. Active Enrollments
        active_group = ttk.LabelFrame(parent, text=f" Active Enrollments ({len(self.profile['active_enrollments'])}) ", padding=6)
        active_group.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        active_cols = [
            ("course", "Course Name", 190, "w"),
            ("cat", "Category", 110, "w"),
            ("level", "Level", 90, "w"),
            ("start", "Start Date", 95, "w"),
            ("monthly", "Monthly Fee", 100, "e"),
            ("admission", "Adm. Fee", 90, "e"),
            ("discount", "Discount", 80, "e"),
            ("billing", "Billing Type", 90, "w"),
            ("instructor", "Instructor", 140, "w"),
        ]
        active_tree = self._create_tree(active_group, active_cols, height=4)
        for e in self.profile["active_enrollments"]:
            active_tree.insert(
                "",
                "end",
                values=(
                    e["course_name"],
                    e["category"],
                    e["level"],
                    e["start_date"] or "-",
                    f"Rs. {float(e['monthly_fee']):,.2f}",
                    f"Rs. {float(e['admission_fee']):,.2f}",
                    f"Rs. {float(e['discount']):,.2f}",
                    e["billing_type"],
                    e["instructor_name"] or "-",
                ),
            )

        # 2. Previous Enrollments
        prev_group = ttk.LabelFrame(parent, text=f" Previous Enrollments History ({len(self.profile['previous_enrollments'])}) ", padding=6)
        prev_group.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        prev_cols = [
            ("course", "Course Name", 200, "w"),
            ("cat", "Category", 110, "w"),
            ("level", "Level", 90, "w"),
            ("start", "Start Date", 95, "w"),
            ("end", "End Date", 95, "w"),
            ("monthly", "Monthly Fee", 100, "e"),
            ("status", "Status", 90, "center"),
        ]
        prev_tree = self._create_tree(prev_group, prev_cols, height=4)
        for e in self.profile["previous_enrollments"]:
            prev_tree.insert(
                "",
                "end",
                values=(
                    e["course_name"],
                    e["category"],
                    e["level"],
                    e["start_date"] or "-",
                    e["end_date"] or "-",
                    f"Rs. {float(e['monthly_fee']):,.2f}",
                    e["status"],
                ),
            )

    def _build_finance_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # 1. Due Bills & Invoices
        due_bills = self.profile["financials"]["due_bills"]
        bills_group = ttk.LabelFrame(parent, text=f" Due Bills & Outstanding Invoices ({len(due_bills)}) ", padding=6)
        bills_group.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        bill_cols = [
            ("bill_no", "Bill #", 120, "w"),
            ("period", "Billing Period", 100, "w"),
            ("course", "Course", 170, "w"),
            ("issue", "Issue Date", 90, "w"),
            ("due", "Due Date", 90, "w"),
            ("total", "Total (Rs)", 95, "e"),
            ("paid", "Paid (Rs)", 95, "e"),
            ("balance", "Balance (Rs)", 95, "e"),
            ("status", "Status", 80, "center"),
        ]
        bills_tree = self._create_tree(bills_group, bill_cols, height=4)
        for b in due_bills:
            bal = float(b["balance"])
            bal_str = f"{bal:,.2f}"
            bills_tree.insert(
                "",
                "end",
                values=(
                    b["bill_number"],
                    b["billing_period"],
                    b["course_name"],
                    b["issue_date"] or "-",
                    b["due_date"] or "-",
                    f"{float(b['total_amount']):,.2f}",
                    f"{float(b['paid_amount']):,.2f}",
                    bal_str,
                    b["status"],
                ),
            )

        # 2. Payment Transactions & Receipts
        txns = self.profile["financials"]["transactions"]
        txns_group = ttk.LabelFrame(parent, text=f" Payment Receipts & Transactions ({len(txns)}) ", padding=6)
        txns_group.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        txn_cols = [
            ("date", "Date", 95, "w"),
            ("receipt", "Receipt #", 110, "w"),
            ("particular", "Particular / Remarks", 210, "w"),
            ("amount", "Paid (Rs)", 100, "e"),
            ("discount", "Discount (Rs)", 90, "e"),
            ("method", "Payment Method", 100, "w"),
            ("account", "Account", 130, "w"),
        ]
        txns_tree = self._create_tree(txns_group, txn_cols, height=4)
        for t in txns:
            txns_tree.insert(
                "",
                "end",
                values=(
                    t["transaction_date"] or "-",
                    t["receipt_no"] or "-",
                    t["particular"] or t["remarks"] or "-",
                    f"{float(t['payment_amount']):,.2f}",
                    f"{float(t['discount_amount']):,.2f}",
                    t["payment_method"] or "-",
                    t["account_name"] or "-",
                ),
            )

    def _build_attendance_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        att = self.profile["attendance"]

        # Top Banner with attendance summary stats
        banner = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1, padx=10, pady=8)
        banner.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        c_month = att.get("current_month", "-")
        tk.Label(
            banner,
            text=f"Monthly Attendance ({c_month})",
            font=("Segoe UI", 11, "bold"),
            fg="#183B56",
            bg="#FFFFFF",
        ).pack(side="left", padx=(0, 20))

        stats_text = (
            f"Present: {att.get('days_present_month', 0)} Days  |  "
            f"Punches: {att.get('total_punches_month', 0)}  |  "
            f"Lifetime: {att.get('lifetime_days', 0)} Days ({att.get('lifetime_punches', 0)} punches)  |  "
            f"First Seen: {att.get('first_seen', '')[:10] or '-'}  |  "
            f"Last Seen: {att.get('last_seen', '')[:10] or '-'}"
        )
        tk.Label(banner, text=stats_text, font=("Segoe UI", 9), fg="#475569", bg="#FFFFFF").pack(side="left")

        # Daily Attendance Log
        logs_group = ttk.LabelFrame(parent, text=f" Current Month Daily Attendance Logs ({len(att.get('recent_punches', []))}) ", padding=6)
        logs_group.grid(row=1, column=0, sticky="nsew")

        att_cols = [
            ("date", "Date (AD)", 130, "w"),
            ("first_in", "First Check-In", 150, "center"),
            ("last_out", "Last Check-Out", 150, "center"),
            ("punches", "Total Punches", 120, "center"),
            ("status", "Status", 110, "center"),
        ]
        att_tree = self._create_tree(logs_group, att_cols, height=8)
        for p in att.get("recent_punches", []):
            att_tree.insert(
                "",
                "end",
                values=(
                    p["date"],
                    p["first_in"] or "-",
                    p["last_out"] or "-",
                    p["punch_count"],
                    "Present",
                ),
            )

    def _build_other_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # 1. Certificates Earned
        certs = self.profile.get("certificates", [])
        cert_group = ttk.LabelFrame(parent, text=f" Certificates & Credentials Earned ({len(certs)}) ", padding=6)
        cert_group.grid(row=0, column=0, sticky="nsew", pady=(0, 6))

        cert_cols = [
            ("cert_no", "Certificate Number", 160, "w"),
            ("course", "Course Name Snapshot", 260, "w"),
            ("certify_date", "Certify Date", 120, "w"),
            ("issue_date", "Issue Date", 120, "w"),
            ("status", "Status", 100, "center"),
        ]
        cert_tree = self._create_tree(cert_group, cert_cols, height=4)
        for c in certs:
            cert_tree.insert(
                "",
                "end",
                values=(
                    c["certificate_number"],
                    c["course_name_snapshot"],
                    c["certify_date"] or "-",
                    c["issue_date"] or "-",
                    c["status"],
                ),
            )

        # 2. Recent SMS Delivery Log
        sms_logs = self.profile.get("recent_sms", [])
        sms_group = ttk.LabelFrame(parent, text=f" Recent SMS Communications Log ({len(sms_logs)}) ", padding=6)
        sms_group.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        sms_cols = [
            ("date", "Sent Date / Time", 140, "w"),
            ("event", "Event Type", 140, "w"),
            ("recipient", "Recipient Mobile", 120, "w"),
            ("message", "Message Text", 340, "w"),
            ("status", "Status", 90, "center"),
        ]
        sms_tree = self._create_tree(sms_group, sms_cols, height=4)
        for s in sms_logs:
            sms_tree.insert(
                "",
                "end",
                values=(
                    str(s.get("created_at") or "-")[:19],
                    s.get("event_key") or "-",
                    s.get("recipient") or "-",
                    s.get("message_text") or "-",
                    s.get("status") or "-",
                ),
            )

    def _create_tree(
        self, parent: ttk.Frame, columns: list[tuple[str, str, int, str]], height: int = 5
    ) -> ttk.Treeview:
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)

        col_ids = [c[0] for c in columns]
        tree = ttk.Treeview(container, columns=col_ids, show="headings", height=height, selectmode="browse")
        for col_id, heading_text, width, anchor in columns:
            tree.heading(col_id, text=heading_text)
            tree.column(col_id, width=width, anchor=anchor)

        v_scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=v_scroll.set)

        tree.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")
        return tree

    def export_pdf(self, print_now: bool = False) -> None:
        """Generate and print or view the ReportLab student profile PDF."""
        try:
            pdf_path = self.app.services.reports.student_profile_pdf(self.student_id)
            opened = open_or_print_pdf(pdf_path, print_now=print_now)
            if print_now and not opened:
                messagebox.showinfo(
                    "Print Profile",
                    f"Direct printing is not registered for PDF on this computer.\nThe document was opened for printing:\n{pdf_path}",
                    parent=self,
                )
        except Exception as exc:
            messagebox.showerror("Export PDF Error", str(exc), parent=self)

    def _handle_edit(self) -> None:
        if self.on_edit_requested:
            dialog = self.on_edit_requested(self.student_id)
            if dialog and isinstance(dialog, tk.Toplevel):
                self.wait_window(dialog)
            self.reload()

    def _handle_sms(self) -> None:
        if self.on_sms_requested:
            self.on_sms_requested(self.student_id)

    def _handle_enroll(self) -> None:
        if self.on_enroll_requested:
            self.on_enroll_requested(self.student_id)
            self.reload()
