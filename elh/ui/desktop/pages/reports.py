from __future__ import annotations
import os
import tkinter as tk
import nepali_datetime as nepali
from pathlib import Path
from tkinter import messagebox,ttk
from elh.ui.desktop.components import BasePage,FormBuilder
from elh.ui.desktop.helpers import today_iso,validate_date


class ReportsPage(BasePage):
    def __init__(self,parent,app):
        super().__init__(parent,app)
        ttk.Label(self,text="Reports & Printing",style="Title.TLabel").pack(anchor="w")
        ttk.Label(self,text="Generate properly headed PDF reports using your saved company and PAN details. The selected period is applied to finance and attendance reports; registers are current snapshots.").pack(anchor="w",pady=(2,14))
        card=ttk.LabelFrame(self,text="Report Period (Nepali BS)",padding=18);card.pack(fill="x")
        self.start=tk.StringVar(value=today_iso());self.end=tk.StringVar(value=today_iso());fb=FormBuilder(card);fb.entry("Start Date *",self.start);fb.entry("End Date *",self.end)
        tabs=ttk.Notebook(self);tabs.pack(fill="both",expand=True,pady=16)
        finance=ttk.Frame(tabs,padding=18);academic=ttk.Frame(tabs,padding=18);attendance=ttk.Frame(tabs,padding=18);people=ttk.Frame(tabs,padding=18)
        tabs.add(finance,text="Finance & Payments");tabs.add(academic,text="Academic");tabs.add(attendance,text="Attendance Reconciliation");tabs.add(people,text="People & Staff")
        self.actions(finance,"Student payment collection and complete account movements.",[("Open Paid Transactions PDF",lambda:self.run("paid",False)),("Print Paid Transactions",lambda:self.run("paid",True)),("Open Account Ledger PDF",lambda:self.run("ledger",False)),("Print Account Ledger",lambda:self.run("ledger",True))])
        self._build_academic_reports(academic)
        self.actions(attendance,"Shows device users who have punched but are not linked to a Student or Staff record. This is the missing-registration list.",[("Open Unregistered Attendance PDF",lambda:self.run("unregistered",False)),("Print Unregistered Attendance",lambda:self.run("unregistered",True))])
        self.actions(people,"Current staff register for administrative and payroll review.",[("Open Staff Register PDF",lambda:self.run("staff",False)),("Print Staff Register",lambda:self.run("staff",True))])

    @staticmethod
    def actions(parent, description, actions):
        ttk.Label(parent,text=description,style="Hint.TLabel",wraplength=720,justify="left").pack(anchor="w",pady=(0,12))
        for label,command in actions: ttk.Button(parent,text=label,style="Accent.TButton" if label.startswith("Open") else "TButton",command=command).pack(anchor="w",pady=4)

    def _build_academic_reports(self, parent) -> None:
        ttk.Label(parent,text="Current registered students, class/school count analysis, and weekly routines.",style="Hint.TLabel",wraplength=720,justify="left").pack(anchor="w",pady=(0,12))
        filter_card=ttk.LabelFrame(parent,text="Class-wise / School-wise Student Register",padding=12)
        filter_card.pack(fill="x",pady=(0,12))
        self.report_class=tk.StringVar(value="All classes")
        self.report_school=tk.StringVar(value="All schools")
        classes=self.db.query("SELECT id,level_name FROM class_levels WHERE status='Active' ORDER BY level_name")
        schools=self.db.query("SELECT id,school_name FROM schools WHERE status='Active' ORDER BY school_name")
        self.report_class_map={"All classes":None,**{str(row["level_name"]):int(row["id"]) for row in classes}}
        self.report_school_map={"All schools":None,**{f"{row['school_name']} (ID: {row['id']})":int(row["id"]) for row in schools}}
        fb=FormBuilder(filter_card)
        fb.combo("Class / Level",self.report_class,self.report_class_map,searchable=True,width=42)
        fb.combo("School",self.report_school,self.report_school_map,searchable=True,width=42)
        actions=ttk.Frame(filter_card);actions.grid(row=0,column=2,rowspan=2,padx=(14,0),sticky="ns")
        ttk.Button(actions,text="Open Filtered Register PDF",style="Accent.TButton",command=lambda:self.run("filtered_students",False)).pack(fill="x",pady=(0,6))
        ttk.Button(actions,text="Print Filtered Register",command=lambda:self.run("filtered_students",True)).pack(fill="x")
        self.actions(parent,"Other academic reports.",[("Open Student Register PDF",lambda:self.run("students",False)),("Print Student Register",lambda:self.run("students",True)),("Open Class & School Analysis PDF",lambda:self.run("analysis",False)),("Print Class & School Analysis",lambda:self.run("analysis",True)),("Open All Class Routines PDF",lambda:self.run("routine",False)),("Print All Class Routines",lambda:self.run("routine",True))])

    def run(self,kind,print_now):
        try:
            start=validate_date(self.start.get(),"Start date");end=validate_date(self.end.get(),"End date")
            if end<start:raise ValueError("End date cannot be earlier than start date.")
            service=self.app.services.reports
            if kind == "unregistered":
                start_at = nepali.date(*map(int, start.split("/"))).to_datetime_date().isoformat() + " 00:00:00"
                end_at = nepali.date(*map(int, end.split("/"))).to_datetime_date().isoformat() + " 23:59:59"
                path = service.unregistered_attendance_pdf(start_at, end_at, start, end)
            elif kind == "filtered_students":
                class_id=self.report_class_map.get(self.report_class.get())
                school_id=self.report_school_map.get(self.report_school.get())
                path=service.student_register_pdf(class_id,school_id)
            else:
                path=(service.paid_transactions_pdf(start,end) if kind=="paid" else service.ledger_pdf(start,end) if kind=="ledger" else service.student_register_pdf() if kind=="students" else service.class_school_analysis_pdf() if kind=="analysis" else service.routine_pdf() if kind=="routine" else service.staff_register_pdf())
            os.startfile(Path(path),"print" if print_now else "open")
        except Exception as exc:messagebox.showerror("Report Error",str(exc),parent=self)
