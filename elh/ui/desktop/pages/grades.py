from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from elh.ui.desktop.components import CrudPage, FormBuilder

class GradesPage(CrudPage):
    def __init__(self,parent,app):
        super().__init__(parent,app); self.selected_id=None
        ttk.Label(self,text="Grade Master",style="Title.TLabel").pack(anchor="w")
        form=self.create_form_dialog("Grade",padding=10);form.pack(fill="x",pady=8)
        self.short=tk.StringVar();self.name=tk.StringVar();self.status=tk.StringVar(value="Active");self.remarks=tk.StringVar()
        fb=FormBuilder(form);fb.entry("Short Name *",self.short);fb.entry("Grade Name *",self.name);fb.combo("Status",self.status,["Active","Inactive"]);fb.entry("Remarks",self.remarks)
        ttk.Button(form,text="Save Grade",style="Accent.TButton",command=self.save).grid(row=0,column=2,padx=12)
        area=ttk.Frame(self);area.pack(fill="both",expand=True);self.tree=self.make_tree(area,[("id","ID",55),("short","Short Name",130),("name","Grade Name",220),("status","Status",100),("remarks","Remarks",250)])
        self.tree.bind("<Double-1>",self.edit)
    def values(self):
        if not self.short.get().strip() or not self.name.get().strip():raise ValueError("Short Name and Grade Name are required.")
        return self.short.get().strip(),self.name.get().strip(),self.status.get(),self.remarks.get().strip()
    def save(self):
        try:self.db.execute("INSERT INTO grades (short_name,grade_name,status,remarks) VALUES (?,?,?,?)",self.values());self.clear();self.app.refresh_all()
        except Exception as exc:self.show_error(exc)
    def clear(self):self.selected_id=None;self.short.set("");self.name.set("");self.status.set("Active");self.remarks.set("")
    def edit(self,_event=None):
        selected=self.tree.selection()
        if not selected:return
        row=self.db.query_one("SELECT * FROM grades WHERE id=?",(int(self.tree.item(selected[0],"values")[0]),));self.selected_id=row["id"];self.short.set(row["short_name"]);self.name.set(row["grade_name"]);self.status.set(row["status"]);self.remarks.set(row["remarks"] or "");self.show_form_dialog()
    def refresh(self):
        self.clear_tree(self.tree)
        for row in self.db.query("SELECT * FROM grades ORDER BY short_name"):
            self.tree.insert("","end",values=(row["id"],row["short_name"],row["grade_name"],row["status"],row["remarks"] or ""))
