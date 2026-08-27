from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elh.config import ROOT_DIR, load_config
from elh.core.validation import validate_date
from elh.infrastructure import create_database
from elh.models import Student
from elh.services.auth import AuthService
from elh.services.container import ServiceContainer


class LoginRequest(BaseModel):
    username: str
    password: str


class StudentInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    class_name: str = ""
    school_id: int | None = None
    contact: str = ""
    gender: str = ""
    joining_date: str
    date_of_birth: str = ""
    parent_name: str = ""
    guardian_relationship: str = ""
    address: str = ""
    status: str = "Active"
    remarks: str = ""


class EnrollmentInput(BaseModel):
    student_id: int
    course_id: int
    level: str = ""
    start_date: str
    end_date: str = ""
    monthly_fee: float = 0
    admission_fee: float = 0
    discount: float = 0


class CourseInput(BaseModel):
    course_name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    billing_type: str = "Monthly"
    default_fee: float = 0
    duration_months: int = 0
    instructor_name: str = ""
    status: str = "Active"
    remarks: str = ""


class SchoolInput(BaseModel):
    school_name: str = Field(min_length=1, max_length=255)
    emis_id: str = ""
    address: str = ""
    contact: str = ""
    status: str = "Active"
    remarks: str = ""


class StaffInput(BaseModel):
    teacher_name: str = Field(min_length=1, max_length=255)
    staff_type: Literal["Teaching", "Non Teaching"] = "Teaching"
    contact: str = ""
    address: str = ""
    email: str = ""
    qualification: str = ""
    subject: str = ""
    joined_date: str
    salary_type: str = "Monthly Salary"
    basic_salary: float = 0
    status: str = "Active"
    remarks: str = ""


class AccountInput(BaseModel):
    account_name: str = Field(min_length=1, max_length=255)
    account_type: str = "Cash Counter"
    bank_name: str = ""
    account_number: str = ""
    account_holder: str = ""
    opening_balance: float = 0
    status: str = "Active"
    remarks: str = ""


class MoneyRecordInput(BaseModel):
    record_date: str
    category: str = Field(min_length=1, max_length=255)
    particular: str = Field(min_length=1, max_length=500)
    amount: float = Field(gt=0)
    account_id: int
    party: str = ""
    payment_method: str = "Cash"
    reference_no: str = ""
    remarks: str = ""


class BillGenerationInput(BaseModel):
    enrollment_ids: list[int] = Field(min_length=1)
    start_month: str
    end_month: str
    issue_date: str
    due_date: str
    remarks: str = ""


class BillPaymentInput(BaseModel):
    amount: float = Field(ge=0)
    discount: float = Field(default=0, ge=0)
    payment_date: str
    account_id: int | None = None
    payment_method: str = "Cash"
    receipt_no: str = ""
    remarks: str = ""


class ManualAttendanceInput(BaseModel):
    person_type: Literal["student", "teacher"]
    person_id: int
    attendance_date: str
    attendance_time: str
    reason: str = Field(min_length=1)


class AttendanceReviewInput(BaseModel):
    status: Literal[
        "Contacted", "Monitoring", "Approved Leave", "Left Institution",
        "No Action Needed", "Suppressed",
    ]
    note: str = ""
    follow_up_date: str = ""


