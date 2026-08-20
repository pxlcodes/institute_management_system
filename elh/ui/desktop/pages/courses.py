from __future__ import annotations

import csv
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import money, parse_amount
from elh.ui.desktop.pages.import_templates import ImportTemplateMixin


class CoursesPage(CrudPage,ImportTemplateMixin):
    IMPORT_HEADERS=["Course Name","Category","Billing Type","Default Fee","Duration Months","Instructor","Status","Remarks"]
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.instructor_names = []
        ttk.Label(self, text="Course Master", style="Title.TLabel").pack(anchor="w")
        form = self.create_form_dialog("Course", padding=8)
        form.pack(fill="x", pady=8)
        self.vars = {key: tk.StringVar(value=value) for key, value in {
            "name": "", "category": "Tuition", "billing": "Monthly", "fee": "0",
            "duration": "0", "instructor": "", "status": "Active", "remarks": "",
        }.items()}
        fb = FormBuilder(form)
        fb.entry("Course Name *", self.vars["name"])
        fb.combo("Category *", self.vars["category"], ["Tuition", "Language", "Computer", "Test Preparation", "Other"], state="normal")
        fb.combo("Billing Type *", self.vars["billing"], ["Monthly", "Course Complete"])
        fb.entry("Default Fee", self.vars["fee"])
        fb.entry("Duration Months", self.vars["duration"])
        self.instructor_combo = fb.combo(
            "Instructor", self.vars["instructor"], [], searchable=True
        )
        fb.combo("Status", self.vars["status"], ["Active", "Inactive"])
        fb.entry("Remarks", self.vars["remarks"])
        actions = ttk.Frame(form, style="Form.TFrame")
        actions.grid(row=0, column=2, rowspan=8, padx=12, sticky="n")
        ttk.Button(actions, text="Save Course", style="Accent.TButton", command=self.save).pack(fill="x", pady=2)
        area = ttk.Frame(self); area.pack(fill="both", expand=True)
        self.tree = self.make_tree(area, [("id","ID",50),("name","Course",220),("category","Category",120),
            ("billing","Billing",130),("fee","Default Fee",100),("duration","Months",70),
            ("instructor","Instructor",160),("status","Status",80)])
        self.tree.bind("<Double-1>", self.open_editor)
        self.add_toolbar_menu("More actions", [
            ("Import CSV…", self.import_csv),
            ("Download import template…", lambda: self.download_csv_template("courses_import_template.csv", self.IMPORT_HEADERS, "Billing Type: Monthly or Course Complete. Status: Active or Inactive.")),
            ("Export CSV…", self.export_csv),
            ("", None),
            ("Delete selected course", self.delete),
        ])

    def values(self, variables=None):
        v = variables or self.vars
        name = v["name"].get().strip()
        if not name: raise ValueError("Course name is required.")
        return (name, v["category"].get().strip(), v["billing"].get(),
                parse_amount(v["fee"].get() or "0", "Default fee"),
                int(v["duration"].get() or 0), v["instructor"].get().strip(),
                v["status"].get(), v["remarks"].get().strip())

    def save(self):
        try:
            self.db.execute("INSERT INTO courses (course_name,category,billing_type,default_fee,duration_months,instructor_name,status,remarks) VALUES (?,?,?,?,?,?,?,?)", self.values())
            self.vars["name"].set(""); self.vars["remarks"].set(""); self.refresh()
        except Exception as exc: self.show_error(exc)

    def selected_id(self):
        selected = self.tree.selection()
        return int(self.tree.item(selected[0], "values")[0]) if selected else None

    def delete(self):
        course_id = self.selected_id()
        if course_id and self.confirm_delete():
            try: self.db.execute("DELETE FROM courses WHERE id=?", (course_id,)); self.refresh()
            except sqlite3.IntegrityError: self.show_error(ValueError("Course is in use and cannot be deleted."))

    def open_editor(self, _event=None):
        course_id = self.selected_id()
        if not course_id: return
        row = self.db.query_one("SELECT * FROM courses WHERE id=?", (course_id,))
        dialog = tk.Toplevel(self); dialog.title("Edit Course"); dialog.transient(self.winfo_toplevel()); dialog.grab_set()
        variables = {"name":tk.StringVar(value=row["course_name"]),"category":tk.StringVar(value=row["category"]),
            "billing":tk.StringVar(value=row["billing_type"]),"fee":tk.StringVar(value=row["default_fee"]),
            "duration":tk.StringVar(value=row["duration_months"]),"instructor":tk.StringVar(value=row["instructor_name"] or ""),"status":tk.StringVar(value=row["status"]),
            "remarks":tk.StringVar(value=row["remarks"] or "")}
        form=ttk.Frame(dialog,padding=12,style="Form.TFrame"); form.pack(fill="both",expand=True); fb=FormBuilder(form)
        fb.entry("Course Name *",variables["name"]); fb.combo("Category *",variables["category"],["Tuition","Language","Computer","Test Preparation","Other"],state="normal")
        fb.combo("Billing Type *",variables["billing"],["Monthly","Course Complete"]); fb.entry("Default Fee",variables["fee"])
        fb.entry("Duration Months",variables["duration"]); fb.combo("Instructor",variables["instructor"],self.instructor_names,searchable=True); fb.combo("Status",variables["status"],["Active","Inactive"]); fb.entry("Remarks",variables["remarks"])
        def update():
            try:
                values = self.values(variables)
                self.db.execute(
                    "UPDATE courses SET course_name=?,category=?,billing_type=?,default_fee=?,duration_months=?,instructor_name=?,status=?,remarks=? WHERE id=?",
                    values+(course_id,),
                )
                dialog.destroy(); self.refresh()
            except Exception as exc: messagebox.showerror("Error",str(exc),parent=dialog)
        ttk.Button(form,text="Save Changes",command=update).grid(row=fb.row,column=1,sticky="e",pady=10)

    def import_csv(self):
        path=filedialog.askopenfilename(parent=self,title="Import Courses",filetypes=[("CSV files","*.csv")])
        if not path:return
        count=0
        try:
            values=[]
            with open(path,newline="",encoding="utf-8-sig") as source:
                reader=csv.DictReader(source);self.require_headers(reader,["Course Name"])
                for row in reader:
                    values.append((row["Course Name"].strip(),row.get("Category","Other"),row.get("Billing Type","Monthly"),float(row.get("Default Fee") or 0),int(row.get("Duration Months") or 0),row.get("Instructor",""),row.get("Status","Active"),row.get("Remarks","")))
                    count+=1
            self.db.executemany("INSERT INTO courses (course_name,category,billing_type,default_fee,duration_months,instructor_name,status,remarks) VALUES (?,?,?,?,?,?,?,?)",values)
            self.refresh(); messagebox.showinfo("Imported",f"Imported {count} courses.",parent=self)
        except Exception as exc:self.show_error(exc)

    def export_csv(self):
        path=filedialog.asksaveasfilename(parent=self,title="Export Courses",defaultextension=".csv",filetypes=[("CSV files","*.csv")])
        if not path:return
        rows=self.db.query("SELECT * FROM courses ORDER BY category,course_name")
        with open(path,"w",newline="",encoding="utf-8-sig") as target:
            writer=csv.writer(target); writer.writerow(self.IMPORT_HEADERS)
            for r in rows:writer.writerow([r["course_name"],r["category"],r["billing_type"],r["default_fee"],r["duration_months"],r["instructor_name"] or "",r["status"],r["remarks"]])
        messagebox.showinfo("Exported",f"Saved to:\n{path}",parent=self)

    def refresh(self):
        self.instructor_names = [
            row["teacher_name"]
            for row in self.db.query(
                "SELECT teacher_name FROM teachers WHERE status='Active' "
                "AND staff_type='Teaching' "
                "ORDER BY teacher_name"
            )
        ]
        self.instructor_combo.set_values(self.instructor_names)
        self.clear_tree(self.tree)
        for r in self.db.query("SELECT * FROM courses ORDER BY category,course_name"):
            self.tree.insert("","end",values=(r["id"],r["course_name"],r["category"],r["billing_type"],money(r["default_fee"]),r["duration_months"],r["instructor_name"] or "",r["status"]))
