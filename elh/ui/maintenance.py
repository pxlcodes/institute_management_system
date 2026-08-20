from __future__ import annotations
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox,ttk
from elh.config import ROOT_DIR
from elh.core.health import HealthService


class MaintenancePanel(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=20);self.app=app
        ttk.Label(self,text="System Maintenance",style="Title.TLabel").pack(anchor="w")
        ttk.Label(self,text=f"Signed in as {app.session.username} (Maintenance)").pack(anchor="w",pady=(2,18))
        actions=ttk.LabelFrame(self,text="Maintenance Actions",padding=12);actions.pack(fill="x")
        ttk.Button(actions,text="Normalize Schema & Indexes",command=self.migrate).pack(side="left",padx=4)
        ttk.Button(actions,text="Clear Python Cache",command=self.clear_cache).pack(side="left",padx=4)
        ttk.Button(actions,text="Check Connected Devices",command=self.refresh_health).pack(side="left",padx=4)
        ttk.Button(actions,text="Exit",command=app.destroy).pack(side="right",padx=4)
        self.tree=ttk.Treeview(self,columns=("name","status","detail"),show="headings")
        for key,title,width in (("name","Component",180),("status","Status",100),("detail","Detail",580)):
            self.tree.heading(key,text=title);self.tree.column(key,width=width,anchor="w")
        self.tree.pack(fill="both",expand=True,pady=(14,0));self.refresh_health()
    def migrate(self):
        if not messagebox.askyesno("Schema Migration","Apply required tables, relationships, normalization rules, and indexes? No sample data will be inserted.",parent=self):return
        try:self.app.db.initialize();messagebox.showinfo("Migration Complete","Schema normalization and database indexes are up to date.",parent=self);self.refresh_health()
        except Exception as exc:messagebox.showerror("Migration Error",str(exc),parent=self)
    def clear_cache(self):
        removed=0
        try:
            for path in ROOT_DIR.rglob("__pycache__"):
                if path.is_dir() and ROOT_DIR in path.parents:
                    shutil.rmtree(path);removed+=1
            messagebox.showinfo("Cache Cleared",f"Removed {removed} Python cache directories.",parent=self)
        except OSError as exc:messagebox.showerror("Cache Error",str(exc),parent=self)
    def refresh_health(self):
        self.tree.delete(*self.tree.get_children())
        report=HealthService(self.app.app_config,self.app.db).report()
        for check in report["checks"]:self.tree.insert("","end",values=(check["name"],check["status"].upper(),check["detail"]))
