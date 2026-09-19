"""Subject & Student Electives maintenance screen for Desktop UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from elh.models.academics import Subject
from elh.ui.desktop.components import CrudPage, FormBuilder, SearchableCombobox


class SubjectsPage(CrudPage):
    """Maintain academic subjects, optional electives, and student subject enrollments."""

    def __init__(self, parent: tk.Widget, app: Any) -> None:
        super().__init__(parent, app)
        self.selected_id: int | None = None
        self.class_map: dict[str, int] = {}
        self.reverse_class_map: dict[int, str] = {}

        ttk.Label(self, text="Subjects & Electives", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Manage curriculum subjects, compulsory and optional electives, and assign them to students.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        # Top Form Dialog / Panel
        form = self.create_form_dialog("Subject Details", padding=10)
        form.pack(fill="x", pady=6)

        self.code_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar(value="Optional")
        self.class_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Active")
        self.remarks_var = tk.StringVar()

        fb = FormBuilder(form)
        fb.entry("Subject Code *", self.code_var)
        fb.entry("Subject Name *", self.name_var)
        fb.combo("Subject Type *", self.type_var, ["Optional", "Compulsory", "Elective", "Vocational"])
        self.class_combo = fb.combo("Class / Level", self.class_var, [], searchable=True)
        fb.combo("Status", self.status_var, ["Active", "Inactive"])
        fb.entry("Remarks", self.remarks_var)

        form.columnconfigure(1, weight=1)
        actions = ttk.Frame(form, style="Form.TFrame")
        actions.grid(row=0, column=2, rowspan=6, padx=12, sticky="n")

        ttk.Button(actions, text="Save Subject", style="Accent.TButton", command=self.save).pack(fill="x", pady=2)
        ttk.Button(actions, text="Update", command=self.update_record).pack(fill="x", pady=2)
        ttk.Button(actions, text="Delete", style="Danger.TButton", command=self.delete_record).pack(fill="x", pady=2)
        ttk.Button(actions, text="Clear Form", command=self.clear).pack(fill="x", pady=2)

        # Filter & Action bar
        bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 4))
        bar.pack(fill="x", pady=(2, 6))

        ttk.Label(bar, text="Filter Type:").pack(side="left", padx=(0, 4))
        self.filter_type = tk.StringVar(value="All")
        type_cb = ttk.Combobox(bar, textvariable=self.filter_type, values=["All", "Optional", "Compulsory", "Elective", "Vocational"], state="readonly", width=12)
        type_cb.pack(side="left", padx=4)
        type_cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Label(bar, text="Status:").pack(side="left", padx=(8, 4))
        self.filter_status = tk.StringVar(value="All")
        status_cb = ttk.Combobox(bar, textvariable=self.filter_status, values=["All", "Active", "Inactive"], state="readonly", width=10)
        status_cb.pack(side="left", padx=4)
        status_cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Button(bar, text="👥 Batch Assign to Students…", style="Accent.TButton", command=self.open_batch_assign_dialog).pack(side="right", padx=4)

        # Treeview
        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(area, [
            ("id", "ID", 50),
            ("code", "Code", 100),
            ("name", "Subject Name", 220),
            ("type", "Type", 120),
            ("class", "Class / Level", 120),
            ("status", "Status", 90),
            ("remarks", "Remarks", 200),
        ])
        self.tree.bind("<Double-1>", self.on_double_click)

    def _load_classes(self) -> None:
        rows = self.db.query("SELECT id, level_name FROM class_levels WHERE status='Active' ORDER BY level_name")
        self.class_map = {r["level_name"]: int(r["id"]) for r in rows}
        self.reverse_class_map = {int(r["id"]): r["level_name"] for r in rows}
        names = [""] + list(self.class_map.keys())
        self.class_combo.configure(values=names)

    def values(self) -> Subject:
        code = self.code_var.get().strip().upper()
        name = self.name_var.get().strip()
        if not code or not name:
            raise ValueError("Subject Code and Subject Name are required.")
        class_name = self.class_var.get().strip() or None
        class_id = self.class_map.get(class_name) if class_name else None

        return Subject(
            id=self.selected_id,
            subject_code=code,
            subject_name=name,
            subject_type=self.type_var.get(),
            class_level_id=class_id,
            class_name=class_name,
            status=self.status_var.get(),
            remarks=self.remarks_var.get().strip(),
        )

    def save(self) -> None:
        try:
            sub = self.values()
            self.app.services.subjects.create(sub)
            self.clear()
            self.app.refresh_all()
            messagebox.showinfo("Success", f"Subject '{sub.subject_name}' created successfully.", parent=self)
        except Exception as exc:
            self.show_error(exc)

    def update_record(self) -> None:
        if not self.selected_id:
            messagebox.showwarning("Warning", "Select a subject from the list to update.", parent=self)
            return
        try:
            sub = self.values()
            self.app.services.subjects.update(sub)
            self.clear()
            self.app.refresh_all()
            messagebox.showinfo("Success", "Subject updated successfully.", parent=self)
        except Exception as exc:
            self.show_error(exc)

    def delete_record(self) -> None:
        if not self.selected_id:
            messagebox.showwarning("Warning", "Select a subject from the list to delete.", parent=self)
            return
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this subject? Student assignments linked to it will be removed.", parent=self):
            return
        try:
            self.app.services.subjects.delete(self.selected_id)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def clear(self) -> None:
        self.selected_id = None
        self.code_var.set("")
        self.name_var.set("")
        self.type_var.set("Optional")
        self.class_var.set("")
        self.status_var.set("Active")
        self.remarks_var.set("")

    def on_double_click(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row_id = int(self.tree.item(selected[0], "values")[0])
        sub = self.app.services.subjects.get(row_id)
        if not sub:
            return
        self.selected_id = sub.id
        self.code_var.set(sub.subject_code)
        self.name_var.set(sub.subject_name)
        self.type_var.set(sub.subject_type or "Optional")
        self.class_var.set(sub.class_name or (self.reverse_class_map.get(sub.class_level_id) if sub.class_level_id else "") or "")
        self.status_var.set(sub.status or "Active")
        self.remarks_var.set(sub.remarks or "")

    def refresh(self) -> None:
        self._load_classes()
        self.clear_tree(self.tree)
        f_type = None if self.filter_type.get() == "All" else self.filter_type.get()
        f_status = None if self.filter_status.get() == "All" else self.filter_status.get()

        rows = self.app.services.subjects.list_subjects(status=f_status, subject_type=f_type)
        for s in rows:
            c_name = s.class_name or (self.reverse_class_map.get(s.class_level_id) if s.class_level_id else "") or "-"
            self.tree.insert(
                "",
                "end",
                values=(s.id, s.subject_code, s.subject_name, s.subject_type, c_name, s.status, s.remarks),
            )

    def open_batch_assign_dialog(self) -> None:
        """Open a dialog to batch assign an elective subject to students."""
        dlg = tk.Toplevel(self)
        dlg.title("Batch Assign Subject to Students")
        dlg.minsize(580, 500)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=14)
        frame.pack(fill="both", expand=True)

        subjects = self.app.services.subjects.list_subjects(status="Active")
        if not subjects:
            messagebox.showwarning("No Subjects", "No active subjects available.", parent=dlg)
            dlg.destroy()
            return

        subj_map = {f"{s.subject_name} ({s.subject_code})": s.id for s in subjects}

        subj_var = tk.StringVar(value=list(subj_map.keys())[0])
        type_var = tk.StringVar(value="Optional")
        class_filter_var = tk.StringVar(value="All")

        top_form = ttk.Frame(frame)
        top_form.pack(fill="x", pady=(0, 10))

        ttk.Label(top_form, text="Subject to Assign:").grid(row=0, column=0, sticky="w", pady=3)
        subj_combo = ttk.Combobox(top_form, textvariable=subj_var, values=list(subj_map.keys()), state="readonly", width=32)
        subj_combo.grid(row=0, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(top_form, text="Enrollment Type:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(top_form, textvariable=type_var, values=["Optional", "Compulsory", "Elective", "Vocational"], state="readonly", width=20).grid(row=1, column=1, sticky="w", padx=6, pady=3)

        classes = ["All"] + list(self.class_map.keys())
        ttk.Label(top_form, text="Filter by Class:").grid(row=2, column=0, sticky="w", pady=3)
        class_cb = ttk.Combobox(top_form, textvariable=class_filter_var, values=classes, state="readonly", width=20)
        class_cb.grid(row=2, column=1, sticky="w", padx=6, pady=3)

        # Student Selection Treeview
        st_frame = ttk.LabelFrame(frame, text="Select Students", padding=8)
        st_frame.pack(fill="both", expand=True, pady=6)

        st_tree = ttk.Treeview(st_frame, columns=("id", "name", "class", "contact"), show="headings", selectmode="extended")
        st_tree.heading("id", text="ID")
        st_tree.heading("name", text="Student Name")
        st_tree.heading("class", text="Class / Level")
        st_tree.heading("contact", text="Contact")
        st_tree.column("id", width=50)
        st_tree.column("name", width=200)
        st_tree.column("class", width=100)
        st_tree.column("contact", width=120)

        s_scroll = ttk.Scrollbar(st_frame, orient="vertical", command=st_tree.yview)
        st_tree.configure(yscrollcommand=s_scroll.set)
        st_tree.pack(side="left", fill="both", expand=True)
        s_scroll.pack(side="right", fill="y")

        def populate_students():
            for item in st_tree.get_children():
                st_tree.delete(item)
            c_sel = class_filter_var.get()
            if c_sel == "All":
                rows = self.db.query("SELECT id, student_name, class_name, contact FROM students WHERE status='Active' ORDER BY student_name")
            else:
                rows = self.db.query("SELECT id, student_name, class_name, contact FROM students WHERE status='Active' AND class_name=? ORDER BY student_name", (c_sel,))
            for r in rows:
                st_tree.insert("", "end", values=(r["id"], r["student_name"], r["class_name"] or "-", r["contact"] or "-"))

        class_cb.bind("<<ComboboxSelected>>", lambda _e: populate_students())
        populate_students()

        sel_all_btn = ttk.Button(st_frame, text="Select All", command=lambda: st_tree.selection_set(st_tree.get_children()))
        sel_all_btn.pack(anchor="w", pady=(4, 0))

        # Action Buttons
        btn_bar = ttk.Frame(frame)
        btn_bar.pack(fill="x", pady=(8, 0))

        def do_assign():
            selected = st_tree.selection()
            if not selected:
                messagebox.showwarning("No Students Selected", "Please select at least one student from the list.", parent=dlg)
                return
            s_id = subj_map.get(subj_var.get())
            if not s_id:
                return
            student_ids = [int(st_tree.item(item, "values")[0]) for item in selected]
            e_type = type_var.get()

            count = self.app.services.subjects.batch_assign(
                student_ids=student_ids,
                subject_id=s_id,
                enrollment_type=e_type,
            )
            messagebox.showinfo("Assignment Complete", f"Successfully assigned subject to {count} student(s).", parent=dlg)
            dlg.destroy()

        ttk.Button(btn_bar, text="Cancel", command=dlg.destroy).pack(side="right", padx=4)
        ttk.Button(btn_bar, text="Assign to Selected Students", style="Accent.TButton", command=do_assign).pack(side="right", padx=4)
