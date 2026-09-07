from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from elh.config import ROOT_DIR
from elh.core.validation import today_iso
from elh.models import Receipt,ReceiptLine


class ReportsService:
    def __init__(self, db, app_title: str, currency_symbol: str, printing=None, settings=None):
        self.db=db;self.app_title=app_title;self.currency_symbol=currency_symbol;self.printing=printing;self.settings=settings

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
        """Print a short attendance follow-up list grouped by class/grade."""
        if not self.printing:
            raise ValueError("POS printing service is unavailable.")
        if not students:
            raise ValueError("There are no absent students to print.")
        grouped: dict[str, list[dict]] = {}
        for row in students:
            grade = str(row["class_name"] or "Not assigned").strip() or "Not assigned"
            grouped.setdefault(grade, []).append(row)

        def grade_order(label: str):
            try:
                return (0, int(label), label.casefold())
            except ValueError:
                return (1, 0, label.casefold())

        lines: list[ReceiptLine] = []
        for grade in sorted(grouped, key=grade_order):
            members = sorted(grouped[grade], key=lambda row: str(row["student_name"]).casefold())
            lines.append(ReceiptLine(f"GRADE {grade} — {len(members)}", Decimal("0")))
            lines.extend(
                ReceiptLine(f"  {index}. {row['student_name']}", Decimal("0"))
                for index, row in enumerate(members, start=1)
            )
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

    def current_table_pdf(
        self, title: str, headers: list[str], rows: list[list],
        column_widths: list[int] | None = None, output: Path | None = None,
    ) -> Path:
        """Print exactly the rows and columns currently visible in an application table."""
        if not headers:
            raise ValueError("There are no visible columns to print.")
        if not rows:
            raise ValueError("There are no displayed rows to print.")
        safe_name = "".join(character if character.isalnum() else "_" for character in title.lower()).strip("_")
        return self._build(
            output or self._path(f"current_table_{safe_name}.pdf"), title,
            "Current filtered and sorted view", "Current",
            headers, rows, [f"Total displayed rows: {len(rows)}", *[""] * (len(headers) - 1)],
            column_widths=column_widths,
        )

    def routine_pdf(
        self, class_level_id: int | None = None, output: Path | None = None,
        routine_plan_id: int | None = None, course_id: int | None = None,
        allowed_course_ids: list[int] | None = None, class_name: str | None = None,
        teacher_id: int | None = None,
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

        if teacher_id:
            where += " AND r.teacher_id=?"
            params += (int(teacher_id),)

        if class_level_id or class_name:
            alt_name = f"Grade {class_name}" if (class_name and str(class_name).isdigit()) else (str(class_name)[6:].strip() if (class_name and str(class_name).lower().startswith("grade ")) else (class_name or ""))
            where += " AND ((r.class_level_id=? AND r.class_level_id!=0) OR (r.class_name IS NOT NULL AND r.class_name!='' AND (r.class_name=? OR r.class_name=? OR cl.level_name=? OR cl.level_name=?)))"
            params += (int(class_level_id or 0), str(class_name or ""), str(alt_name), str(class_name or ""), str(alt_name))

        if course_id:
            where += " AND r.course_id=?"
            params += (int(course_id),)
        elif allowed_course_ids is not None:
            if allowed_course_ids:
                placeholders = ",".join("?" for _ in allowed_course_ids)
                where += f" AND (r.course_id IS NULL OR r.course_id IN ({placeholders}))"
                params += tuple(int(cid) for cid in allowed_course_ids)
            else:
                where += " AND r.course_id IS NULL"

        rows = self.db.query(
            "SELECT COALESCE(cl.level_name,r.class_name) class_name,r.day_of_week,"
            "r.period_label,r.subject_name,COALESCE(t.teacher_name,'') teacher,"
            "COALESCE(c.course_name,'') course_name "
            "FROM class_routines r LEFT JOIN routine_plans p ON p.id=r.routine_plan_id "
            "LEFT JOIN class_levels cl ON cl.id=r.class_level_id "
            "LEFT JOIN teachers t ON t.id=r.teacher_id "
            "LEFT JOIN courses c ON c.id=r.course_id " + where +
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
        for c_name in sorted(grouped, key=class_key):
            periods = sorted(grouped[c_name], key=period_key)
            span_start = len(table_data)
            for period_index, period in enumerate(periods):
                display_class = f"Grade {c_name}" if str(c_name).isdigit() else str(c_name)
                class_label = Paragraph(escape(display_class), row_label) if period_index == 0 else ""
                values = [class_label, Paragraph(f"{escape(period)}<br/>period", row_label)]
                for day in days:
                    entries = grouped[c_name][period].get(day, [])
                    if not entries:
                        values.append(Paragraph("", cell))
                        continue
                    content = "<br/><br/>".join(
                        escape(str(item["subject_name"] or ""))
                        + (f"<br/><font size=7 color='#0284c7'>[{escape(str(item['course_name']))}]</font>"
                           if item["course_name"] else "")
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

        suffix_parts = []
        if class_level_id:
            suffix_parts.append(f"class_{class_level_id}")
        elif class_name:
            suffix_parts.append(f"class_{class_name}")
        if course_id:
            suffix_parts.append(f"course_{course_id}")
        suffix = f"_{'_'.join(suffix_parts)}" if suffix_parts else "_all_classes"
        output = output or self._path(f"class_routine{suffix}.pdf")
        details = []
        if profile.get("pan_number"):
            details.append(f"PAN: {profile['pan_number']}")
        if profile.get("registration_number"):
            details.append(f"Reg. No: {profile['registration_number']}")
        details += [value for value in (
            profile.get("address"), profile.get("phone"), profile.get("email"), profile.get("website")
        ) if value]
        c_filter_name = ""
        if course_id:
            c_row = self.db.query_one("SELECT course_name FROM courses WHERE id=?", (int(course_id),))
            if c_row:
                c_filter_name = str(c_row["course_name"])
        if class_level_id or class_name:
            c_label = class_name or next(iter(grouped), "")
            cls_str = f"Class {c_label}" if not str(c_label).lower().startswith("grade") and not str(c_label).lower().startswith("class") else str(c_label)
            selected_label = f"{cls_str} ({c_filter_name})" if c_filter_name else cls_str
        elif c_filter_name:
            selected_label = c_filter_name
        else:
            selected_label = next(iter(grouped)) if len(grouped) == 1 else "All Classes"
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
        footer=f"Method: {proof['method']}\nAccount: {proof['account']}{discount_note}{attendance_note}\nVERIFIED PAYMENT RECEIPT"

        from elh.core.payment_qr import PaymentQrEngine
        qr_data = PaymentQrEngine.from_settings(
            getattr(self, "settings", None),
            proof["total"],
            proof["number"],
            proof["person"],
            proof["kind"],
        )
        qr_payload = PaymentQrEngine.build_payload(qr_data) if qr_data else ""
        qr_caption = "Receipt Verification" if qr_data else ""

        self.printing.print_receipt(Receipt(
            proof["kind"],proof["number"],proof["date"],proof["person"],lines,footer,
            qr_payload=qr_payload,qr_caption=qr_caption,
        ))

    def payment_proof_pdf(self,kind:str,record_id:int,output:Path|None=None)->Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
        from elh.core.payment_qr import PaymentQrEngine
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

        qr_data = PaymentQrEngine.from_settings(
            getattr(self, "settings", None),
            proof["total"],
            proof["number"],
            proof["person"],
            proof["kind"],
        )
        show_qr = qr_data and (not getattr(self, "settings", None) or self.settings.get_bool("payment_qr_show_on_receipts", True))

        if show_qr:
            amounts=Table(lines,colWidths=[90*mm,35*mm])
            amounts.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.HexColor("#CBD5E1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183B56")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#DDF4EF")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("ALIGN",(1,1),(1,-1),"RIGHT"),("PADDING",(0,0),(-1,-1),6)]))

            qr_drawing = PaymentQrEngine.build_reportlab_flowable(qr_data, size_mm=30.0)
            qr_caption_style = ParagraphStyle("QrCaptionProof", parent=styles["BodyText"], fontSize=8, leading=10, alignment=1, textColor=colors.HexColor("#102A43"))
            qr_sub_style = ParagraphStyle("QrSubProof", parent=styles["BodyText"], fontSize=7, leading=9, alignment=1, textColor=colors.HexColor("#64748B"))
            qr_box = [
                Paragraph("<b>Verified Receipt</b>", qr_caption_style),
                Spacer(1, 1 * mm),
                qr_drawing,
                Spacer(1, 1 * mm),
                Paragraph(f"Ref: {proof['number']}", qr_sub_style),
            ]
            combo = Table([[amounts, qr_box]], colWidths=[130*mm, 60*mm])
            combo.setStyle(TableStyle([
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("ALIGN", (1,0), (1,0), "CENTER"),
                ("BOX", (1,0), (1,0), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (1,0), (1,0), colors.HexColor("#F8FAFC")),
                ("PADDING", (1,0), (1,0), 5),
            ]))
            story.extend([combo, Spacer(1, 8*mm)])
        else:
            amounts=Table(lines,colWidths=[145*mm,45*mm]);amounts.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.HexColor("#CBD5E1")),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183B56")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#DDF4EF")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("ALIGN",(1,1),(1,-1),"RIGHT"),("PADDING",(0,0),(-1,-1),7)]));story.extend([amounts,Spacer(1,8*mm)])

        if proof["remarks"]:story.extend([Paragraph(f"Remarks: {proof['remarks']}",styles["BodyText"]),Spacer(1,8*mm)])
        story.extend([Spacer(1,10*mm),Table([["Receiver Signature: ____________________","Authorized Signature: ____________________"]],colWidths=[95*mm,95*mm])])
        SimpleDocTemplate(str(output),pagesize=A4,leftMargin=10*mm,rightMargin=10*mm,topMargin=12*mm,bottomMargin=12*mm,title=proof["kind"]).build(story);return output

    def _path(self,name):
        path=ROOT_DIR/"output"/"pdf"/name;path.parent.mkdir(parents=True,exist_ok=True);return path
    def _money(self,value):return f"{float(value or 0):,.2f}"

    def _build(self,output,title,start_date,end_date,headers,rows,total_row,column_widths=None):
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
        if column_widths:
            total_width = sum(max(1, int(width)) for width in column_widths)
            widths = [277 * max(1, int(width)) / total_width for width in column_widths]
            from xml.sax.saxutils import escape
            cell_style = ParagraphStyle("TableCell", parent=styles["BodyText"], fontSize=6.8, leading=8.1)
            header_style = ParagraphStyle("TableHeader", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=1)
            total_style = ParagraphStyle("TableTotal", parent=cell_style, fontName="Helvetica-Bold")
            table_data = [
                [Paragraph(escape(str(value)), header_style) for value in headers],
                *[[Paragraph(escape(str(value or "")), cell_style) for value in row] for row in rows],
                [Paragraph(escape(str(value or "")), total_style) for value in total_row],
            ]
        elif len(headers) == 7:
            widths=[25,42,24,27,37,82,35] if "LEDGER" in title else [25,42,75,27,27,48,32]
        else:
            widths=[277 / len(headers)] * len(headers)
        table=Table(table_data,colWidths=[w*mm for w in widths],repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#183B56")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#DDF4EF")),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#CBD5E1")),("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,colors.HexColor("#F7FAFC")]),("FONTSIZE",(0,0),(-1,-1),7.5),("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(3,1),(4,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(table);SimpleDocTemplate(str(output),pagesize=landscape(A4),leftMargin=10*mm,rightMargin=10*mm,topMargin=10*mm,bottomMargin=14*mm,title=title).build(story,onFirstPage=page,onLaterPages=page);return output

    def student_profile_pdf(self, student_id: int, output: Path | None = None) -> Path:
        from io import BytesIO
        from PIL import Image as PILImage
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image as RLImage,
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        from elh.repositories import StudentRepository
        from elh.services.people import StudentService

        profile = StudentService(StudentRepository(self.db)).get_profile(student_id)
        student = profile["student"]
        financials = profile["financials"]
        attendance = profile["attendance"]

        company = self.company_profile()
        company_name = str(company.get("company_name") or getattr(self.app_title, "app_title", self.app_title) or "Expert Learning Hub")
        details = [v for v in (company.get("address"), company.get("phone"), company.get("email")) if v]
        if company.get("pan_number"):
            details.append(f"PAN: {company['pan_number']}")
        if company.get("registration_number"):
            details.append(f"Reg: {company['registration_number']}")

        safe_name = "".join(c for c in student["student_name"] if c.isalnum() or c in (" ", "-", "_")).strip()
        output = output or self._path(f"student_profile_{student_id}_{safe_name.replace(' ', '_')}.pdf")

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "InstituteTitle", parent=styles["Title"], fontSize=16, leading=19,
            textColor=colors.HexColor("#102A43"), alignment=1, fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "InstituteSub", parent=styles["BodyText"], fontSize=8, leading=10.5,
            textColor=colors.HexColor("#475569"), alignment=1,
        )
        banner_style = ParagraphStyle(
            "Banner", parent=styles["Heading2"], fontSize=10.5, leading=13,
            textColor=colors.white, alignment=1, fontName="Helvetica-Bold",
        )
        sec_heading_style = ParagraphStyle(
            "SecHeading", parent=styles["Heading3"], fontSize=9, leading=11,
            textColor=colors.HexColor("#183B56"), fontName="Helvetica-Bold",
        )
        body_bold = ParagraphStyle(
            "BodyBold", parent=styles["BodyText"], fontSize=7.5, leading=9.5,
            textColor=colors.HexColor("#1E293B"), fontName="Helvetica-Bold",
        )
        body_regular = ParagraphStyle(
            "BodyRegular", parent=styles["BodyText"], fontSize=7.5, leading=9.5,
            textColor=colors.HexColor("#334155"),
        )
        table_hdr = ParagraphStyle(
            "TableHdr", parent=styles["BodyText"], fontSize=7, leading=8.5,
            textColor=colors.white, fontName="Helvetica-Bold", alignment=0,
        )
        table_cell = ParagraphStyle(
            "TableCell", parent=styles["BodyText"], fontSize=7, leading=8.5,
            textColor=colors.HexColor("#1E293B"),
        )
        table_cell_right = ParagraphStyle(
            "TableCellR", parent=table_cell, alignment=2,
        )
        table_cell_bold = ParagraphStyle(
            "TableCellB", parent=table_cell, fontName="Helvetica-Bold",
        )

        story = []

        # Header Block
        story.append(Paragraph(company_name, title_style))
        if details:
            story.append(Spacer(1, 1 * mm))
            story.append(Paragraph(" • ".join(details), subtitle_style))
        story.append(Spacer(1, 2 * mm))

        # Title Banner Bar
        banner_table = Table([[Paragraph("STUDENT COMPREHENSIVE PROFILE & DOSSIER", banner_style)]], colWidths=[186 * mm])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#008F7A")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 2 * mm))

        # Bio & Photo Section
        photo_flowable = None
        if student.get("photo_data"):
            try:
                p_stream = BytesIO(student["photo_data"])
                with PILImage.open(p_stream) as pil_img:
                    pil_img = pil_img.convert("RGB")
                    pil_img.thumbnail((300, 380))
                    thumb_buf = BytesIO()
                    pil_img.save(thumb_buf, format="JPEG", quality=90)
                    thumb_buf.seek(0)
                photo_flowable = RLImage(thumb_buf, width=28 * mm, height=35 * mm)
            except Exception:
                photo_flowable = None

        if not photo_flowable:
            photo_box = Table(
                [[Paragraph("<b>[ PHOTO ]</b><br/><font size=6 color='#64748B'>Not on file</font>", ParagraphStyle("NoPhoto", parent=body_regular, alignment=1))]],
                colWidths=[28 * mm], rowHeights=[35 * mm]
            )
            photo_box.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))
            photo_flowable = photo_box
        else:
            photo_wrapper = Table([[photo_flowable]], colWidths=[30 * mm], rowHeights=[37 * mm])
            photo_wrapper.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#008F7A")),
                ("PADDING", (0, 0), (-1, -1), 1),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            photo_flowable = photo_wrapper

        bio_rows = [
            [
                Paragraph("<b>Student ID:</b>", body_regular), Paragraph(f"#{student['id']}", body_bold),
                Paragraph("<b>Status:</b>", body_regular), Paragraph(f"<font color='{'#15803D' if student['status'] == 'Active' else '#991B1B'}'><b>{student['status']}</b></font>", body_bold),
            ],
            [
                Paragraph("<b>Full Name:</b>", body_regular), Paragraph(student["student_name"], body_bold),
                Paragraph("<b>Gender:</b>", body_regular), Paragraph(student.get("gender") or "Not specified", body_regular),
            ],
            [
                Paragraph("<b>Class / Level:</b>", body_regular), Paragraph(student.get("class_level_name") or student.get("class_name") or "-", body_bold),
                Paragraph("<b>Date of Birth:</b>", body_regular), Paragraph(student.get("date_of_birth") or "-", body_regular),
            ],
            [
                Paragraph("<b>School / College:</b>", body_regular), Paragraph(student.get("school_name") or "-", body_regular),
                Paragraph("<b>Joining Date:</b>", body_regular), Paragraph(student.get("joining_date") or "-", body_regular),
            ],
            [
                Paragraph("<b>Primary Contact:</b>", body_regular), Paragraph(student.get("contact") or "-", body_bold),
                Paragraph("<b>Biometric Device:</b>", body_regular), Paragraph(student.get("device_user_id") or "Not mapped", body_regular),
            ],
            [
                Paragraph("<b>Guardian:</b>", body_regular), Paragraph(f"{student.get('parent_name') or '-'} ({student.get('guardian_relationship') or 'Guardian'})", body_regular),
                Paragraph("<b>Address:</b>", body_regular), Paragraph(student.get("address") or "-", body_regular),
            ],
        ]
        bio_table = Table(bio_rows, colWidths=[25 * mm, 48 * mm, 25 * mm, 54 * mm])
        bio_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F8FAFC")),
            ("PADDING", (0, 0), (-1, -1), 2.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        top_combo = Table([[bio_table, photo_flowable]], colWidths=[152 * mm, 34 * mm])
        top_combo.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(top_combo)
        story.append(Spacer(1, 3 * mm))

        # SECTION 1: Active & Previous Enrollments
        story.append(Paragraph("1. COURSE ENROLLMENTS (ACTIVE & PREVIOUS)", sec_heading_style))
        story.append(Spacer(1, 1 * mm))

        enrollments = profile["active_enrollments"] + profile["previous_enrollments"]
        if enrollments:
            e_rows = [
                [
                    Paragraph("Course Name", table_hdr),
                    Paragraph("Category", table_hdr),
                    Paragraph("Level", table_hdr),
                    Paragraph("Start Date", table_hdr),
                    Paragraph("End Date", table_hdr),
                    Paragraph("Monthly Fee", table_hdr),
                    Paragraph("Status", table_hdr),
                ]
            ]
            for e in enrollments:
                stat_color = "#15803D" if e["status"] == "Active" else "#64748B"
                e_rows.append([
                    Paragraph(e["course_name"], table_cell_bold),
                    Paragraph(e["category"], table_cell),
                    Paragraph(e["level"], table_cell),
                    Paragraph(e["start_date"] or "-", table_cell),
                    Paragraph(e["end_date"] or "-", table_cell),
                    Paragraph(f"Rs. {float(e['monthly_fee']):,.2f}", table_cell_right),
                    Paragraph(f"<font color='{stat_color}'><b>{e['status']}</b></font>", table_cell),
                ])
            e_table = Table(e_rows, colWidths=[48 * mm, 26 * mm, 22 * mm, 22 * mm, 22 * mm, 26 * mm, 20 * mm])
            e_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B56")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("PADDING", (0, 0), (-1, -1), 2.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(e_table)
        else:
            story.append(Paragraph("<i>No course enrollments recorded for this student.</i>", body_regular))
        story.append(Spacer(1, 3 * mm))

        # SECTION 2: Account History & Pending Payments
        story.append(Paragraph("2. ACCOUNT HISTORY & PAYMENT STATUS", sec_heading_style))
        story.append(Spacer(1, 1 * mm))

        tot_billed = financials["total_billed"]
        tot_paid = financials["total_paid"]
        tot_due = financials["total_due"]
        due_color = "#DC2626" if tot_due > 0 else "#15803D"

        fin_summary_table = Table(
            [[
                Paragraph(f"Total Invoiced: <b>Rs. {tot_billed:,.2f}</b>", body_regular),
                Paragraph(f"Total Paid: <b>Rs. {tot_paid:,.2f}</b>", body_regular),
                Paragraph(f"Outstanding Due: <font color='{due_color}'><b>Rs. {tot_due:,.2f}</b></font>", body_bold),
            ]],
            colWidths=[62 * mm, 62 * mm, 62 * mm],
        )
        fin_summary_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("PADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(fin_summary_table)
        story.append(Spacer(1, 1.5 * mm))

        due_bills = financials["due_bills"][:6]
        if due_bills:
            b_rows = [
                [
                    Paragraph("Bill No.", table_hdr),
                    Paragraph("Period", table_hdr),
                    Paragraph("Course", table_hdr),
                    Paragraph("Due Date", table_hdr),
                    Paragraph("Total", table_hdr),
                    Paragraph("Paid", table_hdr),
                    Paragraph("Due Bal.", table_hdr),
                    Paragraph("Status", table_hdr),
                ]
            ]
            for b in due_bills:
                bal = float(b["balance"])
                b_stat = "#15803D" if b["status"] == "Paid" else ("#DC2626" if bal > 0 else "#D97706")
                b_rows.append([
                    Paragraph(b["bill_number"], table_cell_bold),
                    Paragraph(b["billing_period"], table_cell),
                    Paragraph(b["course_name"], table_cell),
                    Paragraph(b["due_date"] or "-", table_cell),
                    Paragraph(f"{float(b['total_amount']):,.2f}", table_cell_right),
                    Paragraph(f"{float(b['paid_amount']):,.2f}", table_cell_right),
                    Paragraph(f"<b>{bal:,.2f}</b>", table_cell_right),
                    Paragraph(f"<font color='{b_stat}'><b>{b['status']}</b></font>", table_cell),
                ])
            b_table = Table(b_rows, colWidths=[36 * mm, 20 * mm, 38 * mm, 22 * mm, 20 * mm, 20 * mm, 20 * mm, 10 * mm])
            b_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B56")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("PADDING", (0, 0), (-1, -1), 2.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(b_table)
        else:
            story.append(Paragraph("<i>No bills invoiced yet.</i>", body_regular))
        story.append(Spacer(1, 3 * mm))

        # SECTION 3: Current Month Attendance & History
        story.append(Paragraph(f"3. ATTENDANCE RECORD ({attendance['current_month']})", sec_heading_style))
        story.append(Spacer(1, 1 * mm))

        att_summary = Table(
            [[
                Paragraph(f"Current Month: <b>{attendance['current_month']}</b>", body_regular),
                Paragraph(f"Month Present Days: <b>{attendance['days_present_month']}</b>", body_regular),
                Paragraph(f"Month Total Punches: <b>{attendance['total_punches_month']}</b>", body_regular),
                Paragraph(f"Lifetime Days Present: <b>{attendance['lifetime_days']}</b>", body_regular),
            ]],
            colWidths=[46.5 * mm, 46.5 * mm, 46.5 * mm, 46.5 * mm],
        )
        att_summary.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("PADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(att_summary)
        story.append(Spacer(1, 1.5 * mm))

        recent_punches = attendance["recent_punches"][:8]
        if recent_punches:
            p_rows = [
                [
                    Paragraph("Date (AD)", table_hdr),
                    Paragraph("First In Time", table_hdr),
                    Paragraph("Last Out Time", table_hdr),
                    Paragraph("Punches Recorded", table_hdr),
                    Paragraph("Daily Status", table_hdr),
                ]
            ]
            for p in recent_punches:
                p_rows.append([
                    Paragraph(p["date"], table_cell_bold),
                    Paragraph(p["first_in"] or "-", table_cell),
                    Paragraph(p["last_out"] or "-", table_cell),
                    Paragraph(str(p["punch_count"]), table_cell_right),
                    Paragraph("<font color='#15803D'><b>Present</b></font>", table_cell),
                ])
            p_table = Table(p_rows, colWidths=[40 * mm, 36 * mm, 36 * mm, 38 * mm, 36 * mm])
            p_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B56")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("PADDING", (0, 0), (-1, -1), 2.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(p_table)
        else:
            story.append(Paragraph("<i>No attendance punches recorded for this month.</i>", body_regular))
        story.append(Spacer(1, 3 * mm))

        # SECTION 4: Certificates Issued
        certs = profile.get("certificates", [])
        if certs:
            story.append(Paragraph("4. CERTIFICATES & CREDENTIALS ISSUED", sec_heading_style))
            story.append(Spacer(1, 1 * mm))
            c_rows = [
                [
                    Paragraph("Certificate No.", table_hdr),
                    Paragraph("Course Snapshot", table_hdr),
                    Paragraph("Certify Date", table_hdr),
                    Paragraph("Status", table_hdr),
                ]
            ]
            for c in certs:
                c_rows.append([
                    Paragraph(c["certificate_number"], table_cell_bold),
                    Paragraph(c["course_name_snapshot"], table_cell),
                    Paragraph(c["certify_date"] or "-", table_cell),
                    Paragraph(f"<font color='#15803D'><b>{c['status']}</b></font>", table_cell),
                ])
            c_table = Table(c_rows, colWidths=[48 * mm, 78 * mm, 35 * mm, 25 * mm])
            c_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183B56")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("PADDING", (0, 0), (-1, -1), 2.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(c_table)
            story.append(Spacer(1, 3 * mm))

        # Remarks / Institutional Notes
        if student.get("remarks"):
            story.append(Paragraph("<b>Remarks / Institutional Notes:</b>", sec_heading_style))
            story.append(Paragraph(student["remarks"], body_regular))
            story.append(Spacer(1, 3 * mm))

        # Sign-off Area
        sign_table = Table(
            [[
                Paragraph("<b>Prepared By:</b><br/><br/>______________________", body_regular),
                Paragraph("<b>Checked By:</b><br/><br/>______________________", body_regular),
                Paragraph("<b>Principal / Authorized Stamp:</b><br/><br/>________________________________________", body_regular),
            ]],
            colWidths=[55 * mm, 55 * mm, 76 * mm],
        )
        sign_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(KeepTogether([Spacer(1, 3 * mm), sign_table]))

        footer_text = company.get("report_footer") or "Official ELH Student Academic & Financial Profile"
        def page_footer(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(colors.HexColor("#64748B"))
            canvas.drawString(12 * mm, 7 * mm, f"{footer_text} • Confidential")
            canvas.drawRightString(198 * mm, 7 * mm, f"Page {doc.page}")
            canvas.restoreState()

        SimpleDocTemplate(
            str(output),
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=12 * mm,
            title=f"Student Profile - {student['student_name']}",
        ).build(story, onFirstPage=page_footer, onLaterPages=page_footer)

        return output
