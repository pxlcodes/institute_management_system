from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import nepali_datetime as nepali

from elh.ui.desktop.components import CrudPage, DateEntry, FormBuilder
from elh.ui.desktop.helpers import current_month, today_iso, validate_date, validate_month


class AttendancePage(CrudPage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.person_map: dict[str, int] = {}

        ttk.Label(self, text="Attendance Device", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Fetch device users, import punches, and link them to Students or Staff.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        form = self.create_form_dialog("Attendance Mapping", padding=12)
        form.pack(fill="x", pady=8)
        self.vars = {
            "device": tk.StringVar(),
            "type": tk.StringVar(value="Student"),
            "person": tk.StringVar(),
            "status": tk.StringVar(value="Active"),
        }
        form_builder = FormBuilder(form)
        form_builder.entry("Device User ID *", self.vars["device"])
        self.type_combo = form_builder.combo(
            "Person Type *", self.vars["type"], ["Student", "Staff"]
        )
        self.type_combo.bind("<<ComboboxSelected>>", lambda _event: self.load_people())
        self.person_combo = form_builder.combo(
            "Application User *", self.vars["person"], [], searchable=True
        )
        form_builder.combo("Status", self.vars["status"], ["Active", "Inactive"])
        ttk.Button(
            form,
            text="Save & Merge Attendance",
            style="Accent.TButton",
            command=self.save_mapping,
        ).grid(row=0, column=2, padx=15, sticky="n")

        self.user_sync_button = ttk.Button(
            self.page_toolbar,
            text="Fetch Device Users",
            style="Accent.TButton",
            command=self.fetch_device_users,
        )
        self.user_sync_button.pack(side="left", padx=4)
        self.punch_sync_button = ttk.Button(
            self.page_toolbar,
            text="Import Attendance Punches",
            command=self.sync_device,
        )
        self.punch_sync_button.pack(side="left", padx=4)
        ttk.Button(self.page_toolbar, text="Refresh", command=self.refresh).pack(
            side="left", padx=4
        )

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        mapping_tab = ttk.Frame(tabs, padding=8)
        logs_tab = ttk.Frame(tabs, padding=8)
        summary_tab = ttk.Frame(tabs, padding=8)
        student_summary_tab = ttk.Frame(tabs, padding=8)
        tabs.add(mapping_tab, text="Device Users & Mapping")
        tabs.add(logs_tab, text="Attendance Logs")
        tabs.add(summary_tab, text="Staff Totals")
        tabs.add(student_summary_tab, text="Student Monthly Totals")

        map_area = ttk.Frame(mapping_tab)
        map_area.pack(fill="both", expand=True)
        self.mapping_tree = self.make_tree(
            map_area,
            [
                ("device", "Device User ID", 105),
                ("device_name", "Name on Device", 180),
                ("uid", "Device UID", 85),
                ("status", "Mapping", 85),
                ("type", "Linked Type", 90),
                ("person", "Linked Application User", 190),
                ("logs", "Punches", 75),
                ("last", "Last Seen", 165),
            ],
        )
        self.mapping_tree.bind("<Double-1>", self.edit_mapping)
        ttk.Label(
            mapping_tab,
            text="Double-click a device user to map or change its linked Student/Staff record.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        log_area = ttk.Frame(logs_tab)
        log_area.pack(fill="both", expand=True)
        self.log_tree = self.make_tree(
            log_area,
            [
                ("id", "ID", 55),
                ("device", "Device ID", 90),
                ("type", "Type", 75),
                ("person", "Student / Staff", 180),
                ("time", "Attendance Time", 165),
                ("event", "Event", 90),
                ("serial", "Device Serial", 130),
            ],
        )

        controls = ttk.Frame(summary_tab, style="Toolbar.TFrame", padding=8)
        controls.pack(fill="x", pady=(0, 8))
        self.start_date = tk.StringVar(value=today_iso())
        self.end_date = tk.StringVar(value=today_iso())
        ttk.Label(controls, text="From (BS)", style="Hint.TLabel").pack(side="left")
        DateEntry(controls, self.start_date, width=16).pack(
            side="left", padx=(5, 12)
        )
        ttk.Label(controls, text="To (BS)", style="Hint.TLabel").pack(side="left")
        DateEntry(controls, self.end_date, width=16).pack(
            side="left", padx=(5, 12)
        )
        ttk.Button(
            controls,
            text="Calculate Totals",
            style="Accent.TButton",
            command=self.refresh_totals,
        ).pack(side="left")

        total_area = ttk.Frame(summary_tab)
        total_area.pack(fill="both", expand=True)
        self.total_tree = self.make_tree(
            total_area,
            [
                ("id", "Staff ID", 65),
                ("name", "Staff Name", 190),
                ("type", "Staff Type", 110),
                ("days", "Present Days", 95),
                ("punches", "Punches", 75),
                ("hours", "Worked Hours", 100),
                ("first", "First Attendance", 155),
                ("last", "Last Attendance", 155),
            ],
        )

        student_controls = ttk.Frame(student_summary_tab, style="Toolbar.TFrame", padding=8)
        student_controls.pack(fill="x", pady=(0, 8))
        self.student_month = tk.StringVar(value=current_month())
        ttk.Label(student_controls, text="Attendance Month (BS)", style="Hint.TLabel").pack(side="left")
        ttk.Entry(student_controls, textvariable=self.student_month, width=14).pack(side="left", padx=(6, 10))
        ttk.Button(
            student_controls,
            text="Calculate Student Totals",
            style="Accent.TButton",
            command=self.refresh_student_totals,
        ).pack(side="left")
        self.student_total_note = ttk.Label(student_controls, style="Hint.TLabel")
        self.student_total_note.pack(side="right")
        student_area = ttk.Frame(student_summary_tab)
        student_area.pack(fill="both", expand=True)
        self.student_total_tree = self.make_tree(
            student_area,
            [
                ("id", "Student ID", 75),
                ("name", "Student Name", 230),
                ("class", "Class", 100),
                ("days", "Present Days", 105),
                ("punches", "Punches", 90),
                ("hours", "Attendance Hours", 125),
            ],
        )

    def load_people(self):
        internal_type = "teacher" if self.vars["type"].get() == "Staff" else "student"
        if internal_type == "teacher":
            rows = self.db.query(
                "SELECT id, teacher_name name FROM teachers "
                "WHERE status='Active' ORDER BY teacher_name"
            )
        else:
            rows = self.db.query(
                "SELECT id, student_name name FROM students "
                "WHERE status='Active' ORDER BY student_name"
            )
        self.person_map = {
            f"{row['id']} - {row['name']}": int(row["id"]) for row in rows
        }
        self.person_combo["values"] = list(self.person_map)
        if self.vars["person"].get() not in self.person_map:
            self.vars["person"].set("")

    def show_new_form(self):
        self.vars["device"].set("")
        self.vars["type"].set("Student")
        self.vars["status"].set("Active")
        self.load_people()
        self.show_form_dialog()

    def edit_mapping(self, _event=None):
        selected = self.mapping_tree.selection()
        if not selected:
            return
        device_id = str(self.mapping_tree.item(selected[0], "values")[0])
        row = self.db.query_one(
            "SELECT * FROM device_user_mappings WHERE device_user_id = ?",
            (device_id,),
        )
        self.vars["device"].set(device_id)
        self.vars["type"].set(
            "Staff" if row and row["person_type"] == "teacher" else "Student"
        )
        self.vars["status"].set(row["status"] if row else "Active")
        self.load_people()
        if row:
            target = next(
                (
                    label
                    for label, value in self.person_map.items()
                    if value == int(row["person_id"])
                ),
                "",
            )
            self.vars["person"].set(target)
        self.show_form_dialog()

    def save_mapping(self):
        try:
            person_id = self.person_map.get(self.vars["person"].get())
            if person_id is None:
                raise ValueError("Select a Student or Staff record.")
            person_type = "teacher" if self.vars["type"].get() == "Staff" else "student"
            self.app.services.attendance.map_device_user(
                self.vars["device"].get(),
                person_type,
                person_id,
                self.vars["status"].get(),
            )
            self.hide_form_dialog()
            self.refresh()
            messagebox.showinfo(
                "Attendance Merged",
                "The device user is mapped. Existing and future punches are linked "
                "to this record.",
                parent=self,
            )
        except Exception as exc:
            self.show_error(exc)

    def _set_device_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.user_sync_button.configure(state=state)
        self.punch_sync_button.configure(state=state)

    def fetch_device_users(self):
        self._set_device_buttons(False)
        self.user_sync_button.configure(text="Fetching Users...")

        def work():
            try:
                result = self.app.services.attendance.sync_device_users()
                error = None
            except Exception as exc:
                result = None
                error = exc
            self.after(0, lambda: self.device_users_finished(result, error))

        threading.Thread(target=work, daemon=True).start()

    def device_users_finished(self, result, error):
        self._set_device_buttons(True)
        self.user_sync_button.configure(text="Fetch Device Users")
        if error:
            messagebox.showerror("Device Users", str(error), parent=self)
            return
        self.refresh()
        messagebox.showinfo(
            "Device Users",
            f"Users received from device: {result.received}\n"
            f"Users stored or refreshed: {result.stored}",
            parent=self,
        )

    def sync_device(self):
        self._set_device_buttons(False)
        self.punch_sync_button.configure(text="Importing Punches...")

        def work():
            try:
                result = self.app.services.attendance.sync()
                error = None
            except Exception as exc:
                result = None
                error = exc
            self.after(0, lambda: self.sync_finished(result, error))

        threading.Thread(target=work, daemon=True).start()

    def sync_finished(self, result, error):
        self._set_device_buttons(True)
        self.punch_sync_button.configure(text="Import Attendance Punches")
        if error:
            messagebox.showerror("Attendance Import", str(error), parent=self)
            return
        self.refresh()
        messagebox.showinfo(
            "Attendance Import",
            f"Device punches received: {result.received}\n"
            f"New punches saved: {result.saved}\n"
            f"Unmapped punches: {result.unmapped}",
            parent=self,
        )

    @staticmethod
    def bs_range(value, end=False):
        value = validate_date(value, "Attendance date")
        year, month, day = (int(part) for part in value.split("/"))
        ad_date = nepali.date(year, month, day).to_datetime_date().isoformat()
        return ad_date + (" 23:59:59" if end else " 00:00:00")

    @staticmethod
    def display_time(value):
        if not value:
            return ""
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        bs_date = nepali.date.from_datetime_date(timestamp.date())
        return f"{bs_date.strftime('%Y/%m/%d')} {timestamp.strftime('%H:%M:%S')}"

    @staticmethod
    def person_type_label(value):
        if value == "teacher":
            return "Staff"
        if value == "student":
            return "Student"
        return ""

    def refresh(self):
        self.load_people()
        self.clear_tree(self.mapping_tree)
        rows = self.app.services.attendance.repository.device_users()
        for row in rows:
            self.mapping_tree.insert(
                "",
                "end",
                values=(
                    row["device_user_id"],
                    row["device_name"] or "",
                    row["device_uid"] if row["device_uid"] is not None else "",
                    row["status"],
                    self.person_type_label(row["person_type"]),
                    row["person_name"] or "",
                    row["log_count"],
                    self.display_time(row["last_seen"]),
                ),
            )

        self.clear_tree(self.log_tree)
        for row in self.app.services.attendance.repository.logs(limit=1000):
            person_type = self.person_type_label(row["person_type"]) or "Unmapped"
            self.log_tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["device_user_id"],
                    person_type,
                    row["person_name"] or "",
                    self.display_time(row["occurred_at"]),
                    row["event_type"],
                    row["device_serial"] or "",
                ),
            )
        self.refresh_totals()
        self.refresh_student_totals()

    def refresh_totals(self):
        try:
            start = self.bs_range(self.start_date.get())
            end = self.bs_range(self.end_date.get(), True)
            if end < start:
                raise ValueError("End date cannot be earlier than start date.")
            self.clear_tree(self.total_tree)
            for row in self.app.services.attendance.staff_totals(start, end):
                self.total_tree.insert(
                    "",
                    "end",
                    values=(
                        row["person_id"],
                        row["name"],
                        row["staff_type"],
                        row["days"],
                        row["punches"],
                        f"{row['hours']:,.2f}",
                        self.display_time(row["first"]),
                        self.display_time(row["last"]),
                    ),
                )
        except Exception as exc:
            self.show_error(exc)

    def refresh_student_totals(self):
        try:
            month = validate_month(self.student_month.get(), "Attendance month")
            rows = self.app.services.attendance.student_month_totals(month)
            self.clear_tree(self.student_total_tree)
            for row in rows:
                self.student_total_tree.insert(
                    "",
                    "end",
                    values=(
                        row["person_id"], row["name"], row["class_name"],
                        row["days"], row["punches"], f"{row['hours']:,.2f}",
                    ),
                )
            present = sum(1 for row in rows if row["days"])
            self.student_total_note.configure(
                text=f"{present} of {len(rows)} students present this month"
            )
        except Exception as exc:
            self.show_error(exc)
