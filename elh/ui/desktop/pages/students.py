from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from elh.models import Student
from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import normalize_phone, today_iso
from elh.ui.desktop.pages.attendance_selection import (
    attendance_user_choices,
    selected_attendance_device,
)
from elh.ui.desktop.pages.import_templates import ImportTemplateMixin


class StudentsPage(CrudPage, ImportTemplateMixin):
    """Fast student entry with optional identity, device, and photo details."""

    IMPORT_HEADERS = [
        "Student Name",
        "Class",
        "School ID",
        "School",
        "Contact",
        "Gender",
        "Date of Birth",
        "Parent",
        "Guardian Relationship",
        "Joining Date",
        "Address",
        "Status",
        "Remarks",
    ]
    GUARDIAN_RELATIONSHIPS = ("Son of Mr.", "Daughter of Mr.", "Child of")
    MAX_SOURCE_PHOTO_BYTES = 10 * 1024 * 1024

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id: int | None = None
        self.attendance_user_map: dict[str, str] = {}
        self.school_map: dict[str, int] = {}
        self.school_names: dict[int, str] = {}

        ttk.Label(self, text="Student Records", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Save the essential details first; identity, attendance, and photo can be added later.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 3))

        form = self.create_form_dialog("Student Details", padding=8)
        form.pack(fill="both", expand=True, pady=8)
        self.vars = self._variables()
        self.new_photo = self._photo_state()
        self.new_notebook, self.school_combo, self.attendance_combo = self._build_form(
            form,
            self.vars,
            [],
            {},
            self.new_photo,
        )
        actions = ttk.Frame(form, style="Form.TFrame")
        actions.grid(row=1, column=0, sticky="e", padx=10, pady=(4, 8))
        ttk.Button(
            actions,
            text="Save Student",
            style="Accent.TButton",
            command=self.save,
        ).pack(side="right")
        ttk.Label(
            actions,
            text="Only name and joining date are required.",
            style="Hint.TLabel",
        ).pack(side="right", padx=12)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(0, weight=1)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 55),
                ("name", "Student Name", 180),
                ("gender", "Gender", 75),
                ("class", "Class", 70),
                ("school", "School", 130),
                ("contact", "Contact", 110),
                ("parent", "Parent / Guardian", 160),
                ("date", "Joining Date", 100),
                ("photo", "Photo", 65),
                ("attendance", "Attendance User", 180),
                ("status", "Status", 80),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.open_editor)
        ttk.Button(
            self.page_toolbar,
            text="Send SMS...",
            command=self.open_sms_dialog,
        ).pack(side="left", padx=4)
        self.add_toolbar_menu("More actions", [
            ("Import CSV…", self.import_csv),
            ("Download import template…", lambda: self.download_csv_template(
                "students_import_template.csv", self.IMPORT_HEADERS,
                "Use an existing School ID or exact School name. Gender, Date of Birth, "
                "guardian details, and all other non-required fields may be blank. "
                "Dates use Nepali YYYY/MM/DD. Photos are added from the student editor.",
            )),
            ("Export CSV…", self.export_csv),
            ("", None),
            ("Delete selected student", self.delete),
        ])

    @staticmethod
    def _variables(values: dict[str, str] | None = None) -> dict[str, tk.StringVar]:
        defaults = {
            "name": "",
            "class": "",
            "school": "",
            "contact": "",
            "gender": "",
            "dob": "",
            "parent": "",
            "relationship": "",
            "date": today_iso(),
            "attendance": "",
            "address": "",
            "status": "Active",
            "remarks": "",
        }
        defaults.update(values or {})
        return {key: tk.StringVar(value=value or "") for key, value in defaults.items()}

    @staticmethod
    def _photo_state(data: bytes | None = None, mime_type: str = "") -> dict:
        return {"data": bytes(data) if data else None, "mime_type": mime_type or ""}

    def _build_form(
        self,
        container,
        variables: dict[str, tk.StringVar],
        schools,
        attendance_map: dict[str, str],
        photo_state: dict,
    ):
        notebook = ttk.Notebook(container)
        notebook.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        quick = ttk.Frame(notebook, padding=12, style="Form.TFrame")
        optional = ttk.Frame(notebook, padding=12, style="Form.TFrame")
        notebook.add(quick, text="Quick Entry")
        notebook.add(optional, text="Additional Details & Photo")

        quick_form = FormBuilder(quick)
        quick_form.entry("Student Name *", variables["name"], width=38)
        quick_form.entry("Class", variables["class"], width=38)
        school_combo = quick_form.combo(
            "School", variables["school"], schools, state="normal", searchable=True, width=36
        )
        quick_form.entry("Contact", variables["contact"], width=38)
        quick_form.entry("Joining Date *", variables["date"], width=38)
        quick_form.combo("Status", variables["status"], ["Active", "Inactive"])
        quick.columnconfigure(1, weight=1)

        details = FormBuilder(optional)
        gender_combo = details.combo(
            "Gender", variables["gender"], list(self.app.services.students.GENDERS)
        )
        gender_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._suggest_relationship(variables),
            add="+",
        )
        details.entry("Date of Birth", variables["dob"], width=34)
        details.entry("Parent / Guardian Name", variables["parent"], width=34)
        details.combo(
            "Guardian Relationship",
            variables["relationship"],
            self.GUARDIAN_RELATIONSHIPS,
            state="normal",
            width=32,
        )
        attendance_combo = details.combo(
            "Attendance Device User",
            variables["attendance"],
            list(attendance_map),
            searchable=True,
            width=32,
        )
        details.entry("Address", variables["address"], width=34)
        details.entry("Remarks", variables["remarks"], width=34)
        optional.columnconfigure(1, weight=1)
        self._add_photo_card(optional, details.row, photo_state)
        return notebook, school_combo, attendance_combo

    def _suggest_relationship(self, variables: dict[str, tk.StringVar]) -> None:
        if variables["relationship"].get().strip():
            return
        defaults = {
            "Male": "Son of Mr.",
            "Female": "Daughter of Mr.",
            "Other": "Child of",
        }
        variables["relationship"].set(defaults.get(variables["gender"].get(), ""))

    def _add_photo_card(self, parent, row: int, state: dict) -> None:
        card = ttk.LabelFrame(parent, text="Student Photo (optional)", padding=10)
        card.grid(row=0, column=2, rowspan=max(1, row), sticky="n", padx=(18, 4), pady=2)
        preview = tk.Label(
            card,
            width=15,
            height=7,
            background="#FFFFFF",
            foreground="#64748B",
            relief="solid",
            borderwidth=1,
            text="No photo",
        )
        preview.pack(padx=3, pady=(2, 7))
        status = tk.StringVar(value="Can be added later")
        state["preview"] = preview
        state["status"] = status
        ttk.Label(card, textvariable=status, style="Hint.TLabel", wraplength=150).pack(pady=(0, 6))
        ttk.Button(
            card,
            text="Choose Image",
            command=lambda: self._choose_photo(state, preview, status, parent),
        ).pack(fill="x", pady=2)
        ttk.Button(
            card,
            text="Remove",
            command=lambda: self._clear_photo(state, preview, status),
        ).pack(fill="x", pady=2)
        self._show_photo(state, preview, status)

    def _choose_photo(self, state: dict, preview, status, parent) -> None:
        path = filedialog.askopenfilename(
            parent=parent.winfo_toplevel(),
            title="Select Student Photo",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            if len(raw) > self.MAX_SOURCE_PHOTO_BYTES:
                raise ValueError("Select an image smaller than 10 MB.")
            with Image.open(BytesIO(raw)) as image:
                image.load()
                if image.width * image.height > 40_000_000:
                    raise ValueError("The image dimensions are too large.")
                image = ImageOps.exif_transpose(image)
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                if image.mode != "RGB":
                    background = Image.new("RGB", image.size, "white")
                    if "A" in image.getbands():
                        background.paste(image, mask=image.getchannel("A"))
                    else:
                        background.paste(image.convert("RGB"))
                    image = background
                output = BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
            data = output.getvalue()
            if len(data) > self.app.services.students.MAX_PHOTO_BYTES:
                raise ValueError("The processed student photo is too large.")
            state.update(data=data, mime_type="image/jpeg")
            self._show_photo(state, preview, status)
        except Exception as exc:
            messagebox.showerror("Photo Error", str(exc), parent=parent.winfo_toplevel())

    @staticmethod
    def _clear_photo(state: dict, preview, status) -> None:
        state.update(data=None, mime_type="")
        preview.configure(image="", text="No photo", width=15, height=7)
        preview.image = None
        status.set("Can be added later")

    @staticmethod
    def _show_photo(state: dict, preview, status) -> None:
        data = state.get("data")
        if not data:
            preview.configure(image="", text="No photo", width=15, height=7)
            preview.image = None
            status.set("Can be added later")
            return
        try:
            with Image.open(BytesIO(data)) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((105, 115), Image.Resampling.LANCZOS)
                rendered = ImageTk.PhotoImage(image)
            preview.configure(image=rendered, text="", width=105, height=115)
            preview.image = rendered
            status.set("Photo ready")
        except Exception:
            preview.configure(image="", text="Photo unavailable", width=15, height=7)
            preview.image = None
            status.set("Choose another image")

    def _student_from_form(
        self,
        variables: dict[str, tk.StringVar],
        photo_state: dict,
        student_id: int | None = None,
    ) -> Student:
        school_name = variables["school"].get().strip()
        school_id = self.school_map.get(school_name) if school_name else None
        if school_name and school_id is None:
            raise ValueError("Select an existing school from the list.")
        return Student(
            id=student_id,
            name=variables["name"].get(),
            class_name=variables["class"].get().strip(),
            school_id=school_id,
            school_name=self.school_names.get(school_id, "") if school_id else "",
            contact=variables["contact"].get(),
            gender=variables["gender"].get(),
            date_of_birth=variables["dob"].get(),
            parent_name=variables["parent"].get(),
            guardian_relationship=variables["relationship"].get(),
            joining_date=variables["date"].get(),
            photo_data=photo_state.get("data"),
            photo_mime_type=photo_state.get("mime_type", ""),
            address=variables["address"].get().strip(),
            status=variables["status"].get() or "Active",
            remarks=variables["remarks"].get().strip(),
        )

    def save(self) -> None:
        try:
            student = self._student_from_form(self.vars, self.new_photo)
            device_user_id = selected_attendance_device(
                self.vars["attendance"].get(), self.attendance_user_map
            )
            student_id = self.app.services.students.register(student)
            self.app.services.attendance.assign_person_device(
                "student", student_id, device_user_id
            )
            self.hide_form_dialog()
            self.clear()
            self.app.refresh_all()
            messagebox.showinfo(
                "Saved",
                "Student saved. Additional details and photo can be added later by double-clicking the record.",
                parent=self,
            )
        except Exception as exc:
            self.show_error(exc)

    def delete(self) -> None:
        if not self.selected_id or not self.confirm_delete():
            return
        try:
            self.app.services.students.delete(self.selected_id)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(
                ValueError(
                    "This student has related records and cannot be deleted."
                    if "foreign" in str(exc).lower() or "constraint" in str(exc).lower()
                    else str(exc)
                )
            )

    def clear(self) -> None:
        self.selected_id = None
        for variable in self.vars.values():
            variable.set("")
        self.vars["date"].set(today_iso())
        self.vars["status"].set("Active")
        preview = self.new_photo.get("preview")
        photo_status = self.new_photo.get("status")
        if preview is not None and photo_status is not None and preview.winfo_exists():
            self._clear_photo(self.new_photo, preview, photo_status)
        else:
            self.new_photo.update(data=None, mime_type="")
        if getattr(self, "new_notebook", None):
            self.new_notebook.select(0)
        if getattr(self, "tree", None):
            self.tree.selection_remove(self.tree.selection())

    def on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        self.selected_id = int(self.tree.item(selected[0], "values")[0]) if selected else None

    def open_editor(self, _event=None) -> None:
        if not self.selected_id:
            messagebox.showwarning("Select", "Select a student first.", parent=self)
            return
        student = self.app.services.students.get(self.selected_id)
        if not student:
            self.show_error(ValueError("Student record was not found."))
            return
        attendance_map, current_attendance = attendance_user_choices(
            self.app, "student", self.selected_id
        )
        variables = self._variables(
            {
                "name": student.name,
                "class": student.class_name,
                "school": next(
                    (label for label, value in self.school_map.items() if value == student.school_id),
                    "",
                ),
                "contact": student.contact,
                "gender": student.gender,
                "dob": student.date_of_birth,
                "parent": student.parent_name,
                "relationship": student.guardian_relationship,
                "date": student.joining_date,
                "attendance": current_attendance,
                "address": student.address,
                "status": student.status,
                "remarks": student.remarks,
            }
        )
        photo_state = self._photo_state(student.photo_data, student.photo_mime_type)
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Student - {student.name}")
        dialog.configure(background="#EEF3F8")
        dialog.transient(self.winfo_toplevel())
        dialog.minsize(690, 480)
        frame = ttk.Frame(dialog, padding=12, style="Form.TFrame")
        frame.pack(fill="both", expand=True)
        notebook, _school_combo, _attendance_combo = self._build_form(
            frame,
            variables,
            list(self.school_map),
            attendance_map,
            photo_state,
        )
        actions = ttk.Frame(frame, style="Form.TFrame")
        actions.grid(row=1, column=0, sticky="e", pady=(8, 2))

        def save_changes():
            try:
                updated = self._student_from_form(
                    variables, photo_state, self.selected_id
                )
                device_user_id = selected_attendance_device(
                    variables["attendance"].get(), attendance_map
                )
                self.app.services.students.update(updated)
                self.app.services.attendance.assign_person_device(
                    "student", self.selected_id, device_user_id
                )
                dialog.destroy()
                self.clear()
                self.app.refresh_all()
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=dialog)

        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right", padx=3)
        ttk.Button(
            actions,
            text="Save Changes",
            style="Accent.TButton",
            command=save_changes,
        ).pack(side="right", padx=3)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        dialog.update_idletasks()
        width = max(720, dialog.winfo_reqwidth() + 25)
        height = max(500, dialog.winfo_reqheight() + 25)
        x = max(0, (dialog.winfo_screenwidth() - width) // 2)
        y = max(0, (dialog.winfo_screenheight() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        notebook.select(0)

    def open_sms_dialog(self) -> None:
        if not self.selected_id:
            messagebox.showwarning(
                "Send SMS", "Select a student from the list first.", parent=self
            )
            return
        try:
            history = self.app.services.notifications.student_event_history(
                self.selected_id
            )
        except Exception as exc:
            self.show_error(exc)
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Send Student Event SMS - {history['student_name']}")
        dialog.configure(background="#EEF3F8")
        dialog.transient(self.winfo_toplevel())
        dialog.minsize(760, 480)
        shell = ttk.Frame(dialog, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(
            shell,
            text=f"Send SMS for {history['student_name']}",
            style="SubTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            shell,
            text="Select one or more recorded events. Manual sends use the current templates "
            "even when automatic notifications are disabled.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        recipient_row = ttk.Frame(shell)
        recipient_row.pack(fill="x", pady=(0, 8))
        ttk.Label(recipient_row, text="Mobile Number").pack(side="left")
        recipient = tk.StringVar(value=str(history["contact"] or ""))
        ttk.Entry(recipient_row, textvariable=recipient, width=22).pack(
            side="left", padx=8
        )
        ttk.Label(
            recipient_row,
            text="This override is used only for this send. Ctrl/Shift selects several events.",
            style="Hint.TLabel",
        ).pack(side="left")

        table = ttk.Frame(shell)
        table.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            table,
            columns=("event", "reference", "date", "details"),
            show="headings",
            selectmode="extended",
        )
        for key, heading, width in (
            ("event", "Event", 145),
            ("reference", "Reference", 200),
            ("date", "Date", 100),
            ("details", "Details", 270),
        ):
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        event_map: dict[str, tuple[str, int]] = {}
        for index, event in enumerate(history["events"]):
            iid = f"event-{index}"
            event_map[iid] = (str(event["event_key"]), int(event["source_id"]))
            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    event["event_name"],
                    event["reference"],
                    event["event_date"],
                    event["details"],
                ),
            )

        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions,
            text="Select All",
            command=lambda: tree.selection_set(tree.get_children()),
        ).pack(side="left")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(
            side="right", padx=3
        )

        def send_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showwarning(
                    "Send SMS", "Select at least one event.", parent=dialog
                )
                return
            try:
                log_ids = self.app.services.notifications.queue_student_events(
                    self.selected_id,
                    [event_map[iid] for iid in selected],
                    recipient.get(),
                )
                dialog.destroy()
                messagebox.showinfo(
                    "SMS Queued",
                    f"Queued {len(log_ids)} SMS message(s). Delivery results are available "
                    "under System Admin > SMS & Notifications.",
                    parent=self,
                )
            except Exception as exc:
                messagebox.showerror("Send SMS", str(exc), parent=dialog)

        ttk.Button(
            actions,
            text="Queue Selected SMS",
            style="Accent.TButton",
            command=send_selected,
        ).pack(side="right", padx=3)
        dialog.update_idletasks()
        width = max(800, dialog.winfo_reqwidth() + 20)
        height = max(500, dialog.winfo_reqheight() + 20)
        x = max(0, (dialog.winfo_screenwidth() - width) // 2)
        y = max(0, (dialog.winfo_screenheight() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()

    def refresh(self) -> None:
        schools = self.db.query(
            "SELECT id,school_name FROM schools WHERE status='Active' ORDER BY school_name"
        )
        self.school_names = {int(row["id"]): row["school_name"] for row in schools}
        self.school_map = {
            f"{row['school_name']} (ID: {row['id']})": int(row["id"])
            for row in schools
        }
        self.school_combo.set_values(self.school_map)
        self.attendance_user_map, _current = attendance_user_choices(self.app, "student")
        self.attendance_combo.set_values(self.attendance_user_map)
        self.clear_tree(self.tree)
        rows = self.db.query(
            """
            SELECT s.id,s.student_name,s.class_name,s.contact,s.gender,s.parent_name,
                   s.joining_date,s.status,s.photo_mime_type,sc.school_name,
                   m.device_user_id,u.device_name
            FROM students s
            LEFT JOIN schools sc ON sc.id=s.school_id
            LEFT JOIN (
                SELECT person_id,MIN(id) mapping_id FROM device_user_mappings
                WHERE person_type='student' AND status='Active' GROUP BY person_id
            ) selected_mapping ON selected_mapping.person_id=s.id
            LEFT JOIN device_user_mappings m ON m.id=selected_mapping.mapping_id
            LEFT JOIN attendance_device_users u ON u.device_user_id=m.device_user_id
            ORDER BY s.student_name
            """
        )
        for row in rows:
            attendance_user = ""
            if row["device_user_id"]:
                attendance_user = f"{row['device_user_id']} - {row['device_name'] or 'Unnamed'}"
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["student_name"],
                    row["gender"] or "",
                    row["class_name"] or "",
                    row["school_name"] or "",
                    row["contact"] or "",
                    row["parent_name"] or "",
                    row["joining_date"],
                    "Yes" if row["photo_mime_type"] else "",
                    attendance_user,
                    row["status"],
                ),
            )

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Students",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        rows = self.db.query(
            "SELECT s.id,s.student_name,s.class_name,s.school_id,s.contact,s.gender," 
            "s.date_of_birth,s.parent_name,s.guardian_relationship,s.joining_date," 
            "s.address,s.status,s.remarks,sc.school_name " 
            "FROM students s LEFT JOIN schools sc ON sc.id=s.school_id " 
            "ORDER BY s.student_name"
        )
        with open(path, "w", newline="", encoding="utf-8-sig") as target:
            writer = csv.writer(target)
            writer.writerow(["ID", *self.IMPORT_HEADERS])
            for row in rows:
                writer.writerow(
                    [
                        row["id"], row["student_name"], row["class_name"] or "",
                        row["school_id"] or "", row["school_name"] or "",
                        row["contact"] or "", row["gender"] or "",
                        row["date_of_birth"] or "", row["parent_name"] or "",
                        row["guardian_relationship"] or "", row["joining_date"],
                        row["address"] or "", row["status"], row["remarks"] or "",
                    ]
                )
        messagebox.showinfo("Exported", f"Saved to:\n{path}", parent=self)

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Import Students",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            schools = self.db.query("SELECT id,school_name FROM schools")
            schools_by_id = {int(row["id"]): row for row in schools}
            schools_by_name = {row["school_name"]: row for row in schools}
            students: list[Student] = []
            with open(path, newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                self.require_headers(reader, ["Student Name", "Joining Date"])
                for row in reader:
                    school_id_text = (row.get("School ID") or "").strip()
                    school_name = (row.get("School") or "").strip()
                    school = None
                    if school_id_text:
                        try:
                            school = schools_by_id.get(int(school_id_text))
                        except ValueError as exc:
                            raise ValueError(
                                f"Invalid School ID for {row.get('Student Name', '')}."
                            ) from exc
                    elif school_name:
                        school = schools_by_name.get(school_name)
                    if (school_id_text or school_name) and not school:
                        raise ValueError(
                            f"Unknown school for {row.get('Student Name', '')}: use an existing "
                            "School ID or exact School name."
                        )
                    students.append(
                        Student(
                            id=None,
                            name=(row.get("Student Name") or "").strip(),
                            class_name=(row.get("Class") or "").strip(),
                            school_id=int(school["id"]) if school else None,
                            contact=normalize_phone(row.get("Contact") or ""),
                            gender=(row.get("Gender") or "").strip(),
                            date_of_birth=(row.get("Date of Birth") or "").strip(),
                            parent_name=(row.get("Parent") or "").strip(),
                            guardian_relationship=(
                                row.get("Guardian Relationship") or ""
                            ).strip(),
                            joining_date=(row.get("Joining Date") or "").strip(),
                            address=(row.get("Address") or "").strip(),
                            status=(row.get("Status") or "Active").strip(),
                            remarks=(row.get("Remarks") or "").strip(),
                        )
                    )
            count = self.app.services.students.register_many(students)
            self.app.refresh_all()
            messagebox.showinfo("Imported", f"Imported {count} students.", parent=self)
        except Exception as exc:
            self.show_error(exc)
