"""Weekly academic routine maintenance screen."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder


DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


class RoutinesPage(CrudPage):
    """Maintain scheduled periods used by attendance and per-period payroll."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id: int | None = None
        self.teacher_map: dict[str, int] = {}
        self.course_map: dict[str, int] = {}
        ttk.Label(self, text="Class Routine", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Only a class with an active period on a day is considered working for student absence checks.",
            style="Hint.TLabel",
        ).pack(anchor="w")

        form = self.create_form_dialog("Routine Period", padding=10)
        form.pack(fill="x", pady=8)
        self.vars = {
            "class": tk.StringVar(), "day": tk.StringVar(value="Sunday"),
            "period": tk.StringVar(), "subject": tk.StringVar(), "teacher": tk.StringVar(),
            "course": tk.StringVar(), "start": tk.StringVar(), "end": tk.StringVar(),
            "status": tk.StringVar(value="Active"), "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.class_combo = fb.combo("Class / Level *", self.vars["class"], [], searchable=True)
        fb.combo("Day *", self.vars["day"], DAYS)
        fb.entry("Period *", self.vars["period"])
        fb.entry("Subject *", self.vars["subject"])
        self.teacher_combo = fb.combo("Staff / Teacher", self.vars["teacher"], [], searchable=True)
        self.course_combo = fb.combo("Course (optional)", self.vars["course"], [], searchable=True)
        fb.entry("Start Time", self.vars["start"])
        fb.entry("End Time", self.vars["end"])
        fb.combo("Status", self.vars["status"], ["Active", "Inactive"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)
        actions = ttk.Frame(form, style="Form.TFrame")
        actions.grid(row=0, column=2, rowspan=10, padx=15, sticky="n")
        ttk.Button(actions, text="Save Routine", style="Accent.TButton", command=self.save).pack(fill="x", pady=3)
        ttk.Button(actions, text="Update", command=self.update).pack(fill="x", pady=3)
        ttk.Button(actions, text="Delete", style="Danger.TButton", command=self.delete).pack(fill="x", pady=3)

        area = ttk.Frame(self); area.pack(fill="both", expand=True)
        self.tree = self.make_tree(area, [
            ("id", "ID", 55), ("class", "Class", 110), ("day", "Day", 105),
            ("period", "Period", 110), ("subject", "Subject", 160),
            ("staff", "Staff", 160), ("course", "Course", 150),
            ("time", "Time", 115), ("status", "Status", 90),
        ])
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.open_editor)

    def _values(self):
        class_name = self.vars["class"].get().strip()
        period = self.vars["period"].get().strip()
        subject = self.vars["subject"].get().strip()
        if not class_name or not period or not subject:
            raise ValueError("Class/Level, period, and subject are required.")
        return (
            class_name, self.vars["day"].get(), period, subject,
            self.teacher_map.get(self.vars["teacher"].get()),
            self.course_map.get(self.vars["course"].get()),
            self.vars["start"].get().strip(), self.vars["end"].get().strip(),
            self.vars["status"].get(), self.vars["remarks"].get().strip(),
        )

    def save(self):
        try:
            self.db.execute(
                "INSERT INTO class_routines (class_name,day_of_week,period_label,subject_name,teacher_id,course_id,start_time,end_time,status,remarks) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", self._values(),
            )
            self.clear(); self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def update(self):
        if not self.selected_id:
            return
        try:
            self.db.execute(
                "UPDATE class_routines SET class_name=?,day_of_week=?,period_label=?,subject_name=?,teacher_id=?,course_id=?,start_time=?,end_time=?,status=?,remarks=? WHERE id=?",
                self._values() + (self.selected_id,),
            )
            self.clear(); self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def delete(self):
        if self.selected_id and self.confirm_delete():
            self.db.execute("DELETE FROM class_routines WHERE id=?", (self.selected_id,))
            self.clear(); self.app.refresh_all()

    def clear(self):
        self.selected_id = None
        for key, value in self.vars.items():
            value.set("Sunday" if key == "day" else "Active" if key == "status" else "")

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        row = self.db.query_one("SELECT * FROM class_routines WHERE id=?", (int(self.tree.item(selected[0], "values")[0]),))
        if not row:
            return
        self.selected_id = int(row["id"])
        self.vars["class"].set(row["class_name"])
        self.vars["day"].set(row["day_of_week"])
        self.vars["period"].set(row["period_label"])
        self.vars["subject"].set(row["subject_name"])
        self.vars["teacher"].set(next((label for label, ident in self.teacher_map.items() if ident == row["teacher_id"]), ""))
        self.vars["course"].set(next((label for label, ident in self.course_map.items() if ident == row["course_id"]), ""))
        self.vars["start"].set(row["start_time"] or "")
        self.vars["end"].set(row["end_time"] or "")
        self.vars["status"].set(row["status"])
        self.vars["remarks"].set(row["remarks"] or "")

    def open_editor(self, _event=None):
        if self.tree.selection():
            self.on_select(); self.show_form_dialog()
        return "break"

    def refresh(self):
        classes = self.db.query("SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL AND class_name<>'' ORDER BY class_name")
        self.class_combo.set_values([str(row["class_name"]) for row in classes])
        teachers = self.app.lookup_cache.get("active_staff", lambda: self.db.query("SELECT id,teacher_name FROM teachers WHERE status='Active' ORDER BY teacher_name"))
        self.teacher_map = {f"{row['id']} - {row['teacher_name']}": int(row["id"]) for row in teachers}
        self.teacher_combo.set_values(self.teacher_map)
        courses = self.app.lookup_cache.get("active_courses", lambda: self.db.query("SELECT id,course_name,category FROM courses WHERE status='Active' ORDER BY category,course_name"))
        self.course_map = {f"{row['course_name']} [{row['category']}]": int(row["id"]) for row in courses}
        self.course_combo.set_values(self.course_map)
        self.clear_tree(self.tree)
        rows = self.db.query(
            "SELECT r.*,t.teacher_name,c.course_name FROM class_routines r "
            "LEFT JOIN teachers t ON t.id=r.teacher_id LEFT JOIN courses c ON c.id=r.course_id "
            "ORDER BY CASE r.day_of_week WHEN 'Sunday' THEN 1 WHEN 'Monday' THEN 2 WHEN 'Tuesday' THEN 3 "
            "WHEN 'Wednesday' THEN 4 WHEN 'Thursday' THEN 5 WHEN 'Friday' THEN 6 WHEN 'Saturday' THEN 7 ELSE 8 END,"
            "r.class_name,r.period_label"
        )
        for row in rows:
            time = " - ".join(part for part in (row["start_time"] or "", row["end_time"] or "") if part)
            self.tree.insert("", "end", values=(row["id"], row["class_name"], row["day_of_week"], row["period_label"], row["subject_name"], row["teacher_name"] or "", row["course_name"] or "", time, row["status"]))
