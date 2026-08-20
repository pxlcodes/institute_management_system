from __future__ import annotations
import csv
import tkinter as tk
from tkinter import filedialog,messagebox, ttk
from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.pages.import_templates import ImportTemplateMixin


class SchoolsPage(CrudPage,ImportTemplateMixin):
    IMPORT_HEADERS=["EMIS ID","School Name","Address","Contact","Status","Remarks"]
    def __init__(self,parent,app):
        super().__init__(parent,app)
        ttk.Label(self,text="School Master",style="Title.TLabel").pack(anchor="w")
        form=self.create_form_dialog("School",padding=8); form.pack(fill="x",pady=8)
        self.vars={k:tk.StringVar(value=v) for k,v in {"emis":"","name":"","address":"","contact":"","status":"Active","remarks":""}.items()}
        fb=FormBuilder(form); fb.entry("EMIS ID",self.vars["emis"]);fb.entry("School Name *",self.vars["name"]); fb.entry("Address",self.vars["address"])
        fb.entry("Contact",self.vars["contact"]); fb.combo("Status",self.vars["status"],["Active","Inactive"]); fb.entry("Remarks",self.vars["remarks"])
        ttk.Button(form,text="Save School",style="Accent.TButton",command=self.save).grid(row=0,column=2,padx=12)
        area=ttk.Frame(self); area.pack(fill="both",expand=True)
        self.tree=self.make_tree(area,[("id","ID",50),("emis","EMIS ID",110),("name","School",220),("address","Address",220),("contact","Contact",120),("status","Status",80)])
        self.tree.bind("<Double-1>",self.open_editor)
        self.add_toolbar_menu("More actions", [
            ("Import CSV…", self.import_csv),
            ("Download import template…", lambda: self.download_csv_template("schools_import_template.csv", self.IMPORT_HEADERS, "EMIS ID is optional. School Name is required and must be unique.")),
            ("Export CSV…", self.export_csv),
        ])
    def values(self,v=None):
        v=v or self.vars; name=v["name"].get().strip()
        if not name:raise ValueError("School name is required.")
        return (v["emis"].get().strip() or None),name,v["address"].get().strip(),v["contact"].get().strip(),v["status"].get(),v["remarks"].get().strip()
    def save(self):
        try:self.db.execute("INSERT INTO schools (emis_id,school_name,address,contact,status,remarks) VALUES (?,?,?,?,?,?)",self.values());self.vars["emis"].set("");self.vars["name"].set("");self.refresh()
        except Exception as exc:self.show_error(exc)
    def open_editor(self,_event=None):
        selected=self.tree.selection()
        if not selected:return
        school_id=int(self.tree.item(selected[0],"values")[0]); row=self.db.query_one("SELECT * FROM schools WHERE id=?",(school_id,))
        dialog=tk.Toplevel(self);dialog.title("Edit School");dialog.transient(self.winfo_toplevel());dialog.grab_set();form=ttk.Frame(dialog,padding=12,style="Form.TFrame");form.pack()
        v={"emis":tk.StringVar(value=row["emis_id"] or ""),"name":tk.StringVar(value=row["school_name"]),"address":tk.StringVar(value=row["address"] or ""),"contact":tk.StringVar(value=row["contact"] or ""),"status":tk.StringVar(value=row["status"]),"remarks":tk.StringVar(value=row["remarks"] or "")}
        fb=FormBuilder(form);fb.entry("EMIS ID",v["emis"]);fb.entry("School Name *",v["name"]);fb.entry("Address",v["address"]);fb.entry("Contact",v["contact"]);fb.combo("Status",v["status"],["Active","Inactive"]);fb.entry("Remarks",v["remarks"])
        def update():
            try:self.db.execute("UPDATE schools SET emis_id=?,school_name=?,address=?,contact=?,status=?,remarks=? WHERE id=?",self.values(v)+(school_id,));dialog.destroy();self.refresh()
            except Exception as exc:messagebox.showerror("Error",str(exc),parent=dialog)
        ttk.Button(form,text="Save Changes",command=update).grid(row=fb.row,column=1,sticky="e",pady=10)
    def refresh(self):
        self.clear_tree(self.tree)
        for r in self.db.query("SELECT * FROM schools ORDER BY school_name"):
            self.tree.insert("","end",values=(r["id"],r["emis_id"] or "",r["school_name"],r["address"],r["contact"],r["status"]))

    def import_csv(self):
        path=filedialog.askopenfilename(parent=self,title="Import Schools",filetypes=[("CSV files","*.csv")])
        if not path:return
        count=0
        try:
            values=[]
            with open(path,newline="",encoding="utf-8-sig") as source:
                reader=csv.DictReader(source);self.require_headers(reader,["School Name"])
                for row in reader:
                    name=row.get("School Name","").strip()
                    if not name:raise ValueError("School Name cannot be blank.")
                    values.append(((row.get("EMIS ID") or "").strip() or None,name,row.get("Address",""),row.get("Contact",""),row.get("Status","Active"),row.get("Remarks","")));count+=1
            self.db.executemany("INSERT INTO schools (emis_id,school_name,address,contact,status,remarks) VALUES (?,?,?,?,?,?)",values)
            self.app.refresh_all();messagebox.showinfo("Imported",f"Imported {count} schools.",parent=self)
        except Exception as exc:self.show_error(exc)

    def export_csv(self):
        path=filedialog.asksaveasfilename(parent=self,title="Export Schools",defaultextension=".csv",filetypes=[("CSV files","*.csv")])
        if not path:return
        with open(path,"w",newline="",encoding="utf-8-sig") as target:
            writer=csv.writer(target);writer.writerow(["School ID",*self.IMPORT_HEADERS])
            for r in self.db.query("SELECT * FROM schools ORDER BY school_name"):writer.writerow([r["id"],r["emis_id"] or "",r["school_name"],r["address"],r["contact"],r["status"],r["remarks"]])
        messagebox.showinfo("Exported",f"Saved to:\n{path}",parent=self)
