from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from elh.config import ROOT_DIR
from elh.core.validation import today_iso
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

    def unregistered_attendance_pdf(self, start_at: str, end_at: str, start_date: str, end_date: str, output: Path | None = None) -> Path:
        """Print device users who have attended but are not linked to a student/staff record."""
        rows = self.db.query(
            "SELECT base.device_user_id,COALESCE(u.device_name,'') device_name,COUNT(l.id) punches,"
            "MIN(l.occurred_at) first_seen,MAX(l.occurred_at) last_seen "
            "FROM (SELECT device_user_id FROM attendance_device_users UNION SELECT device_user_id FROM attendance_logs) base "
            "LEFT JOIN attendance_device_users u ON u.device_user_id=base.device_user_id "
            "JOIN attendance_logs l ON l.device_user_id=base.device_user_id "
            "LEFT JOIN device_user_mappings m ON m.device_user_id=base.device_user_id AND m.status='Active' "
            "WHERE m.id IS NULL AND l.occurred_at BETWEEN ? AND ? "
            "GROUP BY base.device_user_id,u.device_name ORDER BY last_seen DESC",
            (start_at, end_at),
        )
        data = [[r["device_user_id"], r["device_name"], r["punches"], str(r["first_seen"]), str(r["last_seen"])] for r in rows]
        return self._build(output or self._path(f"attendance_unregistered_{start_date.replace('/','-')}_{end_date.replace('/','-')}.pdf"), "ATTENDING DEVICE USERS NOT REGISTERED IN ELH", start_date, end_date, ["Device ID", "Name on Device", "Punches", "First Punch", "Last Punch"], data, ["", "TOTAL UNREGISTERED", str(len(rows)), "", ""])

    def punched_not_enrolled_pdf(self, start_at: str, end_at: str, start_date: str, end_date: str, output: Path | None = None) -> Path:
        rows = self.db.query(
            "SELECT s.id,s.student_name,s.class_name,s.contact,COUNT(l.id) punches,"
            "MIN(l.occurred_at) first_seen,MAX(l.occurred_at) last_seen "
            "FROM attendance_logs l JOIN students s ON s.id=l.person_id "
            "WHERE l.person_type='student' AND s.status='Active' AND l.occurred_at BETWEEN ? AND ? "
            "AND NOT EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id=s.id AND e.status='Active') "
            "GROUP BY s.id,s.student_name,s.class_name,s.contact ORDER BY last_seen DESC,s.student_name",
            (start_at, end_at),
        )
        data = [[r["id"], r["student_name"], r["class_name"] or "", r["contact"] or "", r["punches"], str(r["first_seen"]), str(r["last_seen"])] for r in rows]
        return self._build(output or self._path(f"attendance_punched_not_enrolled_{start_date.replace('/','-')}_{end_date.replace('/','-')}.pdf"), "STUDENTS PUNCHED BUT NOT ENROLLED", start_date, end_date, ["ID", "Student", "Class", "Contact", "Punches", "First Punch", "Last Punch"], data, ["", "TOTAL NOT ENROLLED", str(len(rows)), "", "", "", ""])

    def student_register_pdf(
        self,
        class_level_id: int | None = None,
        school_id: int | None = None,
        status: str = "All",
        output: Path | None = None,
    ) -> Path:
        """Build a current student register, optionally for one class or school."""
        where: list[str] = []
        params: list[int] = []
        if class_level_id:
            where.append("s.class_level_id=?")
            params.append(int(class_level_id))
        if school_id:
            where.append("s.school_id=?")
            params.append(int(school_id))
        if status in {"Active", "Inactive"}:
            where.append("s.status=?")
            params.append(status)
        condition = " WHERE " + " AND ".join(where) if where else ""
        rows = self.db.query(
            "SELECT s.id,s.student_name,COALESCE(cl.level_name,s.class_name,'') class_name,"
            "COALESCE(sc.school_name,'') school_name,s.contact,s.joining_date,s.status "
            "FROM students s "
            "LEFT JOIN class_levels cl ON cl.id=s.class_level_id "
            "LEFT JOIN schools sc ON sc.id=s.school_id" + condition +
            " ORDER BY COALESCE(cl.level_name,s.class_name,''),sc.school_name,s.student_name",
            tuple(params),
        )
        data = [[r["id"],r["student_name"],r["class_name"],r["school_name"],r["contact"] or "",r["joining_date"],r["status"]] for r in rows]
        scope: list[str] = []
        if class_level_id:
            row = self.db.query_one("SELECT level_name FROM class_levels WHERE id=?", (class_level_id,))
            scope.append(f"Class: {row['level_name'] if row else class_level_id}")
        if school_id:
            row = self.db.query_one("SELECT school_name FROM schools WHERE id=?", (school_id,))
            scope.append(f"School: {row['school_name'] if row else school_id}")
        if status in {"Active", "Inactive"}:
            scope.append(f"Status: {status}")
        suffix = "_".join(str(value) for value in (class_level_id, school_id, status.lower() if status != "All" else None) if value) or "all"
        return self._build(
            output or self._path(f"student_register_{suffix}.pdf"),
            "STUDENT REGISTER" + (" — " + " | ".join(scope) if scope else ""),
            " | ".join(scope) if scope else "All records", "Current",
            ["ID","Student","Class","School","Contact","Joining","Status"], data,
            ["","TOTAL STUDENTS",str(len(rows)),"","","",""]
        )

    def enrollment_register_pdf(self, status: str = "All", output: Path | None = None) -> Path:
        """Build a current enrollment register, optionally limited by its status."""
        where, params = "", ()
        if status in {"Active", "Inactive", "Completed", "Cancelled"}:
            where, params = " WHERE e.status=?", (status,)
        rows = self.db.query(
            "SELECT e.id,s.student_name,COALESCE(cl.level_name,s.class_name,'') class_name,"
            "COALESCE(sc.school_name,'') school_name,c.course_name,e.start_date,e.end_date,"
            "e.monthly_fee,e.status "
            "FROM enrollments e JOIN students s ON s.id=e.student_id "
            "JOIN courses c ON c.id=e.course_id "
            "LEFT JOIN class_levels cl ON cl.id=s.class_level_id "
            "LEFT JOIN schools sc ON sc.id=s.school_id" + where +
            " ORDER BY s.student_name,e.start_date,e.id",
            params,
        )
        data = [[r["id"],r["student_name"],r["class_name"],r["school_name"],r["course_name"],r["start_date"],r["end_date"] or "",self._money(r["monthly_fee"]),r["status"]] for r in rows]
        title = "ENROLLMENT REGISTER" + (f" — {status}" if status != "All" else "")
        return self._build(
            output or self._path(f"enrollment_register_{status.lower()}.pdf"), title,
            f"Status: {status}", "Current",
            ["ID","Student","Class","School","Course","Start","End","Monthly Fee","Status"], data,
            ["","TOTAL ENROLLMENTS",str(len(rows)),"","","","","",""]
        )

    def print_absent_students_pos(self, students: list[dict]) -> None:
        """Print a short attendance follow-up list without financial columns."""
        if not self.printing:
            raise ValueError("POS printing service is unavailable.")
        if not students:
            raise ValueError("There are no absent students to print.")
        lines = [
            ReceiptLine(
                f"{index}. {row['student_name']} ({row.get('class_name') or 'No class'})",
                Decimal("0"),
            )
            for index, row in enumerate(students, start=1)
        ]
        self.printing.print_receipt(Receipt(
            "ABSENT STUDENTS TODAY", f"ABS-{today_iso().replace('/', '-')}", today_iso(),
            lines=lines, footer=f"Total absent: {len(students)} | Attendance follow-up",
            show_amounts=False,
        ))

    def class_school_analysis_pdf(self, output: Path | None = None) -> Path:
        classes = self.db.query("SELECT COALESCE(cl.level_name,s.class_name,'Not assigned') label,COUNT(*) total FROM students s LEFT JOIN class_levels cl ON cl.id=s.class_level_id GROUP BY COALESCE(cl.level_name,s.class_name,'Not assigned') ORDER BY label")
        schools = self.db.query("SELECT COALESCE(sc.school_name,'Not assigned') label,COUNT(*) total FROM students s LEFT JOIN schools sc ON sc.id=s.school_id GROUP BY COALESCE(sc.school_name,'Not assigned') ORDER BY label")
        data = [["Class / Level", r["label"], r["total"]] for r in classes] + [["School", r["label"], r["total"]] for r in schools]
        return self._build(output or self._path("student_class_school_analysis.pdf"), "STUDENT COUNT ANALYSIS", "Current", "Current", ["Group","Class / School","Students"], data, ["","TOTAL STUDENTS",str(sum(int(r["total"]) for r in classes))])

    def current_table_pdf(self, title: str, headers: list[str], rows: list[list], output: Path | None = None) -> Path:
        """Print exactly the rows and columns currently visible in an application table."""
        if not headers:
            raise ValueError("There are no visible columns to print.")
        if not rows:
            raise ValueError("There are no displayed rows to print.")
        safe_name = "".join(character if character.isalnum() else "_" for character in title.lower()).strip("_")
        return self._build(
            output or self._path(f"current_table_{safe_name}.pdf"), title,
            "Current filtered and sorted view", "Current",
            headers, rows, ["TOTAL DISPLAYED ROWS", str(len(rows)), *[""] * (len(headers) - 2)],
        )

    def routine_pdf(
        self, class_level_id: int | None = None, output: Path | None = None,
        routine_plan_id: int | None = None,
    ) -> Path:
        """Render the routine as a day-by-day timetable, not a transaction list."""
        from xml.sax.saxutils import escape
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        days = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        where, params = "WHERE r.status='Active'", ()
        if routine_plan_id:
            where += " AND r.routine_plan_id=?"
            params += (int(routine_plan_id),)
        else:
            where += " AND p.status='Active'"
        if class_level_id:
            where += " AND r.class_level_id=?"
            params += (int(class_level_id),)
        rows = self.db.query(
            "SELECT COALESCE(cl.level_name,r.class_name) class_name,r.day_of_week,"
            "r.period_label,r.subject_name,COALESCE(t.teacher_name,'') teacher "
            "FROM class_routines r LEFT JOIN routine_plans p ON p.id=r.routine_plan_id "
            "LEFT JOIN class_levels cl ON cl.id=r.class_level_id "
            "LEFT JOIN teachers t ON t.id=r.teacher_id " + where +
            " ORDER BY CAST(COALESCE(cl.level_name,r.class_name) AS UNSIGNED),"
            "CASE r.day_of_week WHEN 'Sunday' THEN 1 WHEN 'Monday' THEN 2 "
            "WHEN 'Tuesday' THEN 3 WHEN 'Wednesday' THEN 4 WHEN 'Thursday' THEN 5 "
            "WHEN 'Friday' THEN 6 ELSE 7 END,r.period_label",
            params,
        )
        if not rows:
            raise ValueError("There are no active routine periods to print.")

        def class_key(value):
            try:
                return (0, int(str(value)))
            except ValueError:
                return (1, str(value).casefold())

        def period_key(value):
            text = str(value).strip()
            digits = "".join(char for char in text if char.isdigit())
            return (int(digits) if digits else 999, text.casefold())

        # A class can run parallel subjects in the same period. Keep every row
        # for a day rather than allowing the last one to overwrite the others.
        grouped: dict[str, dict[str, dict[str, list[dict]]]] = {}
        for row in rows:
            grouped.setdefault(str(row["class_name"]), {}).setdefault(
                str(row["period_label"]), {}
            ).setdefault(str(row["day_of_week"]), []).append(row)

        styles = getSampleStyleSheet()
        profile = self.company_profile()
        heading = ParagraphStyle(
            "RoutineCompany", parent=styles["Title"], fontSize=16, leading=18,
            textColor=colors.HexColor("#102A43"), alignment=1,
        )
        sub = ParagraphStyle(
            "RoutineSub", parent=styles["BodyText"], fontSize=7.5, leading=9,
            alignment=1, textColor=colors.HexColor("#475569"),
        )
        cell = ParagraphStyle(
            "RoutineCell", parent=styles["BodyText"], fontSize=7.5, leading=8.5,
            alignment=1, fontName="Helvetica-Bold",
        )
        row_label = ParagraphStyle(
            "RoutineRowLabel", parent=cell, textColor=colors.white, fontSize=8,
        )
        table_data = [["CLASS", "PERIOD", *[day.upper() for day in days]]]
        body_row_colors = []
        class_spans = []
        for class_name in sorted(grouped, key=class_key):
            periods = sorted(grouped[class_name], key=period_key)
            span_start = len(table_data)
            for period_index, period in enumerate(periods):
                class_label = Paragraph(f"Grade {escape(class_name)}", row_label) if period_index == 0 else ""
                values = [class_label, Paragraph(f"{escape(period)}<br/>period", row_label)]
                for day in days:
                    entries = grouped[class_name][period].get(day, [])
                    if not entries:
                        values.append(Paragraph("", cell))
                        continue
                    content = "<br/><br/>".join(
                        escape(str(item["subject_name"] or ""))
                        + (f"<br/><font size=7>{escape(str(item['teacher'] or ''))}</font>"
                           if item["teacher"] else "")
                        for item in entries
                    )
                    values.append(Paragraph(content, cell))
                table_data.append(values)
                body_row_colors.append(
                    colors.HexColor("#C5E6F5") if len(body_row_colors) % 2 == 0
                    else colors.HexColor("#8AC9E6")
                )
            if len(periods) > 1:
                class_spans.append((span_start, len(table_data) - 1))

        suffix = f"_class_{class_level_id}" if class_level_id else "_all_classes"
        output = output or self._path(f"class_routine{suffix}.pdf")
        details = []
        if profile.get("pan_number"):
            details.append(f"PAN: {profile['pan_number']}")
        if profile.get("registration_number"):
            details.append(f"Reg. No: {profile['registration_number']}")
        details += [value for value in (
            profile.get("address"), profile.get("phone"), profile.get("email"), profile.get("website")
        ) if value]
        selected_label = next(iter(grouped)) if class_level_id and len(grouped) == 1 else "All Classes"
        story = [
            Paragraph(profile.get("company_name") or self.app_title, heading),
            Paragraph(" | ".join(details), sub), Spacer(1, 2 * mm),
            Paragraph("WEEKLY CLASS ROUTINE", ParagraphStyle(
                "RoutineTitle", parent=styles["Heading2"], fontSize=14, leading=16, alignment=1,
                textColor=colors.HexColor("#008F7A"),
            )),
            Paragraph(f"{selected_label} | Printed: {today_iso()} (BS)", sub),
            Spacer(1, 3 * mm),
        ]
        table = Table(
            table_data, colWidths=[24 * mm, 18 * mm] + [39.1 * mm] * len(days), repeatRows=1
        )
        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D6989")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#1D6989")),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for index, background in enumerate(body_row_colors, start=1):
            table_style.append(("BACKGROUND", (2, index), (-1, index), background))
        for start_row, end_row in class_spans:
            table_style.append(("SPAN", (0, start_row), (0, end_row)))
        table.setStyle(TableStyle(table_style))
        story.append(table)

        footer = profile.get("report_footer") or "Computer generated report"
        def page(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#64748B"))
            canvas.drawString(14 * mm, 8 * mm, footer)
            canvas.drawRightString(283 * mm, 8 * mm, f"Page {doc.page}")
            canvas.restoreState()

        SimpleDocTemplate(
            str(output), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
            topMargin=10 * mm, bottomMargin=14 * mm, title="Weekly Class Routine",
        ).build(story, onFirstPage=page, onLaterPages=page)
        return output

    def staff_register_pdf(self, output: Path | None = None) -> Path:
        rows = self.db.query("SELECT id,teacher_name,staff_type,contact,subject,joined_date,status FROM teachers ORDER BY teacher_name")
        data = [[r["id"],r["teacher_name"],r["staff_type"],r["contact"] or "",r["subject"] or "",r["joined_date"],r["status"]] for r in rows]
        return self._build(output or self._path("staff_register.pdf"), "STAFF REGISTER", "All records", "Current", ["ID","Staff","Type","Contact","Subject","Joined","Status"], data, ["","TOTAL STAFF",str(len(rows)),"","","",""])

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
        story=[Paragraph(profile.get("company_name") or self.app_title,heading),Paragraph(" | ".join(details),sub),Spacer(1,4*mm),Paragraph(title,ParagraphStyle("Report",parent=styles["Heading2"],alignment=1,textColor=colors.HexColor("#008F7A"))),Paragraph(f"Period: {start_date} to {end_date} (BS)  |  Printed: {today_iso()} (BS)",sub),Spacer(1,5*mm)]
        table_data=[headers,*rows,total_row]
        if len(headers) == 7:
            widths=[25,42,24,27,37,82,35] if "LEDGER" in title else [25,42,75,27,27,48,32]
        else:
            widths=[277 / len(headers)] * len(headers)
        table=Table(table_data,colWidths=[w*mm for w in widths],repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183B56")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#DDF4EF")),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#CBD5E1")),("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,colors.HexColor("#F7FAFC")]),("FONTSIZE",(0,0),(-1,-1),7.5),("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(3,1),(4,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(table);SimpleDocTemplate(str(output),pagesize=landscape(A4),leftMargin=10*mm,rightMargin=10*mm,topMargin=10*mm,bottomMargin=14*mm,title=title).build(story,onFirstPage=page,onLaterPages=page);return output
