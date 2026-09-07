from __future__ import annotations
from decimal import Decimal
from pathlib import Path
from elh.config import ROOT_DIR
from elh.core.validation import validate_month

from elh.models import BillGenerationResult, Receipt, ReceiptLine
from elh.repositories import BillingRepository


class BillingService:
    def __init__(self,repository:BillingRepository,printing,app_title:str,currency_symbol:str,notifications=None,settings=None):
        self.repository=repository;self.printing=printing;self.app_title=app_title;self.currency_symbol=currency_symbol;self.notifications=notifications;self.settings=settings
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
    def get_bill_arrears(self, bill) -> tuple[list[dict], Decimal, Decimal]:
        if not hasattr(self.repository, "get_unpaid_bills_for_student"):
            return [], Decimal("0"), max(Decimal("0"), bill.total_amount - bill.paid_amount)

        show_arrears = True
        if getattr(self, "settings", None):
            show_arrears = self.settings.get_bool("billing_show_arrears_on_due_bills", True)
        if not show_arrears:
            return [], Decimal("0"), max(Decimal("0"), bill.total_amount - bill.paid_amount)

        try:
            older_bills = self.repository.get_unpaid_bills_for_student(
                student_id=bill.student_id,
                exclude_bill_id=bill.id,
                before_date=bill.issue_date,
                before_bill_id=bill.id,
            )
        except Exception:
            return [], Decimal("0"), max(Decimal("0"), bill.total_amount - bill.paid_amount)

        arrears = []
        total_arrears = Decimal("0")
        for ob in older_bills:
            rem = max(Decimal("0"), ob.total_amount - ob.paid_amount)
            if rem > 0:
                arrears.append({
                    "bill_id": ob.id,
                    "bill_number": ob.bill_number,
                    "billing_period": ob.billing_period,
                    "course_name": ob.course_name,
                    "total_amount": ob.total_amount,
                    "paid_amount": ob.paid_amount,
                    "balance": rem,
                })
                total_arrears += rem

        current_balance = max(Decimal("0"), bill.total_amount - bill.paid_amount)
        grand_total = current_balance + total_arrears
        return arrears, total_arrears, grand_total

    def create_pdf(self,bill,output:Path|None=None)->Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        from elh.core.payment_qr import PaymentQrEngine
        safe_bill_number=bill.bill_number.replace("/","-").replace("\\","-")
        output=output or ROOT_DIR/"output"/"pdf"/f"due_bill_{safe_bill_number}.pdf"
        output.parent.mkdir(parents=True,exist_ok=True)
        styles=getSampleStyleSheet();doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm)
        story=[Paragraph(self.app_title,styles["Title"]),Paragraph("STUDENT DUE BILL",styles["Heading2"]),Spacer(1,6*mm)]
        details=[["Bill Number",bill.bill_number,"Billing Period",bill.billing_period],["Student",bill.student_name,"Course",bill.course_name],["Issue Date",bill.issue_date,"Due Date",bill.due_date],["Status",bill.status,"",""]]
        table=Table(details,colWidths=[30*mm,58*mm,30*mm,55*mm]);table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF0F6")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#EAF0F6")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("PADDING",(0,0),(-1,-1),6)]));story.extend([table,Spacer(1,7*mm)])

        arrears, total_arrears, grand_total = self.get_bill_arrears(bill)
        payable_amount = grand_total if arrears else bill.total_amount

        amount_rows = [["Description", "Amount"]]
        amount_rows.append([f"Course fee - {bill.course_name} ({bill.billing_period})", f"{self.currency_symbol} {bill.subtotal:,.2f}"])
        if bill.discount > 0:
            amount_rows.append(["Discount", f"- {self.currency_symbol} {bill.discount:,.2f}"])
        if arrears:
            amount_rows.append([f"Current Bill Due ({bill.billing_period})", f"{self.currency_symbol} {bill.total_amount:,.2f}"])
            for arr in arrears:
                amount_rows.append([
                    f"Previous Overdue ({arr['billing_period']}) - {arr['bill_number']}",
                    f"{self.currency_symbol} {arr['balance']:,.2f}",
                ])
            amount_rows.append(["TOTAL PREVIOUS ARREARS", f"{self.currency_symbol} {total_arrears:,.2f}"])
            amount_rows.append(["GRAND TOTAL OUTSTANDING DUE", f"{self.currency_symbol} {grand_total:,.2f}"])
        else:
            amount_rows.append(["TOTAL DUE", f"{self.currency_symbol} {bill.total_amount:,.2f}"])

        qr_data = PaymentQrEngine.from_settings(
            getattr(self, "settings", None),
            payable_amount,
            bill.bill_number,
            bill.student_name,
            bill.course_name,
        )
        show_qr = qr_data and (not getattr(self, "settings", None) or self.settings.get_bool("payment_qr_show_on_due_bills", True)) and payable_amount > 0

        amounts_style = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263B50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]
        if arrears:
            amounts_style.extend([
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#92400E")),
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#D97706")),
            ])

        if show_qr:
            amounts = Table(amount_rows, colWidths=[70 * mm, 38 * mm])
            amounts.setStyle(TableStyle(amounts_style))

            qr_drawing = PaymentQrEngine.build_reportlab_flowable(qr_data, size_mm=35.0)
            qr_caption_style = ParagraphStyle("QrCaption", parent=styles["BodyText"], fontSize=8, leading=10, alignment=1, textColor=colors.HexColor("#102A43"))
            qr_sub_style = ParagraphStyle("QrSub", parent=styles["BodyText"], fontSize=7, leading=9, alignment=1, textColor=colors.HexColor("#64748B"))

            caption_label = f"<b>📱 Scan to Pay Grand Total ({qr_data.provider})</b>" if arrears else f"<b>📱 Scan to Pay ({qr_data.provider})</b>"
            qr_content = [
                Paragraph(caption_label, qr_caption_style),
                Spacer(1, 1.5 * mm),
                qr_drawing,
                Spacer(1, 1.5 * mm),
                Paragraph(qr_data.instructions, qr_sub_style),
            ]

            combo_table = Table([[amounts, qr_content]], colWidths=[110 * mm, 64 * mm])
            combo_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("BOX", (1, 0), (1, 0), 0.6, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
                ("PADDING", (1, 0), (1, 0), 5),
            ]))
            story.extend([combo_table, Spacer(1, 12 * mm)])
        else:
            amounts=Table(amount_rows,colWidths=[125*mm,48*mm])
            amounts.setStyle(TableStyle(amounts_style))
            story.extend([amounts,Spacer(1,14*mm)])

        story.extend([Paragraph("Please pay by the due date. Keep this bill for your records.",styles["BodyText"]),Spacer(1,12*mm),Paragraph("Authorized Signature: ______________________________",styles["BodyText"])]);doc.build(story)
        self.repository.set_pdf(bill.id,str(output));return output

    def create_batch_pdf(self,bills:list,output:Path|None=None)->Path:
        if not bills:raise ValueError("Select at least one bill.")
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import HRFlowable,KeepTogether,PageBreak,Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        from elh.core.payment_qr import PaymentQrEngine
        safe_date=bills[0].issue_date.replace("/","-")
        output=output or ROOT_DIR/"output"/"pdf"/f"due_bills_batch_{safe_date}.pdf"
        output.parent.mkdir(parents=True,exist_ok=True);styles=getSampleStyleSheet();story=[]
        compact_title=ParagraphStyle("BatchTitle",parent=styles["Heading2"],fontSize=16,leading=18,alignment=1,spaceAfter=3)
        compact_heading=ParagraphStyle("BatchHeading",parent=styles["Heading3"],fontSize=12,leading=14,alignment=1,spaceAfter=5)
        compact_body=ParagraphStyle("BatchBody",parent=styles["BodyText"],fontSize=9,leading=12,alignment=1)
        signature_style=ParagraphStyle("BatchSignature",parent=compact_body,alignment=1,fontSize=9)
        qr_caption_style = ParagraphStyle("BatchQrCaption", parent=compact_body, fontSize=7, leading=8, alignment=1)

        for index,bill in enumerate(bills):
            if index and index%2==0:story.append(PageBreak())
            elif index:story.extend([Spacer(1,6*mm),HRFlowable(width="90%",thickness=1.2,color=colors.HexColor("#667788"),hAlign="CENTER"),Spacer(1,6*mm)])
            bill_story=[Paragraph(self.app_title,compact_title),Paragraph("STUDENT DUE BILL",compact_heading),Spacer(1,3*mm)]
            details=[["Bill Number",bill.bill_number,"Billing Period",bill.billing_period],["Student",bill.student_name,"Course",bill.course_name],["Issue Date",bill.issue_date,"Due Date",bill.due_date],["Status",bill.status,"",""]]
            info=Table(details,colWidths=[27*mm,61*mm,27*mm,58*mm],hAlign="CENTER");info.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF0F6")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#EAF0F6")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("FONTSIZE",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));bill_story.extend([info,Spacer(1,4*mm)])

            arrears, total_arrears, grand_total = self.get_bill_arrears(bill)
            payable_amount = grand_total if arrears else bill.total_amount

            amount_rows = [["Description", "Amount"]]
            amount_rows.append([f"Course fee - {bill.course_name} ({bill.billing_period})", f"{self.currency_symbol} {bill.subtotal:,.2f}"])
            if bill.discount > 0:
                amount_rows.append(["Discount", f"- {self.currency_symbol} {bill.discount:,.2f}"])
            if arrears:
                amount_rows.append([f"Current Due ({bill.billing_period})", f"{self.currency_symbol} {bill.total_amount:,.2f}"])
                for arr in arrears:
                    amount_rows.append([
                        f"Overdue ({arr['billing_period']})",
                        f"{self.currency_symbol} {arr['balance']:,.2f}",
                    ])
                amount_rows.append(["GRAND TOTAL DUE", f"{self.currency_symbol} {grand_total:,.2f}"])
            else:
                amount_rows.append(["TOTAL DUE", f"{self.currency_symbol} {bill.total_amount:,.2f}"])

            qr_data = PaymentQrEngine.from_settings(
                getattr(self, "settings", None),
                payable_amount,
                bill.bill_number,
                bill.student_name,
                bill.course_name,
            )
            show_qr = qr_data and (not getattr(self, "settings", None) or self.settings.get_bool("payment_qr_show_on_due_bills", True)) and payable_amount > 0

            b_amounts_style = [
                ("GRID",(0,0),(-1,-1),0.5,colors.grey),
                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#263B50")),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("ALIGN",(1,1),(-1,-1),"RIGHT"),
                ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
                ("FONTSIZE",(0,0),(-1,-1),9),
                ("TOPPADDING",(0,0),(-1,-1),4),
                ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ]
            if arrears:
                b_amounts_style.extend([
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),
                    ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#92400E")),
                    ("LINEABOVE", (0, -1), (-1, -1), 1.0, colors.HexColor("#D97706")),
                ])

            if show_qr:
                amounts = Table(amount_rows, colWidths=[65 * mm, 38 * mm], hAlign="CENTER")
                amounts.setStyle(TableStyle(b_amounts_style))
                qr_drawing = PaymentQrEngine.build_reportlab_flowable(qr_data, size_mm=30.0)
                qr_cell = [
                    Paragraph(f"<b>Pay ({qr_data.provider})</b>", qr_caption_style),
                    Spacer(1, 1 * mm),
                    qr_drawing,
                ]
                combo = Table([[amounts, qr_cell]], colWidths=[110 * mm, 64 * mm], hAlign="CENTER")
                combo.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor("#CBD5E1")),
                    ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
                    ("PADDING", (1, 0), (1, 0), 4),
                ]))
                bill_story.extend([combo, Spacer(1, 4 * mm)])
            else:
                amounts=Table(amount_rows,colWidths=[125*mm,48*mm],hAlign="CENTER");amounts.setStyle(TableStyle(b_amounts_style));bill_story.extend([amounts,Spacer(1,5*mm)])

            bill_story.extend([Paragraph("Please pay by the due date. Keep this bill for your records.",compact_body),Spacer(1,5*mm),Paragraph("Authorized Signature:  ______________________________",signature_style),Spacer(1,3*mm)])
            story.append(KeepTogether(bill_story))
        SimpleDocTemplate(str(output),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=10*mm,bottomMargin=10*mm).build(story)
        for bill in bills:self.repository.set_pdf(bill.id,str(output))
        return output
    def print_pos_many(self,bills:list):
        if not bills:raise ValueError("Select at least one bill.")
        for bill in bills:self.print_pos(bill)
    def print_pos(self,bill):
        from elh.core.payment_qr import PaymentQrEngine
        arrears, total_arrears, grand_total = self.get_bill_arrears(bill)
        payable_amount = grand_total if arrears else bill.total_amount

        lines=[ReceiptLine(f"{bill.course_name} ({bill.billing_period})",bill.subtotal)]
        if bill.discount>0:lines.append(ReceiptLine("Discount",-bill.discount))
        if arrears:
            for arr in arrears:
                lines.append(ReceiptLine(f"Arrears ({arr['billing_period']})", arr["balance"]))

        qr_data = PaymentQrEngine.from_settings(
            getattr(self, "settings", None),
            payable_amount,
            bill.bill_number,
            bill.student_name,
            bill.course_name,
        )
        qr_payload = PaymentQrEngine.build_payload(qr_data) if (qr_data and payable_amount > 0) else ""
        qr_caption = f"Scan to Pay Grand Total ({qr_data.provider})" if (qr_data and arrears) else (f"Scan to Pay ({qr_data.provider})" if qr_data else "")

        receipt=Receipt(
            "ELH DUE BILL",bill.bill_number,bill.issue_date,bill.student_name,lines,f"DUE BY: {bill.due_date}",
            qr_payload=qr_payload,qr_caption=qr_caption,
        )
        self.printing.print_receipt(receipt);self.repository.mark_pos_printed(bill.id)

    def create_consolidated_statement_pdf(
        self,
        bills: list | None = None,
        student_id: int | None = None,
        output: Path | None = None,
    ) -> Path:
        if not bills and not student_id:
            raise ValueError("Provide either a list of bills or a student ID.")

        if not bills and student_id:
            if hasattr(self.repository, "get_unpaid_bills_for_student"):
                bills = self.repository.get_unpaid_bills_for_student(student_id)
            else:
                bills = [b for b in self.repository.list() if b.student_id == student_id and b.total_amount > b.paid_amount]

        if not bills:
            raise ValueError("No bills found to generate a consolidated statement.")

        student_names = {b.student_name for b in bills}
        if len(student_names) > 1:
            raise ValueError(f"All bills in a statement must belong to the same student. Found: {', '.join(student_names)}")

        bills = sorted(bills, key=lambda b: (b.issue_date, b.id))
        target_student_id = bills[0].student_id
        student_name = bills[0].student_name
        courses = list(dict.fromkeys(b.course_name for b in bills))
        courses_str = ", ".join(courses)

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from elh.core.payment_qr import PaymentQrEngine

        safe_name = student_name.replace(" ", "_").replace("/", "-").replace("\\", "-")
        safe_date = bills[-1].issue_date.replace("/", "-")
        output = output or ROOT_DIR / "output" / "pdf" / f"statement_{safe_name}_{safe_date}.pdf"
        output.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
        )

        title_style = ParagraphStyle(
            "StmtTitle",
            parent=styles["Title"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0F172A"),
            alignment=1,
            spaceAfter=2,
        )
        sub_style = ParagraphStyle(
            "StmtSub",
            parent=styles["Heading2"],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#0284C7"),
            alignment=1,
            spaceAfter=6,
        )
        normal_style = styles["BodyText"]

        story = [
            Paragraph(self.app_title, title_style),
            Paragraph("STUDENT FEE DUE STATEMENT / CONSOLIDATED BILL", sub_style),
            Spacer(1, 4 * mm),
        ]

        total_original = sum(b.total_amount for b in bills)
        total_paid = sum(b.paid_amount for b in bills)
        total_outstanding = sum(max(Decimal("0"), b.total_amount - b.paid_amount) for b in bills)

        meta_data = [
            ["Student Name", student_name, "Student ID", f"#{target_student_id}"],
            ["Course(s)", courses_str, "Unpaid Months", f"{len(bills)} bill(s)"],
            ["Statement Date", bills[-1].issue_date, "Total Dues", f"{self.currency_symbol} {total_outstanding:,.2f}"],
        ]
        meta_table = Table(meta_data, colWidths=[32 * mm, 60 * mm, 32 * mm, 54 * mm])
        meta_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([meta_table, Spacer(1, 6 * mm)])

        table_rows = [["Bill No.", "Period", "Course", "Total Bill", "Paid", "Balance Due"]]
        for b in bills:
            bal = max(Decimal("0"), b.total_amount - b.paid_amount)
            table_rows.append([
                b.bill_number,
                b.billing_period,
                b.course_name,
                f"{self.currency_symbol} {b.total_amount:,.2f}",
                f"{self.currency_symbol} {b.paid_amount:,.2f}",
                f"{self.currency_symbol} {bal:,.2f}",
            ])

        table_rows.append([
            "TOTAL OUTSTANDING BALANCE", "", "",
            f"{self.currency_symbol} {total_original:,.2f}",
            f"{self.currency_symbol} {total_paid:,.2f}",
            f"{self.currency_symbol} {total_outstanding:,.2f}",
        ])

        col_w = [40 * mm, 24 * mm, 44 * mm, 24 * mm, 22 * mm, 24 * mm]
        tbl = Table(table_rows, colWidths=col_w)
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("SPAN", (0, -1), (2, -1)),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#92400E")),
            ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#D97706")),
        ]))

        qr_data = PaymentQrEngine.from_settings(
            getattr(self, "settings", None),
            total_outstanding,
            f"STMT-{target_student_id}",
            student_name,
            courses_str,
        )
        show_qr = qr_data and (not getattr(self, "settings", None) or self.settings.get_bool("payment_qr_show_on_due_bills", True)) and total_outstanding > 0

        if show_qr:
            qr_drawing = PaymentQrEngine.build_reportlab_flowable(qr_data, size_mm=34.0)
            qr_caption_style = ParagraphStyle("QrCaption", parent=normal_style, fontSize=8, leading=10, alignment=1, textColor=colors.HexColor("#102A43"))
            qr_sub_style = ParagraphStyle("QrSub", parent=normal_style, fontSize=7, leading=9, alignment=1, textColor=colors.HexColor("#64748B"))

            qr_content = [
                Paragraph(f"<b>📱 Scan to Settle All Dues ({qr_data.provider})</b>", qr_caption_style),
                Spacer(1, 1.5 * mm),
                qr_drawing,
                Spacer(1, 1.5 * mm),
                Paragraph(qr_data.instructions, qr_sub_style),
            ]

            note_text = (
                "<b>Notice & Instructions:</b><br/>"
                "• This statement shows all outstanding fee bills up to the current date.<br/>"
                "• When making a combined payment, older months are automatically cleared first.<br/>"
                "• Any surplus or excess payment will be credited to student advance balance.<br/>"
                "• Please keep your payment receipts or digital transaction references safe."
            )
            note_p = Paragraph(note_text, ParagraphStyle("StmtNote", parent=normal_style, fontSize=8, leading=11, textColor=colors.HexColor("#475569")))

            bottom_table = Table([[note_p, qr_content]], colWidths=[118 * mm, 60 * mm])
            bottom_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("BOX", (1, 0), (1, 0), 0.6, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([tbl, Spacer(1, 6 * mm), bottom_table, Spacer(1, 8 * mm)])
        else:
            story.extend([tbl, Spacer(1, 12 * mm)])

        story.extend([
            Paragraph("Authorized Signature & Seal: ______________________________", normal_style)
        ])

        doc.build(story)
        return output
    def pay_bills(
        self,
        bill_ids: list[int],
        amount: Decimal,
        payment_date: str,
        account_id: int | None,
        method: str,
        receipt_no: str = "",
        remarks: str = "",
        discount: Decimal = Decimal("0"),
        allow_advance: bool = True,
    ) -> dict:
        amount = Decimal(str(amount))
        discount = Decimal(str(discount))
        if hasattr(self.repository, "record_multi_payment"):
            result = self.repository.record_multi_payment(
                bill_ids,
                amount,
                discount,
                payment_date,
                account_id,
                method,
                receipt_no,
                remarks,
                allow_advance=allow_advance,
            )
        else:
            tid = self.repository.record_payment(
                bill_ids[0] if bill_ids else 0,
                amount,
                discount,
                payment_date,
                account_id,
                method,
                receipt_no,
                remarks,
            )
            result = {
                "student_id": 0,
                "student_name": "",
                "transaction_ids": [tid] if tid else [],
                "updated_bills": [],
                "total_paid": amount,
                "total_discount": discount,
                "advance_amount": Decimal("0"),
            }
        if getattr(self, "notifications", None) and result.get("transaction_ids"):
            first_tid = result["transaction_ids"][0]
            contact = self.repository.student_contact(bill_ids[0]) if (bill_ids and hasattr(self.repository, "student_contact")) else ""
            bill_numbers = ", ".join(u["bill_number"] for u in result.get("updated_bills", []))
            first_bill = self.repository.get(bill_ids[0]) if bill_ids else None
            course_title = (
                getattr(first_bill, "course_name", "")
                if (first_bill and len(bill_ids) == 1)
                else f"{len(bill_ids)} bill(s)"
            )
            self.notifications.notify(
                "bill_payment",
                "student_transaction",
                first_tid,
                contact,
                {
                    "student_name": result.get("student_name", ""),
                    "bill_number": bill_numbers or "Advance",
                    "amount": f"{amount:,.2f}",
                    "discount": f"{discount:,.2f}",
                    "advance": f"{result.get('advance_amount', Decimal('0')):,.2f}",
                    "balance": "0.00" if result.get("advance_amount", Decimal("0")) > 0 else (f"{max(Decimal('0'), first_bill.total_amount - first_bill.paid_amount):,.2f}" if hasattr(first_bill, "total_amount") else "0.00"),
                    "payment_date": payment_date,
                    "course_name": course_title,
                },
            )
        return result

    def pay(
        self,
        bill_id: int,
        amount: Decimal,
        payment_date: str,
        account_id: int | None,
        method: str,
        receipt_no: str = "",
        remarks: str = "",
        discount: Decimal = Decimal("0"),
        allow_advance: bool = True,
    ):
        amount = Decimal(str(amount))
        discount = Decimal(str(discount))
        self.pay_bills(
            [bill_id],
            amount,
            payment_date,
            account_id,
            method,
            receipt_no,
            remarks,
            discount,
            allow_advance=allow_advance,
        )
        return self.repository.get(bill_id)

    def payment_alerts(self, include_suppressed: bool = False, student_id: int | None = None) -> list[dict]:
        """Return overdue payment alerts for unpaid bills whose due date has passed.
        
        Supports review status and follow-up suppression.
        """
        import nepali_datetime as nepali
        from datetime import datetime, date

        today_ad = datetime.now().date()
        today_bs = nepali.date.today().strftime("%Y/%m/%d")

        query = (
            "SELECT b.id, b.bill_number, b.enrollment_id, e.student_id, s.student_name, "
            "COALESCE(s.class_name, '') AS class_name, COALESCE(s.contact, '') AS contact, "
            "COALESCE(s.parent_name, '') AS parent_name, c.course_name, b.billing_period, "
            "b.issue_date, b.due_date, b.total_amount, b.paid_amount, "
            "(b.total_amount - b.paid_amount) AS balance, b.status "
            "FROM due_bills b "
            "JOIN enrollments e ON e.id = b.enrollment_id "
            "JOIN students s ON s.id = e.student_id "
            "JOIN courses c ON c.id = e.course_id "
            "WHERE b.status <> 'Paid' AND b.total_amount > b.paid_amount "
        )
        params: list = []
        if student_id:
            query += "AND e.student_id = ? "
            params.append(student_id)

        rows = self.repository.db.query(query, tuple(params))
        if not rows:
            return []

        review_rows = self.repository.db.query(
            "SELECT r.*, COALESCE(u.display_name, u.username, '') AS reviewer "
            "FROM payment_alert_reviews r "
            "LEFT JOIN app_users u ON u.id = r.reviewed_by_user_id "
            "WHERE r.id IN (SELECT MAX(id) FROM payment_alert_reviews GROUP BY bill_id)"
        )
        reviews = {int(r["bill_id"]): r for r in review_rows}

        alerts = []
        for b in rows:
            due_str = str(b["due_date"] or "").strip()
            if not due_str:
                continue

            clean_due = due_str.replace("-", "/")
            parts = clean_due.split("/")
            is_overdue = False
            days_overdue = 0
            try:
                if len(parts) >= 3 and int(parts[0]) > 2050:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    due_ad = nepali.date(y, m, d).to_datetime_date()
                    diff = (today_ad - due_ad).days
                    if diff > 0:
                        is_overdue = True
                        days_overdue = diff
                elif len(parts) >= 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    due_ad = date(y, m, d)
                    diff = (today_ad - due_ad).days
                    if diff > 0:
                        is_overdue = True
                        days_overdue = diff
            except Exception:
                if clean_due < today_bs:
                    is_overdue = True
                    days_overdue = 1

            if not is_overdue:
                continue

            review = reviews.get(int(b["id"]))
            review_status = review["review_status"] if review else "Not reviewed"
            follow_up_date = review["follow_up_date"] if review else ""
            clean_follow_up = str(follow_up_date or "").strip().replace("-", "/")

            is_future_follow_up = False
            if clean_follow_up:
                try:
                    f_parts = clean_follow_up.split("/")
                    if len(f_parts) >= 3 and int(f_parts[0]) > 2050:
                        f_ad = nepali.date(int(f_parts[0]), int(f_parts[1]), int(f_parts[2])).to_datetime_date()
                        is_future_follow_up = f_ad >= today_ad
                    elif len(f_parts) >= 3:
                        f_ad = date(int(f_parts[0]), int(f_parts[1]), int(f_parts[2]))
                        is_future_follow_up = f_ad >= today_ad
                except Exception:
                    is_future_follow_up = clean_follow_up >= today_bs

            suppressed = (
                review_status == "Suppressed"
                and (not clean_follow_up or is_future_follow_up)
            )
            if suppressed and not include_suppressed:
                continue
            if review_status == "Suppressed" and not suppressed:
                review_status = "Suppression expired"

            alerts.append({
                "bill_id": int(b["id"]),
                "bill_number": b["bill_number"],
                "student_id": int(b["student_id"]),
                "student_name": b["student_name"],
                "class_name": b["class_name"] or "",
                "contact": b["contact"] or "",
                "parent_name": b["parent_name"] or "",
                "course_name": b["course_name"] or "",
                "billing_period": b["billing_period"],
                "issue_date": b["issue_date"],
                "due_date": b["due_date"],
                "total_amount": float(b["total_amount"]),
                "paid_amount": float(b["paid_amount"]),
                "balance": float(b["balance"]),
                "days_overdue": days_overdue,
                "review_status": review_status,
                "review_note": review["note"] if review else "",
                "follow_up_date": follow_up_date or "",
                "reviewer": review["reviewer"] if review else "",
                "reviewed_at": review["created_at"] if review else None,
                "suppressed": suppressed,
            })

        return sorted(alerts, key=lambda x: (-x["days_overdue"], -x["balance"], x["student_name"].casefold()))

    def record_payment_alert_review(self, bill_id: int, status: str, note: str, follow_up_date: str, user_id: int | None) -> None:
        allowed = {
            "Contacted", "Promise to Pay", "Payment Plan", "Dispute / Under Review",
            "No Action Needed", "Suppressed", "Monitoring",
        }
        if status not in allowed:
            raise ValueError("Select a valid review status.")
        bill_row = self.repository.db.query_one(
            "SELECT e.student_id FROM due_bills b JOIN enrollments e ON e.id=b.enrollment_id WHERE b.id=?",
            (int(bill_id),)
        )
        if not bill_row:
            raise ValueError("Bill was not found.")
        student_id = int(bill_row["student_id"])
        self.repository.db.execute(
            "INSERT INTO payment_alert_reviews (bill_id, student_id, review_status, note, follow_up_date, reviewed_by_user_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (int(bill_id), student_id, status, note.strip(), follow_up_date.strip() or None, user_id),
        )
