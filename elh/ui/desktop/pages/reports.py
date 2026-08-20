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
        buttons=ttk.Frame(card);buttons.grid(row=0,column=2,rowspan=2,padx=(28,0),sticky="n")
        ttk.Button(buttons,text="Open Paid Transactions PDF",style="Accent.TButton",command=lambda:self.run("paid",False)).pack(fill="x",pady=3)
        ttk.Button(buttons,text="Print Paid Transactions",command=lambda:self.run("paid",True)).pack(fill="x",pady=3)
        ttk.Button(buttons,text="Open Account Ledger PDF",style="Accent.TButton",command=lambda:self.run("ledger",False)).pack(fill="x",pady=(14,3))
        ttk.Button(buttons,text="Print Account Ledger",command=lambda:self.run("ledger",True)).pack(fill="x",pady=3)
        note=ttk.LabelFrame(self,text="Included",padding=18);note.pack(fill="x",pady=16)
        ttk.Label(note,text="Paid Transactions: student, payment, discount, account and receipt totals.\nAccount Ledger: all IN/OUT movements, sources, references and net total.\nEach PDF includes company name, PAN, registration/contact details, report period and page numbers.",justify="left").pack(anchor="w")
    def run(self,kind,print_now):
        try:
            start=validate_date(self.start.get(),"Start date");end=validate_date(self.end.get(),"End date")
            if end<start:raise ValueError("End date cannot be earlier than start date.")
            path=self.app.services.reports.paid_transactions_pdf(start,end) if kind=="paid" else self.app.services.reports.ledger_pdf(start,end)
            os.startfile(Path(path),"print" if print_now else "open")
        except Exception as exc:messagebox.showerror("Report Error",str(exc),parent=self)
