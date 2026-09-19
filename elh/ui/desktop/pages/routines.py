"""Weekly academic routine maintenance screen."""

from __future__ import annotations

import tkinter as tk
import os
from pathlib import Path
from tkinter import messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder, SearchableCombobox, TimeEntry
from elh.ui.desktop.helpers import today_iso


DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


class RoutinesPage(CrudPage):
    """Maintain scheduled periods used by attendance and per-period payroll."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id: int | None = None
        self.teacher_map: dict[str, int] = {}
        self.course_map: dict[str, int] = {}
        self.class_map: dict[str, int] = {}
        self.subject_map: dict[str, int] = {}
        self.routine_plan_map: dict[str, int] = {}
        self.routine_plan = tk.StringVar()
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
        self.subject_combo = fb.combo("Subject *", self.vars["subject"], [], searchable=True)
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
        ttk.Button(actions, text="Copy Record…", command=self.copy_record).pack(fill="x", pady=3)
        ttk.Button(actions, text="Delete", style="Danger.TButton", command=self.delete).pack(fill="x", pady=3)
        ttk.Button(actions, text="Clear", command=self.clear).pack(fill="x", pady=3)

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

        self.context_menu = tk.Menu(self, tearoff=False)
        self.context_menu.add_command(label="📋 Copy / Duplicate Record…", command=self.copy_record)
        self.context_menu.add_command(label="✏️ Edit Record", command=self.open_editor)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ Delete Record", command=self.delete)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        plan_bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 6))
        plan_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(plan_bar, text="Routine Plan", style="Form.TLabel").pack(side="left")
        self.plan_combo = SearchableCombobox(plan_bar, textvariable=self.routine_plan, values=[], width=38)
        self.plan_combo.pack(side="left", padx=(8, 6))
        self.plan_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(plan_bar, text="New Effective Plan…", command=self.new_effective_plan).pack(side="left")
        ttk.Label(
            plan_bar, text="Periods belong to a dated plan; creating a new plan keeps the old schedule for history.",
            style="Hint.TLabel",
        ).pack(side="left", padx=10)
        ttk.Button(
            self.page_toolbar, text="📋 Copy Record…", command=self.copy_record
        ).pack(side="left", padx=4)
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
        plan_id = self.routine_plan_map.get(self.routine_plan.get())
        if not plan_id:
            raise ValueError("Select a routine plan before saving periods.")
        subject_id = None
        for key, sid in self.subject_map.items():
            if subject.lower() == key.lower() or f"{subject.lower()} (" in key.lower() or key.lower().startswith(subject.lower()):
                subject_id = sid
                break
        return (
            class_name, self.vars["day"].get(), period, subject,
            subject_id,
            class_id,
            self.teacher_map.get(self.vars["teacher"].get()),
            self.course_map.get(self.vars["course"].get()),
            self.vars["start"].get().strip(), self.vars["end"].get().strip(),
            self.vars["status"].get(), self.vars["remarks"].get().strip(), plan_id,
        )

    def save(self):
        try:
            self.db.execute(
                "INSERT INTO class_routines (class_name,day_of_week,period_label,subject_name,subject_id,class_level_id,teacher_id,course_id,start_time,end_time,status,remarks,routine_plan_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", self._values(),
            )
            self.clear(); self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def update(self):
        if not self.selected_id:
            return
        try:
            self.db.execute(
                "UPDATE class_routines SET class_name=?,day_of_week=?,period_label=?,subject_name=?,subject_id=?,class_level_id=?,teacher_id=?,course_id=?,start_time=?,end_time=?,status=?,remarks=?,routine_plan_id=? WHERE id=?",
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

    def _on_tree_right_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.on_select()
            self.context_menu.post(event.x_root, event.y_root)

    def copy_record(self) -> None:
        """Allow copying a specific selected routine record to another day, multiple days, or another class."""
        selected = self.tree.selection()
        if selected:
            record_id = int(self.tree.item(selected[0], "values")[0])
        elif self.selected_id:
            record_id = self.selected_id
        else:
            messagebox.showwarning(
                "Class Routine",
                "Select a specific routine record from the list to copy.",
                parent=self,
            )
            return

        row = self.db.query_one("SELECT * FROM class_routines WHERE id=?", (record_id,))
        if not row:
            messagebox.showerror("Class Routine", "The selected routine record could not be found.", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title("Copy Routine Record")
        dialog.configure(background="#EEF3F8")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)

        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)

        header_frame = ttk.Frame(shell, style="Form.TFrame")
        header_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(header_frame, text="Copy Routine Record", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header_frame,
            text=f"Source: {row['class_name']} • {row['subject_name']} ({row['period_label']}) on {row['day_of_week']}",
            style="Hint.TLabel",
        ).pack(anchor="w")

        notebook = ttk.Notebook(shell)
        notebook.pack(fill="both", expand=True, pady=(0, 10))

        # --- TAB 1: Duplicate to Other Days ---
        tab_days = ttk.Frame(notebook, padding=10, style="Form.TFrame")
        notebook.add(tab_days, text="  Duplicate to Other Days  ")

        ttk.Label(
            tab_days,
            text="Duplicate this routine period across other days of the week with the same teacher, subject, and time:",
            style="Hint.TLabel",
            wraplength=480,
        ).pack(anchor="w", pady=(0, 10))

        day_check_frame = ttk.Frame(tab_days, style="Form.TFrame")
        day_check_frame.pack(fill="x", pady=(0, 8))

        day_vars: dict[str, tk.BooleanVar] = {}
        for idx, day in enumerate(DAYS):
            var = tk.BooleanVar(value=False)
            day_vars[day] = var
            label_text = f"{day} (Current)" if day == row["day_of_week"] else day
            cb = ttk.Checkbutton(day_check_frame, text=label_text, variable=var)
            cb.grid(row=idx // 4, column=idx % 4, sticky="w", padx=6, pady=4)

        btn_row = ttk.Frame(tab_days, style="Form.TFrame")
        btn_row.pack(fill="x", pady=(4, 10))

        def select_working_days():
            for d in ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
                if d != row["day_of_week"]:
                    day_vars[d].set(True)

        def select_weekdays():
            for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
                if d != row["day_of_week"]:
                    day_vars[d].set(True)

        def clear_days():
            for v in day_vars.values():
                v.set(False)

        ttk.Button(btn_row, text="Sun - Fri (All Working Days)", command=select_working_days).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Mon - Fri", command=select_weekdays).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Clear", command=clear_days).pack(side="left", padx=4)

        def copy_to_days():
            chosen_days = [d for d, v in day_vars.items() if v.get()]
            if not chosen_days:
                messagebox.showwarning("Copy Routine", "Select at least one day to copy to.", parent=dialog)
                return
            plan_id = self.routine_plan_map.get(self.routine_plan.get())
            if not plan_id:
                messagebox.showerror("Copy Routine", "No active routine plan selected.", parent=dialog)
                return
            try:
                for target_day in chosen_days:
                    self.db.execute(
                        "INSERT INTO class_routines (class_name,day_of_week,period_label,subject_name,class_level_id,teacher_id,course_id,start_time,end_time,status,remarks,routine_plan_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            row["class_name"], target_day, row["period_label"], row["subject_name"],
                            row["class_level_id"], row["teacher_id"], row["course_id"],
                            row["start_time"], row["end_time"], row["status"], row["remarks"],
                            plan_id,
                        ),
                    )
                dialog.destroy()
                self.app.refresh_all()
                messagebox.showinfo("Copy Routine", f"Successfully copied routine to {len(chosen_days)} day(s): {', '.join(chosen_days)}.", parent=self)
            except Exception as exc:
                messagebox.showerror("Copy Routine", str(exc), parent=dialog)

        ttk.Button(tab_days, text="Copy Period to Selected Day(s)", style="Accent.TButton", command=copy_to_days).pack(anchor="e", pady=(4, 0))

        # --- TAB 2: Custom / Single Copy ---
        tab_custom = ttk.Frame(notebook, padding=10, style="Form.TFrame")
        notebook.add(tab_custom, text="  Customize & Copy  ")

        c_class = tk.StringVar(value=row["class_name"])
        c_day = tk.StringVar(value=row["day_of_week"])
        c_period = tk.StringVar(value=row["period_label"])
        c_subject = tk.StringVar(value=row["subject_name"])
        teacher_label = next((l for l, ident in self.teacher_map.items() if ident == row["teacher_id"]), "")
        c_teacher = tk.StringVar(value=teacher_label)
        course_label = next((l for l, ident in self.course_map.items() if ident == row["course_id"]), "")
        c_course = tk.StringVar(value=course_label)
        c_start = tk.StringVar(value=row["start_time"] or "")
        c_end = tk.StringVar(value=row["end_time"] or "")
        c_status = tk.StringVar(value=row["status"] or "Active")
        c_remarks = tk.StringVar(value=row["remarks"] or "")

        custom_form = ttk.Frame(tab_custom, style="Form.TFrame")
        custom_form.pack(fill="x")
        cfb = FormBuilder(custom_form)
        cfb.combo("Class / Level *", c_class, list(self.class_map), searchable=True)
        cfb.combo("Day *", c_day, DAYS)
        cfb.entry("Period *", c_period)
        cfb.entry("Subject *", c_subject)
        cfb.combo("Staff / Teacher", c_teacher, list(self.teacher_map), searchable=True)
        cfb.combo("Course (optional)", c_course, list(self.course_map), searchable=True)
        cfb.entry("Start Time", c_start)
        cfb.entry("End Time", c_end)
        cfb.combo("Status", c_status, ["Active", "Inactive"])
        cfb.entry("Remarks", c_remarks)

        def save_custom_copy():
            class_name = c_class.get().strip()
            period = c_period.get().strip()
            subject = c_subject.get().strip()
            if not class_name or not period or not subject:
                messagebox.showerror("Copy Routine", "Class/Level, period, and subject are required.", parent=dialog)
                return
            class_id = self.class_map.get(class_name)
            if not class_id:
                messagebox.showerror("Copy Routine", "Select a valid class/level.", parent=dialog)
                return
            plan_id = self.routine_plan_map.get(self.routine_plan.get())
            if not plan_id:
                messagebox.showerror("Copy Routine", "Select a routine plan first.", parent=dialog)
                return
            try:
                self.db.execute(
                    "INSERT INTO class_routines (class_name,day_of_week,period_label,subject_name,class_level_id,teacher_id,course_id,start_time,end_time,status,remarks,routine_plan_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        class_name, c_day.get(), period, subject,
                        class_id,
                        self.teacher_map.get(c_teacher.get()),
                        self.course_map.get(c_course.get()),
                        c_start.get().strip(), c_end.get().strip(),
                        c_status.get(), c_remarks.get().strip(), plan_id,
                    ),
                )
                dialog.destroy()
                self.app.refresh_all()
                messagebox.showinfo("Copy Routine", "New routine copy saved successfully.", parent=self)
            except Exception as exc:
                messagebox.showerror("Copy Routine", str(exc), parent=dialog)

        ttk.Button(tab_custom, text="Save as New Routine", style="Accent.TButton", command=save_custom_copy).pack(anchor="e", pady=(8, 0))

        # Bottom actions for dialog
        bottom_actions = ttk.Frame(shell, style="Form.TFrame")
        bottom_actions.pack(fill="x", pady=(8, 0))

        def copy_into_main_form():
            self.selected_id = None
            self.vars["class"].set(c_class.get())
            self.vars["day"].set(c_day.get())
            self.vars["period"].set(c_period.get())
            self.vars["subject"].set(c_subject.get())
            self.vars["teacher"].set(c_teacher.get())
            self.vars["course"].set(c_course.get())
            self.vars["start"].set(c_start.get())
            self.vars["end"].set(c_end.get())
            self.vars["status"].set(c_status.get())
            self.vars["remarks"].set(c_remarks.get())
            dialog.destroy()
            self.show_form_dialog()

        ttk.Button(bottom_actions, text="Load into Form as New (Unsaved)", command=copy_into_main_form).pack(side="left")
        ttk.Button(bottom_actions, text="Close", command=dialog.destroy).pack(side="right")

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

    def new_effective_plan(self) -> None:
        source_plan_id = self.routine_plan_map.get(self.routine_plan.get())
        if not source_plan_id:
            messagebox.showwarning("Routine Plan", "Select the routine plan to copy first.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Create Effective Routine Plan")
        dialog.configure(background="#EEF3F8")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Create a New Routine Plan", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="The selected plan is retained as history. Its periods are copied so you can edit the new plan safely.",
            style="Hint.TLabel", wraplength=520,
        ).pack(anchor="w", pady=(0, 10))
        name = tk.StringVar()
        effective_from = tk.StringVar(value=today_iso())
        remarks = tk.StringVar()
        form = ttk.Frame(shell, style="Form.TFrame")
        form.pack(fill="x")
        fb = FormBuilder(form)
        fb.entry("Plan Name *", name, width=42)
        fb.entry("Effective From *", effective_from, width=42)
        fb.entry("Remarks", remarks, width=42)
        archive_source = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            shell, text="Archive selected plan when this plan starts", variable=archive_source
        ).pack(anchor="w", pady=(8, 0))
        actions = ttk.Frame(shell, style="Form.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")

        def create_plan():
            try:
                plan_name = name.get().strip()
                starts = effective_from.get().strip()
                if not plan_name or not starts:
                    raise ValueError("Plan name and effective-from date are required.")
                new_id = self.db.execute(
                    "INSERT INTO routine_plans (plan_name,effective_from,status,remarks) VALUES (?,?,?,?)",
                    (plan_name, starts, "Active", remarks.get().strip()),
                )
                self.db.execute(
                    "INSERT INTO class_routines (routine_plan_id,class_name,day_of_week,period_label,subject_name,"
                    "class_level_id,teacher_id,course_id,start_time,end_time,status,remarks,grade_id) "
                    "SELECT ?,class_name,day_of_week,period_label,subject_name,class_level_id,teacher_id,course_id,"
                    "start_time,end_time,status,remarks,grade_id FROM class_routines WHERE routine_plan_id=?",
                    (new_id, source_plan_id),
                )
                if archive_source:
                    self.db.execute(
                        "UPDATE routine_plans SET status='Archived',effective_to=? WHERE id=?",
                        (starts, source_plan_id),
                    )
                dialog.destroy()
                self.routine_plan.set(f"{plan_name} (from {starts})")
                self.clear()
                self.app.refresh_all()
            except Exception as exc:
                messagebox.showerror("Routine Plan", str(exc), parent=dialog)

        ttk.Button(actions, text="Create and Copy Periods", style="Accent.TButton", command=create_plan).pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()

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

        apply_subject = tk.BooleanVar()
        apply_course = tk.BooleanVar()
        apply_teacher = tk.BooleanVar()
        apply_start = tk.BooleanVar()
        apply_end = tk.BooleanVar()
        apply_status = tk.BooleanVar()
        apply_remarks = tk.BooleanVar()
        subject = tk.StringVar()
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

        subject_box = SearchableCombobox(shell, textvariable=subject, values=list(self.subject_map), width=34)
        course_box = SearchableCombobox(shell, textvariable=course, values=list(self.course_map), width=34)
        teacher_box = SearchableCombobox(shell, textvariable=teacher, values=list(self.teacher_map), width=34)
        start_box = TimeEntry(shell, start_time, width=34)
        end_box = TimeEntry(shell, end_time, width=34)
        status_box = ttk.Combobox(shell, textvariable=status, values=("Active", "Inactive"), width=31, state="readonly")
        remarks_box = ttk.Entry(shell, textvariable=remarks, width=36)
        bulk_row(2, "Subject", apply_subject, subject_box)
        bulk_row(3, "Course", apply_course, course_box)
        bulk_row(4, "Staff / Teacher", apply_teacher, teacher_box)
        bulk_row(5, "Start Time", apply_start, start_box)
        bulk_row(6, "End Time", apply_end, end_box)
        bulk_row(7, "Status", apply_status, status_box)
        bulk_row(8, "Remarks", apply_remarks, remarks_box)
        shell.columnconfigure(2, weight=1)

        actions = ttk.Frame(shell, style="Form.TFrame")
        actions.grid(row=9, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")

        def apply_changes():
            updates: list[str] = []
            params: list[object] = []
            if apply_subject.get():
                subj_text = subject.get().strip()
                if not subj_text:
                    raise ValueError("Subject cannot be empty.")
                matched_id = None
                clean_name = subj_text
                for key, sid in self.subject_map.items():
                    if subj_text.lower() == key.lower() or f"{subj_text.lower()} (" in key.lower() or key.lower().startswith(subj_text.lower()):
                        matched_id = sid
                        if " (" in key and key.endswith(")"):
                            clean_name = key[:key.rfind(" (")].strip()
                        break
                if matched_id is None:
                    row = self.db.query_one(
                        "SELECT id, subject_name FROM subjects WHERE LOWER(subject_name) = ? OR LOWER(subject_code) = ?",
                        (subj_text.lower(), subj_text.lower()),
                    )
                    if row:
                        matched_id = int(row["id"])
                        clean_name = row["subject_name"]
                updates.append("subject_name=?")
                params.append(clean_name)
                updates.append("subject_id=?")
                params.append(matched_id)
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
        height = max(420, dialog.winfo_reqheight() + 20)
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
            os.startfile(Path(self.app.services.reports.routine_pdf(
                class_id, routine_plan_id=self.routine_plan_map.get(self.routine_plan.get())
            )), "print")
        except Exception as exc:
            self.show_error(exc)

    def open_all_pdf(self):
        try:
            os.startfile(Path(self.app.services.reports.routine_pdf(
                routine_plan_id=self.routine_plan_map.get(self.routine_plan.get())
            )), "print")
        except Exception as exc:
            self.show_error(exc)

    def refresh(self):
        plans = self.db.query(
            "SELECT id,plan_name,effective_from,status FROM routine_plans "
            "ORDER BY CASE status WHEN 'Active' THEN 0 ELSE 1 END,effective_from DESC,id DESC"
        )
        self.routine_plan_map = {
            f"{row['plan_name']} (from {row['effective_from']})": int(row["id"])
            for row in plans
        }
        self.plan_combo.set_values(self.routine_plan_map)
        if self.routine_plan.get() not in self.routine_plan_map and self.routine_plan_map:
            self.routine_plan.set(next(iter(self.routine_plan_map)))
        classes = self.db.query("SELECT id,level_name FROM class_levels WHERE status='Active' ORDER BY level_name")
        self.class_map = {str(row["level_name"]): int(row["id"]) for row in classes}
        self.class_combo.set_values(self.class_map)
        teachers = self.app.lookup_cache.get("active_staff", lambda: self.db.query("SELECT id,teacher_name FROM teachers WHERE status='Active' ORDER BY teacher_name"))
        self.teacher_map = {f"{row['id']} - {row['teacher_name']}": int(row["id"]) for row in teachers}
        self.teacher_combo.set_values(self.teacher_map)
        courses = self.app.lookup_cache.get("active_courses", lambda: self.db.query("SELECT id,course_name,category FROM courses WHERE status='Active' ORDER BY category,course_name"))
        self.course_map = {f"{row['course_name']} [{row['category']}]": int(row["id"]) for row in courses}
        self.course_combo.set_values(self.course_map)
        subjects = self.db.query("SELECT id, subject_name, subject_code FROM subjects WHERE status='Active' ORDER BY subject_name")
        self.subject_map = {f"{row['subject_name']} ({row['subject_code']})": int(row["id"]) for row in subjects}
        self.subject_combo.set_values([row["subject_name"] for row in subjects])
        self.clear_tree(self.tree)
        plan_id = self.routine_plan_map.get(self.routine_plan.get())
        if not plan_id:
            return
        rows = self.db.query(
            "SELECT r.*,t.teacher_name,c.course_name FROM class_routines r "
            "LEFT JOIN teachers t ON t.id=r.teacher_id LEFT JOIN courses c ON c.id=r.course_id "
            "WHERE r.routine_plan_id=? "
            "ORDER BY CASE r.day_of_week WHEN 'Sunday' THEN 1 WHEN 'Monday' THEN 2 WHEN 'Tuesday' THEN 3 "
            "WHEN 'Wednesday' THEN 4 WHEN 'Thursday' THEN 5 WHEN 'Friday' THEN 6 WHEN 'Saturday' THEN 7 ELSE 8 END,"
            "r.class_name,r.period_label", (plan_id,)
        )
        for row in rows:
            time = " - ".join(part for part in (row["start_time"] or "", row["end_time"] or "") if part)
            self.tree.insert("", "end", values=(row["id"], row["class_name"], row["day_of_week"], row["period_label"], row["subject_name"], row["teacher_name"] or "", row["course_name"] or "", time, row["status"]))
