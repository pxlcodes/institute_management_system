"""Desktop presentation adapter for website admission leads and inquiries."""

from __future__ import annotations

import csv
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any

from elh.ui.desktop.components import CrudPage
from elh.ui.desktop.helpers import today_iso


class InquiriesPage(CrudPage):
    """View and manage prospective student admission inquiries submitted from the website."""

    STATUSES = ("All", "New", "Contacted", "Counseling Scheduled", "Enrolled", "Closed")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_inquiry_id: int | None = None
        self._inquiries_cache: list[dict[str, Any]] = []

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="Admission Leads & Inquiries", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Review prospective student leads submitted via the website, track counseling progress, and register enrolled students.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 6))

        # KPI Summary cards
        self.stats_frame = ttk.Frame(self)
        self.stats_frame.pack(fill="x", pady=(0, 10))
        self.stat_labels: dict[str, ttk.Label] = {}
        for idx, (key, title) in enumerate([
            ("total", "Total Leads"),
            ("new", "New Leads"),
            ("contacted", "Contacted"),
            ("counseling", "Counseling"),
            ("enrolled", "Enrolled"),
        ]):
            card = ttk.Frame(self.stats_frame, style="DashboardCard.TFrame", padding=(12, 8))
            card.grid(row=0, column=idx, padx=(0 if idx == 0 else 6, 0), sticky="nsew")
            ttk.Label(card, text=title, style="DashboardCardTitle.TLabel").pack(anchor="w")
            val_lbl = ttk.Label(card, text="0", style="DashboardCardValue.TLabel")
            val_lbl.pack(anchor="w")
            self.stat_labels[key] = val_lbl
            self.stats_frame.columnconfigure(idx, weight=1)

        # Filters toolbar
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=6)
        toolbar.pack(fill="x", pady=(0, 6))

        ttk.Label(toolbar, text="Status:").pack(side="left", padx=(0, 4))
        self.status_var = tk.StringVar(value="All")
        status_combo = ttk.Combobox(toolbar, textvariable=self.status_var, values=self.STATUSES, state="readonly", width=18)
        status_combo.pack(side="left", padx=(0, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        ttk.Label(toolbar, text="Search:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=24)
        search_entry.pack(side="left", padx=(0, 8))
        search_entry.bind("<KeyRelease>", lambda _: self.refresh())

        ttk.Button(toolbar, text="Clear", command=self._clear_filters).pack(side="left", padx=(0, 10))
        ttk.Button(toolbar, text="⟳ Refresh", command=self.refresh).pack(side="left", padx=(0, 4))

        # Main Table
        table_area = ttk.Frame(self)
        table_area.pack(fill="both", expand=True, pady=4)
        self.tree = self.make_tree(
            table_area,
            [
                ("id", "ID", 50),
                ("date", "Date", 95),
                ("name", "Student Name", 160),
                ("phone", "Phone", 110),
                ("grade", "Grade / Level", 110),
                ("course", "Course Interest", 150),
                ("status", "Status", 130),
                ("notes", "Notes / Message", 280),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _: self.review_inquiry())

        # Action Buttons
        actions = ttk.Frame(self, style="Toolbar.TFrame", padding=6)
        actions.pack(fill="x", pady=(8, 0))

        ttk.Button(actions, text="📝 Review & Update Status", style="Accent.TButton", command=self.review_inquiry).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="🎓 Convert to Student", style="TButton", command=self.convert_to_student).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="📥 Export CSV", style="TButton", command=self.export_csv).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="🗑 Delete Lead", style="Danger.TButton", command=self.delete_inquiry).pack(side="right")

    def _clear_filters(self):
        self.status_var.set("All")
        self.search_var.set("")
        self.refresh()

    def _on_select(self, _event=None):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            self.selected_inquiry_id = int(item["values"][0])
        else:
            self.selected_inquiry_id = None

    def refresh(self):
        self.clear_tree(self.tree)
        cms_service = getattr(self.app.services, "cms", None)
        if not cms_service:
            return

        status = self.status_var.get()
        search = self.search_var.get().strip()

        all_inquiries = cms_service.list_inquiries()
        self._inquiries_cache = all_inquiries

        # Update KPI cards
        total_count = len(all_inquiries)
        new_count = sum(1 for i in all_inquiries if i.get("status") == "New")
        contacted_count = sum(1 for i in all_inquiries if i.get("status") == "Contacted")
        counseling_count = sum(1 for i in all_inquiries if i.get("status") == "Counseling Scheduled")
        enrolled_count = sum(1 for i in all_inquiries if i.get("status") == "Enrolled")

        self.stat_labels["total"].configure(text=str(total_count))
        self.stat_labels["new"].configure(text=str(new_count))
        self.stat_labels["contacted"].configure(text=str(contacted_count))
        self.stat_labels["counseling"].configure(text=str(counseling_count))
        self.stat_labels["enrolled"].configure(text=str(enrolled_count))

        # Filter
        filtered = all_inquiries
        if status and status != "All":
            filtered = [i for i in filtered if i.get("status") == status]
        if search:
            s_lower = search.lower()
            filtered = [
                i for i in filtered
                if s_lower in str(i.get("full_name") or "").lower()
                or s_lower in str(i.get("phone") or "").lower()
                or s_lower in str(i.get("course_interest") or "").lower()
                or s_lower in str(i.get("grade") or "").lower()
            ]

        for inq in filtered:
            inq_id = inq.get("id")
            created_at = str(inq.get("created_at") or "")[:10]
            name = inq.get("full_name") or "-"
            phone = inq.get("phone") or "-"
            grade = inq.get("grade") or "-"
            course = inq.get("course_interest") or "-"
            stat = inq.get("status") or "New"
            notes = inq.get("staff_notes") or inq.get("message") or "-"

            self.tree.insert(
                "",
                "end",
                values=(inq_id, created_at, name, phone, grade, course, stat, notes),
            )

    def _get_selected_record(self) -> dict[str, Any] | None:
        if not self.selected_inquiry_id:
            messagebox.showwarning("Select Lead", "Please select an admission inquiry lead from the table.", parent=self)
            return None
        for inq in self._inquiries_cache:
            if inq.get("id") == self.selected_inquiry_id:
                return inq
        return None

    def review_inquiry(self):
        inq = self._get_selected_record()
        if not inq:
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Lead Review #{inq['id']} - {inq.get('full_name', '')}")
        dialog.geometry("520x420")
        dialog.transient(self)
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text=f"Lead Review: {inq.get('full_name')}", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        meta_frame = ttk.LabelFrame(content, text="Lead Information", padding=10)
        meta_frame.pack(fill="x", pady=(0, 10))

        info_rows = [
            ("Phone:", inq.get("phone") or "-"),
            ("Email:", inq.get("email") or "-"),
            ("Grade / Level:", inq.get("grade") or "-"),
            ("Course Interest:", inq.get("course_interest") or "-"),
            ("Inquiry Date:", str(inq.get("created_at") or "")),
            ("Initial Message:", inq.get("message") or "-"),
        ]
        for idx, (k, v) in enumerate(info_rows):
            ttk.Label(meta_frame, text=k, font=("Segoe UI", 9, "bold")).grid(row=idx, column=0, sticky="w", padx=4, pady=2)
            ttk.Label(meta_frame, text=v).grid(row=idx, column=1, sticky="w", padx=8, pady=2)

        form_frame = ttk.LabelFrame(content, text="Counseling Progress & Status", padding=10)
        form_frame.pack(fill="both", expand=True, pady=(0, 10))

        ttk.Label(form_frame, text="Status:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        status_var = tk.StringVar(value=inq.get("status") or "New")
        statuses = [s for s in self.STATUSES if s != "All"]
        status_combo = ttk.Combobox(form_frame, textvariable=status_var, values=statuses, state="readonly", width=25)
        status_combo.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(form_frame, text="Staff Notes:").grid(row=1, column=0, sticky="nw", padx=4, pady=4)
        notes_text = tk.Text(form_frame, width=38, height=4, font=("Segoe UI", 9))
        notes_text.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        notes_text.insert("1.0", inq.get("staff_notes") or "")

        def save_changes():
            new_status = status_var.get()
            new_notes = notes_text.get("1.0", "end").strip()
            cms_service = getattr(self.app.services, "cms", None)
            if cms_service:
                cms_service.update_inquiry(inq["id"], new_status, new_notes)
            messagebox.showinfo("Saved", "Inquiry status updated successfully.", parent=dialog)
            dialog.destroy()
            self.refresh()

        btn_bar = ttk.Frame(content)
        btn_bar.pack(fill="x")
        ttk.Button(btn_bar, text="Save Changes", style="Accent.TButton", command=save_changes).pack(side="right", padx=(6, 0))
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy).pack(side="right")

    def convert_to_student(self):
        inq = self._get_selected_record()
        if not inq:
            return

        name = (inq.get("full_name") or "").strip()
        phone = (inq.get("phone") or "").strip()
        grade = (inq.get("grade") or "").strip()
        course = (inq.get("course_interest") or "").strip()

        if messagebox.askyesno(
            "Convert to Student",
            f"Convert lead '{name}' (Phone: {phone}) into a registered student?",
            parent=self,
        ):
            # Check if student already exists with this phone or name
            existing = self.db.query_one("SELECT id FROM students WHERE contact = ? OR student_name = ?", (phone, name))
            if existing:
                if not messagebox.askyesno(
                    "Duplicate Warning",
                    f"A student with matching name or contact already exists (ID: {existing['id']}). Proceed anyway?",
                    parent=self,
                ):
                    return

            today = today_iso()
            remarks = f"Converted from website lead #{inq['id']}. Interest: {course}. {inq.get('staff_notes') or inq.get('message') or ''}".strip()
            student_id = self.db.execute(
                "INSERT INTO students (student_name, class_name, contact, joining_date, status, remarks) "
                "VALUES (?, ?, ?, ?, 'Active', ?)",
                (name, grade, phone, today, remarks),
            )

            # Mark inquiry as enrolled
            cms_service = getattr(self.app.services, "cms", None)
            if cms_service:
                cms_service.update_inquiry(inq["id"], "Enrolled", f"Converted to Student ID #{student_id} on {today}")

            messagebox.showinfo(
                "Student Registered",
                f"Successfully registered student:\n\nID: {student_id}\nName: {name}\n\nInquiry lead marked as 'Enrolled'.",
                parent=self,
            )
            self.refresh()

            # Switch to Students page if available
            if hasattr(self.app, "show_page"):
                if messagebox.askyesno("Open Students", "Would you like to open the Students page now?", parent=self):
                    self.app.show_page("Students")

    def delete_inquiry(self):
        inq = self._get_selected_record()
        if not inq:
            return

        if messagebox.askyesno(
            "Delete Lead",
            f"Are you sure you want to permanently delete lead #{inq['id']} ({inq.get('full_name')})?",
            parent=self,
        ):
            cms_service = getattr(self.app.services, "cms", None)
            if cms_service:
                cms_service.delete_inquiry(inq["id"])
            messagebox.showinfo("Deleted", "Inquiry lead removed.", parent=self)
            self.refresh()

    def export_csv(self):
        if not self._inquiries_cache:
            messagebox.showinfo("Export CSV", "No inquiries to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Admission Leads",
            initialfile="admission_leads.csv",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return

        headers = ["ID", "Created At", "Full Name", "Phone", "Email", "Grade", "Course Interest", "Status", "Staff Notes", "Message"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for inq in self._inquiries_cache:
                writer.writerow([
                    inq.get("id"),
                    inq.get("created_at"),
                    inq.get("full_name"),
                    inq.get("phone"),
                    inq.get("email"),
                    inq.get("grade"),
                    inq.get("course_interest"),
                    inq.get("status"),
                    inq.get("staff_notes"),
                    inq.get("message"),
                ])

        messagebox.showinfo("Export Successful", f"Saved {len(self._inquiries_cache)} leads to:\n{path}", parent=self)
