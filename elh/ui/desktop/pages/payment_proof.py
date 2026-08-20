from __future__ import annotations
import os
from pathlib import Path
from tkinter import messagebox,ttk


class PaymentProofMixin:
    proof_kind: str
    def add_payment_proof_buttons(self,parent):
        bar=ttk.Frame(parent);bar.pack(fill="x",pady=(7,0))
        ttk.Button(bar,text="Print POS Receipt",command=self.print_proof_pos).pack(side="right",padx=3)
        ttk.Button(bar,text="Print Normal Receipt",command=self.print_proof_normal).pack(side="right",padx=3)
        ttk.Button(bar,text="Open Receipt PDF",style="Accent.TButton",command=self.open_proof_pdf).pack(side="right",padx=3)
    def selected_proof_id(self):
        selected=self.tree.selection()
        if not selected:raise ValueError("Select a payment record first.")
        return int(self.tree.item(selected[0],"values")[0])
    def open_proof_pdf(self):
        try:os.startfile(Path(self.app.services.reports.payment_proof_pdf(self.proof_kind,self.selected_proof_id())))
        except Exception as exc:messagebox.showerror("Receipt Error",str(exc),parent=self)
    def print_proof_normal(self):
        try:os.startfile(Path(self.app.services.reports.payment_proof_pdf(self.proof_kind,self.selected_proof_id())),"print")
        except Exception as exc:messagebox.showerror("Print Error",str(exc),parent=self)
    def print_proof_pos(self):
        try:self.app.services.reports.print_payment_pos(self.proof_kind,self.selected_proof_id());messagebox.showinfo("Printed","Payment proof sent to the configured POS printer.",parent=self)
        except Exception as exc:messagebox.showerror("POS Print Error",str(exc),parent=self)
