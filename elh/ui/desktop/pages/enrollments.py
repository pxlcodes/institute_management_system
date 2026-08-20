from __future__ import annotations

import csv
import sqlite3
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Iterable, Optional

from elh.models import Student
from elh.ui.desktop.helpers import money, normalize_phone, parse_amount, today_iso, validate_date
from elh.ui.desktop.components import BasePage, CrudPage, FormBuilder, ScrollableFrame
from elh.ui.desktop.pages.import_templates import ImportTemplateMixin

# Enrollment
# ---------------------------------------------------------------------------

class EnrollmentsPage(CrudPage,ImportTemplateMixin):
    IMPORT_HEADERS=["Student ID","Student Name","Course","Level","Start Date","End Date","Monthly Fee","Admission Fee","Discount","Status","Remarks"]
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.selected_id = None
        self.student_map: dict[str, int] = {}
        self.course_map: dict[str, tuple[int, str]] = {}

        ttk.Label(self, text="Enrollment Details", style="Title.TLabel").pack(anchor="w")
        form = self.create_form_dialog("Enrollment", padding=8)
        form.pack(fill="x", pady=8)

        self.vars = {
            "student": tk.StringVar(),
            "course": tk.StringVar(),
            "level": tk.StringVar(),
            "start": tk.StringVar(value=today_iso()),
            "end": tk.StringVar(),
            "monthly": tk.StringVar(value="0"),
            "admission": tk.StringVar(value="0"),
            "discount": tk.StringVar(value="0"),
            "status": tk.StringVar(value="Active"),
            "remarks": tk.StringVar(),
        }
        fb = FormBuilder(form)
        self.student_combo = fb.combo(
            "Student *", self.vars["student"], [], searchable=True
        )
        self.course_combo = fb.combo(
            "Course *", self.vars["course"], [], searchable=True
        )
        fb.entry("Level / Class", self.vars["level"])
        fb.entry("Start Date *", self.vars["start"])
        fb.entry("End Date", self.vars["end"])
        fb.entry("Monthly Fee", self.vars["monthly"])
        fb.entry("Admission Fee", self.vars["admission"])
        fb.entry("Discount", self.vars["discount"])
        fb.combo("Status", self.vars["status"], ["Active", "Completed", "Cancelled"])
        fb.entry("Remarks", self.vars["remarks"])
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form, style="Form.TFrame")
        buttons.grid(row=0, column=2, rowspan=10, padx=15, sticky="n")
        ttk.Button(buttons, text="Save Enrollment", style="Accent.TButton", command=self.save).pack(fill="x", pady=3)

        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("student", "Student", 170), ("course", "Course", 150),
                ("level", "Level", 80), ("start", "Start Date", 100),
                ("end", "End Date", 100), ("fee", "Monthly Fee", 100),
                ("status", "Status", 90),
            ],
        )
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.open_editor)
        ttk.Button(
            self.page_toolbar,
            text="Enroll Students With Attendance",
            style="Accent.TButton",
            command=self.open_present_students_enrollment,
        ).pack(side="left", padx=4)
        self.add_toolbar_menu("More actions", [
            ("Import CSV…", self.import_csv),
            ("Download import template…", lambda: self.download_csv_template("enrollments_import_template.csv", self.IMPORT_HEADERS, "Student ID must exist. Course must exactly match an existing course. Dates: Nepali YYYY/MM/DD.")),
            ("Export CSV…", self.export_csv),
            ("", None),
            ("Delete selected enrollment", self.delete),
        ])

    def load_students(self):
        rows = self.db.query("SELECT id, student_name FROM students ORDER BY student_name")
        self.student_map = {f"{r['id']} - {r['student_name']}": r["id"] for r in rows}
        self.student_combo["values"] = list(self.student_map)
        courses=self.db.query("SELECT id,course_name,category FROM courses WHERE status='Active' ORDER BY category,course_name")
        self.course_map={f"{r['course_name']} [{r['category']}]":(r["id"],r["course_name"]) for r in courses}
        self.course_combo["values"]=list(self.course_map)

    def values(self):
        student_id = self.student_map.get(self.vars["student"].get())
        if not student_id:
            raise ValueError("Please select a student.")
        course_data = self.course_map.get(self.vars["course"].get())
        if not course_data: raise ValueError("Please select a course.")
        return (
            student_id,
            course_data[0],
            self.vars["level"].get().strip(),
            validate_date(self.vars["start"].get(), "Start date"),
            validate_date(self.vars["end"].get(), "End date", allow_blank=True),
            parse_amount(self.vars["monthly"].get() or "0", "Monthly fee"),
            parse_amount(self.vars["admission"].get() or "0", "Admission fee"),
            parse_amount(self.vars["discount"].get() or "0", "Discount"),
            self.vars["status"].get(),
            self.vars["remarks"].get().strip(),
        )

    def save(self):
        try:
            vals = self.values()
            self.app.services.enrollments.create(*vals)
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def update(self):
        if not self.selected_id:
            messagebox.showwarning("Select", "Select an enrollment first.", parent=self)
            return
        try:
            self.app.services.enrollments.update(self.selected_id, *self.values())
            self.clear()
            self.app.refresh_all()
        except Exception as exc:
            self.show_error(exc)

    def delete(self):
        if self.selected_id and self.confirm_delete():
            try:
                self.app.services.enrollments.delete(self.selected_id)
                self.clear()
                self.app.refresh_all()
            except sqlite3.IntegrityError:
                self.show_error(ValueError("This enrollment has transactions and cannot be deleted."))

    def clear(self):
        self.selected_id = None
        for var in self.vars.values():
            var.set("")
        self.vars["start"].set(today_iso())
        self.vars["monthly"].set("0")
        self.vars["admission"].set("0")
        self.vars["discount"].set("0")
        self.vars["status"].set("Active")

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        row_id = int(self.tree.item(selected[0], "values")[0])
        row = self.db.query_one(
            """
            SELECT e.*, s.student_name,c.course_name
            FROM enrollments e JOIN students s ON s.id=e.student_id
            JOIN courses c ON c.id=e.course_id
            WHERE e.id=?
            """,
            (row_id,),
        )
        if not row:
            return
        self.selected_id = row_id
        self.vars["student"].set(f"{row['student_id']} - {row['student_name']}")
        display=next((key for key,value in self.course_map.items() if value[0]==row["course_id"]),row["course_name"])
        self.vars["course"].set(display)
        self.vars["level"].set(row["level"] or "")
        self.vars["start"].set(row["start_date"])
        self.vars["end"].set(row["end_date"] or "")
        self.vars["monthly"].set(str(row["monthly_fee"]))
        self.vars["admission"].set(str(row["admission_fee"]))
        self.vars["discount"].set(str(row["discount"]))
        self.vars["status"].set(row["status"])
        self.vars["remarks"].set(row["remarks"] or "")

    def refresh(self):
        self.load_students()
        self.clear_tree(self.tree)
        rows = self.db.query(
            """
            SELECT e.*, s.student_name,c.course_name
            FROM enrollments e JOIN students s ON s.id=e.student_id
            JOIN courses c ON c.id=e.course_id
            ORDER BY e.start_date DESC, s.student_name
            """
        )
        for r in rows:
            self.tree.insert(
                "", "end",
                values=(r["id"], r["student_name"], r["course_name"], r["level"],
                        r["start_date"], r["end_date"], money(r["monthly_fee"]), r["status"])
            )

    def open_editor(self,_event=None):
        if not self.selected_id:
            messagebox.showwarning("Select","Select an enrollment first.",parent=self);return
        row=self.db.query_one("SELECT e.*,s.student_name,c.course_name FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id WHERE e.id=?",(self.selected_id,))
        dialog=tk.Toplevel(self);dialog.title("Edit Enrollment");dialog.transient(self.winfo_toplevel());dialog.grab_set();form=ttk.Frame(dialog,padding=12,style="Form.TFrame");form.pack()
        course_display=next((k for k,v in self.course_map.items() if v[0]==row["course_id"]),row["course_name"])
        v={"student":tk.StringVar(value=f"{row['student_id']} - {row['student_name']}"),"course":tk.StringVar(value=course_display),"level":tk.StringVar(value=row["level"] or ""),"start":tk.StringVar(value=row["start_date"]),"end":tk.StringVar(value=row["end_date"] or ""),"monthly":tk.StringVar(value=row["monthly_fee"]),"admission":tk.StringVar(value=row["admission_fee"]),"discount":tk.StringVar(value=row["discount"]),"status":tk.StringVar(value=row["status"]),"remarks":tk.StringVar(value=row["remarks"] or "")}
        fb=FormBuilder(form);fb.combo("Student *",v["student"],list(self.student_map),searchable=True);fb.combo("Course *",v["course"],list(self.course_map),searchable=True);fb.entry("Level / Class",v["level"]);fb.entry("Start Date *",v["start"]);fb.entry("End Date",v["end"]);fb.entry("Monthly Fee",v["monthly"]);fb.entry("Admission Fee",v["admission"]);fb.entry("Discount",v["discount"]);fb.combo("Status",v["status"],["Active","Completed","Cancelled"]);fb.entry("Remarks",v["remarks"])
        def save_changes():
            try:
                student_id=self.student_map[v["student"].get()];course_id,_course_name=self.course_map[v["course"].get()]
                vals=(student_id,course_id,v["level"].get().strip(),validate_date(v["start"].get(),"Start date"),validate_date(v["end"].get(),"End date",True),parse_amount(v["monthly"].get() or "0"),parse_amount(v["admission"].get() or "0"),parse_amount(v["discount"].get() or "0"),v["status"].get(),v["remarks"].get().strip(),self.selected_id)
                self.app.services.enrollments.update(self.selected_id,*vals[:-1]);dialog.destroy();self.clear();self.app.refresh_all()
            except Exception as exc:messagebox.showerror("Error",str(exc),parent=dialog)
        ttk.Button(form,text="Save Changes",command=save_changes).grid(row=fb.row,column=1,sticky="e",pady=10)

    def open_present_students_enrollment(self):
        """Fast bulk enrollment for mapped students with at least one punch."""
        present = self.app.services.attendance.students_with_attendance()
        if not present:
            messagebox.showinfo(
                "Student Attendance",
                "No attendance punches have been imported for mapped active students yet.",
                parent=self,
            )
            return
        courses = self.db.query(
            "SELECT id,course_name,category,default_fee FROM courses "
            "WHERE status='Active' ORDER BY category,course_name"
        )
        if not courses:
            self.show_error(ValueError("Create an active course before assigning enrollments."))
            return

        dialog = tk.Toplevel(self)
        dialog.title("Enroll Students With Attendance")
        dialog.transient(self.winfo_toplevel())
        dialog.minsize(760, 530)
        shell = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Enroll Students With Attendance", style="SubTitle.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="Each enrollment uses the student's saved Joining Date and Class/Level. Students already active in the selected course are safely skipped.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        course_map = {
            f"{row['course_name']} [{row['category']}] (ID: {row['id']})": row
            for row in courses
        }
        variables = {
            "course": tk.StringVar(), "end": tk.StringVar(),
            "monthly": tk.StringVar(value="0"), "admission": tk.StringVar(value="0"),
            "discount": tk.StringVar(value="0"), "remarks": tk.StringVar(value=""),
        }
        details = ttk.Frame(shell, style="Form.TFrame")
        details.pack(fill="x")
        fb = FormBuilder(details)
        course_combo = fb.combo("Course *", variables["course"], list(course_map), searchable=True, width=55)
        fb.entry("End Date", variables["end"], width=40)
        fb.entry("Monthly Fee", variables["monthly"], width=40)
        fb.entry("Admission Fee", variables["admission"], width=40)
        fb.entry("Discount", variables["discount"], width=40)
        fb.entry("Remarks", variables["remarks"], width=40)
        details.columnconfigure(1, weight=1)

        def set_course_fee(_event=None):
            course = course_map.get(variables["course"].get())
            if course:
                variables["monthly"].set(str(course["default_fee"] or 0))

        course_combo.bind("<<ComboboxSelected>>", set_course_fee, add="+")
        ttk.Label(shell, text="Students with at least one attendance punch", style="SubTitle.TLabel").pack(anchor="w", pady=(12, 5))
        # Reserve the footer before the table is packed.  Otherwise a long student
        # list can consume the available dialog height and hide the save action.
        actions = ttk.Frame(shell, style="Form.TFrame")
        actions.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(actions, text="Select All", command=lambda: tree.selection_set(tree.get_children())).pack(side="left")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right", padx=3)
        table = ttk.Frame(shell)
        table.pack(fill="both", expand=True)
        tree = ttk.Treeview(table, columns=("id", "student", "class", "punches", "first", "last"), show="headings", selectmode="extended")
        for key, heading, width in (
            ("id", "ID", 60), ("student", "Student", 245), ("class", "Class", 110),
            ("punches", "Total Punches", 100), ("first", "First Punch", 145), ("last", "Last Punch", 145),
        ):
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for row in present:
            iid = f"student-{row['person_id']}"
            first = row["first_seen"]
            first_text = first.strftime("%Y/%m/%d %H:%M") if hasattr(first, "strftime") else str(first).replace("-", "/")[:16]
            last = row["last_seen"]
            last_text = last.strftime("%Y/%m/%d %H:%M") if hasattr(last, "strftime") else str(last).replace("-", "/")[:16]
            tree.insert("", "end", iid=iid, values=(
                row["person_id"], row["student_name"], row["class_name"] or "", row["punches"], first_text, last_text,
            ))
        tree.selection_set(tree.get_children())

        def create_enrollments():
            try:
                course = course_map.get(variables["course"].get())
                if not course:
                    raise ValueError("Select a course.")
                selected = tree.selection()
                if not selected:
                    raise ValueError("Select at least one student.")
                student_ids = [int(tree.item(iid, "values")[0]) for iid in selected]
                created, skipped = self.app.services.enrollments.create_for_attendance_students(
                    student_ids,
                    int(course["id"]),
                    end_date=validate_date(variables["end"].get(), "End date", True),
                    monthly_fee=parse_amount(variables["monthly"].get() or "0", "Monthly fee"),
                    admission_fee=parse_amount(variables["admission"].get() or "0", "Admission fee"),
                    discount=parse_amount(variables["discount"].get() or "0", "Discount"),
                    remarks=variables["remarks"].get().strip(),
                )
                dialog.destroy()
                self.app.refresh_all()
                messagebox.showinfo(
                    "Enrollment Complete",
                    f"Created: {len(created)}\nAlready active in this course: {len(skipped)}",
                    parent=self,
                )
            except Exception as exc:
                messagebox.showerror("Enrollment", str(exc), parent=dialog)

        ttk.Button(actions, text="Create Selected Enrollments", style="Accent.TButton", command=create_enrollments).pack(side="right")
        dialog.update_idletasks()
        width = min(dialog.winfo_screenwidth() - 60, max(880, dialog.winfo_reqwidth() + 20))
        height = min(dialog.winfo_screenheight() - 80, max(560, dialog.winfo_reqheight() + 20))
        dialog.geometry(f"{width}x{height}")
        dialog.grab_set()

    def export_csv(self):
        path=filedialog.asksaveasfilename(parent=self,title="Export Enrollments",defaultextension=".csv",filetypes=[("CSV files","*.csv")])
        if not path:return
        rows=self.db.query("SELECT e.*,s.student_name,c.course_name FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id ORDER BY e.id")
        with open(path,"w",newline="",encoding="utf-8-sig") as target:
            w=csv.writer(target);w.writerow(["Student ID","Student Name","Course","Level","Start Date","End Date","Monthly Fee","Admission Fee","Discount","Status","Remarks"])
            for r in rows:w.writerow([r["student_id"],r["student_name"],r["course_name"],r["level"],r["start_date"],r["end_date"],r["monthly_fee"],r["admission_fee"],r["discount"],r["status"],r["remarks"]])
        messagebox.showinfo("Exported",f"Saved to:\n{path}",parent=self)

    def import_csv(self):
        path=filedialog.askopenfilename(parent=self,title="Import Enrollments",filetypes=[("CSV files","*.csv")])
        if not path:return
        count=0
        try:
            courses={row["course_name"]:row for row in self.db.query("SELECT id,course_name FROM courses")}
            student_ids={int(row["id"]) for row in self.db.query("SELECT id FROM students")}
            values=[]
            with open(path,newline="",encoding="utf-8-sig") as source:
                reader=csv.DictReader(source);self.require_headers(reader,["Student ID","Course","Start Date"])
                for row in reader:
                    student_id=int(row["Student ID"]);course=courses.get(row["Course"])
                    if student_id not in student_ids:raise ValueError(f"Unknown student ID: {student_id}")
                    if not course:raise ValueError(f"Unknown course: {row['Course']}")
                    values.append((student_id,course["id"],row.get("Level",""),validate_date(row["Start Date"],"Start date"),validate_date(row.get("End Date","").strip(),"End date",True),float(row.get("Monthly Fee") or 0),float(row.get("Admission Fee") or 0),float(row.get("Discount") or 0),row.get("Status","Active"),row.get("Remarks","")));count+=1
            self.app.services.enrollments.create_many(values)
            self.app.refresh_all();messagebox.showinfo("Imported",f"Imported {count} enrollments.",parent=self)
        except Exception as exc:self.show_error(exc)


# ---------------------------------------------------------------------------
# Account helpers/mixins
