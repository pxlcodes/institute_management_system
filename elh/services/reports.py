from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from elh.config import ROOT_DIR
from elh.models import Receipt,ReceiptLine


class ReportsService:
    def __init__(self, db, app_title: str, currency_symbol: str, printing=None):
        self.db=db;self.app_title=app_title;self.currency_symbol=currency_symbol;self.printing=printing

    def company_profile(self):
        row=self.db.query_one("SELECT * FROM company_profile WHERE id=1")
        return dict(row) if row else {"company_name":self.app_title,"pan_number":"","registration_number":"","address":"","phone":"","email":"","website":"","report_footer":""}

    def paid_transactions_pdf(self,start_date:str,end_date:str,output:Path|None=None)->Path:
        rows=self.db.query("SELECT st.transaction_date,s.student_name,st.particular,st.payment_amount,st.discount_amount,COALESCE(a.account_name,'') account_name,st.payment_method,st.receipt_no FROM student_transactions st JOIN students s ON s.id=st.student_id LEFT JOIN accounts a ON a.id=st.account_id WHERE st.transaction_date BETWEEN ? AND ? AND (st.payment_amount>0 OR st.discount_amount>0) ORDER BY st.transaction_date,st.id",(start_date,end_date))
        data=[[r["transaction_date"],r["student_name"],r["particular"],self._money(r["payment_amount"]),self._money(r["discount_amount"]),r["account_name"],r["receipt_no"] or ""] for r in rows]
        totals=(sum(float(r["payment_amount"]) for r in rows),sum(float(r["discount_amount"]) for r in rows))
        output=output or self._path(f"paid_transactions_{start_date.replace('/','-')}_{end_date.replace('/','-')}.pdf")
        return self._build(output,"PAID STUDENT TRANSACTIONS",start_date,end_date,["Date","Student","Particular","Paid","Discount","Account","Receipt"],data,["","","TOTAL",self._money(totals[0]),self._money(totals[1]),"",""])

    def ledger_pdf(self,start_date:str,end_date:str,output:Path|None=None)->Path:
        rows=self.db.query("SELECT l.transaction_date,a.account_name,l.direction,l.amount,l.source_type,l.particular,l.reference_no FROM ledger l JOIN accounts a ON a.id=l.account_id WHERE l.transaction_date BETWEEN ? AND ? ORDER BY l.transaction_date,l.id",(start_date,end_date))
        data=[[r["transaction_date"],r["account_name"],r["direction"],self._money(r["amount"]),r["source_type"],r["particular"],r["reference_no"] or ""] for r in rows]
        incoming=sum(float(r["amount"]) for r in rows if r["direction"]=="IN");outgoing=sum(float(r["amount"]) for r in rows if r["direction"]=="OUT")
        output=output or self._path(f"account_ledger_{start_date.replace('/','-')}_{end_date.replace('/','-')}.pdf")
        return self._build(output,"CENTRAL ACCOUNT LEDGER",start_date,end_date,["Date","Account","Type","Amount","Source","Particular","Reference"],data,["","","NET",self._money(incoming-outgoing),f"IN {self._money(incoming)}",f"OUT {self._money(outgoing)}",""])

    def payment_proof(self,kind:str,record_id:int):
        if kind=="student":
            r=self.db.query_one("SELECT st.*,s.student_name person_name,COALESCE(a.account_name,'') account_name FROM student_transactions st JOIN students s ON s.id=st.student_id LEFT JOIN accounts a ON a.id=st.account_id WHERE st.id=?",(record_id,))
            if not r:raise ValueError("Student transaction was not found.")
            return {"kind":"STUDENT PAYMENT RECEIPT","number":r["receipt_no"] or f"ST-{r['id']}","date":r["transaction_date"],"person":r["person_name"],"account":r["account_name"],"method":r["payment_method"] or "","reference":r["receipt_no"] or "","remarks":r["remarks"] or "","lines":[("Payment",r["payment_amount"]),("Discount",r["discount_amount"])],"total":r["payment_amount"]}
        if kind=="salary":
            r=self.db.query_one("SELECT sp.*,t.teacher_name person_name,a.account_name FROM salary_payouts sp JOIN teachers t ON t.id=sp.teacher_id JOIN accounts a ON a.id=sp.paid_from_account_id WHERE sp.id=?",(record_id,))
            if not r:raise ValueError("Salary payment was not found.")
            attendance = (
                f"{int(r['attendance_days'] or 0)} present days / "
                f"{float(r['working_hours'] or 0):.2f} working hours"
            )
            return {"kind":"STAFF SALARY PAYMENT PROOF","number":r["voucher_no"] or f"SAL-{r['id']}","date":r["payment_date"],"person":r["person_name"],"account":r["account_name"],"method":r["payment_method"] or "","reference":r["voucher_no"] or "","attendance":attendance,"remarks":r["remarks"] or "","lines":[(f"Basic salary - {r['salary_month']}",r["basic_salary"]),("Extra payment",r["extra_payment"]),("Bonus",r["bonus"]),("Allowance",r["allowance"]),("Advance deduction",-Decimal(str(r["advance_deduction"]))),("Other deduction",-Decimal(str(r["other_deduction"])))],"total":r["net_salary"]}
        if kind=="advance":
            r=self.db.query_one("SELECT ta.*,t.teacher_name person_name,a.account_name FROM teacher_advances ta JOIN teachers t ON t.id=ta.teacher_id JOIN accounts a ON a.id=ta.paid_from_account_id WHERE ta.id=?",(record_id,))
            if not r:raise ValueError("Staff advance was not found.")
            return {"kind":"STAFF ADVANCE PAYMENT PROOF","number":r["reference_no"] or f"ADV-{r['id']}","date":r["advance_date"],"person":r["person_name"],"account":r["account_name"],"method":r["payment_method"] or "","reference":r["reference_no"] or "","remarks":r["remarks"] or "","lines":[("Advance payment",r["amount"])],"total":r["amount"]}
        raise ValueError("Unsupported payment proof type.")

    def print_payment_pos(self,kind:str,record_id:int):
        if not self.printing:raise ValueError("POS printing service is unavailable.")
        proof=self.payment_proof(kind,record_id);lines=[]
        for label,amount in proof["lines"]:
            if kind=="student" and label=="Discount":continue
            amount=Decimal(str(amount or 0))
            if amount:lines.append(ReceiptLine(label,amount))
        discount=next((amount for label,amount in proof["lines"] if label=="Discount"),0)
        discount_note=f"\nDiscount: {self._money(discount)}" if Decimal(str(discount or 0))>0 else ""
        attendance_note=(f"\nAttendance: {proof['attendance']}" if proof.get("attendance") else "")
        footer=f"Method: {proof['method']}\nAccount: {proof['account']}{discount_note}{attendance_note}\nPAYMENT PROOF"
        self.printing.print_receipt(Receipt(proof["kind"],proof["number"],proof["date"],proof["person"],lines,footer))

    def payment_proof_pdf(self,kind:str,record_id:int,output:Path|None=None)->Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        proof=self.payment_proof(kind,record_id);profile=self.company_profile();safe=proof["number"].replace("/","-").replace("\\","-")
        output=output or self._path(f"payment_proof_{kind}_{safe}.pdf");styles=getSampleStyleSheet()
        title=ParagraphStyle("Company",parent=styles["Title"],fontSize=20,textColor=colors.HexColor("#102A43"),alignment=1)
        center=ParagraphStyle("Center",parent=styles["BodyText"],alignment=1,textColor=colors.HexColor("#475569"))
        details=[v for v in (profile.get("address"),profile.get("phone"),profile.get("email")) if v]
        tax=[]
        if profile.get("pan_number"):tax.append(f"PAN: {profile['pan_number']}")
        if profile.get("registration_number"):tax.append(f"Reg. No: {profile['registration_number']}")
        story=[Paragraph(profile.get("company_name") or self.app_title,title),Paragraph(" | ".join(details+tax),center),Spacer(1,6*mm),Paragraph(proof["kind"],ParagraphStyle("Proof",parent=styles["Heading2"],alignment=1,textColor=colors.HexColor("#008F7A"))),Spacer(1,5*mm)]
        info_rows=[["Receipt / Voucher",proof["number"],"Date (BS)",proof["date"]],["Paid To / Received From",proof["person"],"Payment Method",proof["method"]],["Account",proof["account"],"Reference",proof["reference"]]]
        if proof.get("attendance"):info_rows.append(["Attendance Reference",proof["attendance"],"Salary Adjustment","Not automatic"])
        info=Table(info_rows,colWidths=[48*mm,47*mm,38*mm,57*mm])
        info.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.HexColor("#CBD5E1")),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#E8F0F7")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#E8F0F7")),("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"),("PADDING",(0,0),(-1,-1),7)]));story.extend([info,Spacer(1,7*mm)])
        lines=[["Description","Amount"]]+[[label,self._money(amount)] for label,amount in proof["lines"] if Decimal(str(amount or 0))!=0]+[["NET PAYMENT",self._money(proof["total"])]]
        amounts=Table(lines,colWidths=[145*mm,45*mm]);amounts.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.HexColor("#CBD5E1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183B56")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#DDF4EF")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("ALIGN",(1,1),(1,-1),"RIGHT"),("PADDING",(0,0),(-1,-1),7)]));story.extend([amounts,Spacer(1,8*mm)])
        if proof["remarks"]:story.extend([Paragraph(f"Remarks: {proof['remarks']}",styles["BodyText"]),Spacer(1,10*mm)])
        story.extend([Spacer(1,12*mm),Table([["Receiver Signature: ____________________","Authorized Signature: ____________________"]],colWidths=[95*mm,95*mm])])
        SimpleDocTemplate(str(output),pagesize=A4,leftMargin=10*mm,rightMargin=10*mm,topMargin=12*mm,bottomMargin=12*mm,title=proof["kind"]).build(story);return output

    def _path(self,name):
        path=ROOT_DIR/"output"/"pdf"/name;path.parent.mkdir(parents=True,exist_ok=True);return path
    def _money(self,value):return f"{float(value or 0):,.2f}"

    def _build(self,output,title,start_date,end_date,headers,rows,total_row):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        profile=self.company_profile();styles=getSampleStyleSheet()
        heading=ParagraphStyle("Company",parent=styles["Title"],fontSize=18,leading=21,textColor=colors.HexColor("#102A43"),alignment=1)
        sub=ParagraphStyle("Sub",parent=styles["BodyText"],fontSize=8.5,leading=11,alignment=1,textColor=colors.HexColor("#475569"))
        footer=profile.get("report_footer") or "Computer generated report"
        def page(canvas,doc):
            canvas.saveState();canvas.setFont("Helvetica",8);canvas.setFillColor(colors.HexColor("#64748B"));canvas.drawString(14*mm,8*mm,footer);canvas.drawRightString(283*mm,8*mm,f"Page {doc.page}");canvas.restoreState()
        details=[]
        if profile.get("pan_number"):details.append(f"PAN: {profile['pan_number']}")
        if profile.get("registration_number"):details.append(f"Reg. No: {profile['registration_number']}")
        details += [v for v in (profile.get("address"),profile.get("phone"),profile.get("email"),profile.get("website")) if v]
        story=[Paragraph(profile.get("company_name") or self.app_title,heading),Paragraph(" | ".join(details),sub),Spacer(1,4*mm),Paragraph(title,ParagraphStyle("Report",parent=styles["Heading2"],alignment=1,textColor=colors.HexColor("#008F7A"))),Paragraph(f"Period: {start_date} to {end_date} (BS)",sub),Spacer(1,5*mm)]
        table_data=[headers,*rows,total_row]
        widths=[25,42,24,27,37,82,35] if "LEDGER" in title else [25,42,75,27,27,48,32]
        table=Table(table_data,colWidths=[w*mm for w in widths],repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183B56")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#DDF4EF")),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#CBD5E1")),("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,colors.HexColor("#F7FAFC")]),("FONTSIZE",(0,0),(-1,-1),7.5),("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(3,1),(4,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(table);SimpleDocTemplate(str(output),pagesize=landscape(A4),leftMargin=10*mm,rightMargin=10*mm,topMargin=10*mm,bottomMargin=14*mm,title=title).build(story,onFirstPage=page,onLaterPages=page);return output
