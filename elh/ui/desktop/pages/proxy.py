"""Desktop presentation adapter for faculty absences, proxy classes, and substitutions."""

from __future__ import annotations

import csv
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any

from elh.ui.desktop.components import CrudPage
from elh.ui.desktop.helpers import today_iso


class ProxyClassesPage(CrudPage):
    """View and manage faculty absence requests, proxy classes, and substitute faculty assignments."""

    STATUSES = ("All", "Pending", "Approved", "Accepted", "Declined", "Rejected", "Completed")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_proxy_id: int | None = None
        self._proxy_cache: list[dict[str, Any]] = []

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="Proxy & Substitute Class Management", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Manage faculty leaves, assign substitute teachers for class routines, and coordinate student schedule changes.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 6))

        # KPI Summary cards
        self.stats_frame = ttk.Frame(self)
        self.stats_frame.pack(fill="x", pady=(0, 10))
        self.stat_labels: dict[str, ttk.Label] = {}
        for idx, (key, title) in enumerate([
            ("total", "Total Requests"),
            ("pending_approval", "Pending Approval"),
            ("proxy_needed", "Proxy Needed"),
            ("confirmed", "Confirmed Subs"),
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
        status_combo = ttk.Combobox(toolbar, textvariable=self.status_var, values=self.STATUSES, state="readonly", width=14)
        status_combo.pack(side="left", padx=(0, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        ttk.Label(toolbar, text="Search:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=22)
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
                ("id", "ID", 45),
                ("date", "Date", 90),
                ("time", "Time", 95),
                ("class", "Class", 100),
                ("subject", "Subject", 120),
                ("room", "Room", 60),
                ("orig_faculty", "Original Faculty", 140),
                ("proxy_faculty", "Substitute Faculty", 140),
                ("status", "Request Status", 105),
                ("proxy_status", "Proxy Status", 100),
                ("reason", "Reason & Notes", 220),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _: self.assign_substitute())

        # Action Buttons
        actions = ttk.Frame(self, style="Toolbar.TFrame", padding=6)
        actions.pack(fill="x", pady=(8, 0))

        ttk.Button(actions, text="➕ Record Absence / Request Proxy", style="Accent.TButton", command=self.request_proxy).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="👥 Assign Substitute", style="TButton", command=self.assign_substitute).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="✔ Approve", style="TButton", command=self.approve_request).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="✖ Reject", style="TButton", command=self.reject_request).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="📲 Send SMS Alert", style="TButton", command=self.send_sms_alert).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="📥 Export CSV", style="TButton", command=self.export_csv).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="🗑 Delete", style="Danger.TButton", command=self.delete_request).pack(side="right")

    def _clear_filters(self):
        self.status_var.set("All")
        self.search_var.set("")
        self.refresh()

    def _on_select(self, _event=None):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            self.selected_proxy_id = int(item["values"][0])
        else:
            self.selected_proxy_id = None

    def _query_requests(self) -> list[dict[str, Any]]:
        try:
            rows = self.db.query(
                """
                SELECT p.*,
                       r.class_name, r.subject_name AS subject, r.start_time, r.end_time, r.period_label AS room_number,
                       ot.teacher_name AS original_teacher_name,
                       pt.teacher_name AS proxy_teacher_name
                FROM proxy_class_requests p
                JOIN class_routines r ON r.id = p.routine_id
                LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
                LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id
                ORDER BY p.class_date DESC, r.start_time ASC
                """
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def refresh(self):
        self.clear_tree(self.tree)
        all_requests = self._query_requests()
        self._proxy_cache = all_requests

        # Update KPI cards
        total_count = len(all_requests)
        pending_approval = sum(1 for r in all_requests if r.get("status") == "Pending")
        proxy_needed = sum(1 for r in all_requests if r.get("status") == "Approved" and (not r.get("proxy_teacher_id") or r.get("proxy_status") == "Pending"))
        confirmed = sum(1 for r in all_requests if r.get("proxy_status") == "Accepted")

        self.stat_labels["total"].configure(text=str(total_count))
        self.stat_labels["pending_approval"].configure(text=str(pending_approval))
        self.stat_labels["proxy_needed"].configure(text=str(proxy_needed))
        self.stat_labels["confirmed"].configure(text=str(confirmed))

        # Filter
        status = self.status_var.get()
        search = self.search_var.get().strip().lower()

        filtered = all_requests
        if status and status != "All":
            filtered = [r for r in filtered if r.get("status") == status or r.get("proxy_status") == status]
        if search:
            filtered = [
                r for r in filtered
                if search in str(r.get("original_teacher_name") or "").lower()
                or search in str(r.get("proxy_teacher_name") or "").lower()
                or search in str(r.get("class_name") or "").lower()
                or search in str(r.get("subject") or "").lower()
                or search in str(r.get("class_date") or "").lower()
            ]

        for req in filtered:
            req_id = req.get("id")
            c_date = req.get("class_date") or "-"
            time_str = f"{req.get('start_time') or ''} - {req.get('end_time') or ''}".strip(" -")
            c_name = req.get("class_name") or "-"
            subj = req.get("subject") or "-"
            room = req.get("room_number") or "-"
            orig_teacher = req.get("original_teacher_name") or "Regular Faculty"
            proxy_teacher = req.get("proxy_teacher_name") or (
                "⚠️ Assigned (Pending)" if req.get("proxy_teacher_id") else "⚠️ Needed"
            )
            stat = req.get("status") or "Pending"
            p_stat = req.get("proxy_status") or "-"
            reason = req.get("reason") or req.get("admin_notes") or "-"

            self.tree.insert(
                "",
                "end",
                values=(req_id, c_date, time_str, c_name, subj, room, orig_teacher, proxy_teacher, stat, p_stat, reason),
            )

    def _get_selected_record(self) -> dict[str, Any] | None:
        if not self.selected_proxy_id:
            messagebox.showwarning("Select Request", "Please select a proxy class request from the table.", parent=self)
            return None
        for r in self._proxy_cache:
            if r.get("id") == self.selected_proxy_id:
                return r
        return None

    def request_proxy(self):
        """Dialog to create a new absence / proxy class request."""
        # Load routines
        routines = self.db.query(
            """
            SELECT r.id, r.class_name, r.subject_name AS subject, r.start_time, r.end_time, r.day_of_week, r.period_label AS room_number, r.teacher_id,
                   t.teacher_name
            FROM class_routines r
            LEFT JOIN teachers t ON t.id = r.teacher_id
            WHERE r.status = 'Active' OR r.status IS NULL
            ORDER BY r.day_of_week, r.start_time
            """
        )
        if not routines:
            messagebox.showwarning("No Routines", "No active class routines found in the system.", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title("Record Absence / Request Proxy Class")
        dialog.geometry("540x440")
        dialog.transient(self)
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="Record Absence & Request Substitute", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

        form = ttk.Frame(content)
        form.pack(fill="both", expand=True)

        ttk.Label(form, text="Class Date (BS or YYYY-MM-DD):*").grid(row=0, column=0, sticky="w", pady=6)
        date_var = tk.StringVar(value=today_iso())
        ttk.Entry(form, textvariable=date_var, width=22).grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Select Routine Period:*").grid(row=1, column=0, sticky="w", pady=6)
        routine_options = []
        routine_map = {}
        for r in routines:
            label = f"{r.get('day_of_week')}: {r.get('class_name')} - {r.get('subject')} ({r.get('start_time')}-{r.get('end_time')}) [{r.get('teacher_name') or 'No Faculty'}]"
            routine_options.append(label)
            routine_map[label] = r

        routine_var = tk.StringVar(value=routine_options[0] if routine_options else "")
        routine_combo = ttk.Combobox(form, textvariable=routine_var, values=routine_options, state="readonly", width=42)
        routine_combo.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Reason for Absence:*").grid(row=2, column=0, sticky="nw", pady=6)
        reason_text = tk.Text(form, width=35, height=4, font=("Segoe UI", 9))
        reason_text.grid(row=2, column=1, sticky="w", pady=6)

        # Teachers for immediate substitute assignment (optional)
        teachers = self.db.query("SELECT id, teacher_name FROM teachers WHERE status = 'Active' ORDER BY teacher_name")
        teacher_opts = ["-- None / Assign Later --"] + [t["teacher_name"] for t in teachers]
        teacher_id_map = {t["teacher_name"]: t["id"] for t in teachers}

        ttk.Label(form, text="Substitute Faculty (Optional):").grid(row=3, column=0, sticky="w", pady=6)
        sub_var = tk.StringVar(value=teacher_opts[0])
        sub_combo = ttk.Combobox(form, textvariable=sub_var, values=teacher_opts, state="readonly", width=30)
        sub_combo.grid(row=3, column=1, sticky="w", pady=6)

        def save_request():
            c_date = date_var.get().strip()
            if not c_date:
                messagebox.showerror("Error", "Class date is required.", parent=dialog)
                return
            sel_routine_label = routine_var.get()
            routine = routine_map.get(sel_routine_label)
            if not routine:
                messagebox.showerror("Error", "Please select a valid routine period.", parent=dialog)
                return
            reason = reason_text.get("1.0", "end").strip()
            if not reason:
                messagebox.showerror("Error", "Please provide a reason for absence.", parent=dialog)
                return

            sub_choice = sub_var.get()
            proxy_teacher_id = teacher_id_map.get(sub_choice)
            status = "Approved" if proxy_teacher_id else "Pending"
            proxy_status = "Accepted" if proxy_teacher_id else "Pending"

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute(
                """
                INSERT INTO proxy_class_requests
                (class_date, routine_id, original_teacher_id, proxy_teacher_id, reason, status, proxy_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c_date, routine["id"], routine.get("teacher_id"), proxy_teacher_id, reason, status, proxy_status, now_str, now_str)
            )

            messagebox.showinfo("Success", "Proxy class request recorded successfully.", parent=dialog)
            dialog.destroy()
            self.refresh()

        btn_bar = ttk.Frame(content)
        btn_bar.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_bar, text="Save Request", style="Accent.TButton", command=save_request).pack(side="right", padx=(6, 0))
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy).pack(side="right")

    def assign_substitute(self):
        req = self._get_selected_record()
        if not req:
            return

        teachers = self.db.query("SELECT id, teacher_name FROM teachers WHERE status = 'Active' ORDER BY teacher_name")
        if not teachers:
            messagebox.showwarning("No Teachers", "No active teachers found in the system.", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Assign Substitute - Request #{req['id']}")
        dialog.geometry("480x320")
        dialog.transient(self)
        dialog.grab_set()

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text=f"Assign Substitute Faculty", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
        desc = f"Class: {req.get('class_name')} - {req.get('subject')}\nDate: {req.get('class_date')} ({req.get('start_time')} - {req.get('end_time')})\nOriginal Faculty: {req.get('original_teacher_name') or 'Regular'}"
        ttk.Label(content, text=desc, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 12))

        form = ttk.Frame(content)
        form.pack(fill="both", expand=True)

        teacher_opts = [t["teacher_name"] for t in teachers]
        teacher_id_map = {t["teacher_name"]: t["id"] for t in teachers}

        ttk.Label(form, text="Select Substitute Faculty:*").grid(row=0, column=0, sticky="w", pady=6)
        sub_var = tk.StringVar(value=teacher_opts[0])
        sub_combo = ttk.Combobox(form, textvariable=sub_var, values=teacher_opts, state="readonly", width=28)
        sub_combo.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(form, text="Admin Notes:").grid(row=1, column=0, sticky="nw", pady=6)
        notes_text = tk.Text(form, width=28, height=3, font=("Segoe UI", 9))
        notes_text.grid(row=1, column=1, sticky="w", pady=6)

        def save_sub():
            sub_name = sub_var.get()
            proxy_id = teacher_id_map.get(sub_name)
            if not proxy_id:
                messagebox.showerror("Error", "Please select a valid substitute teacher.", parent=dialog)
                return
            notes = notes_text.get("1.0", "end").strip()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.db.execute(
                """
                UPDATE proxy_class_requests
                SET proxy_teacher_id = ?, status = 'Approved', proxy_status = 'Accepted',
                    admin_notes = ?, proxy_accepted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (proxy_id, notes, now_str, now_str, req["id"])
            )

            messagebox.showinfo("Success", f"Assigned '{sub_name}' as substitute faculty. Request approved.", parent=dialog)
            dialog.destroy()
            self.refresh()

        btn_bar = ttk.Frame(content)
        btn_bar.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_bar, text="Confirm Assignment", style="Accent.TButton", command=save_sub).pack(side="right", padx=(6, 0))
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy).pack(side="right")

    def approve_request(self):
        req = self._get_selected_record()
        if not req:
            return

        if messagebox.askyesno("Approve Request", f"Approve proxy class request #{req['id']} for {req.get('class_name')} on {req.get('class_date')}?", parent=self):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute("UPDATE proxy_class_requests SET status = 'Approved', updated_at = ? WHERE id = ?", (now_str, req["id"]))
            messagebox.showinfo("Approved", "Request approved.", parent=self)
            self.refresh()

    def reject_request(self):
        req = self._get_selected_record()
        if not req:
            return

        if messagebox.askyesno("Reject Request", f"Reject proxy class request #{req['id']}?", parent=self):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute("UPDATE proxy_class_requests SET status = 'Rejected', updated_at = ? WHERE id = ?", (now_str, req["id"]))
            messagebox.showinfo("Rejected", "Request marked as Rejected.", parent=self)
            self.refresh()

    def send_sms_alert(self):
        req = self._get_selected_record()
        if not req:
            return

        # Find students enrolled in this class
        routine_id = req.get("routine_id")
        routine = self.db.query_one("SELECT * FROM class_routines WHERE id = ?", (routine_id,))
        if not routine:
            messagebox.showwarning("Not Found", "Associated routine not found.", parent=self)
            return

        c_name = routine.get("class_name")
        students = self.db.query("SELECT student_name, contact FROM students WHERE class_name = ? AND status = 'Active'", (c_name,))

        sub_name = req.get("proxy_teacher_name") or "Substitute Faculty"
        orig_name = req.get("original_teacher_name") or "Regular Faculty"
        msg = f"Notice: {req.get('subject')} class on {req.get('class_date')} will be conducted by {sub_name} instead of {orig_name}. - Expert Learning Hub"

        if not students:
            messagebox.showinfo("No Students", f"No active students found in class '{c_name}'.", parent=self)
            return

        if messagebox.askyesno(
            "Send SMS Alert",
            f"Send schedule alert to {len(students)} students in '{c_name}'?\n\nMessage preview:\n\"{msg}\"",
            parent=self,
        ):
            sent_count = 0
            notif_service = getattr(self.app.services, "notifications", None)
            for s in students:
                phone = s.get("contact")
                if phone and notif_service:
                    try:
                        notif_service.send_sms(phone, msg)
                        sent_count += 1
                    except Exception:
                        pass

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute(
                "UPDATE proxy_class_requests SET sms_sent = sms_sent + ?, sms_sent_at = ? WHERE id = ?",
                (sent_count, now_str, req["id"]),
            )
            messagebox.showinfo("SMS Sent", f"Alert successfully dispatched to {sent_count} student(s).", parent=self)
            self.refresh()

    def delete_request(self):
        req = self._get_selected_record()
        if not req:
            return

        if messagebox.askyesno("Delete Request", f"Permanently delete proxy class request #{req['id']}?", parent=self):
            self.db.execute("DELETE FROM proxy_class_requests WHERE id = ?", (req["id"],))
            messagebox.showinfo("Deleted", "Request deleted.", parent=self)
            self.refresh()

    def export_csv(self):
        if not self._proxy_cache:
            messagebox.showinfo("Export CSV", "No proxy class records to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Proxy Classes",
            initialfile="proxy_classes.csv",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return

        headers = ["ID", "Class Date", "Start Time", "End Time", "Class", "Subject", "Room", "Original Faculty", "Substitute Faculty", "Request Status", "Proxy Status", "Reason", "Admin Notes", "SMS Sent"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in self._proxy_cache:
                writer.writerow([
                    r.get("id"),
                    r.get("class_date"),
                    r.get("start_time"),
                    r.get("end_time"),
                    r.get("class_name"),
                    r.get("subject"),
                    r.get("room_number"),
                    r.get("original_teacher_name"),
                    r.get("proxy_teacher_name"),
                    r.get("status"),
                    r.get("proxy_status"),
                    r.get("reason"),
                    r.get("admin_notes"),
                    r.get("sms_sent"),
                ])

        messagebox.showinfo("Export Successful", f"Saved {len(self._proxy_cache)} records to:\n{path}", parent=self)
