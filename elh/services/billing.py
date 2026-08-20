from __future__ import annotations
from decimal import Decimal
from pathlib import Path
from elh.config import ROOT_DIR
from elh.core.validation import validate_month

from elh.models import BillGenerationResult, Receipt, ReceiptLine
from elh.repositories import BillingRepository


class BillingService:
    def __init__(self,repository:BillingRepository,printing,app_title:str,currency_symbol:str,notifications=None):
        self.repository=repository;self.printing=printing;self.app_title=app_title;self.currency_symbol=currency_symbol;self.notifications=notifications
    def generate(self,enrollment_id:int,period:str,issue_date:str,due_date:str,remarks:str="") -> BillGenerationResult:
        period=validate_month(period.strip(),"Billing period")
        enrollment=self.repository.enrollment(enrollment_id)
        if not enrollment:raise ValueError("Enrollment was not found.")
        start_month=str(enrollment["start_date"])[:7]
        if period<start_month:raise ValueError(f"Cannot bill {period}; enrollment starts in {start_month}.")
        existing=self.repository.find(enrollment_id,period)
        if existing:return BillGenerationResult(existing,False)
        first=self.repository.count_for_enrollment(enrollment_id)==0
        fee=Decimal(str(enrollment["monthly_fee"] or 0));admission=Decimal(str(enrollment["admission_fee"] or 0)) if first else Decimal("0")
        discount=Decimal(str(enrollment["discount"] or 0)) if first else Decimal("0")
        subtotal=fee+admission;total=max(Decimal("0"),subtotal-discount)
        bill_number=f"ELH-{enrollment_id}-{period.replace('/','-').replace(' ','-')}"
        bill_id=self.repository.create((bill_number,enrollment_id,period,issue_date,due_date,subtotal,discount,total,remarks))
        bill=self.repository.get(bill_id);self._notify_bill(bill)
        return BillGenerationResult(bill,True)
    def generate_many(self,enrollment_ids:list[int],period:str,issue_date:str,due_date:str,remarks:str=""):
        if not enrollment_ids:raise ValueError("Select at least one enrollment.")
        results=[]
        for enrollment_id in enrollment_ids:
            results.append(self.generate(enrollment_id,period,issue_date,due_date,remarks))
        return results
    def generate_month_range(self,enrollment_ids:list[int],start_month:str,end_month:str,issue_date:str,due_date:str,remarks:str=""):
        if not enrollment_ids:raise ValueError("Select at least one enrollment.")
        start_month=validate_month(start_month,"Start month");end_month=validate_month(end_month,"End month")
        sy,sm=(int(v) for v in start_month.split("/"));ey,em=(int(v) for v in end_month.split("/"))
        if (ey,em)<(sy,sm):raise ValueError("End month cannot be earlier than start month.")
        periods=[];year,month=sy,sm
        while (year,month)<=(ey,em):
            periods.append(f"{year:04d}/{month:02d}");month+=1
            if month==13:year+=1;month=1
        results=[]
        for enrollment_id in enrollment_ids:
            for period in periods:results.append(self.generate(enrollment_id,period,issue_date,due_date,remarks))
        return results
    def generate_combined_month_range(self,enrollment_ids:list[int],start_month:str,end_month:str,issue_date:str,due_date:str,remarks:str=""):
        if not enrollment_ids:
            raise ValueError("Select at least one enrollment.")
        months = self._months(start_month, end_month)
        enrollment_ids = list(dict.fromkeys(enrollment_ids))
        enrollments = self.repository.enrollments(enrollment_ids)
        missing = [value for value in enrollment_ids if value not in enrollments]
        if missing:
            raise ValueError(f"Enrollment was not found: {missing[0]}")

        billed = self.repository.billed_months_many(enrollment_ids, months)
        bill_counts = self.repository.bill_counts(enrollment_ids)
        specs = []
        result_slots: list[tuple[str, int] | None] = []

        for enrollment_id in enrollment_ids:
            enrollment = enrollments[enrollment_id]
            enrollment_start = str(enrollment["start_date"])[:7]
            eligible_months = [month for month in months if month >= enrollment_start]
            if not eligible_months:
                result_slots.append(None)
                continue

            existing_months = billed.get(enrollment_id, {})
            unbilled = [month for month in eligible_months if month not in existing_months]
            if not unbilled:
                existing_id = existing_months.get(eligible_months[0])
                result_slots.append(("existing", existing_id) if existing_id else None)
                continue

            first = bill_counts.get(enrollment_id, 0) == 0
            monthly = Decimal(str(enrollment["monthly_fee"] or 0))
            admission = Decimal(str(enrollment["admission_fee"] or 0)) if first else Decimal("0")
            discount = Decimal(str(enrollment["discount"] or 0)) if first else Decimal("0")
            subtotal = monthly * len(unbilled) + admission
            total = max(Decimal("0"), subtotal - discount)
            period = unbilled[0] if len(unbilled) == 1 else f"{unbilled[0]} to {unbilled[-1]}"
            bill_number = (
                f"ELH-{enrollment_id}-{unbilled[0].replace('/','-')}-"
                f"{unbilled[-1].replace('/','-')}"
            )
            header = (
                bill_number, enrollment_id, period, issue_date, due_date,
                subtotal, discount, total, remarks,
            )
            result_slots.append(("created", len(specs)))
            specs.append((header, unbilled, monthly))

        created_ids = self.repository.create_combined_many(specs) if specs else []
        needed_ids = [
            created_ids[value] if kind == "created" else value
            for slot in result_slots if slot is not None
            for kind, value in (slot,)
        ]
        bills = self.repository.get_many(needed_ids)
        results = []
        for slot in result_slots:
            if slot is None:
                continue
            kind, value = slot
            bill_id = created_ids[value] if kind == "created" else value
            results.append(BillGenerationResult(bills[bill_id], kind == "created"))
        for result in results:
            if result.created:
                self._notify_bill(result.bill)
        return results

    def _notify_bill(self,bill):
        if not getattr(self,"notifications",None) or not bill:return
        contact=self.repository.student_contact(bill.id)
        self.notifications.notify(
            "due_bill","due_bill",bill.id,contact,
            {"student_name":bill.student_name,"bill_number":bill.bill_number,
             "amount":f"{bill.total_amount:,.2f}","due_date":bill.due_date,
             "period":bill.billing_period,"course_name":bill.course_name},
        )
    @staticmethod
    def _months(start_month:str,end_month:str):
        start_month=validate_month(start_month,"Start month");end_month=validate_month(end_month,"End month")
        sy,sm=(int(v) for v in start_month.split("/"));ey,em=(int(v) for v in end_month.split("/"))
        if (ey,em)<(sy,sm):raise ValueError("End month cannot be earlier than start month.")
        periods=[];year,month=sy,sm
        while (year,month)<=(ey,em):
            periods.append(f"{year:04d}/{month:02d}");month+=1
            if month==13:year+=1;month=1
        return periods
    def create_pdf(self,bill,output:Path|None=None)->Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
        safe_bill_number=bill.bill_number.replace("/","-").replace("\\","-")
        output=output or ROOT_DIR/"output"/"pdf"/f"due_bill_{safe_bill_number}.pdf"
        output.parent.mkdir(parents=True,exist_ok=True)
        styles=getSampleStyleSheet();doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm)
        story=[Paragraph(self.app_title,styles["Title"]),Paragraph("STUDENT DUE BILL",styles["Heading2"]),Spacer(1,6*mm)]
        details=[["Bill Number",bill.bill_number,"Billing Period",bill.billing_period],["Student",bill.student_name,"Course",bill.course_name],["Issue Date",bill.issue_date,"Due Date",bill.due_date],["Status",bill.status,"",""]]
        table=Table(details,colWidths=[30*mm,58*mm,30*mm,55*mm]);table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF0F6")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#EAF0F6")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("PADDING",(0,0),(-1,-1),6)]));story.extend([table,Spacer(1,8*mm)])
        amount_rows=[["Description","Amount"],[f"Course fee - {bill.course_name}",f"{self.currency_symbol} {bill.subtotal:,.2f}"]]
        if bill.discount>0:amount_rows.append(["Discount",f"- {self.currency_symbol} {bill.discount:,.2f}"])
        amount_rows.append(["TOTAL DUE",f"{self.currency_symbol} {bill.total_amount:,.2f}"])
        amounts=Table(amount_rows,colWidths=[125*mm,48*mm])
        amounts.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#263B50")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("ALIGN",(1,1),(-1,-1),"RIGHT"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("PADDING",(0,0),(-1,-1),7)]));story.extend([amounts,Spacer(1,14*mm),Paragraph("Please pay by the due date. Keep this bill for your records.",styles["BodyText"]),Spacer(1,12*mm),Paragraph("Authorized Signature: ______________________________",styles["BodyText"])]);doc.build(story)
        self.repository.set_pdf(bill.id,str(output));return output
    def create_batch_pdf(self,bills:list,output:Path|None=None)->Path:
        if not bills:raise ValueError("Select at least one bill.")
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import HRFlowable,KeepTogether,PageBreak,Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        safe_date=bills[0].issue_date.replace("/","-")
        output=output or ROOT_DIR/"output"/"pdf"/f"due_bills_batch_{safe_date}.pdf"
        output.parent.mkdir(parents=True,exist_ok=True);styles=getSampleStyleSheet();story=[]
        compact_title=ParagraphStyle("BatchTitle",parent=styles["Heading2"],fontSize=16,leading=18,alignment=1,spaceAfter=3)
        compact_heading=ParagraphStyle("BatchHeading",parent=styles["Heading3"],fontSize=12,leading=14,alignment=1,spaceAfter=5)
        compact_body=ParagraphStyle("BatchBody",parent=styles["BodyText"],fontSize=9,leading=12,alignment=1)
        signature_style=ParagraphStyle("BatchSignature",parent=compact_body,alignment=1,fontSize=9)
        for index,bill in enumerate(bills):
            if index and index%2==0:story.append(PageBreak())
            elif index:story.extend([Spacer(1,6*mm),HRFlowable(width="90%",thickness=1.2,color=colors.HexColor("#667788"),hAlign="CENTER"),Spacer(1,6*mm)])
            bill_story=[Paragraph(self.app_title,compact_title),Paragraph("STUDENT DUE BILL",compact_heading),Spacer(1,3*mm)]
            details=[["Bill Number",bill.bill_number,"Billing Period",bill.billing_period],["Student",bill.student_name,"Course",bill.course_name],["Issue Date",bill.issue_date,"Due Date",bill.due_date],["Status",bill.status,"",""]]
            info=Table(details,colWidths=[27*mm,61*mm,27*mm,58*mm],hAlign="CENTER");info.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF0F6")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#EAF0F6")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("FONTSIZE",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));bill_story.extend([info,Spacer(1,5*mm)])
            amount_rows=[["Description","Amount"],[f"Course fee - {bill.course_name}",f"{self.currency_symbol} {bill.subtotal:,.2f}"]]
            if bill.discount>0:amount_rows.append(["Discount",f"- {self.currency_symbol} {bill.discount:,.2f}"])
            amount_rows.append(["TOTAL DUE",f"{self.currency_symbol} {bill.total_amount:,.2f}"])
            amounts=Table(amount_rows,colWidths=[125*mm,48*mm],hAlign="CENTER");amounts.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#263B50")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("ALIGN",(1,1),(-1,-1),"RIGHT"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));bill_story.extend([amounts,Spacer(1,5*mm),Paragraph("Please pay by the due date. Keep this bill for your records.",compact_body),Spacer(1,6*mm),Paragraph("Authorized Signature:  ______________________________",signature_style),Spacer(1,3*mm)])
            story.append(KeepTogether(bill_story))
        SimpleDocTemplate(str(output),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=10*mm,bottomMargin=10*mm).build(story)
        for bill in bills:self.repository.set_pdf(bill.id,str(output))
        return output
    def print_pos_many(self,bills:list):
        if not bills:raise ValueError("Select at least one bill.")
        for bill in bills:self.print_pos(bill)
    def print_pos(self,bill):
        lines=[ReceiptLine(f"{bill.course_name} ({bill.billing_period})",bill.subtotal)]
        if bill.discount>0:lines.append(ReceiptLine("Discount",-bill.discount))
        receipt=Receipt("ELH DUE BILL",bill.bill_number,bill.issue_date,bill.student_name,lines,f"DUE BY: {bill.due_date}")
        self.printing.print_receipt(receipt);self.repository.mark_pos_printed(bill.id)
    def pay(self,bill_id:int,amount:Decimal,payment_date:str,account_id:int|None,method:str,receipt_no:str="",remarks:str="",discount:Decimal=Decimal("0")):
        amount=Decimal(str(amount));discount=Decimal(str(discount))
        transaction_id=self.repository.record_payment(bill_id,amount,discount,payment_date,account_id,method,receipt_no,remarks)
        bill=self.repository.get(bill_id)
        if getattr(self,"notifications",None):
            self.notifications.notify(
                "bill_payment","student_transaction",transaction_id,
                self.repository.student_contact(bill_id),
                {"student_name":bill.student_name,"bill_number":bill.bill_number,
                 "amount":f"{amount:,.2f}","discount":f"{discount:,.2f}",
                 "balance":f"{max(Decimal('0'),bill.total_amount-bill.paid_amount):,.2f}",
                 "payment_date":payment_date,"course_name":bill.course_name},
            )
        return bill
