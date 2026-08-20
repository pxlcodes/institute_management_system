from __future__ import annotations
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox,ttk
from elh.ui.desktop.components import CrudPage,FormBuilder
from elh.ui.desktop.helpers import add_days,current_month,money,parse_amount,today_iso,validate_date


class DueBillsPage(CrudPage):
    def __init__(self,parent,app):
        super().__init__(parent,app);self.enrollment_map={};self.selected_bill_id=None
        ttk.Label(self,text="Student Due Bills",style="Title.TLabel").pack(anchor="w")
        form=self.create_form_dialog("Generate Bill",padding=8);form.pack(fill="x",pady=8)
        self.vars={"enrollment":tk.StringVar(),"period":tk.StringVar(value=current_month()),"issue":tk.StringVar(value=today_iso()),"due":tk.StringVar(value=add_days(today_iso(),7)),"remarks":tk.StringVar()}
        fb=FormBuilder(form);self.enrollment_combo=fb.combo("Enrollment *",self.vars["enrollment"],[],searchable=True);fb.entry("Billing Period *",self.vars["period"]);fb.entry("Issue Date *",self.vars["issue"]);fb.entry("Due Date *",self.vars["due"]);fb.entry("Remarks",self.vars["remarks"])
        actions=ttk.Frame(form,style="Form.TFrame");actions.grid(row=0,column=2,rowspan=5,padx=12,sticky="n")
        ttk.Button(actions,text="Generate Due Bill",command=self.generate).pack(fill="x",pady=2)
        ttk.Button(actions,text="Generate Multiple...",command=self.open_bulk_generator).pack(fill="x",pady=2)
        ttk.Button(actions,text="Create / Open PDF",command=self.create_pdf).pack(fill="x",pady=2)
        ttk.Button(actions,text="Print PDF (Normal Printer)",command=self.print_pdf).pack(fill="x",pady=2)
        ttk.Button(actions,text="Print POS Receipt",command=self.print_pos).pack(fill="x",pady=2)
        area=ttk.Frame(self);area.pack(fill="both",expand=True)
        self.tree=self.make_tree(area,[("id","ID",45),("bill","Bill No.",150),("student","Student",160),("course","Course",170),("period","Period",85),("issue","Issue",90),("due","Due",90),("amount","Total",90),("paid","Paid",90),("balance","Balance",90),("status","Status",100)])
        self.tree.configure(selectmode="extended")
        self.tree.bind("<<TreeviewSelect>>",self.on_select)
        batch=ttk.Frame(self);batch.pack(fill="x",pady=(6,0))
        ttk.Button(batch,text="Select All Bills",command=lambda:self.tree.selection_set(self.tree.get_children())).pack(side="left")
        ttk.Button(batch,text="Clear Selection",command=lambda:self.tree.selection_remove(self.tree.selection())).pack(side="left",padx=5)
        ttk.Button(batch,text="Pay Selected Bill",style="Accent.TButton",command=self.open_payment).pack(side="left",padx=8)
        ttk.Button(batch,text="Open Batch PDF",command=self.open_batch_pdf).pack(side="right",padx=3)
        ttk.Button(batch,text="Print Batch PDF",command=self.print_batch_pdf).pack(side="right",padx=3)
        ttk.Button(batch,text="Batch POS Print",command=self.print_pos_batch).pack(side="right",padx=3)
    def refresh(self):
        rows=self.db.query("SELECT e.id,s.student_name,c.course_name FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id WHERE e.status='Active' ORDER BY s.student_name,c.course_name")
        self.enrollment_map={f"{r['student_name']} - {r['course_name']} (#{r['id']})":r["id"] for r in rows};self.enrollment_combo["values"]=list(self.enrollment_map)
        self.clear_tree(self.tree)
        for b in self.app.services.billing.repository.list():self.tree.insert("","end",values=(b.id,b.bill_number,b.student_name,b.course_name,b.billing_period,b.issue_date,b.due_date,money(b.total_amount),money(b.paid_amount),money(b.total_amount-b.paid_amount),b.status))
    def generate(self):
        try:
            enrollment_id=self.enrollment_map.get(self.vars["enrollment"].get())
            if not enrollment_id:raise ValueError("Please select an enrollment.")
            result=self.app.services.billing.generate(enrollment_id,self.vars["period"].get(),validate_date(self.vars["issue"].get(),"Issue date"),validate_date(self.vars["due"].get(),"Due date"),self.vars["remarks"].get())
            self.selected_bill_id=result.bill.id;self.refresh()
            messagebox.showinfo("Bill Generated" if result.created else "Already Generated",f"Bill {result.bill.bill_number}\nAmount due: {money(result.bill.total_amount)}" if result.created else f"A bill already exists for this enrollment and period:\n{result.bill.bill_number}",parent=self)
        except Exception as exc:self.show_error(exc)
    def on_select(self,_event=None):
        selected=self.tree.selection()
        if selected:self.selected_bill_id=int(self.tree.item(selected[0],"values")[0])
    def selected_bill(self):
        if not self.selected_bill_id:raise ValueError("Select or generate a bill first.")
        return self.app.services.billing.repository.get(self.selected_bill_id)
    def selected_bills(self):
        selected=self.tree.selection()
        if not selected:raise ValueError("Select one or more bills first.")
        return [self.app.services.billing.repository.get(int(self.tree.item(item,"values")[0])) for item in selected]
    def open_payment(self):
        try: bill=self.selected_bill()
        except Exception as exc:self.show_error(exc);return
        remaining=bill.total_amount-bill.paid_amount
        if remaining<=0:self.show_error(ValueError("This bill is already paid."));return
        accounts=self.db.query("SELECT id,account_name,account_type FROM accounts WHERE status='Active' ORDER BY account_name")
        account_map={f"{r['account_name']} ({r['account_type']})":r["id"] for r in accounts}
        if not account_map:self.show_error(ValueError("Create an active payment account first."));return
        dialog=tk.Toplevel(self);dialog.title("Quick Bill Payment");dialog.transient(self.winfo_toplevel());dialog.grab_set();dialog.resizable(False,False)
        panel=ttk.LabelFrame(dialog,text=f"{bill.student_name} - {bill.bill_number}",padding=14);panel.pack(fill="both",expand=True,padx=12,pady=12)
        ttk.Label(panel,text=f"Course: {bill.course_name}    Period: {bill.billing_period}").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,8))
        ttk.Label(panel,text=f"Remaining balance: {money(remaining)}",style="Card.TLabel").grid(row=1,column=0,columnspan=2,sticky="w",pady=(0,12))
        values={"amount":tk.StringVar(value=str(remaining)),"discount":tk.StringVar(value="0"),"date":tk.StringVar(value=today_iso()),"account":tk.StringVar(value=next(iter(account_map))),"method":tk.StringVar(value="Cash"),"receipt":tk.StringVar(),"remarks":tk.StringVar()}
        fb=FormBuilder(panel,start_row=2);fb.entry("Payment Amount *",values["amount"]);fb.entry("Discount Amount",values["discount"]);fb.entry("Payment Date *",values["date"]);fb.combo("Payment Account *",values["account"],account_map);fb.combo("Payment Method",values["method"],["Cash","Bank","Wallet","Other"]);fb.entry("Receipt No.",values["receipt"]);fb.entry("Remarks",values["remarks"])
        def save_payment():
            try:
                amount=parse_amount(values["amount"].get() or "0","Payment");discount=parse_amount(values["discount"].get() or "0","Discount")
                paid=self.app.services.billing.pay(bill.id,amount,validate_date(values["date"].get(),"Payment date"),account_map.get(values["account"].get()),values["method"].get(),values["receipt"].get().strip(),values["remarks"].get().strip(),discount)
                dialog.destroy();self.app.refresh_all();messagebox.showinfo("Payment Saved",f"Payment: {money(amount)}\nDiscount: {money(discount)}\nBill status: {paid.status}\nRemaining: {money(paid.total_amount-paid.paid_amount)}",parent=self)
            except Exception as exc:messagebox.showerror("Payment Error",str(exc),parent=dialog)
        ttk.Button(panel,text="Receive Payment",style="Accent.TButton",command=save_payment).grid(row=fb.row,column=1,sticky="e",pady=(12,0))
    def create_pdf(self):
        try:
            path=self.app.services.billing.create_pdf(self.selected_bill());os.startfile(path)
        except Exception as exc:self.show_error(exc)
    def print_pdf(self):
        try:
            bill=self.selected_bill();path=Path(bill.pdf_path) if bill.pdf_path else self.app.services.billing.create_pdf(bill)
            os.startfile(path,"print")
        except Exception as exc:self.show_error(exc)
    def print_pos(self):
        try:self.app.services.billing.print_pos(self.selected_bill());messagebox.showinfo("Printed","Bill sent to the configured POS printer.",parent=self)
        except Exception as exc:self.show_error(exc)
    def open_batch_pdf(self):
        try:path=self.app.services.billing.create_batch_pdf(self.selected_bills());os.startfile(path)
        except Exception as exc:self.show_error(exc)
    def print_batch_pdf(self):
        try:path=self.app.services.billing.create_batch_pdf(self.selected_bills());os.startfile(path,"print")
        except Exception as exc:self.show_error(exc)
    def print_pos_batch(self):
        try:
            bills=self.selected_bills();self.app.services.billing.print_pos_many(bills);messagebox.showinfo("Batch Printed",f"Sent {len(bills)} bills to the POS printer.",parent=self)
        except Exception as exc:self.show_error(exc)

    def open_bulk_generator(self):
        dialog=tk.Toplevel(self);dialog.title("Generate Bills for Multiple Students");dialog.geometry("840x700");dialog.minsize(760,620);dialog.transient(self.winfo_toplevel());dialog.grab_set()
        top=ttk.Frame(dialog,padding=10);top.pack(fill="x")
        start_month=tk.StringVar(value=self.vars["period"].get());end_month=tk.StringVar(value=self.vars["period"].get());issue=tk.StringVar(value=self.vars["issue"].get());due=tk.StringVar(value=self.vars["due"].get());remarks=tk.StringVar()
        fb=FormBuilder(top);fb.entry("Start Month (YYYY/MM) *",start_month);fb.entry("End Month (YYYY/MM) *",end_month);fb.entry("Issue Date *",issue);fb.entry("Due Date *",due);fb.entry("Remarks",remarks)
        ttk.Label(dialog,text="Select students/enrollments (Ctrl or Shift for multiple selection)").pack(anchor="w",padx=10)
        area=ttk.Frame(dialog,padding=(10,4));area.pack(fill="both",expand=True)
        tree=ttk.Treeview(area,columns=("id","student","course","start","fee"),show="headings",selectmode="extended")
        for key,title,width in (("id","Enrollment ID",90),("student","Student",190),("course","Course",190),("start","Start Date",100),("fee","Fee",90)):
            tree.heading(key,text=title);tree.column(key,width=width,anchor="w")
        ybar=ttk.Scrollbar(area,orient="vertical",command=tree.yview);tree.configure(yscrollcommand=ybar.set);tree.pack(side="left",fill="both",expand=True);ybar.pack(side="right",fill="y")
        rows=self.db.query("SELECT e.id,s.student_name,c.course_name,e.start_date,e.monthly_fee FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id WHERE e.status='Active' ORDER BY s.student_name,c.course_name")
        for row in rows:tree.insert("","end",values=(row["id"],row["student_name"],row["course_name"],row["start_date"],money(row["monthly_fee"])))
        buttons=ttk.Frame(dialog,padding=10);buttons.pack(fill="x")
        ttk.Button(buttons,text="Select All",command=lambda:tree.selection_set(tree.get_children())).pack(side="left")
        ttk.Button(buttons,text="Clear Selection",command=lambda:tree.selection_remove(tree.selection())).pack(side="left",padx=5)
        def generate_batch():
            try:
                ids=[int(tree.item(item,"values")[0]) for item in tree.selection()]
                results=self.app.services.billing.generate_combined_month_range(ids,start_month.get(),end_month.get(),validate_date(issue.get(),"Issue date"),validate_date(due.get(),"Due date"),remarks.get())
                created=sum(1 for result in results if result.created);existing=len(results)-created;not_started=len(ids)-len(results)
                dialog.destroy();self.refresh();messagebox.showinfo("Batch Complete",f"Combined student bills generated: {created}\nAlready billed or paid (skipped): {existing}\nNot yet enrolled for selected months (skipped): {not_started}\nStudents/enrollments selected: {len(ids)}",parent=self)
            except Exception as exc:messagebox.showerror("Batch Error",str(exc),parent=dialog)
        ttk.Button(buttons,text="Generate Selected Bills",command=generate_batch).pack(side="right")
        buttons.pack_configure(side="bottom",before=area,pady=(4,0))
