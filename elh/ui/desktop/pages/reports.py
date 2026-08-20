from __future__ import annotations
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox,ttk
from elh.ui.desktop.components import BasePage,FormBuilder
from elh.ui.desktop.helpers import today_iso,validate_date


class ReportsPage(BasePage):
    def __init__(self,parent,app):
        super().__init__(parent,app)
        ttk.Label(self,text="Reports & Printing",style="Title.TLabel").pack(anchor="w")
        ttk.Label(self,text="Generate properly headed PDF reports using your saved company and PAN details.").pack(anchor="w",pady=(2,14))
        card=ttk.LabelFrame(self,text="Report Period (Nepali BS)",padding=18);card.pack(fill="x")
        self.start=tk.StringVar(value=today_iso());self.end=tk.StringVar(value=today_iso());fb=FormBuilder(card);fb.entry("Start Date *",self.start);fb.entry("End Date *",self.end)
        tabs=ttk.Notebook(self);tabs.pack(fill="both",expand=True,pady=16)
        finance=ttk.Frame(tabs,padding=18);academic=ttk.Frame(tabs,padding=18);attendance=ttk.Frame(tabs,padding=18);people=ttk.Frame(tabs,padding=18)
        tabs.add(finance,text="Finance & Payments");tabs.add(academic,text="Academic");tabs.add(attendance,text="Attendance Reconciliation");tabs.add(people,text="People & Staff")
        self.actions(finance,"Student payment collection and complete account movements.",[("Open Paid Transactions PDF",lambda:self.run("paid",False)),("Print Paid Transactions",lambda:self.run("paid",True)),("Open Account Ledger PDF",lambda:self.run("ledger",False)),("Print Account Ledger",lambda:self.run("ledger",True))])
        self.actions(academic,"Current registered students for admission, class, and school verification.",[("Open Student Register PDF",lambda:self.run("students",False)),("Print Student Register",lambda:self.run("students",True))])
        self.actions(attendance,"Shows device users who have punched but are not linked to a Student or Staff record. This is the missing-registration list.",[("Open Unregistered Attendance PDF",lambda:self.run("unregistered",False)),("Print Unregistered Attendance",lambda:self.run("unregistered",True))])
        self.actions(people,"Current staff register for administrative and payroll review.",[("Open Staff Register PDF",lambda:self.run("staff",False)),("Print Staff Register",lambda:self.run("staff",True))])

    @staticmethod
    def actions(parent, description, actions):
        ttk.Label(parent,text=description,style="Hint.TLabel",wraplength=720,justify="left").pack(anchor="w",pady=(0,12))
        for label,command in actions: ttk.Button(parent,text=label,style="Accent.TButton" if label.startswith("Open") else "TButton",command=command).pack(anchor="w",pady=4)
    def run(self,kind,print_now):
        try:
            start=validate_date(self.start.get(),"Start date");end=validate_date(self.end.get(),"End date")
            if end<start:raise ValueError("End date cannot be earlier than start date.")
            service=self.app.services.reports
            path=(service.paid_transactions_pdf(start,end) if kind=="paid" else service.ledger_pdf(start,end) if kind=="ledger" else service.student_register_pdf() if kind=="students" else service.staff_register_pdf() if kind=="staff" else service.unregistered_attendance_pdf())
            os.startfile(Path(path),"print" if print_now else "open")
        except Exception as exc:messagebox.showerror("Report Error",str(exc),parent=self)