class CompanyProfileInput(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    pan_number: str = ""
    registration_number: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    principal_name: str = ""
    report_footer: str = ""


class TransferInput(BaseModel):
    transfer_date: str
    from_account_id: int
    to_account_id: int
    amount: float = Field(gt=0)
    transfer_charge: float = Field(default=0, ge=0)
    reference_no: str = ""
    remarks: str = ""


class TodoInput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    details: str = ""
    assigned_teacher_id: int | None = None
    due_date: str = ""
    priority: Literal["Low", "Normal", "High"] = "Normal"


class BugReportInput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    details: str = Field(min_length=1)
    page_name: str = ""
    severity: Literal["Low", "Normal", "High", "Critical"] = "Normal"


def create_app() -> FastAPI:
    """Create the web adapter without changing the existing business services."""
    config = load_config()
    db = create_database(config)
    services = ServiceContainer.build(config, db)
    auth = AuthService(db, config)
    auth.ensure_initial_users()
    # Tokens intentionally live only in process memory. A server restart signs users out.
    sessions: dict[str, object] = {}
    app = FastAPI(title="ELH Web", version="1.0.0")
    static_dir = ROOT_DIR / "web"

    def records(rows):
        return [dict(row) for row in rows]

    def positive(value: float, field_name: str) -> Decimal:
        amount = Decimal(str(value))
        if amount <= 0:
            raise HTTPException(status_code=422, detail=f"{field_name} must be greater than zero.")
        return amount

    def session(authorization: str | None = Header(default=None)):
        token = (authorization or "").removeprefix("Bearer ").strip()
        user = sessions.get(token)
        if not user:
            raise HTTPException(status_code=401, detail="Please sign in.")
        return user

    def require(permission: str):
        def dependency(user=Depends(session)):
            if not auth.has_permission(user, permission):
                raise HTTPException(status_code=403, detail="You do not have permission for this action.")
            return user
        return dependency

    @app.post("/api/auth/login")
    def login(payload: LoginRequest):
        user = auth.authenticate(payload.username, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        token = secrets.token_urlsafe(32)
        sessions[token] = user
        return {"token": token, "user": {"username": user.username, "display_name": user.display_name, "role": user.role, "permissions": sorted(user.permissions)}}

    @app.post("/api/auth/logout")
    def logout(authorization: str | None = Header(default=None)):
        sessions.pop((authorization or "").removeprefix("Bearer ").strip(), None)
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(user=Depends(session)):
        return {"username": user.username, "display_name": user.display_name, "role": user.role, "permissions": sorted(user.permissions)}

    @app.get("/api/dashboard")
    def dashboard(_user=Depends(require("dashboard.view"))):
        metrics = db.query_one(
            "SELECT (SELECT COUNT(*) FROM students WHERE status<>'Archived') students,"
            "(SELECT COUNT(*) FROM teachers WHERE status='Active') staff,"
            "(SELECT COUNT(*) FROM enrollments WHERE status='Active') enrollments,"
            "(SELECT COALESCE(SUM(charge_amount-payment_amount-discount_amount),0) FROM student_transactions) outstanding"
        )
        result = dict(metrics)
        result["outstanding"] = float(result["outstanding"] or 0)
        return {
            "metrics": result,
            "punched_not_enrolled": records(services.attendance.students_punched_not_enrolled()),
            "present_today": records(services.attendance.students_present_today()),
            "attendance_alerts": records(services.attendance.student_attendance_alerts()),
        }

    @app.get("/api/students")
    def students(query: str = "", status: str = "All", _user=Depends(require("students.manage"))):
        clauses, params = ["s.status <> 'Archived'"], []
        if status in {"Active", "Inactive"}:
            clauses.append("s.status=?"); params.append(status)
        if query.strip():
            clauses.append("(s.student_name LIKE ? OR s.contact LIKE ? OR COALESCE(sc.school_name,'') LIKE ?)")
            params.extend([f"%{query.strip()}%"] * 3)
        rows = db.query(
            "SELECT s.id,s.student_name,s.class_name,COALESCE(sc.school_name,'') school_name,s.contact,s.gender,s.joining_date,s.status,"
            "CASE WHEN EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id=s.id AND e.status='Active') THEN 1 ELSE 0 END enrolled "
            "FROM students s LEFT JOIN schools sc ON sc.id=s.school_id WHERE " + " AND ".join(clauses) + " ORDER BY s.student_name",
            tuple(params),
        )
        return records(rows)

    @app.get("/api/students/{student_id}")
    def student_detail(student_id: int, _user=Depends(require("students.manage"))):
        student = services.students.get(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student was not found.")
        return {key: value for key, value in student.__dict__.items() if key != "photo_data"}

    @app.post("/api/students", status_code=201)
    def create_student(payload: StudentInput, _user=Depends(require("students.manage"))):
        student = Student(
            id=None, name=payload.name, class_name=payload.class_name,
            school_id=payload.school_id, contact=payload.contact, gender=payload.gender,
            date_of_birth=payload.date_of_birth, parent_name=payload.parent_name,
            guardian_relationship=payload.guardian_relationship,
            joining_date=payload.joining_date, address=payload.address,
            status=payload.status, remarks=payload.remarks,
        )
        student_id = services.students.register(student)
        if payload.class_name:
            level = db.query_one("SELECT id FROM class_levels WHERE level_name=?", (payload.class_name,))
            db.execute("UPDATE students SET class_level_id=? WHERE id=?", (level["id"] if level else None, student_id))
        return {"id": student_id}

    @app.put("/api/students/{student_id}")
    def update_student(student_id: int, payload: StudentInput, _user=Depends(require("students.manage"))):
        existing = services.students.get(student_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Student was not found.")
        services.students.update(Student(
            id=student_id, name=payload.name, class_name=payload.class_name,
            school_id=payload.school_id, contact=payload.contact, gender=payload.gender,
            date_of_birth=payload.date_of_birth, parent_name=payload.parent_name,
            guardian_relationship=payload.guardian_relationship,
            joining_date=payload.joining_date, photo_data=existing.photo_data,
            photo_mime_type=existing.photo_mime_type, address=payload.address,
            status=payload.status, remarks=payload.remarks,
        ))
        if payload.class_name:
            level = db.query_one("SELECT id FROM class_levels WHERE level_name=?", (payload.class_name,))
            db.execute("UPDATE students SET class_level_id=? WHERE id=?", (level["id"] if level else None, student_id))
        return {"ok": True}

    @app.post("/api/students/{student_id}/archive")
    def archive_student(student_id: int, _user=Depends(require("students.manage"))):
        services.students.archive(student_id)
        return {"ok": True}

    @app.get("/api/courses")
    def courses(include_inactive: bool = False, _user=Depends(require("enrollments.manage"))):
        sql = "SELECT * FROM courses"
        if not include_inactive:
            sql += " WHERE status='Active'"
        return records(db.query(sql + " ORDER BY category,course_name"))

    @app.post("/api/courses", status_code=201)
    def create_course(payload: CourseInput, _user=Depends(require("master_data.manage"))):
        course_id = db.execute(
            "INSERT INTO courses (course_name,category,billing_type,default_fee,duration_months,instructor_name,status,remarks) VALUES (?,?,?,?,?,?,?,?)",
            (payload.course_name.strip(), payload.category.strip(), payload.billing_type.strip(),
             str(Decimal(str(payload.default_fee))), max(0, payload.duration_months),
             payload.instructor_name.strip(), payload.status, payload.remarks.strip()),
        )
        return {"id": course_id}

    @app.put("/api/courses/{course_id}")
    def update_course(course_id: int, payload: CourseInput, _user=Depends(require("master_data.manage"))):
        db.execute(
            "UPDATE courses SET course_name=?,category=?,billing_type=?,default_fee=?,duration_months=?,instructor_name=?,status=?,remarks=? WHERE id=?",
            (payload.course_name.strip(), payload.category.strip(), payload.billing_type.strip(),
             str(Decimal(str(payload.default_fee))), max(0, payload.duration_months),
             payload.instructor_name.strip(), payload.status, payload.remarks.strip(), course_id),
        )
        return {"ok": True}

    @app.get("/api/schools")
    def schools(include_inactive: bool = False, _user=Depends(require("master_data.manage"))):
        sql = "SELECT * FROM schools"
        if not include_inactive:
            sql += " WHERE status='Active'"
        return records(db.query(sql + " ORDER BY school_name"))

    @app.post("/api/schools", status_code=201)
    def create_school(payload: SchoolInput, _user=Depends(require("master_data.manage"))):
        school_id = db.execute(
            "INSERT INTO schools (school_name,emis_id,address,contact,status,remarks) VALUES (?,?,?,?,?,?)",
            (payload.school_name.strip(), payload.emis_id.strip() or None, payload.address.strip(),
             payload.contact.strip(), payload.status, payload.remarks.strip()),
        )
        return {"id": school_id}

    @app.get("/api/lookups")
    def lookups(_user=Depends(session)):
        return {
            "schools": records(db.query("SELECT id,school_name FROM schools WHERE status='Active' ORDER BY school_name")),
            "classes": records(db.query("SELECT id,level_name FROM class_levels WHERE status='Active' ORDER BY level_name")),
            "accounts": records(db.query("SELECT id,account_name,account_type FROM accounts WHERE status='Active' ORDER BY account_name")),
        }

    @app.get("/api/enrollments")
    def enrollments(_user=Depends(require("enrollments.manage"))):
        rows = db.query("SELECT e.id,s.student_name,c.course_name,e.level,e.start_date,e.end_date,e.monthly_fee,e.status FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id ORDER BY e.start_date DESC,s.student_name")
        return records(rows)

    @app.post("/api/enrollments", status_code=201)
    def create_enrollment(payload: EnrollmentInput, _user=Depends(require("enrollments.manage"))):
        enrollment_id = services.enrollments.create(payload.student_id, payload.course_id, payload.level, payload.start_date, payload.end_date, payload.monthly_fee, payload.admission_fee, payload.discount, "Active", "")
        return {"id": enrollment_id}

    @app.get("/api/attendance/punched-not-enrolled")
    def punched_not_enrolled(_user=Depends(require("enrollments.manage"))):
        return records(services.attendance.students_punched_not_enrolled())

    @app.get("/api/attendance/present-today")
    def attendance_present_today(_user=Depends(require("devices.manage"))):
        return records(services.attendance.students_present_today())

    @app.get("/api/attendance/absent-today")
    def attendance_absent_today(_user=Depends(require("devices.manage"))):
        return records(services.attendance.students_absent_today())

    @app.get("/api/attendance/alerts")
    def attendance_alerts(include_suppressed: bool = False, _user=Depends(require("devices.manage"))):
        return records(services.attendance.student_attendance_alerts(include_suppressed))

    @app.get("/api/attendance/people")
    def attendance_people(_user=Depends(require("devices.manage"))):
        """Small, purpose-specific lookup used by manual attendance."""
        return {
            "students": records(db.query(
                "SELECT id,student_name FROM students WHERE status='Active' ORDER BY student_name"
            )),
            "staff": records(db.query(
                "SELECT id,teacher_name FROM teachers WHERE status='Active' ORDER BY teacher_name"
            )),
        }

    @app.post("/api/attendance/manual", status_code=201)
    def manual_attendance(payload: ManualAttendanceInput, _user=Depends(require("devices.manage"))):
        created = services.attendance.mark_manual_present(
            payload.person_type, payload.person_id, payload.attendance_date,
            payload.attendance_time, payload.reason,
        )
        return {"created": created}

    @app.post("/api/attendance/alerts/{student_id}/review")
    def review_attendance_alert(student_id: int, payload: AttendanceReviewInput, user=Depends(require("devices.manage"))):
        follow_up = validate_date(payload.follow_up_date, "Follow-up date", allow_blank=True, date_format=config.date_format)
        services.attendance.record_attendance_alert_review(student_id, payload.status, payload.note, follow_up, user.user_id)
        return {"ok": True}

    @app.get("/api/bills")
    def bills(_user=Depends(require("billing.manage"))):
        result = []
        for bill in services.billing.repository.list():
            result.append({
                "id": bill.id, "bill_number": bill.bill_number, "enrollment_id": bill.enrollment_id,
                "student_name": bill.student_name, "course_name": bill.course_name,
                "billing_period": bill.billing_period, "issue_date": bill.issue_date,
                "due_date": bill.due_date, "subtotal": float(bill.subtotal),
                "discount": float(bill.discount), "total_amount": float(bill.total_amount),
                "paid_amount": float(bill.paid_amount), "balance": float(bill.total_amount - bill.paid_amount),
                "status": bill.status,
            })
        return result

    @app.post("/api/bills/generate")
    def generate_bills(payload: BillGenerationInput, _user=Depends(require("billing.manage"))):
        validate_date(payload.issue_date, "Issue date", date_format=config.date_format)
        validate_date(payload.due_date, "Due date", date_format=config.date_format)
        result = services.billing.generate_combined_month_range(
            payload.enrollment_ids, payload.start_month, payload.end_month,
            payload.issue_date, payload.due_date, payload.remarks,
        )
        return {"created": sum(1 for item in result if item.created), "bill_ids": [item.bill.id for item in result]}

    @app.post("/api/bills/{bill_id}/payment")
    def pay_bill(bill_id: int, payload: BillPaymentInput, _user=Depends(require("billing.manage"))):
        validate_date(payload.payment_date, "Payment date", date_format=config.date_format)
        if payload.amount > 0 and not payload.account_id:
            raise HTTPException(status_code=422, detail="Select the receiving account.")
        bill = services.billing.pay(
            bill_id, Decimal(str(payload.amount)), payload.payment_date, payload.account_id,
            payload.payment_method, payload.receipt_no, payload.remarks,
            Decimal(str(payload.discount)),
        )
        return {"id": bill.id, "status": bill.status}

    @app.get("/api/staff")
    def staff(_user=Depends(require("staff.manage"))):
        return records(db.query(
            "SELECT id,teacher_name,staff_type,contact,email,subject,joined_date,salary_type,basic_salary,status FROM teachers ORDER BY teacher_name"
        ))

    @app.post("/api/staff", status_code=201)
    def create_staff(payload: StaffInput, _user=Depends(require("staff.manage"))):
        joined_date = validate_date(payload.joined_date, "Joined date", date_format=config.date_format)
        staff_id = db.execute(
            "INSERT INTO teachers (teacher_name,staff_type,contact,address,email,qualification,subject,joined_date,salary_type,basic_salary,status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (payload.teacher_name.strip(), payload.staff_type, payload.contact.strip(), payload.address.strip(),
             payload.email.strip(), payload.qualification.strip(), payload.subject.strip(), joined_date,
             payload.salary_type.strip(), str(Decimal(str(payload.basic_salary))), payload.status, payload.remarks.strip()),
        )
        services.staff_finance.sync_account(staff_id)
        return {"id": staff_id}

    @app.get("/api/accounts")
    def accounts(_user=Depends(require("finance.manage"))):
        rows = db.query("SELECT * FROM accounts ORDER BY account_name")
        return [{**dict(row), "balance": float(db.account_balance(row["id"]))} for row in rows]

    @app.post("/api/accounts", status_code=201)
    def create_account(payload: AccountInput, _user=Depends(require("finance.manage"))):
        account_id = db.execute(
            "INSERT INTO accounts (account_name,account_type,bank_name,account_number,account_holder,opening_balance,status,remarks) VALUES (?,?,?,?,?,?,?,?)",
            (payload.account_name.strip(), payload.account_type.strip(), payload.bank_name.strip(),
             payload.account_number.strip(), payload.account_holder.strip(), str(Decimal(str(payload.opening_balance))),
             payload.status, payload.remarks.strip()),
        )
        return {"id": account_id}

    def save_money_record(payload: MoneyRecordInput, record_type: str) -> int:
        record_date = validate_date(payload.record_date, "Record date", date_format=config.date_format)
        amount = positive(payload.amount, "Amount")
        account = db.query_one("SELECT id FROM accounts WHERE id=? AND status='Active'", (payload.account_id,))
        if not account:
            raise HTTPException(status_code=422, detail="Select an active account.")
        source, direction = ("Income", "IN") if record_type == "income" else ("Expense", "OUT")
        def callback(conn):
            if record_type == "income":
                cursor = conn.execute(
                    "INSERT INTO income_records (income_date,category,particular,amount,received_in_account_id,received_from,payment_method,reference_no,remarks) VALUES (?,?,?,?,?,?,?,?,?)",
                    (record_date, payload.category.strip(), payload.particular.strip(), str(amount), payload.account_id,
                     payload.party.strip(), payload.payment_method, payload.reference_no.strip(), payload.remarks.strip()),
                )
            else:
                cursor = conn.execute(
                    "INSERT INTO expense_records (expense_date,category,particular,amount,paid_from_account_id,paid_to,payment_status,payment_method,reference_no,remarks) VALUES (?,?,?,?,?,?,'Paid',?,?,?)",
                    (record_date, payload.category.strip(), payload.particular.strip(), str(amount), payload.account_id,
                     payload.party.strip(), payload.payment_method, payload.reference_no.strip(), payload.remarks.strip()),
                )
            record_id = int(cursor.lastrowid)
            cursor.close()
            db.add_ledger(conn, record_date, payload.account_id, direction, str(amount), source, record_id,
                          payload.particular.strip(), payload.reference_no.strip(), payload.remarks.strip())
            return record_id
        return db.transaction(callback)

    @app.get("/api/income")
    def income(_user=Depends(require("finance.manage"))):
        return records(db.query(
            "SELECT r.*,a.account_name FROM income_records r JOIN accounts a ON a.id=r.received_in_account_id ORDER BY r.income_date DESC,r.id DESC"
        ))

    @app.post("/api/income", status_code=201)
    def create_income(payload: MoneyRecordInput, _user=Depends(require("finance.manage"))):
        return {"id": save_money_record(payload, "income")}

    @app.get("/api/expenses")
    def expenses(_user=Depends(require("finance.manage"))):
        return records(db.query(
            "SELECT r.*,a.account_name,COALESCE(c.counterparty_name,r.paid_to,'') payee_name FROM expense_records r JOIN accounts a ON a.id=r.paid_from_account_id LEFT JOIN counterparties c ON c.id=r.counterparty_id ORDER BY r.expense_date DESC,r.id DESC"
        ))

    @app.post("/api/expenses", status_code=201)
    def create_expense(payload: MoneyRecordInput, _user=Depends(require("finance.manage"))):
        return {"id": save_money_record(payload, "expense")}

    @app.get("/api/ledger")
    def ledger(_user=Depends(require("reports.view"))):
        return records(db.query(
            "SELECT l.*,a.account_name FROM ledger l JOIN accounts a ON a.id=l.account_id ORDER BY l.transaction_date DESC,l.id DESC LIMIT 1000"
        ))

    @app.get("/api/transfers")
    def transfers(_user=Depends(require("finance.manage"))):
        return records(db.query(
            "SELECT tr.*,fa.account_name from_account,ta.account_name to_account "
            "FROM account_transfers tr JOIN accounts fa ON fa.id=tr.from_account_id "
            "JOIN accounts ta ON ta.id=tr.to_account_id ORDER BY tr.transfer_date DESC,tr.id DESC"
        ))

    @app.post("/api/transfers", status_code=201)
    def create_transfer(payload: TransferInput, _user=Depends(require("finance.manage"))):
        transfer_date = validate_date(payload.transfer_date, "Transfer date", date_format=config.date_format)
        if payload.from_account_id == payload.to_account_id:
            raise HTTPException(status_code=422, detail="Choose different source and destination accounts.")
        amount = positive(payload.amount, "Transfer amount")
        charge = Decimal(str(payload.transfer_charge))
        if db.account_balance(payload.from_account_id) < amount + charge:
            raise HTTPException(status_code=422, detail="The source account does not have enough balance.")
        def callback(conn):
            cursor = conn.execute(
                "INSERT INTO account_transfers (transfer_date,from_account_id,to_account_id,amount,transfer_charge,reference_no,remarks) VALUES (?,?,?,?,?,?,?)",
                (transfer_date, payload.from_account_id, payload.to_account_id, str(amount), str(charge),
                 payload.reference_no.strip(), payload.remarks.strip()),
            )
            transfer_id = int(cursor.lastrowid)
            cursor.close()
            db.add_ledger(conn, transfer_date, payload.from_account_id, "OUT", amount + charge,
                          "Account Transfer", transfer_id, "Transfer out", payload.reference_no.strip(), payload.remarks.strip())
            db.add_ledger(conn, transfer_date, payload.to_account_id, "IN", amount,
                          "Account Transfer", transfer_id, "Transfer in", payload.reference_no.strip(), payload.remarks.strip())
            return transfer_id
        return {"id": db.transaction(callback)}

    @app.get("/api/tasks")
    def tasks(_user=Depends(require("dashboard.view"))):
        return records(db.query(
            "SELECT t.*,COALESCE(s.teacher_name,'Unassigned') assigned_to "
            "FROM todo_items t LEFT JOIN teachers s ON s.id=t.assigned_teacher_id "
            "ORDER BY t.status='Done',t.due_date,t.id DESC"
        ))

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: TodoInput, user=Depends(require("dashboard.view"))):
        due_date = validate_date(payload.due_date, "Due date", allow_blank=True, date_format=config.date_format)
        return {"id": db.execute(
            "INSERT INTO todo_items (title,details,assigned_teacher_id,due_date,priority,status,created_by_user_id) VALUES (?,?,?,?,?,'Open',?)",
            (payload.title.strip(), payload.details.strip(), payload.assigned_teacher_id, due_date, payload.priority, user.user_id),
        )}

    @app.post("/api/tasks/{task_id}/complete")
    def complete_task(task_id: int, _user=Depends(require("dashboard.view"))):
        db.execute("UPDATE todo_items SET status='Done',completed_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
        return {"ok": True}

    @app.get("/api/bug-reports")
    def bug_reports(_user=Depends(require("dashboard.view"))):
        return records(db.query(
            "SELECT b.*,COALESCE(u.display_name,u.username,'Unknown') reported_by "
            "FROM bug_reports b LEFT JOIN app_users u ON u.id=b.reported_by_user_id ORDER BY b.status='Resolved',b.id DESC"
        ))

    @app.post("/api/bug-reports", status_code=201)
    def create_bug_report(payload: BugReportInput, user=Depends(require("dashboard.view"))):
        return {"id": db.execute(
            "INSERT INTO bug_reports (title,details,page_name,severity,status,reported_by_user_id) VALUES (?,?,?,?,'Open',?)",
            (payload.title.strip(), payload.details.strip(), payload.page_name.strip(), payload.severity, user.user_id),
        )}

    @app.get("/api/company-profile")
    def company_profile(_user=Depends(require("administration.manage"))):
        row = db.query_one("SELECT * FROM company_profile WHERE id=1")
        return dict(row) if row else {}

    @app.put("/api/company-profile")
    def update_company_profile(payload: CompanyProfileInput, _user=Depends(require("administration.manage"))):
        values = (payload.company_name, payload.pan_number, payload.registration_number, payload.address,
                  payload.phone, payload.email, payload.website, payload.principal_name, payload.report_footer)
        if db.query_one("SELECT id FROM company_profile WHERE id=1"):
            db.execute(
                "UPDATE company_profile SET company_name=?,pan_number=?,registration_number=?,address=?,phone=?,email=?,website=?,principal_name=?,report_footer=? WHERE id=1",
                values,
            )
        else:
            db.execute(
                "INSERT INTO company_profile (id,company_name,pan_number,registration_number,address,phone,email,website,principal_name,report_footer) VALUES (1,?,?,?,?,?,?,?,?,?)",
                values,
            )
        return {"ok": True}

    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    return app
