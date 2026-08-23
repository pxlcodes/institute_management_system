"""Weekly academic routine maintenance screen."""

from __future__ import annotations

import tkinter as tk
import os
from pathlib import Path
from tkinter import messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder, SearchableCombobox, TimeEntry


DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


class RoutinesPage(CrudPage):
    """Maintain scheduled periods used by attendance and per-period payroll."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id: int | None = None
        self.teacher_map: dict[str, int] = {}
        self.course_map: dict[str, int] = {}
        self.class_map: dict[str, int] = {}
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
        self.tree.configure(selectmode="extended")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.open_editor)
        ttk.Button(
            self.page_toolbar, text="Bulk Edit Selected…", command=self.bulk_edit_selected
        ).pack(side="left", padx=4)
        ttk.Button(self.page_toolbar, text="Print Selected Class", command=self.print_selected_class).pack(side="left", padx=4)
        ttk.Button(self.page_toolbar, text="Open All Routines PDF", command=self.open_all_pdf).pack(side="left", padx=4)

    def _values(self):
        class_name = self.vars["class"].get().strip()
        period = self.vars["period"].get().strip()
        subject = self.vars["subject"].get().strip()
        if not class_name or not period or not subject:
            raise ValueError("Class/Level, period, and subject are required.")
        class_id = self.class_map.get(class_name)
        if not class_id:
            raise ValueError("Select a class/level from the Class Levels list.")
        return (
            class_name, self.vars["day"].get(), period, subject,
            class_id,
            self.teacher_map.get(self.vars["teacher"].get()),
            self.course_map.get(self.vars["course"].get()),
            self.vars["start"].get().strip(), self.vars["end"].get().strip(),
            self.vars["status"].get(), self.vars["remarks"].get().strip(),
        )

    def save(self):
        try:
            self.db.execute(
                "INSERT INTO class_routines (class_name,day_of_week,period_label,subject_name,class_level_id,teacher_id,course_id,start_time,end_time,status,remarks) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", self._values(),
            )
            self.clear(); self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def update(self):
        if not self.selected_id:
            return
        try:
            self.db.execute(
                "UPDATE class_routines SET class_name=?,day_of_week=?,period_label=?,subject_name=?,class_level_id=?,teacher_id=?,course_id=?,start_time=?,end_time=?,status=?,remarks=? WHERE id=?",
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

    def bulk_edit_selected(self) -> None:
        """Apply only explicitly selected fields to all selected routine periods."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Bulk Edit", "Select one or more routine rows first.", parent=self
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Bulk Edit Routine Periods")
        dialog.configure(background="#EEF3F8")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Bulk Edit Selected Routine Periods", style="SubTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            shell,
            text=f"{len(selected)} period(s) selected. Tick only the fields you want to replace.",
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        apply_course = tk.BooleanVar()
        apply_teacher = tk.BooleanVar()
        apply_start = tk.BooleanVar()
        apply_end = tk.BooleanVar()
        apply_status = tk.BooleanVar()
        apply_remarks = tk.BooleanVar()
        course = tk.StringVar()
        teacher = tk.StringVar()
        start_time = tk.StringVar()
        end_time = tk.StringVar()
        status = tk.StringVar(value="Active")
        remarks = tk.StringVar()

        def bulk_row(row, label, apply_var, widget):
            ttk.Checkbutton(shell, variable=apply_var).grid(row=row, column=0, padx=(0, 5), pady=4)
            ttk.Label(shell, text=label, style="Form.TLabel").grid(row=row, column=1, sticky="w", padx=4, pady=4)
            widget.grid(row=row, column=2, sticky="ew", padx=(6, 0), pady=4)

        course_box = SearchableCombobox(shell, textvariable=course, values=list(self.course_map), width=34)
        teacher_box = SearchableCombobox(shell, textvariable=teacher, values=list(self.teacher_map), width=34)
        start_box = TimeEntry(shell, start_time, width=34)
        end_box = TimeEntry(shell, end_time, width=34)
        status_box = ttk.Combobox(shell, textvariable=status, values=("Active", "Inactive"), width=31, state="readonly")
        remarks_box = ttk.Entry(shell, textvariable=remarks, width=36)
        bulk_row(2, "Course", apply_course, course_box)
        bulk_row(3, "Staff / Teacher", apply_teacher, teacher_box)
        bulk_row(4, "Start Time", apply_start, start_box)
        bulk_row(5, "End Time", apply_end, end_box)
        bulk_row(6, "Status", apply_status, status_box)
        bulk_row(7, "Remarks", apply_remarks, remarks_box)
        shell.columnconfigure(2, weight=1)

        actions = ttk.Frame(shell, style="Form.TFrame")
        actions.grid(row=8, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")

        def apply_changes():
            updates: list[str] = []
            params: list[object] = []
            if apply_course.get():
                course_label = course.get().strip()
                if course_label and course_label not in self.course_map:
                    raise ValueError("Select a course from the list, or leave it blank to remove it.")
                updates.append("course_id=?")
                params.append(self.course_map.get(course_label))
            if apply_teacher.get():
                teacher_label = teacher.get().strip()
                if teacher_label and teacher_label not in self.teacher_map:
                    raise ValueError("Select a staff member from the list, or leave it blank to remove it.")
                updates.append("teacher_id=?")
                params.append(self.teacher_map.get(teacher_label))
            if apply_start.get():
                updates.append("start_time=?")
                params.append(start_time.get().strip())
            if apply_end.get():
                updates.append("end_time=?")
                params.append(end_time.get().strip())
            if apply_status.get():
                updates.append("status=?")
                params.append(status.get())
            if apply_remarks.get():
                updates.append("remarks=?")
                params.append(remarks.get().strip())
            if not updates:
                raise ValueError("Tick at least one field to update.")
            routine_ids = [int(self.tree.item(item, "values")[0]) for item in selected]
            if not messagebox.askyesno(
                "Confirm Bulk Edit",
                f"Apply these changes to {len(routine_ids)} selected routine period(s)?",
                parent=dialog,
            ):
                return
            placeholders = ",".join("?" for _ in routine_ids)
            self.db.execute(
                f"UPDATE class_routines SET {', '.join(updates)} WHERE id IN ({placeholders})",
                tuple(params + routine_ids),
            )
            dialog.destroy()
            self.clear()
            self.app.refresh_all()

        def save_bulk():
            try:
                apply_changes()
            except Exception as exc:
                messagebox.showerror("Bulk Edit", str(exc), parent=dialog)

        ttk.Button(actions, text="Apply to Selected", style="Accent.TButton", command=save_bulk).pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()
        width = max(560, dialog.winfo_reqwidth() + 20)
        height = max(370, dialog.winfo_reqheight() + 20)
        x = max(0, (dialog.winfo_screenwidth() - width) // 2)
        y = max(0, (dialog.winfo_screenheight() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()

    def print_selected_class(self):
        class_id = self.class_map.get(self.vars["class"].get())
        if not class_id:
            messagebox.showinfo("Class Routine", "Select a routine row or class first.", parent=self)
            return
        try:
            os.startfile(Path(self.app.services.reports.routine_pdf(class_id)), "print")
        except Exception as exc:
            self.show_error(exc)

    def open_all_pdf(self):
        try:
            os.startfile(Path(self.app.services.reports.routine_pdf()))
        except Exception as exc:
            self.show_error(exc)

    def refresh(self):
        classes = self.db.query("SELECT id,level_name FROM class_levels WHERE status='Active' ORDER BY level_name")
        self.class_map = {str(row["level_name"]): int(row["id"]) for row in classes}
        self.class_combo.set_values(self.class_map)
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
