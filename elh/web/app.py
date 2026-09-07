from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import nepali_datetime as nepali

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elh.config import AppConfig, ROOT_DIR, load_config
from elh.core.backup import BackupService
from elh.core.health import HealthService
from elh.core.settings import SettingsService
from elh.core.validation import current_month, validate_date, validate_month
from elh.infrastructure import create_database
from elh.models import CertificateIssueRequest, Student, UserSession
from elh.services.assistant import InstituteAssistant
from elh.services.auth import AuthService, ROLES
from elh.services.container import ServiceContainer
from elh.web.security import RateLimiter, SecurityHeadersMiddleware, TokenManager


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


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


class EnrollmentUpdateInput(BaseModel):
    student_id: int | None = None
    course_id: int | None = None
    level: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    completion_date: str | None = None
    monthly_fee: float | None = None
    admission_fee: float | None = None
    discount: float | None = None
    status: str | None = None
    remarks: str | None = None


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
    bank_code: str = ""
    account_number: str = ""
    account_holder: str = ""
    opening_balance: float = 0
    is_billing_default: bool = False
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


class MultiBillPaymentInput(BaseModel):
    bill_ids: list[int] = Field(min_length=1)
    amount: float = Field(ge=0)
    discount: float = Field(default=0, ge=0)
    payment_date: str
    account_id: int | None = None
    payment_method: str = "Cash"
    receipt_no: str = ""
    remarks: str = ""


class AutoBillingRunInput(BaseModel):
    target_month: str = ""
    issue_date: str = ""
    due_date: str = ""
    send_sms: bool | None = None
    remarks: str = "Automated monthly recurring invoice"


class AutoBillingConfigInput(BaseModel):
    enabled: bool | None = None
    due_days: int | None = None
    auto_sms: bool | None = None


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


class PaymentAlertReviewInput(BaseModel):
    status: Literal[
        "Contacted", "Promise to Pay", "Payment Plan", "Dispute / Under Review",
        "No Action Needed", "Suppressed", "Monitoring",
    ]
    note: str = ""
    follow_up_date: str = ""


class PollerConfigInput(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = None


class PublicInquiryInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=6, max_length=50)
    email: str = ""
    course_interest: str = ""
    grade: str = ""
    message: str = ""


class CmsSectionUpdateInput(BaseModel):
    data: Any


class InquiryUpdateInput(BaseModel):
    status: str
    staff_notes: str = ""


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


class CalendarEventInput(BaseModel):
    event_name: str = Field(min_length=1, max_length=255)
    event_type: Literal["Holiday", "Closure", "Working Day", "Event"] = "Holiday"
    course_id: int | None = None
    start_date: str
    end_date: str = ""
    status: Literal["Active", "Inactive"] = "Active"
    remarks: str = ""


class BulkWeekendInput(BaseModel):
    month: str
    course_id: int | None = None
    weekend_days: list[Literal["Saturday", "Sunday"]] = ["Saturday", "Sunday"]
    event_type: Literal["Holiday", "Closure"] = "Holiday"
    remarks: str = ""


class AssistantQueryInput(BaseModel):
    prompt: str


class CertificateInput(BaseModel):
    enrollment_id: int
    certificate_number: str
    certify_date: str
    instructor_name: str = ""
    principal_name: str = ""
    remarks: str = ""


class StudentTransactionInput(BaseModel):
    student_id: int
    enrollment_id: int | None = None
    transaction_date: str
    transaction_type: str = "Payment Received"
    particular: str
    charge_amount: float = 0
    payment_amount: float = 0
    discount_amount: float = 0
    account_id: int | None = None
    payment_method: str = "Cash"
    receipt_no: str = ""
    remarks: str = ""


class GradeInput(BaseModel):
    short_name: str = Field(min_length=1, max_length=50)
    grade_name: str = Field(min_length=1, max_length=100)
    status: Literal["Active", "Inactive"] = "Active"
    remarks: str = ""


class ClassLevelInput(BaseModel):
    level_name: str = Field(min_length=1, max_length=100)
    status: Literal["Active", "Inactive"] = "Active"
    remarks: str = ""


class RoutinePlanInput(BaseModel):
    plan_name: str = Field(min_length=1, max_length=100)
    effective_from: str
    remarks: str = ""
    copy_from_plan_id: int | None = None
    archive_source: bool = True


class RoutinePeriodInput(BaseModel):
    class_name: str = Field(min_length=1, max_length=100)
    day_of_week: Literal["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    period_label: str = Field(min_length=1, max_length=50)
    subject_name: str = Field(min_length=1, max_length=150)
    class_level_id: int
    teacher_id: int | None = None
    course_id: int | None = None
    start_time: str = ""
    end_time: str = ""
    status: Literal["Active", "Inactive"] = "Active"
    remarks: str = ""
    routine_plan_id: int


class StaffAdvanceInput(BaseModel):
    teacher_id: int
    advance_date: str
    amount: float = Field(gt=0)
    paid_from_account_id: int
    payment_method: str = "Cash"
    reference_no: str = ""
    recovery_method: str = "Salary Deduction"
    recovery_start_month: str = ""
    monthly_deduction: float = 0
    remarks: str = ""


class SalaryCalculateInput(BaseModel):
    teacher_id: int
    salary_month: str


class SalaryPayoutInput(BaseModel):
    teacher_id: int
    salary_month: str
    basic_salary: float = Field(ge=0)
    extra_payment: float = 0
    bonus: float = 0
    allowance: float = 0
    advance_deduction: float = 0
    other_deduction: float = 0
    attendance_days: int = 0
    working_hours: float = 0
    class_count: int = 0
    payment_date: str
    paid_from_account_id: int
    payment_method: str = "Bank"
    voucher_no: str = ""
    remarks: str = ""


class SettingsUpdateInput(BaseModel):
    settings: dict[str, str]


class UserCreateInput(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6)
    display_name: str = Field(min_length=1, max_length=255)
    email: str = ""
    phone: str = ""
    role: str = "operator"
    status: Literal["Active", "Disabled"] = "Active"
    student_id: int | None = None
    teacher_id: int | None = None
    must_change_password: bool = False
    permissions: list[str] | None = None


class UserUpdateInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    email: str = ""
    phone: str = ""
    role: str
    status: Literal["Active", "Disabled"] = "Active"
    student_id: int | None = None
    teacher_id: int | None = None
    must_change_password: bool | None = None
    permissions: list[str] | None = None


class UserResetPasswordInput(BaseModel):
    new_password: str = Field(min_length=6)
    must_change_password: bool = True


class UserStatusToggleInput(BaseModel):
    status: Literal["Active", "Disabled"]


class ProxyLeaveRequestInput(BaseModel):
    routine_id: int
    class_date: str
    reason: str = ""
    leave_type: str = "Absent"
    original_teacher_id: int | None = None
    proxy_teacher_id: int | None = None


class ProxyAssignInput(BaseModel):
    proxy_teacher_id: int
    admin_note: str = ""


class ProxyStatusInput(BaseModel):
    status: Literal["Approved", "Rejected"]
    admin_note: str = ""


class ProxyResponseInput(BaseModel):
    response: Literal["Accept", "Decline"]
    declined_reason: str = ""


class ProxySmsModeInput(BaseModel):
    mode: Literal["disabled", "manual", "auto"]



def create_app(app_config: AppConfig | None = None) -> FastAPI:
    """Create the web adapter without changing the existing business services."""
    config = app_config or load_config()
    db = create_database(config)
    services = ServiceContainer.build(config, db)
    auth = AuthService(db, config)
    auth.ensure_initial_users()
    token_manager = TokenManager(config.secret_key or None)
    rate_limiter = RateLimiter(max_attempts=5, window_seconds=60, lock_seconds=300)

    app = FastAPI(title="ELH Web", version="1.0.0")
    app.state.services = services
    app.state.auth = auth
    app.state.token_manager = token_manager
    app.add_middleware(SecurityHeadersMiddleware)
    static_dir = ROOT_DIR / "web"

    def records(rows):
        return [dict(row) for row in rows]

    def positive(value: float, field_name: str) -> Decimal:
        amount = Decimal(str(value))
        if amount <= 0:
            raise HTTPException(status_code=422, detail=f"{field_name} must be greater than zero.")
        return amount

    def session(
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
        cookie_session: str | None = Cookie(default=None, alias="elh_session"),
        token_param: str | None = Query(default=None, alias="token"),
    ) -> UserSession:
        raw_token = authorization or x_session_token or cookie_session or token_param or ""
        token = raw_token.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")

        payload = token_manager.decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid. Please sign in.",
            )

        user_id = payload.get("uid")
        row = db.query_one("SELECT * FROM app_users WHERE id = ?", (user_id,))
        if not row or row["status"] != "Active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive or disabled.",
            )

        locked_until = auth._parse_datetime(row["locked_until"])
        if locked_until and locked_until > datetime.now():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is temporarily locked.",
            )

        permissions = auth.permissions_for_user(int(row["id"]), row["role"])
        keys = row.keys() if hasattr(row, "keys") else ()
        phone = str(row["phone"] or "") if "phone" in keys else ""
        student_id = int(row["student_id"]) if "student_id" in keys and row["student_id"] else None
        teacher_id = int(row["teacher_id"]) if "teacher_id" in keys and row["teacher_id"] else None
        return UserSession(
            user_id=int(row["id"]),
            username=row["username"],
            role=row["role"],
            display_name=row["display_name"] or row["username"],
            permissions=permissions,
            must_change_password=bool(row["must_change_password"]),
            phone=phone,
            student_id=student_id,
            teacher_id=teacher_id,
        )

    def require(permission: str):
        def dependency(user=Depends(session)):
            if not auth.has_permission(user, permission):
                raise HTTPException(status_code=403, detail="You do not have permission for this action.")
            return user
        return dependency

    def require_any(*permissions: str):
        def dependency(user=Depends(session)):
            if not any(auth.has_permission(user, p) for p in permissions):
                raise HTTPException(status_code=403, detail="You do not have permission for this action.")
            return user
        return dependency

    @app.post("/api/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response):
        client_ip = request.client.host if request.client else "127.0.0.1"
        rate_key = f"{client_ip}:{payload.username.strip().lower()}"
        is_limited, retry_after = rate_limiter.is_rate_limited(rate_key)
        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        user = auth.authenticate(payload.username, payload.password)
        if not user:
            rate_limiter.record_failure(rate_key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )

        rate_limiter.record_success(rate_key)
        token = token_manager.create_token(
            user.user_id,
            user.username,
            user.role,
            expiry_minutes=config.web_session_expiry_minutes,
        )
        response.set_cookie(
            key="elh_session",
            value=token,
            max_age=config.web_session_expiry_minutes * 60,
            httponly=True,
            samesite="lax",
            secure=False,
        )
        return {
            "token": token,
            "user": {
                "id": user.user_id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "phone": user.phone,
                "student_id": user.student_id,
                "teacher_id": user.teacher_id,
                "permissions": sorted(user.permissions),
                "must_change_password": user.must_change_password,
            },
        }

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        authorization: str | None = Header(default=None),
        x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
        cookie_session: str | None = Cookie(default=None, alias="elh_session"),
    ):
        raw_token = authorization or x_session_token or cookie_session or ""
        token = raw_token.removeprefix("Bearer ").strip()
        if token:
            token_manager.revoke_token(token)
        response.delete_cookie(key="elh_session", path="/")
        return {"ok": True}

    @app.get("/api/public/site-info")
    def public_site_info():
        teachers_count = db.query_one("SELECT COUNT(*) AS c FROM teachers WHERE status='Active'")
        students_count = db.query_one("SELECT COUNT(*) AS c FROM students WHERE status='Active'")
        courses_rows = records(db.query("SELECT id, course_name, category, default_fee, duration_months, instructor_name, remarks FROM courses WHERE status='Active'"))
        return {
            "name": "Expert Learning Hub",
            "tagline": "Redefining Education Through Excellence & Innovation",
            "address": "Expert Tower, Shikar Chowk, Pathari Shanishchare-1, Morang, Nepal",
            "phone": "+977 9800924090",
            "alt_phone": "+977 9842121118",
            "email": "info@expertlearninghub.edu.np",
            "website": "https://expertlearninghub.edu.np",
            "students_count": int(students_count["c"] or 0) if students_count else 500,
            "teachers_count": int(teachers_count["c"] or 0) if teachers_count else 14,
            "courses": courses_rows,
        }

    @app.get("/api/public/website-data")
    def public_website_data():
        return services.cms.get_all_content()

    @app.post("/api/public/inquiry")
    def public_inquiry(payload: PublicInquiryInput):
        title = f"Admission Inquiry: {payload.full_name}"
        if payload.course_interest:
            title += f" ({payload.course_interest})"
        details = (
            f"Phone: {payload.phone}\n"
            f"Email: {payload.email or 'N/A'}\n"
            f"Grade/Level: {payload.grade or 'N/A'}\n"
            f"Course Interest: {payload.course_interest or 'General'}\n"
            f"Message: {payload.message or '-'}"
        )
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            services.cms.create_inquiry(
                full_name=payload.full_name,
                phone=payload.phone,
                email=payload.email,
                grade=payload.grade,
                course_interest=payload.course_interest,
                message=payload.message,
            )
        except Exception as exc:
            logger.warning(f"Failed to record inquiry in website_inquiries: {exc}")
        try:
            db.execute(
                "INSERT INTO todo_items (title, details, priority, status, created_at) VALUES (?, ?, 'High', 'Open', ?)",
                (title, details, now_str)
            )
        except Exception as exc:
            logger.warning(f"Failed to record inquiry as todo item: {exc}")
        return {
            "ok": True,
            "message": f"Thank you {payload.full_name}! Your inquiry has been received. Our admissions team will reach out to you shortly."
        }

    # -------------------------------------------------------------------------
    # Website CMS & Inquiries Management (Requires cms.manage permission)
    # -------------------------------------------------------------------------
    @app.get("/api/cms/content")
    def get_all_cms_content(user: UserSession = Depends(require("cms.manage"))):
        return services.cms.get_all_content()

    @app.get("/api/cms/sections/{section_key}")
    def get_cms_section(section_key: str, user: UserSession = Depends(require("cms.manage"))):
        return services.cms.get_section(section_key)

    @app.put("/api/cms/sections/{section_key}")
    def update_cms_section(
        section_key: str,
        payload: CmsSectionUpdateInput,
        user: UserSession = Depends(require("cms.manage"))
    ):
        return services.cms.save_section(section_key, payload.data, updated_by=user.username)

    @app.post("/api/cms/reset-defaults")
    def reset_cms_defaults(user: UserSession = Depends(require("cms.manage"))):
        return services.cms.reset_defaults(updated_by=user.username)

    @app.get("/api/cms/inquiries")
    def list_cms_inquiries(
        status: str | None = None,
        search: str | None = None,
        user: UserSession = Depends(require("cms.manage"))
    ):
        return services.cms.list_inquiries(status=status, search=search)

    @app.put("/api/cms/inquiries/{inquiry_id}")
    def update_cms_inquiry(
        inquiry_id: int,
        payload: InquiryUpdateInput,
        user: UserSession = Depends(require("cms.manage"))
    ):
        services.cms.update_inquiry(inquiry_id, payload.status, payload.staff_notes)
        return {"ok": True}

    @app.delete("/api/cms/inquiries/{inquiry_id}")
    def delete_cms_inquiry(
        inquiry_id: int,
        user: UserSession = Depends(require("cms.manage"))
    ):
        services.cms.delete_inquiry(inquiry_id)
        return {"ok": True}

    @app.post("/api/auth/refresh")
    def refresh(response: Response, user: UserSession = Depends(session)):
        new_token = token_manager.create_token(
            user.user_id,
            user.username,
            user.role,
            expiry_minutes=config.web_session_expiry_minutes,
        )
        response.set_cookie(
            key="elh_session",
            value=new_token,
            max_age=config.web_session_expiry_minutes * 60,
            httponly=True,
            samesite="lax",
            secure=False,
        )
        return {
            "token": new_token,
            "user": {
                "id": user.user_id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "phone": user.phone,
                "student_id": user.student_id,
                "teacher_id": user.teacher_id,
                "permissions": sorted(user.permissions),
                "must_change_password": user.must_change_password,
            },
        }

    @app.post("/api/auth/change-password")
    def change_password(payload: ChangePasswordRequest, user: UserSession = Depends(session)):
        if payload.new_password != payload.confirm_password:
            raise HTTPException(status_code=400, detail="New passwords do not match.")
        if not auth.verify_user_password(user.user_id, payload.current_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        try:
            AuthService.validate_password(payload.new_password)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))
        auth.update_password(user, user.user_id, payload.new_password, must_change_password=False)
        return {"ok": True, "message": "Password changed successfully."}

    @app.get("/api/auth/me")
    def me(user: UserSession = Depends(session)):
        return {
            "id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "phone": user.phone,
            "student_id": user.student_id,
            "teacher_id": user.teacher_id,
            "permissions": sorted(user.permissions),
            "must_change_password": user.must_change_password,
        }

    # -----------------------------------------------------------------------
    # User Management & Administration
    # -----------------------------------------------------------------------
    @app.get("/api/users")
    def list_users(_user=Depends(require("administration.manage"))):
        rows = auth.list_users()
        return records(rows)

    @app.get("/api/users/roles-permissions")
    def get_roles_and_permissions(_user=Depends(require("administration.manage"))):
        return {
            "roles": list(ROLES),
            "permissions": auth.list_permissions(),
            "role_defaults": {role: sorted(auth.role_permissions(role)) for role in ROLES},
        }

    @app.get("/api/users/audit-log")
    def get_users_audit_log(limit: int = 200, _user=Depends(require("administration.manage"))):
        return records(auth.list_audit(limit=limit))

    @app.get("/api/users/{user_id}")
    def get_user(user_id: int, _user=Depends(require("administration.manage"))):
        row = auth.get_user(user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User was not found.")
        effective_permissions = sorted(auth.permissions_for_user(user_id, row["role"]))
        data = dict(row)
        data.pop("password_hash", None)
        data["permissions"] = effective_permissions
        return data

    @app.post("/api/users", status_code=201)
    def create_user_account(payload: UserCreateInput, actor: UserSession = Depends(require("administration.manage"))):
        try:
            permissions = set(payload.permissions) if payload.permissions is not None else None
            user_id = auth.create_user(
                username=payload.username,
                password=payload.password,
                display_name=payload.display_name,
                email=payload.email,
                role=payload.role,
                status=payload.status,
                permissions=permissions,
                actor=actor,
                must_change_password=payload.must_change_password,
                phone=payload.phone,
                student_id=payload.student_id,
                teacher_id=payload.teacher_id,
            )
            return {"id": user_id, "ok": True}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/users/{user_id}")
    def update_user_account(user_id: int, payload: UserUpdateInput, actor: UserSession = Depends(require("administration.manage"))):
        try:
            permissions = set(payload.permissions) if payload.permissions is not None else auth.permissions_for_user(user_id, payload.role)
            auth.update_user(
                user_id=user_id,
                display_name=payload.display_name,
                email=payload.email,
                role=payload.role,
                status=payload.status,
                permissions=permissions,
                actor=actor,
                must_change_password=payload.must_change_password,
                phone=payload.phone,
                student_id=payload.student_id,
                teacher_id=payload.teacher_id,
            )
            return {"ok": True}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/users/{user_id}/reset-password")
    def reset_user_password(user_id: int, payload: UserResetPasswordInput, actor: UserSession = Depends(require("administration.manage"))):
        try:
            auth.change_password(
                user_id=user_id,
                new_password=payload.new_password,
                actor=actor,
                must_change_password=payload.must_change_password,
            )
            return {"ok": True, "message": "User password reset successfully."}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/users/{user_id}/unlock")
    def unlock_user_account(user_id: int, actor: UserSession = Depends(require("administration.manage"))):
        try:
            auth.unlock_user(user_id, actor)
            return {"ok": True, "message": "User account unlocked."}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/users/{user_id}/toggle-status")
    def toggle_user_status(user_id: int, payload: UserStatusToggleInput, actor: UserSession = Depends(require("administration.manage"))):
        try:
            auth.toggle_user_status(user_id, payload.status, actor)
            return {"ok": True, "status": payload.status}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _can_access_student(user: UserSession, student_id: int) -> bool:
        if auth.has_permission(user, "students.manage"):
            return True
        if auth.has_permission(user, "portal.student") and user.student_id and int(user.student_id) == int(student_id):
            return True
        return False

    def _can_access_teacher(user: UserSession, teacher_id: int) -> bool:
        if auth.has_permission(user, "staff.manage") or auth.has_permission(user, "administration.manage"):
            return True
        if auth.has_permission(user, "portal.staff") and user.teacher_id and int(user.teacher_id) == int(teacher_id):
            return True
        return False

    def _build_teacher_portal_data(teacher_id: int | None, user: UserSession, target_month: str | None = None) -> dict:
        teacher_row = db.query_one(
            "SELECT id, teacher_name, contact, address, email, qualification, subject, "
            "staff_type, joined_date, salary_type, basic_salary, bank_account_number, "
            "account_holder_name, bank_name, status, remarks "
            "FROM teachers WHERE id=?",
            (teacher_id,)
        ) if teacher_id else None

        teacher_info = dict(teacher_row) if teacher_row else {
            "id": teacher_id or 0,
            "teacher_name": user.display_name or user.username,
            "staff_type": "Teaching",
            "subject": "",
            "qualification": "",
            "contact": "",
            "email": "",
            "salary_type": "Monthly Salary",
            "basic_salary": 0.0,
            "joined_date": "",
            "status": "Active",
        }
        teacher_info["basic_salary"] = float(teacher_info.get("basic_salary") or 0)
        teacher_info["monthly_salary"] = teacher_info["basic_salary"]
        teacher_info["name"] = teacher_info.get("teacher_name", "")

        # 1. Total class in this week (and today)
        active_plan = db.query_one("SELECT id, plan_name FROM routine_plans WHERE status='Active' ORDER BY effective_from DESC LIMIT 1")
        plan_clause = "AND (r.routine_plan_id = ? OR r.routine_plan_id IS NULL) " if active_plan else ""
        plan_params = (active_plan["id"],) if active_plan else ()

        weekly_routines = []
        if teacher_id:
            teacher_match_clauses = ["r.teacher_id = ?"]
            teacher_match_params = [teacher_id]
            t_name = (teacher_info.get("teacher_name") or "").strip()
            if t_name:
                parts = [p for p in t_name.split() if p]
                if len(parts) >= 2:
                    initials_dotted = f"{parts[0][0]}.{parts[-1][0]}."
                    initials_space = f"{parts[0][0]}. {parts[-1][0]}."
                    teacher_match_clauses.append("(r.teacher_id IS NULL AND (r.subject_name LIKE ? OR r.subject_name LIKE ? OR r.subject_name LIKE ?))")
                    teacher_match_params.extend([f"%{initials_dotted}%", f"%{initials_space}%", f"%{t_name}%"])
            teacher_where = f"({' OR '.join(teacher_match_clauses)})"

            weekly_routines = records(db.query(
                "SELECT r.id, r.class_name, r.class_level_id, r.day_of_week, r.period_label, "
                "r.subject_name, r.start_time, r.end_time, r.status, r.course_id, r.teacher_id, "
                "COALESCE(t.teacher_name, '') AS teacher_name, "
                "COALESCE(c.course_name, '') AS course_name, "
                "COALESCE(cl.level_name, r.class_name) AS display_class_name "
                "FROM class_routines r "
                "LEFT JOIN teachers t ON t.id = r.teacher_id "
                "LEFT JOIN courses c ON c.id = r.course_id "
                "LEFT JOIN class_levels cl ON cl.id = r.class_level_id "
                f"WHERE {teacher_where} AND r.status = 'Active' {plan_clause}"
                "ORDER BY CASE r.day_of_week "
                "WHEN 'Sunday' THEN 1 "
                "WHEN 'Monday' THEN 2 "
                "WHEN 'Tuesday' THEN 3 "
                "WHEN 'Wednesday' THEN 4 "
                "WHEN 'Thursday' THEN 5 "
                "WHEN 'Friday' THEN 6 "
                "WHEN 'Saturday' THEN 7 "
                "ELSE 8 END, r.start_time ASC, r.period_label ASC",
                (*teacher_match_params, *plan_params)
            ))

            for r in weekly_routines:
                c_val = str(r.get("display_class_name") or r.get("class_name") or "").strip()
                if c_val.isdigit():
                    r["display_class_name"] = f"Class {c_val}"
                elif c_val and not c_val.lower().startswith("grade") and not c_val.lower().startswith("class"):
                    r["display_class_name"] = f"Class {c_val}"
                else:
                    r["display_class_name"] = c_val or "General"
                if not r.get("teacher_name") and t_name:
                    r["teacher_name"] = t_name

        total_classes_week = len(weekly_routines)
        today_weekday = datetime.now().strftime("%A")
        today_routines = [r for r in weekly_routines if str(r.get("day_of_week", "")).strip().lower() == today_weekday.lower()]

        # 2. Students assigned in class to them
        assigned_student_ids = set()
        if teacher_id:
            for r in weekly_routines:
                c_level_id = r.get("class_level_id")
                c_name = str(r.get("class_name") or "").strip()
                c_id = r.get("course_id")
                where_parts = ["s.status <> 'Archived'"]
                params = []
                if c_level_id:
                    where_parts.append("((s.class_level_id = ? AND s.class_level_id != 0) OR s.class_name = ? OR s.class_name = ?)")
                    params.extend([c_level_id, c_name, f"Grade {c_name}"])
                elif c_name:
                    where_parts.append("(s.class_name = ? OR s.class_name = ?)")
                    params.extend([c_name, f"Grade {c_name}"])

                if c_id:
                    where_parts.append("s.id IN (SELECT student_id FROM enrollments WHERE course_id = ? AND status = 'Active')")
                    params.append(c_id)

                rows = db.query(f"SELECT s.id FROM students s WHERE {' AND '.join(where_parts)}", params)
                for row in rows:
                    assigned_student_ids.add(row["id"])

            t_name = teacher_info.get("teacher_name", "")
            if t_name:
                c_rows = db.query(
                    "SELECT e.student_id FROM enrollments e "
                    "JOIN courses c ON c.id = e.course_id "
                    "WHERE c.instructor_name = ? AND e.status = 'Active'",
                    (t_name,)
                )
                for row in c_rows:
                    assigned_student_ids.add(row["student_id"])

        assigned_students = []
        if assigned_student_ids:
            placeholders = ",".join("?" for _ in assigned_student_ids)
            st_rows = db.query(
                f"SELECT s.id, s.student_name, s.class_name, s.class_level_id, "
                f"COALESCE(cl.level_name, s.class_name) AS display_class_name, "
                f"COALESCE(sc.school_name, '') AS school_name, s.contact, s.parent_name, s.gender, s.status "
                f"FROM students s "
                f"LEFT JOIN class_levels cl ON cl.id = s.class_level_id "
                f"LEFT JOIN schools sc ON sc.id = s.school_id "
                f"WHERE s.id IN ({placeholders}) "
                f"ORDER BY s.class_name ASC, s.student_name ASC",
                tuple(assigned_student_ids)
            )
            assigned_students = records(st_rows)

        class_distribution = {}
        for st in assigned_students:
            c_label = st.get("display_class_name") or st.get("class_name") or "General"
            class_distribution[c_label] = class_distribution.get(c_label, 0) + 1

        # 3. Payment history, advance and other payments, and pending payment
        salary_payouts = []
        advances = []
        statement_txns = []
        total_salary_paid = 0.0
        total_other_payments = 0.0
        total_bonus = 0.0
        total_allowance = 0.0
        total_extra_payment = 0.0
        total_advances_taken = 0.0
        total_advances_recovered = 0.0
        pending_advance = 0.0

        if teacher_id:
            sp_rows = db.query(
                "SELECT sp.id, sp.teacher_id, sp.salary_month, sp.basic_salary, sp.extra_payment, "
                "sp.bonus, sp.allowance, (sp.extra_payment + sp.bonus + sp.allowance) AS other_payments, "
                "sp.advance_deduction, sp.other_deduction, sp.net_salary, "
                "sp.payment_date, sp.payment_method, sp.voucher_no, sp.status, sp.remarks, "
                "sp.attendance_days, sp.working_hours, sp.class_count, "
                "COALESCE(a.account_name, '') AS paid_from_account "
                "FROM salary_payouts sp "
                "LEFT JOIN accounts a ON a.id = sp.paid_from_account_id "
                "WHERE sp.teacher_id = ? "
                "ORDER BY sp.salary_month DESC, sp.payment_date DESC, sp.id DESC",
                (teacher_id,)
            )
            salary_payouts = records(sp_rows)
            for sp in salary_payouts:
                sp["basic_salary"] = float(sp["basic_salary"] or 0)
                sp["extra_payment"] = float(sp["extra_payment"] or 0)
                sp["bonus"] = float(sp["bonus"] or 0)
                sp["allowance"] = float(sp["allowance"] or 0)
                sp["other_payments"] = float(sp["other_payments"] or 0)
                sp["advance_deduction"] = float(sp["advance_deduction"] or 0)
                sp["other_deduction"] = float(sp["other_deduction"] or 0)
                sp["net_salary"] = float(sp["net_salary"] or 0)
                total_salary_paid += sp["net_salary"]
                total_other_payments += sp["other_payments"]
                total_bonus += sp["bonus"]
                total_allowance += sp["allowance"]
                total_extra_payment += sp["extra_payment"]

            adv_rows = db.query(
                "SELECT ta.id, ta.teacher_id, ta.advance_date, ta.amount, ta.recovery_method, "
                "ta.recovery_start_month, ta.monthly_deduction, ta.recovered_amount, "
                "(ta.amount - ta.recovered_amount) AS balance, ta.status, ta.payment_method, "
                "ta.reference_no, ta.remarks, COALESCE(a.account_name, '') AS paid_from_account "
                "FROM teacher_advances ta "
                "LEFT JOIN accounts a ON a.id = ta.paid_from_account_id "
                "WHERE ta.teacher_id = ? "
                "ORDER BY ta.advance_date DESC, ta.id DESC",
                (teacher_id,)
            )
            advances = records(adv_rows)
            for adv in advances:
                adv["amount"] = float(adv["amount"] or 0)
                adv["monthly_deduction"] = float(adv["monthly_deduction"] or 0)
                adv["recovered_amount"] = float(adv["recovered_amount"] or 0)
                adv["balance"] = float(adv["balance"] or 0)
                total_advances_taken += adv["amount"]
                total_advances_recovered += adv["recovered_amount"]
                if adv["status"] in ("Outstanding", "Partially Recovered"):
                    pending_advance += adv["balance"]

            try:
                _, txns = services.staff_finance.statement(teacher_id)
                statement_txns = records(txns)
                for tx in statement_txns:
                    tx["amount"] = float(tx["amount"] or 0)
            except Exception:
                statement_txns = []

        now = datetime.now()
        cur_month = current_month()

        paid_months = {sp["salary_month"] for sp in salary_payouts}
        is_cur_month_paid = cur_month in paid_months if cur_month else False
        basic_sal = float(teacher_info.get("basic_salary") or 0)
        pending_salary = basic_sal if (not is_cur_month_paid and basic_sal > 0) else 0.0

        payment_summary = {
            "total_salary_paid": total_salary_paid,
            "total_paid_salary": total_salary_paid,
            "total_other_payments": total_other_payments,
            "total_bonus": total_bonus,
            "total_allowance": total_allowance,
            "total_extra_payment": total_extra_payment,
            "total_advances_taken": total_advances_taken,
            "total_advances_received": total_advances_taken,
            "total_advances_recovered": total_advances_recovered,
            "pending_advance": pending_advance,
            "total_advances_pending": pending_advance,
            "pending_salary": pending_salary,
            "total_pending_payment": pending_salary,
            "current_month": cur_month,
            "current_month_paid": is_cur_month_paid,
        }

        # 4. Attendance history of his/her own
        today_str = now.strftime("%Y-%m-%d")
        today_punches = []
        month_days_count = 0
        month_hours_count = 0.0
        lifetime_days_count = 0
        daily_logs = []

        if teacher_id:
            today_rows = records(db.query(
                "SELECT occurred_at FROM attendance_logs "
                "WHERE person_type = 'teacher' AND person_id = ? AND DATE(occurred_at) = ? "
                "ORDER BY occurred_at ASC",
                (teacher_id, today_str)
            ))
            today_punches = []
            for r in today_rows:
                occ = r["occurred_at"]
                if isinstance(occ, datetime):
                    today_punches.append(occ.strftime("%I:%M %p"))
                else:
                    try:
                        today_punches.append(datetime.fromisoformat(str(occ)).strftime("%I:%M %p"))
                    except Exception:
                        today_punches.append(str(occ)[11:16])

            c_month_start_ad = f"{today_str[:7]}-01"
            try:
                today_bs = nepali.date.from_datetime_date(now.date())
                start_bs = nepali.date(today_bs.year, today_bs.month, 1)
                c_month_start_ad = start_bs.to_datetime_date().isoformat()
            except Exception:
                pass

            m_row = db.query_one(
                "SELECT COUNT(DISTINCT DATE(occurred_at)) AS cnt "
                "FROM attendance_logs WHERE person_type='teacher' AND person_id=? AND occurred_at >= ?",
                (teacher_id, f"{c_month_start_ad} 00:00:00")
            )
            month_days_count = int(m_row["cnt"] or 0) if m_row else 0

            life_row = db.query_one(
                "SELECT COUNT(DISTINCT DATE(occurred_at)) AS cnt "
                "FROM attendance_logs WHERE person_type='teacher' AND person_id=?",
                (teacher_id,)
            )
            lifetime_days_count = int(life_row["cnt"] or 0) if life_row else 0

            date_filter = ""
            date_filter_params = [teacher_id]
            if target_month and "/" in target_month:
                try:
                    ty, tm = (int(p) for p in target_month.split("/"))
                    t_start_bs = nepali.date(ty, tm, 1)
                    t_next_bs = nepali.date(ty + 1, 1, 1) if tm == 12 else nepali.date(ty, tm + 1, 1)
                    t_start_ad = f"{t_start_bs.to_datetime_date().isoformat()} 00:00:00"
                    t_end_ad = f"{(t_next_bs.to_datetime_date() - timedelta(days=1)).isoformat()} 23:59:59"
                    date_filter = "AND occurred_at BETWEEN ? AND ?"
                    date_filter_params.extend([t_start_ad, t_end_ad])
                except Exception:
                    pass

            all_logs = db.query(
                f"SELECT occurred_at, device_user_id, event_type "
                f"FROM attendance_logs WHERE person_type = 'teacher' AND person_id = ? {date_filter} "
                f"ORDER BY occurred_at ASC",
                tuple(date_filter_params)
            )
            from collections import defaultdict
            daily_map = defaultdict(list)
            for al in all_logs:
                occ = al["occurred_at"]
                if isinstance(occ, datetime):
                    d_str = occ.date().isoformat()
                    t_dt = occ
                    t_str = occ.strftime("%I:%M %p")
                else:
                    occ_str = str(occ)
                    d_str = occ_str[:10]
                    try:
                        t_dt = datetime.fromisoformat(occ_str)
                        t_str = t_dt.strftime("%I:%M %p")
                    except Exception:
                        t_dt = None
                        t_str = occ_str[11:16]
                daily_map[d_str].append((t_dt, t_str))

            for d_str in sorted(daily_map.keys(), reverse=True):
                tuples = daily_map[d_str]
                times = [t[1] for t in tuples]
                first_in = times[0] if times else ""
                last_out = times[-1] if len(times) > 1 else first_in
                hrs = 0.0
                valid_dts = [t[0] for t in tuples if t[0] is not None]
                if len(valid_dts) >= 2:
                    hrs = round((valid_dts[-1] - valid_dts[0]).total_seconds() / 3600, 2)
                if d_str >= c_month_start_ad:
                    month_hours_count += hrs

                try:
                    d_ad = datetime.strptime(d_str, "%Y-%m-%d").date()
                    d_bs = nepali.date.from_datetime_date(d_ad).strftime("%Y/%m/%d")
                    day_w = d_ad.strftime("%A")
                except Exception:
                    d_bs = d_str
                    day_w = ""

                daily_logs.append({
                    "date": d_str,
                    "date_bs": d_bs,
                    "day_of_week": day_w,
                    "first_in": first_in,
                    "last_out": last_out,
                    "punches": times,
                    "punch_count": len(times),
                    "hours": hrs,
                    "status": "Present",
                })

        tasks = []
        if teacher_id:
            tasks = records(db.query(
                "SELECT id, title, details, due_date, priority, status "
                "FROM todo_items WHERE assigned_teacher_id = ? ORDER BY id DESC LIMIT 10",
                (teacher_id,)
            ))

        proxy_requests = records(db.query(
            """
            SELECT p.*, r.period_label, r.subject_name, r.start_time, r.end_time, r.class_name,
                   COALESCE(cl.level_name, r.class_name) AS display_class_name,
                   COALESCE(pt.teacher_name, 'Unassigned') AS proxy_teacher_name
            FROM proxy_class_requests p
            JOIN class_routines r ON r.id = p.routine_id
            LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id
            LEFT JOIN class_levels cl ON cl.id = r.class_level_id
            WHERE p.original_teacher_id = ? OR p.requested_by_teacher_id = ?
            ORDER BY p.class_date DESC, r.start_time ASC LIMIT 20
            """,
            (teacher_id, teacher_id)
        )) if teacher_id else []

        proxy_assignments = records(db.query(
            """
            SELECT p.*, r.period_label, r.subject_name, r.start_time, r.end_time, r.class_name,
                   COALESCE(cl.level_name, r.class_name) AS display_class_name,
                   COALESCE(ot.teacher_name, 'Regular Faculty') AS original_teacher_name
            FROM proxy_class_requests p
            JOIN class_routines r ON r.id = p.routine_id
            LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
            LEFT JOIN class_levels cl ON cl.id = r.class_level_id
            WHERE p.proxy_teacher_id = ?
            ORDER BY p.class_date DESC, r.start_time ASC LIMIT 20
            """,
            (teacher_id,)
        )) if teacher_id else []

        return {
            "role": "staff",
            "teacher": teacher_info,
            "metrics": {
                "total_classes_week": total_classes_week,
                "today_classes_count": len(today_routines),
                "total_students_assigned": len(assigned_students),
                "classes_count": len(class_distribution),
                "today_present": len(today_punches) > 0,
                "today_punches": today_punches,
                "month_days_present": month_days_count,
                "month_hours_worked": round(month_hours_count, 1),
                "lifetime_days": lifetime_days_count,
                "pending_salary": pending_salary,
                "pending_advance": pending_advance,
                "total_salary_paid": total_salary_paid,
                "total_other_payments": total_other_payments,
                "current_month_paid": is_cur_month_paid,
                "pending_proxy_count": len([p for p in proxy_assignments if p.get("proxy_status") == "Pending"]),
            },
            "weekly_routines": weekly_routines,
            "today_routines": today_routines,
            "today_weekday": today_weekday,
            "active_plan_name": active_plan["plan_name"] if active_plan else "Regular Routine",
            "assigned_students": assigned_students,
            "assigned_students_count": len(assigned_students),
            "class_distribution": class_distribution,
            "salary_payouts": salary_payouts,
            "advances": advances,
            "statement": statement_txns,
            "payment_summary": payment_summary,
            "attendance_history": {
                "today_punches": today_punches,
                "today_present": len(today_punches) > 0,
                "month_days": month_days_count,
                "month_hours": round(month_hours_count, 1),
                "lifetime_days": lifetime_days_count,
                "current_month": cur_month,
                "daily_logs": daily_logs,
            },
            "tasks": tasks,
            "proxy_requests": proxy_requests,
            "proxy_assignments": proxy_assignments,
        }

    @app.get("/api/dashboard")
    def dashboard(user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "dashboard.view") or auth.has_permission(user, "portal.student") or auth.has_permission(user, "portal.staff")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")

        is_student = user.role == "student" or (user.student_id and not auth.has_permission(user, "students.manage"))
        if is_student:
            student_id = user.student_id
            if not student_id:
                user_row = db.query_one("SELECT student_id FROM app_users WHERE id=?", (user.user_id,))
                if user_row and user_row["student_id"]:
                    student_id = user_row["student_id"]

            student_info = None
            if student_id:
                student_info = db.query_one(
                    "SELECT s.id, s.student_name, s.class_name, s.class_level_id, "
                    "COALESCE(sc.school_name, '') AS school_name, "
                    "s.contact, s.status, s.joining_date, s.parent_name, s.gender, s.date_of_birth, s.address "
                    "FROM students s LEFT JOIN schools sc ON sc.id = s.school_id WHERE s.id = ?",
                    (student_id,)
                )

            enrollments = []
            if student_id:
                enrollments = records(db.query(
                    "SELECT e.id, e.course_id, c.course_name, COALESCE(e.level, '') AS level, e.start_date, e.status, "
                    "COALESCE(c.instructor_name, '') AS instructor_name, COALESCE(e.monthly_fee, 0) AS monthly_fee "
                    "FROM enrollments e JOIN courses c ON c.id = e.course_id "
                    "WHERE e.student_id = ? AND e.status = 'Active' "
                    "ORDER BY e.start_date DESC",
                    (student_id,)
                ))

            due_bills = []
            outstanding_due = 0.0
            if student_id:
                bills_raw = records(db.query(
                    "SELECT b.id, b.bill_number, c.course_name, b.billing_period, b.issue_date, b.due_date, "
                    "b.total_amount, b.paid_amount, (b.total_amount - b.paid_amount) AS balance, b.status "
                    "FROM due_bills b JOIN enrollments e ON e.id = b.enrollment_id "
                    "JOIN courses c ON c.id = e.course_id "
                    "WHERE e.student_id = ? ORDER BY b.issue_date DESC LIMIT 5",
                    (student_id,)
                ))
                due_bills = [{**b, "total_amount": float(b["total_amount"] or 0), "paid_amount": float(b["paid_amount"] or 0), "balance": float(b["balance"] or 0)} for b in bills_raw]
                sum_row = db.query_one(
                    "SELECT COALESCE(SUM(total_amount - paid_amount), 0) AS total_due "
                    "FROM due_bills b JOIN enrollments e ON e.id = b.enrollment_id "
                    "WHERE e.student_id = ? AND b.status <> 'Paid'",
                    (student_id,)
                )
                outstanding_due = float(sum_row["total_due"] or 0) if sum_row else 0.0

            today_str = datetime.now().strftime("%Y-%m-%d")
            today_punches = []
            month_days_count = 0
            lifetime_days_count = 0
            if student_id:
                today_rows = records(db.query(
                    "SELECT occurred_at FROM attendance_logs "
                    "WHERE person_type = 'student' AND person_id = ? AND DATE(occurred_at) = ? "
                    "ORDER BY occurred_at ASC",
                    (student_id, today_str)
                ))
                today_punches = [str(r["occurred_at"])[11:16] for r in today_rows]

                c_month_start = f"{today_str[:7]}-01"
                month_days = db.query_one(
                    "SELECT COUNT(DISTINCT DATE(occurred_at)) AS cnt "
                    "FROM attendance_logs WHERE person_type='student' AND person_id=? AND occurred_at >= ?",
                    (student_id, c_month_start)
                )
                month_days_count = int(month_days["cnt"] or 0) if month_days else 0

                life_row = db.query_one(
                    "SELECT COUNT(DISTINCT DATE(occurred_at)) AS cnt "
                    "FROM attendance_logs WHERE person_type='student' AND person_id=?",
                    (student_id,)
                )
                lifetime_days_count = int(life_row["cnt"] or 0) if life_row else 0

            today_weekday = datetime.now().strftime("%A")
            today_routine = []
            if student_info:
                st_dict = dict(student_info)
                st_class = str(st_dict.get("class_name") or "").strip()
                st_class_id = st_dict.get("class_level_id")
                alt_class = f"Grade {st_class}" if st_class.isdigit() else (st_class[6:].strip() if st_class.lower().startswith("grade ") else st_class)
                active_enrolled_cids = [int(e["course_id"]) for e in enrollments if e.get("course_id")]

                active_plan = db.query_one("SELECT id FROM routine_plans WHERE status='Active' ORDER BY effective_from DESC LIMIT 1")
                plan_clause = "AND (r.routine_plan_id = ? OR r.routine_plan_id IS NULL) " if active_plan else ""
                plan_params = (active_plan["id"],) if active_plan else ()

                if st_class_id or st_class:
                    class_clause = "((r.class_level_id = ? AND r.class_level_id != 0) OR (r.class_name IS NOT NULL AND r.class_name != '' AND (r.class_name = ? OR r.class_name = ?)) OR ((r.class_level_id IS NULL OR r.class_level_id = 0) AND (r.class_name IS NULL OR r.class_name = '' OR LOWER(r.class_name) = 'all')))"
                    class_params = [st_class_id or 0, st_class, alt_class]
                else:
                    class_clause = "1=1"
                    class_params = []

                if active_enrolled_cids:
                    c_placeholders = ",".join("?" for _ in active_enrolled_cids)
                    where_match = f"({class_clause} AND (r.course_id IS NULL OR r.course_id IN ({c_placeholders})))"
                    c_params = [*class_params, *active_enrolled_cids]
                else:
                    where_match = f"({class_clause} AND r.course_id IS NULL)"
                    c_params = list(class_params)

                today_routine = records(db.query(
                    "SELECT r.id, r.class_name, r.period_label, r.subject_name, r.start_time, r.end_time, "
                    "COALESCE(t.teacher_name, '') AS teacher_name, COALESCE(c.course_name, '') AS course_name "
                    "FROM class_routines r "
                    "LEFT JOIN teachers t ON t.id = r.teacher_id "
                    "LEFT JOIN courses c ON c.id = r.course_id "
                    f"WHERE {where_match} AND r.day_of_week = ? AND r.status = 'Active' {plan_clause}"
                    "ORDER BY r.start_time ASC, r.period_label ASC",
                    (*c_params, today_weekday, *plan_params)
                ))

            certificates = []
            if student_id:
                cert_rows = records(db.query(
                    "SELECT cert.id, cert.certificate_number, cert.certify_date, c.course_name "
                    "FROM course_certificates cert "
                    "JOIN enrollments e ON e.id = cert.enrollment_id "
                    "JOIN courses c ON c.id = e.course_id "
                    "WHERE e.student_id = ? ORDER BY cert.certify_date DESC",
                    (student_id,)
                ))
                certificates = cert_rows

            overdue_alerts = services.billing.payment_alerts(student_id=student_id) if student_id else []

            proxy_notifs = []
            if student_id:
                proxy_notifs = records(db.query(
                    """
                    SELECT n.id AS notification_id, n.read_at, p.class_date, p.leave_type,
                           r.period_label, r.subject_name, r.start_time, r.end_time,
                           COALESCE(cl.level_name, r.class_name) AS display_class_name,
                           COALESCE(ot.teacher_name, 'Regular Faculty') AS original_teacher_name,
                           COALESCE(pt.teacher_name, 'Substitute Faculty') AS proxy_teacher_name
                    FROM proxy_student_notifications n
                    JOIN proxy_class_requests p ON p.id = n.proxy_request_id
                    JOIN class_routines r ON r.id = p.routine_id
                    LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
                    LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id
                    LEFT JOIN class_levels cl ON cl.id = r.class_level_id
                    WHERE n.student_id = ? AND p.class_date >= ?
                    ORDER BY p.class_date ASC, r.start_time ASC
                    """,
                    (student_id, today_str)
                ))

            return {
                "role": "student",
                "student": dict(student_info) if student_info else {"id": student_id, "student_name": user.display_name or user.username, "class_name": "", "school_name": ""},
                "metrics": {
                    "enrollments": len(enrollments),
                    "attendance_month_days": month_days_count,
                    "lifetime_days": lifetime_days_count,
                    "today_present": len(today_punches) > 0,
                    "today_punches": today_punches,
                    "outstanding": outstanding_due,
                    "certificates": len(certificates),
                    "overdue_bills_count": len(overdue_alerts),
                    "proxy_notifications_count": len([pn for pn in proxy_notifs if not pn.get("read_at")]),
                },
                "enrollments": enrollments,
                "due_bills": due_bills,
                "overdue_alerts": overdue_alerts,
                "today_routine": today_routine,
                "today_weekday": today_weekday,
                "certificates": certificates,
                "proxy_notifications": proxy_notifs,
            }
        # Staff / Teacher portal
        is_teacher = user.role in ("staff", "teacher") or (user.teacher_id and not auth.has_permission(user, "administration.manage") and not auth.has_permission(user, "students.manage"))
        if is_teacher:
            teacher_id = user.teacher_id
            if not teacher_id:
                user_row = db.query_one("SELECT teacher_id FROM app_users WHERE id=?", (user.user_id,))
                if user_row and user_row["teacher_id"]:
                    teacher_id = user_row["teacher_id"]
            return _build_teacher_portal_data(teacher_id, user)
        today_weekday = datetime.now().strftime("%A")
        active_plan = db.query_one("SELECT id, plan_name FROM routine_plans WHERE status='Active' ORDER BY effective_from DESC LIMIT 1")
        plan_clause = "AND (r.routine_plan_id = ? OR r.routine_plan_id IS NULL) " if active_plan else ""
        plan_params = (active_plan["id"],) if active_plan else ()

        today_classes = records(db.query(
            "SELECT r.id, r.class_name, r.class_level_id, r.day_of_week, r.period_label, "
            "r.subject_name, r.start_time, r.end_time, r.status, r.course_id, r.teacher_id, "
            "COALESCE(t.teacher_name, '') AS teacher_name, "
            "COALESCE(c.course_name, '') AS course_name, "
            "COALESCE(cl.level_name, r.class_name) AS display_class_name "
            "FROM class_routines r "
            "LEFT JOIN teachers t ON t.id = r.teacher_id "
            "LEFT JOIN courses c ON c.id = r.course_id "
            "LEFT JOIN class_levels cl ON cl.id = r.class_level_id "
            f"WHERE r.day_of_week = ? AND r.status = 'Active' {plan_clause}"
            "ORDER BY r.start_time ASC, r.period_label ASC",
            (today_weekday, *plan_params)
        ))

        all_teachers = records(db.query("SELECT id, teacher_name FROM teachers WHERE status='Active'"))
        teacher_initials_map = {}
        teacher_name_to_id = {}
        for tr in all_teachers:
            t_name = (tr.get("teacher_name") or "").strip()
            tid = int(tr["id"])
            if t_name:
                teacher_name_to_id[t_name.lower()] = tid
            parts = [p for p in t_name.split() if p]
            if len(parts) >= 2:
                initials = f"{parts[0][0]}.{parts[-1][0]}."
                teacher_initials_map[initials.upper()] = (tid, t_name)

        today_date_str = datetime.now().date().isoformat()
        today_start = f"{today_date_str} 00:00:00"
        today_end = f"{today_date_str} 23:59:59"
        punch_rows = records(db.query(
            "SELECT person_id, COUNT(*) AS punches, MIN(occurred_at) AS first_punch, MAX(occurred_at) AS last_punch "
            "FROM attendance_logs "
            "WHERE person_type = 'teacher' AND occurred_at BETWEEN ? AND ? "
            "GROUP BY person_id",
            (today_start, today_end)
        ))
        teacher_punches = {int(p["person_id"]): p for p in punch_rows}

        today_proxies = records(db.query(
            """
            SELECT p.id AS proxy_request_id, p.routine_id, p.proxy_teacher_id,
                   pt.teacher_name AS proxy_teacher_name, p.proxy_status,
                   ot.teacher_name AS original_teacher_name
            FROM proxy_class_requests p
            JOIN teachers pt ON pt.id = p.proxy_teacher_id
            LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
            WHERE p.class_date = ? AND p.status = 'Approved' AND p.proxy_status = 'Accepted'
            """,
            (today_date_str,)
        ))
        proxy_by_routine = {int(pr["routine_id"]): pr for pr in today_proxies}

        for tc in today_classes:
            c_val = str(tc.get("display_class_name") or tc.get("class_name") or "").strip()
            if c_val.isdigit():
                tc["display_class_name"] = f"Class {c_val}"
            elif c_val and not c_val.lower().startswith("grade") and not c_val.lower().startswith("class"):
                tc["display_class_name"] = f"Class {c_val}"
            else:
                tc["display_class_name"] = c_val or "General"

            assigned_ids = []
            if tc.get("teacher_id"):
                assigned_ids.append(int(tc["teacher_id"]))

            if not tc.get("teacher_name"):
                s_name = tc.get("subject_name") or ""
                matched_names = []
                for inits, (m_id, full_n) in teacher_initials_map.items():
                    if inits in s_name.upper():
                        matched_names.append(full_n)
                        assigned_ids.append(m_id)
                if matched_names:
                    tc["teacher_name"] = " & ".join(matched_names)
            elif not assigned_ids and tc.get("teacher_name"):
                t_lower = tc["teacher_name"].strip().lower()
                if t_lower in teacher_name_to_id:
                    assigned_ids.append(teacher_name_to_id[t_lower])

            # Check if there is an accepted proxy for this routine today
            if tc["id"] in proxy_by_routine:
                pr = proxy_by_routine[tc["id"]]
                tc["has_proxy"] = True
                tc["proxy_teacher_id"] = pr["proxy_teacher_id"]
                tc["proxy_teacher_name"] = pr["proxy_teacher_name"]
                tc["original_teacher_name"] = pr["original_teacher_name"] or tc.get("teacher_name")
                proxy_tid = int(pr["proxy_teacher_id"])
                if proxy_tid in teacher_punches:
                    tc["teacher_present"] = True
                    tc["teacher_attendance_status"] = "Present (Proxy)"
                    punch = teacher_punches[proxy_tid]
                    tc["first_punch"] = str(punch["first_punch"])
                    tc["last_punch"] = str(punch["last_punch"])
                    tc["punch_count"] = punch["punches"]
                else:
                    tc["teacher_present"] = False
                    tc["teacher_attendance_status"] = "Absent (Proxy)"
                    tc["first_punch"] = None
                    tc["last_punch"] = None
                    tc["punch_count"] = 0
            elif assigned_ids:
                present_punches = [teacher_punches[tid] for tid in assigned_ids if tid in teacher_punches]
                if present_punches:
                    tc["teacher_present"] = True
                    tc["teacher_attendance_status"] = "Present"
                    earliest_first = min(p["first_punch"] for p in present_punches)
                    latest_last = max(p["last_punch"] for p in present_punches)
                    tc["first_punch"] = str(earliest_first) if earliest_first else None
                    tc["last_punch"] = str(latest_last) if latest_last else None
                    tc["punch_count"] = sum(p["punches"] for p in present_punches)
                else:
                    tc["teacher_present"] = False
                    tc["teacher_attendance_status"] = "Absent"
                    tc["first_punch"] = None
                    tc["last_punch"] = None
                    tc["punch_count"] = 0
            else:
                tc["teacher_present"] = None
                tc["teacher_attendance_status"] = "Unassigned"
                tc["first_punch"] = None
                tc["last_punch"] = None
                tc["punch_count"] = 0

        metrics = db.query_one(
            "SELECT (SELECT COUNT(*) FROM students WHERE status<>'Archived') students,"
            "(SELECT COUNT(*) FROM teachers WHERE status='Active') staff,"
            "(SELECT COUNT(*) FROM enrollments WHERE status='Active') enrollments,"
            "(SELECT COALESCE(SUM(charge_amount-payment_amount-discount_amount),0) FROM student_transactions) outstanding"
        )
        payment_alerts = services.billing.payment_alerts(include_suppressed=False)
        result = dict(metrics)
        result["outstanding"] = float(result["outstanding"] or 0)
        result["overdue_bills_count"] = len(payment_alerts)
        result["overdue_amount"] = sum(float(a["balance"]) for a in payment_alerts)
        result["today_classes_count"] = len(today_classes)
        result["today_weekday"] = today_weekday
        present_count = len([tc for tc in today_classes if tc.get("teacher_present") is True])
        absent_count = len([tc for tc in today_classes if tc.get("teacher_present") is False])
        result["present_teachers_count"] = present_count
        result["absent_teachers_count"] = absent_count
        return {
            "role": user.role,
            "metrics": result,
            "today_classes": today_classes,
            "today_classes_count": len(today_classes),
            "present_teachers_count": present_count,
            "absent_teachers_count": absent_count,
            "today_weekday": today_weekday,
            "active_plan_name": active_plan["plan_name"] if active_plan else "Regular Routine",
            "punched_not_enrolled": records(services.attendance.students_punched_not_enrolled()),
            "present_today": records(services.attendance.students_present_today()),
            "attendance_alerts": records(services.attendance.student_attendance_alerts()),
            "payment_alerts": payment_alerts,
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

    def _can_access_student(user: UserSession, student_id: int) -> bool:
        if auth.has_permission(user, "students.manage"):
            return True
        if auth.has_permission(user, "portal.student") and user.student_id and int(user.student_id) == int(student_id):
            return True
        return False

    @app.get("/api/students/{student_id}/profile")
    def student_profile(student_id: int, user: UserSession = Depends(session)):
        if not _can_access_student(user, student_id):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        try:
            profile = services.students.get_profile(student_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        student_data = dict(profile["student"])
        has_photo = bool(student_data.get("photo_data"))
        student_data.pop("photo_data", None)
        student_data["has_photo"] = has_photo
        profile["student"] = student_data
        return profile

    @app.get("/api/students/{student_id}/profile/pdf")
    def student_profile_pdf_download(student_id: int, user: UserSession = Depends(session)):
        if not _can_access_student(user, student_id):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        try:
            pdf_path = services.reports.student_profile_pdf(student_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return FileResponse(
            str(pdf_path),
            media_type="application/pdf",
            filename=pdf_path.name,
        )

    @app.get("/api/students/{student_id}/photo")
    def student_photo(student_id: int, user: UserSession = Depends(session)):
        if not _can_access_student(user, student_id):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        student = services.students.get(student_id)
        if not student or not student.photo_data:
            raise HTTPException(status_code=404, detail="Student photo was not found.")
        return Response(
            content=student.photo_data,
            media_type=student.photo_mime_type or "image/jpeg",
        )

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
            "grades": records(db.query("SELECT id,short_name,grade_name FROM grades WHERE status='Active' ORDER BY short_name")),
            "teachers": records(db.query("SELECT id,teacher_name,staff_type,basic_salary,salary_type,contact,email FROM teachers WHERE status='Active' ORDER BY teacher_name")),
            "students": records(db.query("SELECT id,student_name,contact,'' AS email,class_name FROM students WHERE status<>'Archived' ORDER BY student_name")),
            "roles": list(ROLES),
        }

    @app.get("/api/enrollments")
    def enrollments(_user=Depends(require("enrollments.manage"))):
        rows = db.query("SELECT e.id,s.student_name,c.course_name,e.level,e.start_date,e.end_date,e.monthly_fee,e.status FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id ORDER BY e.start_date DESC,s.student_name")
        return records(rows)

    @app.post("/api/enrollments", status_code=201)
    def create_enrollment(payload: EnrollmentInput, _user=Depends(require("enrollments.manage"))):
        enrollment_id = services.enrollments.create(payload.student_id, payload.course_id, payload.level, payload.start_date, payload.end_date, payload.monthly_fee, payload.admission_fee, payload.discount, "Active", "")
        return {"id": enrollment_id}

    @app.put("/api/enrollments/{enrollment_id}")
    def update_enrollment(enrollment_id: int, payload: EnrollmentUpdateInput, _user=Depends(require("enrollments.manage"))):
        existing = db.query_one("SELECT * FROM enrollments WHERE id=?", (enrollment_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Enrollment not found.")
        student_id = payload.student_id if payload.student_id is not None else existing["student_id"]
        course_id = payload.course_id if payload.course_id is not None else existing["course_id"]
        level = payload.level if payload.level is not None else (existing["level"] or "")
        start_date = payload.start_date if payload.start_date is not None else existing["start_date"]
        end_date = payload.end_date or payload.completion_date or (existing["end_date"] or "")
        monthly_fee = payload.monthly_fee if payload.monthly_fee is not None else float(existing["monthly_fee"] or 0)
        admission_fee = payload.admission_fee if payload.admission_fee is not None else float(existing["admission_fee"] or 0)
        discount = payload.discount if payload.discount is not None else float(existing["discount"] or 0)
        status = payload.status if payload.status is not None else existing["status"]
        remarks = payload.remarks if payload.remarks is not None else (existing["remarks"] or "")
        try:
            services.enrollments.update(
                enrollment_id, student_id, course_id, level, start_date, end_date,
                monthly_fee, admission_fee, discount, status, remarks
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True}

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

    @app.get("/api/attendance/poller/status")
    def attendance_poller_status(_user=Depends(require("devices.manage"))):
        return services.attendance_poller.status()

    @app.post("/api/attendance/poller/trigger")
    def attendance_poller_trigger(_user=Depends(require("devices.manage"))):
        try:
            result = services.attendance_poller.poll_now()
            return {
                "ok": True,
                "received": result.received,
                "saved": result.saved,
                "unmapped": result.unmapped,
            }
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/api/attendance/poller/config")
    def attendance_poller_config(payload: PollerConfigInput, _user=Depends(require("devices.manage"))):
        if payload.interval_seconds is not None:
            services.attendance_poller.set_interval(payload.interval_seconds)
        if payload.enabled is not None:
            services.attendance_poller.set_enabled(payload.enabled)
        return services.attendance_poller.status()

    @app.get("/api/academic-calendar")
    def academic_calendar(month: str = "", _user=Depends(require("devices.manage"))):
        selected_month = month or nepali.date.today().strftime("%Y/%m")
        return {
            "month": selected_month,
            "days": services.attendance.academic_calendar_month(selected_month),
            "events": records(db.query(
                "SELECT event.*,c.course_name FROM academic_calendar_events event "
                "LEFT JOIN courses c ON c.id=event.course_id "
                "WHERE event.start_date<=? AND event.end_date>=? ORDER BY event.start_date,event.id",
                (f"{selected_month}/99", f"{selected_month}/01"),
            )),
        }

    @app.get("/api/academic-calendar/courses")
    def academic_calendar_courses(_user=Depends(require("devices.manage"))):
        return records(db.query(
            "SELECT id,course_name,category FROM courses WHERE status='Active' ORDER BY course_name"
        ))

    @app.post("/api/academic-calendar", status_code=201)
    def create_calendar_event(payload: CalendarEventInput, _user=Depends(require("master_data.manage"))):
        start_date = validate_date(payload.start_date, "Start date", date_format=config.date_format)
        end_date = validate_date(payload.end_date, "End date", allow_blank=True, date_format=config.date_format) or start_date
        if end_date < start_date:
            raise HTTPException(status_code=422, detail="End date cannot be before start date.")
        if payload.course_id is not None and not db.query_one("SELECT id FROM courses WHERE id=?", (payload.course_id,)):
            raise HTTPException(status_code=422, detail="Selected course was not found.")
        return {"id": db.execute(
            "INSERT INTO academic_calendar_events (event_name,event_type,course_id,start_date,end_date,status,remarks) VALUES (?,?,?,?,?,?,?)",
            (payload.event_name.strip(), payload.event_type, payload.course_id, start_date, end_date, payload.status, payload.remarks.strip()),
        )}

    @app.post("/api/academic-calendar/bulk-weekends", status_code=201)
    def create_weekend_events(payload: BulkWeekendInput, _user=Depends(require("master_data.manage"))):
        try:
            month = validate_month(payload.month, "Calendar month")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not payload.weekend_days:
            raise HTTPException(status_code=422, detail="Select at least one weekend day.")
        if payload.course_id is not None and not db.query_one("SELECT id FROM courses WHERE id=?", (payload.course_id,)):
            raise HTTPException(status_code=422, detail="Selected course was not found.")
        year, month_number = (int(part) for part in month.split("/"))
        first = nepali.date(year, month_number, 1)
        next_month = nepali.date(year + 1, 1, 1) if month_number == 12 else nepali.date(year, month_number + 1, 1)
        wanted_days = set(payload.weekend_days)
        created = 0
        for day in range(1, (next_month - first).days + 1):
            value = nepali.date(year, month_number, day)
            weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[value.to_datetime_date().weekday()]
            if weekday not in wanted_days:
                continue
            business_date = value.strftime("%Y/%m/%d")
            existing = db.query_one(
                "SELECT id FROM academic_calendar_events WHERE event_name=? AND event_type=? "
                "AND start_date=? AND end_date=? AND (course_id=? OR (course_id IS NULL AND ? IS NULL))",
                (f"Weekend - {weekday}", payload.event_type, business_date, business_date, payload.course_id, payload.course_id),
            )
            if existing:
                continue
            db.execute(
                "INSERT INTO academic_calendar_events (event_name,event_type,course_id,start_date,end_date,status,remarks) VALUES (?,?,?,?,?,?,?)",
                (f"Weekend - {weekday}", payload.event_type, payload.course_id, business_date, business_date, "Active", payload.remarks.strip()),
            )
            created += 1
        return {"created": created, "month": month}

    @app.get("/api/billing/alerts")
    def billing_alerts(include_suppressed: bool = False, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "billing.manage") or auth.has_permission(user, "dashboard.view")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return services.billing.payment_alerts(include_suppressed=include_suppressed)

    @app.post("/api/billing/alerts/{bill_id}/review")
    def review_payment_alert(bill_id: int, payload: PaymentAlertReviewInput, user: UserSession = Depends(require("billing.manage"))):
        follow_up = validate_date(payload.follow_up_date, "Follow-up date", allow_blank=True, date_format=config.date_format)
        services.billing.record_payment_alert_review(bill_id, payload.status, payload.note, follow_up, user.user_id)
        return {"ok": True}

    @app.get("/api/bills")
    def bills(user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "billing.manage") or auth.has_permission(user, "portal.student")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        result = []
        is_student = user.role == "student" and user.student_id
        for bill in services.billing.repository.list():
            if is_student and bill.student_id != user.student_id:
                continue
            result.append({
                "id": bill.id, "bill_number": bill.bill_number, "enrollment_id": bill.enrollment_id,
                "student_id": bill.student_id,
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

    @app.get("/api/bills/auto-billing/preview")
    def auto_billing_preview(month: str = "", _user=Depends(require("billing.manage"))):
        try:
            return services.recurring_billing.preview(month or None)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/bills/auto-billing/run")
    def auto_billing_run(payload: AutoBillingRunInput, user=Depends(require("billing.manage"))):
        try:
            result = services.recurring_billing.run_auto_billing(
                target_month=payload.target_month or None,
                issue_date=payload.issue_date or None,
                due_date=payload.due_date or None,
                send_sms=payload.send_sms,
                remarks=payload.remarks,
                actor_username=user.username,
            )
            return result.to_dict()
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/bills/auto-billing/config")
    def auto_billing_config(payload: AutoBillingConfigInput, _user=Depends(require("billing.manage"))):
        try:
            return services.recurring_billing.update_config(
                enabled=payload.enabled,
                due_days=payload.due_days,
                auto_sms=payload.auto_sms,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/api/bills/{bill_id}/qr")
    def bill_payment_qr(bill_id: int, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "billing.manage") or auth.has_permission(user, "portal.student")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        bill = services.billing.repository.get(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill was not found.")
        if user.role == "student" and user.student_id and bill.student_id != user.student_id:
            raise HTTPException(status_code=403, detail="You do not have permission for this bill.")
        from elh.core.payment_qr import PaymentQrEngine
        remaining = max(Decimal("0"), bill.total_amount - bill.paid_amount)
        qr_data = PaymentQrEngine.from_settings(
            services.recurring_billing.settings,
            remaining,
            bill.bill_number,
            bill.student_name,
            bill.course_name,
        )
        if not qr_data:
            return {"enabled": False}
        payload = PaymentQrEngine.build_payload(qr_data)
        qr_svg = ""
        try:
            from reportlab.graphics import renderSVG
            drawing = PaymentQrEngine.build_reportlab_drawing(qr_data, size_mm=50.0)
            qr_svg = renderSVG.drawToString(drawing)
        except Exception:
            pass
        return {
            "enabled": True,
            "provider": qr_data.provider,
            "merchant_id": qr_data.merchant_id,
            "merchant_name": qr_data.merchant_name,
            "amount": float(remaining),
            "bill_number": bill.bill_number,
            "student_name": bill.student_name,
            "payload": payload,
            "instructions": qr_data.instructions,
            "qr_svg": qr_svg,
        }

    @app.get("/api/bills/{bill_id}/whatsapp")
    def bill_whatsapp_info(bill_id: int, _user=Depends(require("billing.manage"))):
        notif_svc = getattr(services, "notifications", None)
        if not notif_svc:
            raise HTTPException(status_code=503, detail="Notification service unavailable.")
        try:
            data = notif_svc.build_bill_whatsapp_message(bill_id)
            return {
                "bill_id": bill_id,
                "student_name": data["student_name"],
                "recipient": data["recipient"],
                "amount_due": data["amount_due"],
                "message": data["message"],
                "whatsapp_url": data["whatsapp_url"],
            }
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/bills/{bill_id}/whatsapp/send")
    def send_bill_whatsapp(bill_id: int, _user=Depends(require("billing.manage"))):
        notif_svc = getattr(services, "notifications", None)
        if not notif_svc:
            raise HTTPException(status_code=503, detail="Notification service unavailable.")
        try:
            data = notif_svc.build_bill_whatsapp_message(bill_id)
            resp = notif_svc.send_whatsapp(data["recipient"], data["message"])
            return {
                "success": resp.success,
                "code": resp.code,
                "message": resp.message,
                "message_id": resp.message_id,
            }
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/bills/pay-multiple")
    def pay_multiple_bills(payload: MultiBillPaymentInput, _user=Depends(require("billing.manage"))):
        validate_date(payload.payment_date, "Payment date", date_format=config.date_format)
        if payload.amount > 0 and not payload.account_id:
            raise HTTPException(status_code=422, detail="Select the receiving account.")
        try:
            result = services.billing.pay_bills(
                payload.bill_ids,
                Decimal(str(payload.amount)),
                payload.payment_date,
                payload.account_id,
                payload.payment_method,
                payload.receipt_no.strip(),
                payload.remarks.strip(),
                Decimal(str(payload.discount)),
                allow_advance=True,
            )
            return {
                "success": True,
                "student_id": result["student_id"],
                "student_name": result["student_name"],
                "updated_bills": result["updated_bills"],
                "total_paid": float(result["total_paid"]),
                "total_discount": float(result["total_discount"]),
                "advance_amount": float(result["advance_amount"]),
                "transaction_ids": result["transaction_ids"],
            }
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/bills/{bill_id}/payment")
    def pay_bill(bill_id: int, payload: BillPaymentInput, _user=Depends(require("billing.manage"))):
        validate_date(payload.payment_date, "Payment date", date_format=config.date_format)
        if payload.amount > 0 and not payload.account_id:
            raise HTTPException(status_code=422, detail="Select the receiving account.")
        try:
            result = services.billing.pay_bills(
                [bill_id],
                Decimal(str(payload.amount)),
                payload.payment_date,
                payload.account_id,
                payload.payment_method,
                payload.receipt_no.strip(),
                payload.remarks.strip(),
                Decimal(str(payload.discount)),
                allow_advance=True,
            )
            bill = services.billing.repository.get(bill_id)
            return {
                "id": bill.id,
                "status": bill.status,
                "advance_amount": float(result["advance_amount"]),
                "transaction_ids": result["transaction_ids"],
            }
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/api/staff")
    def staff(_user=Depends(require_any("staff.manage", "portal.staff", "master_data.manage"))):
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

    # -----------------------------------------------------------------------
    # Teacher / Staff Self-Service Portal
    # -----------------------------------------------------------------------
    @app.get("/api/teacher/dashboard")
    def get_teacher_portal_dashboard(user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "portal.staff") or auth.has_permission(user, "staff.manage") or auth.has_permission(user, "dashboard.view")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        teacher_id = user.teacher_id
        if not teacher_id:
            user_row = db.query_one("SELECT teacher_id FROM app_users WHERE id=?", (user.user_id,))
            if user_row and user_row["teacher_id"]:
                teacher_id = user_row["teacher_id"]
        return _build_teacher_portal_data(teacher_id, user)

    @app.get("/api/teacher/classes")
    def get_teacher_portal_classes(user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "portal.staff") or auth.has_permission(user, "staff.manage")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        teacher_id = user.teacher_id
        if not teacher_id:
            user_row = db.query_one("SELECT teacher_id FROM app_users WHERE id=?", (user.user_id,))
            if user_row and user_row["teacher_id"]:
                teacher_id = user_row["teacher_id"]
        data = _build_teacher_portal_data(teacher_id, user)
        return {
            "classes": data["class_distribution"],
            "students": data["assigned_students"],
            "total_students": data["assigned_students_count"],
            "weekly_routines": data["weekly_routines"],
            "total_classes_week": data["metrics"]["total_classes_week"],
            "today_routines": data["today_routines"],
            "today_classes_count": data["metrics"]["today_classes_count"],
            "teacher": data["teacher"],
        }

    @app.get("/api/teacher/attendance")
    def get_teacher_portal_attendance(month: str | None = None, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "portal.staff") or auth.has_permission(user, "staff.manage")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        teacher_id = user.teacher_id
        if not teacher_id:
            user_row = db.query_one("SELECT teacher_id FROM app_users WHERE id=?", (user.user_id,))
            if user_row and user_row["teacher_id"]:
                teacher_id = user_row["teacher_id"]
        data = _build_teacher_portal_data(teacher_id, user, target_month=month)
        return {
            "history": data["attendance_history"],
            "teacher": data["teacher"],
        }

    @app.get("/api/teacher/payments")
    def get_teacher_portal_payments(user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "portal.staff") or auth.has_permission(user, "staff.manage") or auth.has_permission(user, "payroll.manage")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        teacher_id = user.teacher_id
        if not teacher_id:
            user_row = db.query_one("SELECT teacher_id FROM app_users WHERE id=?", (user.user_id,))
            if user_row and user_row["teacher_id"]:
                teacher_id = user_row["teacher_id"]
        data = _build_teacher_portal_data(teacher_id, user)
        return {
            "salaries": data["salary_payouts"],
            "advances": data["advances"],
            "statement": data["statement"],
            "summary": data["payment_summary"],
            "teacher": data["teacher"],
        }

    @app.get("/api/accounts")
    def accounts(_user=Depends(require("finance.manage"))):
        rows = db.query("SELECT * FROM accounts ORDER BY is_billing_default DESC, account_name")
        return [{**dict(row), "balance": float(db.account_balance(row["id"]))} for row in rows]

    @app.post("/api/accounts", status_code=201)
    def create_account(payload: AccountInput, _user=Depends(require("finance.manage"))):
        if payload.is_billing_default:
            db.execute("UPDATE accounts SET is_billing_default=0")
        account_id = db.execute(
            "INSERT INTO accounts (account_name,account_type,bank_name,bank_code,account_number,account_holder,opening_balance,is_billing_default,status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (payload.account_name.strip(), payload.account_type.strip(), payload.bank_name.strip(),
             payload.bank_code.strip(), payload.account_number.strip(), payload.account_holder.strip(),
             str(Decimal(str(payload.opening_balance))), 1 if payload.is_billing_default else 0,
             payload.status, payload.remarks.strip()),
        )
        if payload.is_billing_default:
            _sync_billing_qr_account(account_id)
        return {"id": account_id}

    @app.post("/api/accounts/{account_id}/set-billing-default")
    def set_account_billing_default(account_id: int, _user=Depends(require("finance.manage"))):
        acc = db.query_one("SELECT * FROM accounts WHERE id=?", (account_id,))
        if not acc:
            raise HTTPException(status_code=404, detail="Account was not found.")
        db.execute("UPDATE accounts SET is_billing_default=0")
        db.execute("UPDATE accounts SET is_billing_default=1 WHERE id=?", (account_id,))
        _sync_billing_qr_account(account_id)
        return {"status": "success", "message": f"'{acc['account_name']}' is now set as the active billing QR account."}

    def _sync_billing_qr_account(account_id: int):
        acc = db.query_one("SELECT * FROM accounts WHERE id=?", (account_id,))
        if not acc:
            return
        from elh.core.settings import SettingsService
        settings = SettingsService(db)
        if acc["account_number"]:
            settings.set("payment_qr_account_number", str(acc["account_number"]))
            settings.set("payment_qr_merchant_id", str(acc["account_number"]))
        if "bank_code" in acc.keys() and acc["bank_code"]:
            settings.set("payment_qr_bank_code", str(acc["bank_code"]))
        label = str(acc["account_holder"] or acc["account_name"] or "").strip()
        if label:
            settings.set("payment_qr_merchant_name", label)

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
    # -----------------------------------------------------------------------
    # AI Assistant
    # -----------------------------------------------------------------------
    @app.post("/api/assistant/query")
    def assistant_query(payload: AssistantQueryInput, _user=Depends(require("assistant.view"))):
        if _user.role not in ("super_admin", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI Assistant is only accessible by admin and super admin.",
            )
        assistant = InstituteAssistant(services, db)
        res = assistant.execute(payload.prompt)
        return {
            "title": res.title,
            "content": res.content,
            "badge": res.badge,
            "data_rows": res.data_rows,
            "suggested_actions": res.suggested_actions,
        }

    # -----------------------------------------------------------------------
    # Course Certificates
    # -----------------------------------------------------------------------
    @app.get("/api/certificates")
    def list_certificates(user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "certificates.manage") or auth.has_permission(user, "portal.student")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        rows = services.certificates.repository.list()
        if user.role == "student" and user.student_id:
            rows = [r for r in rows if r["student_id"] == user.student_id]
        return records(rows)

    @app.get("/api/certificates/available-enrollments")
    def certificate_available_enrollments(_user=Depends(require("certificates.manage"))):
        return records(services.certificates.available_enrollments())

    @app.get("/api/certificates/next-number")
    def certificate_next_number(_user=Depends(require("certificates.manage"))):
        return {"certificate_number": services.certificates.next_certificate_number()}

    @app.post("/api/certificates", status_code=201)
    def issue_certificate(payload: CertificateInput, user=Depends(require("certificates.manage"))):
        cert = services.certificates.issue(CertificateIssueRequest(
            enrollment_id=payload.enrollment_id,
            certificate_number=payload.certificate_number,
            certify_date=payload.certify_date,
            instructor_name=payload.instructor_name,
            principal_name=payload.principal_name,
            remarks=payload.remarks,
            created_by_user_id=user.user_id,
        ))
        return {
            "id": cert.id,
            "certificate_number": cert.certificate_number,
            "pdf_path": cert.pdf_path,
            "document_path": cert.document_path,
        }

    @app.get("/api/certificates/{cert_id}/pdf")
    def certificate_pdf(cert_id: int, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "certificates.manage") or auth.has_permission(user, "portal.student")):
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        cert = services.certificates.repository.get(cert_id)
        if not cert:
            raise HTTPException(status_code=404, detail="Certificate was not found.")
        if user.role == "student" and user.student_id:
            enrollment = services.enrollments.repository.get(cert.enrollment_id)
            if not enrollment or enrollment.student_id != user.student_id:
                raise HTTPException(status_code=403, detail="You do not have permission for this certificate.")
        if not cert.pdf_path or not Path(cert.pdf_path).exists():
            pdf_path = services.certificates.generate_pdf(cert_id)
            services.certificates.repository.update_pdf(cert_id, str(pdf_path), sha256(pdf_path.read_bytes()).hexdigest())
            cert = services.certificates.repository.get(cert_id)
        return FileResponse(cert.pdf_path, media_type="application/pdf", filename=f"certificate_{cert.certificate_number}.pdf")

    @app.get("/api/certificates/{cert_id}/docx")
    def certificate_docx(cert_id: int, _user=Depends(require("certificates.manage"))):
        cert = services.certificates.repository.get(cert_id)
        if not cert:
            raise HTTPException(status_code=404, detail="Certificate was not found.")
        if not cert.document_path or not Path(cert.document_path).exists():
            doc_path = services.certificates.generate_docx(cert_id)
            services.certificates.repository.update_document_path(cert_id, str(doc_path))
            cert = services.certificates.repository.get(cert_id)
        return FileResponse(cert.document_path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=f"certificate_{cert.certificate_number}.docx")

    @app.post("/api/certificates/{cert_id}/regenerate-pdf")
    def regenerate_certificate_pdf(cert_id: int, _user=Depends(require("certificates.manage"))):
        pdf_path = services.certificates.generate_pdf(cert_id)
        services.certificates.repository.update_pdf(cert_id, str(pdf_path), sha256(pdf_path.read_bytes()).hexdigest())
        return {"ok": True}

    @app.post("/api/certificates/{cert_id}/regenerate-docx")
    def regenerate_certificate_docx(cert_id: int, _user=Depends(require("certificates.manage"))):
        doc_path = services.certificates.generate_docx(cert_id)
        services.certificates.repository.update_document_path(cert_id, str(doc_path))
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Student Account Transactions
    # -----------------------------------------------------------------------
    @app.get("/api/student-transactions")
    def list_student_transactions(student_id: int | None = None, _user=Depends(require("billing.manage"))):
        sql = """
            SELECT st.*, s.student_name, COALESCE(a.account_name, '') account_name
            FROM student_transactions st
            JOIN students s ON s.id=st.student_id
            LEFT JOIN accounts a ON a.id=st.account_id
        """
        params = []
        if student_id:
            sql += " WHERE st.student_id=?"
            params.append(student_id)
        sql += " ORDER BY st.transaction_date DESC, st.id DESC LIMIT 1000"
        return records(db.query(sql, tuple(params)))

    @app.post("/api/student-transactions", status_code=201)
    def create_student_transaction(payload: StudentTransactionInput, _user=Depends(require("billing.manage"))):
        trans_date = validate_date(payload.transaction_date, "Transaction date", date_format=config.date_format)
        particular = payload.particular.strip()
        if not particular:
            raise HTTPException(status_code=422, detail="Particular is required.")
        charge = Decimal(str(payload.charge_amount))
        payment = Decimal(str(payload.payment_amount))
        discount = Decimal(str(payload.discount_amount))
        if charge == 0 and payment == 0 and discount == 0:
            raise HTTPException(status_code=422, detail="Enter a charge, payment, or discount amount.")

        account_id = payload.account_id
        if (payment > 0 or payload.transaction_type == "Refund") and not account_id:
            raise HTTPException(status_code=422, detail="Payment account is required for this transaction.")

        if payload.transaction_type == "Refund" and payment > 0:
            if db.account_balance(account_id) < payment:
                raise HTTPException(status_code=422, detail="Account has insufficient balance for refund.")

        def callback(conn):
            cur = conn.execute(
                """
                INSERT INTO student_transactions
                (student_id, enrollment_id, transaction_date, transaction_type,
                 particular, charge_amount, payment_amount, discount_amount,
                 account_id, payment_method, receipt_no, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.student_id, payload.enrollment_id, trans_date, payload.transaction_type,
                    particular, str(charge), str(payment), str(discount), account_id,
                    payload.payment_method, payload.receipt_no.strip(),
                    payload.remarks.strip(),
                ),
            )
            trans_id = cur.lastrowid
            if account_id and payment > 0:
                direction = "OUT" if payload.transaction_type == "Refund" else "IN"
                db.add_ledger(
                    conn, trans_date, account_id, direction, float(payment),
                    "Student Transaction", trans_id, particular,
                    payload.receipt_no.strip(), payload.remarks.strip(),
                )
            return trans_id
        return {"id": db.transaction(callback)}

    # -----------------------------------------------------------------------
    # Grades & Class Levels
    # -----------------------------------------------------------------------
    @app.get("/api/grades")
    def list_grades(_user=Depends(require("master_data.manage"))):
        return records(db.query("SELECT * FROM grades ORDER BY short_name"))

    @app.post("/api/grades", status_code=201)
    def create_grade(payload: GradeInput, _user=Depends(require("master_data.manage"))):
        grade_id = db.execute(
            "INSERT INTO grades (short_name, grade_name, status, remarks) VALUES (?, ?, ?, ?)",
            (payload.short_name.strip(), payload.grade_name.strip(), payload.status, payload.remarks.strip()),
        )
        return {"id": grade_id}

    @app.put("/api/grades/{grade_id}")
    def update_grade(grade_id: int, payload: GradeInput, _user=Depends(require("master_data.manage"))):
        db.execute(
            "UPDATE grades SET short_name=?, grade_name=?, status=?, remarks=? WHERE id=?",
            (payload.short_name.strip(), payload.grade_name.strip(), payload.status, payload.remarks.strip(), grade_id),
        )
        return {"ok": True}

    @app.get("/api/class-levels")
    def list_class_levels(_user=Depends(require("master_data.manage"))):
        return records(db.query("SELECT * FROM class_levels ORDER BY level_name"))

    @app.post("/api/class-levels", status_code=201)
    def create_class_level(payload: ClassLevelInput, _user=Depends(require("master_data.manage"))):
        level_id = db.execute(
            "INSERT INTO class_levels (level_name, status, remarks) VALUES (?, ?, ?)",
            (payload.level_name.strip(), payload.status, payload.remarks.strip()),
        )
        return {"id": level_id}

    @app.put("/api/class-levels/{level_id}")
    def update_class_level(level_id: int, payload: ClassLevelInput, _user=Depends(require("master_data.manage"))):
        db.execute(
            "UPDATE class_levels SET level_name=?, status=?, remarks=? WHERE id=?",
            (payload.level_name.strip(), payload.status, payload.remarks.strip(), level_id),
        )
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Class Routines
    # -----------------------------------------------------------------------
    @app.get("/api/routines/plans")
    def list_routine_plans(_user=Depends(require_any("master_data.manage", "portal.student", "portal.staff"))):
        return records(db.query(
            "SELECT id, plan_name, effective_from, status, remarks FROM routine_plans "
            "ORDER BY CASE status WHEN 'Active' THEN 0 ELSE 1 END, effective_from DESC, id DESC"
        ))

    @app.post("/api/routines/plans", status_code=201)
    def create_routine_plan(payload: RoutinePlanInput, _user=Depends(require("master_data.manage"))):
        plan_name = payload.plan_name.strip()
        starts = validate_date(payload.effective_from, "Effective from date", date_format=config.date_format)
        def callback(conn):
            cur = conn.execute(
                "INSERT INTO routine_plans (plan_name, effective_from, status, remarks) VALUES (?, ?, 'Active', ?)",
                (plan_name, starts, payload.remarks.strip()),
            )
            new_id = cur.lastrowid
            if payload.copy_from_plan_id:
                conn.execute(
                    "INSERT INTO class_routines (routine_plan_id, class_name, day_of_week, period_label, subject_name, "
                    "class_level_id, teacher_id, course_id, start_time, end_time, status, remarks) "
                    "SELECT ?, class_name, day_of_week, period_label, subject_name, class_level_id, teacher_id, course_id, "
                    "start_time, end_time, status, remarks FROM class_routines WHERE routine_plan_id=?",
                    (new_id, payload.copy_from_plan_id),
                )
                if payload.archive_source:
                    conn.execute(
                        "UPDATE routine_plans SET status='Archived', effective_to=? WHERE id=?",
                        (starts, payload.copy_from_plan_id),
                    )
            return new_id
        return {"id": db.transaction(callback)}

    @app.get("/api/routines")
    def list_routines(
        routine_plan_id: int | None = None,
        class_level_id: int | None = None,
        course_id: int | None = None,
        _user=Depends(require_any("master_data.manage", "portal.student", "portal.staff")),
    ):
        if not routine_plan_id:
            active_plan = db.query_one("SELECT id FROM routine_plans WHERE status='Active' ORDER BY effective_from DESC LIMIT 1")
            routine_plan_id = active_plan["id"] if active_plan else None
        if not routine_plan_id:
            return []

        is_student = _user.role == "student" or (_user.student_id and not auth.has_permission(_user, "master_data.manage"))
        where_match = "1=1"
        match_params = []

        if is_student:
            student_id = _user.student_id
            if not student_id:
                user_row = db.query_one("SELECT student_id FROM app_users WHERE id=?", (_user.user_id,))
                if user_row and user_row["student_id"]:
                    student_id = user_row["student_id"]
            if not student_id:
                return []
            student = db.query_one("SELECT id, class_name, class_level_id, grade_id FROM students WHERE id=?", (student_id,))
            if not student:
                return []

            enrolled_rows = db.query(
                "SELECT e.course_id FROM enrollments e WHERE e.student_id=? AND e.status='Active'",
                (student_id,),
            )
            enrolled_course_ids = [int(r["course_id"]) for r in enrolled_rows if r["course_id"]]
            st_class = str(student["class_name"] or "").strip()
            st_class_id = student["class_level_id"]
            alt_class = f"Grade {st_class}" if st_class.isdigit() else (st_class[6:].strip() if st_class.lower().startswith("grade ") else st_class)

            if st_class_id or st_class:
                class_clause = "((r.class_level_id = ? AND r.class_level_id != 0) OR (r.class_name IS NOT NULL AND r.class_name != '' AND (r.class_name = ? OR r.class_name = ?)) OR ((r.class_level_id IS NULL OR r.class_level_id = 0) AND (r.class_name IS NULL OR r.class_name = '' OR LOWER(r.class_name) = 'all')))"
                class_params = [st_class_id or 0, st_class, alt_class]
            else:
                class_clause = "1=1"
                class_params = []

            if course_id is not None and course_id > 0:
                if int(course_id) not in enrolled_course_ids:
                    return []
                where_match = f"({class_clause} AND r.course_id = ?)"
                match_params = [*class_params, int(course_id)]
            elif course_id is not None and course_id <= 0:
                where_match = f"({class_clause} AND r.course_id IS NULL)"
                match_params = list(class_params)
            else:
                if enrolled_course_ids:
                    c_placeholders = ",".join("?" for _ in enrolled_course_ids)
                    where_match = f"({class_clause} AND (r.course_id IS NULL OR r.course_id IN ({c_placeholders})))"
                    match_params = [*class_params, *enrolled_course_ids]
                else:
                    where_match = f"({class_clause} AND r.course_id IS NULL)"
                    match_params = list(class_params)
        else:
            is_teacher = _user.role in ("staff", "teacher") or (_user.teacher_id and not auth.has_permission(_user, "master_data.manage"))
            if is_teacher and _user.teacher_id:
                where_match += " AND r.teacher_id = ?"
                match_params.append(int(_user.teacher_id))
            if class_level_id:
                where_match += " AND r.class_level_id = ?"
                match_params.append(int(class_level_id))
            if course_id:
                where_match += " AND r.course_id = ?"
                match_params.append(int(course_id))

        rows = db.query(
            "SELECT r.*, t.teacher_name, c.course_name, cl.level_name "
            "FROM class_routines r "
            "LEFT JOIN teachers t ON t.id=r.teacher_id "
            "LEFT JOIN courses c ON c.id=r.course_id "
            "LEFT JOIN class_levels cl ON cl.id=r.class_level_id "
            f"WHERE r.routine_plan_id=? AND {where_match} "
            "ORDER BY CASE r.day_of_week WHEN 'Sunday' THEN 1 WHEN 'Monday' THEN 2 WHEN 'Tuesday' THEN 3 "
            "WHEN 'Wednesday' THEN 4 WHEN 'Thursday' THEN 5 WHEN 'Friday' THEN 6 WHEN 'Saturday' THEN 7 ELSE 8 END, "
            "r.class_name, r.start_time, r.period_label",
            (routine_plan_id, *match_params),
        )
        return records(rows)

    @app.post("/api/routines", status_code=201)
    def create_routine_period(payload: RoutinePeriodInput, _user=Depends(require("master_data.manage"))):
        routine_id = db.execute(
            "INSERT INTO class_routines (class_name, day_of_week, period_label, subject_name, class_level_id, teacher_id, course_id, start_time, end_time, status, remarks, routine_plan_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (payload.class_name.strip(), payload.day_of_week, payload.period_label.strip(), payload.subject_name.strip(),
             payload.class_level_id, payload.teacher_id, payload.course_id, payload.start_time.strip(), payload.end_time.strip(),
             payload.status, payload.remarks.strip(), payload.routine_plan_id),
        )
        return {"id": routine_id}

    @app.put("/api/routines/{routine_id}")
    def update_routine_period(routine_id: int, payload: RoutinePeriodInput, _user=Depends(require("master_data.manage"))):
        db.execute(
            "UPDATE class_routines SET class_name=?, day_of_week=?, period_label=?, subject_name=?, class_level_id=?, teacher_id=?, course_id=?, start_time=?, end_time=?, status=?, remarks=?, routine_plan_id=? WHERE id=?",
            (payload.class_name.strip(), payload.day_of_week, payload.period_label.strip(), payload.subject_name.strip(),
             payload.class_level_id, payload.teacher_id, payload.course_id, payload.start_time.strip(), payload.end_time.strip(),
             payload.status, payload.remarks.strip(), payload.routine_plan_id, routine_id),
        )
        return {"ok": True}

    @app.delete("/api/routines/{routine_id}")
    def delete_routine_period(routine_id: int, _user=Depends(require("master_data.manage"))):
        db.execute("DELETE FROM class_routines WHERE id=?", (routine_id,))
        return {"ok": True}

    @app.get("/api/routines/pdf")
    def download_routine_pdf(
        class_level_id: int | None = None,
        routine_plan_id: int | None = None,
        course_id: int | None = None,
        _user=Depends(require_any("master_data.manage", "portal.student", "portal.staff")),
    ):
        is_student = _user.role == "student" or (_user.student_id and not auth.has_permission(_user, "master_data.manage"))
        allowed_course_ids = None
        class_name = None

        if is_student:
            student_id = _user.student_id
            if not student_id:
                user_row = db.query_one("SELECT student_id FROM app_users WHERE id=?", (_user.user_id,))
                if user_row and user_row["student_id"]:
                    student_id = user_row["student_id"]
            if not student_id:
                raise HTTPException(status_code=403, detail="Student account is not linked to a student record.")
            student = db.query_one("SELECT id, class_name, class_level_id FROM students WHERE id=?", (student_id,))
            if not student:
                raise HTTPException(status_code=404, detail="Student record not found.")

            class_level_id = student["class_level_id"]
            class_name = student["class_name"]

            enrolled_rows = db.query(
                "SELECT e.course_id FROM enrollments e WHERE e.student_id=? AND e.status='Active'",
                (student_id,),
            )
            enrolled_course_ids = [int(r["course_id"]) for r in enrolled_rows if r["course_id"]]
            allowed_course_ids = enrolled_course_ids

            if course_id is not None and course_id > 0:
                if int(course_id) not in enrolled_course_ids:
                    raise HTTPException(status_code=403, detail="You are not enrolled in this course.")
            elif course_id is not None and course_id <= 0:
                allowed_course_ids = []
                course_id = None

        is_teacher = _user.role in ("staff", "teacher") or (_user.teacher_id and not auth.has_permission(_user, "master_data.manage"))
        filter_teacher_id = None
        if is_teacher and _user.teacher_id:
            filter_teacher_id = int(_user.teacher_id)

        try:
            pdf_path = services.reports.routine_pdf(
                class_level_id=class_level_id,
                routine_plan_id=routine_plan_id,
                course_id=course_id if (course_id and course_id > 0) else None,
                allowed_course_ids=allowed_course_ids,
                class_name=class_name,
                teacher_id=filter_teacher_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=pdf_path.name)

    # -----------------------------------------------------------------------
    # Staff Advances
    # -----------------------------------------------------------------------
    @app.get("/api/advances")
    def list_advances(_user=Depends(require_any("payroll.manage", "finance.manage"))):
        rows = db.query(
            "SELECT ta.*, t.teacher_name, a.account_name, "
            "(ta.amount - ta.recovered_amount) remaining "
            "FROM teacher_advances ta "
            "JOIN teachers t ON t.id=ta.teacher_id "
            "JOIN accounts a ON a.id=ta.paid_from_account_id "
            "ORDER BY ta.advance_date DESC, ta.id DESC"
        )
        return records(rows)

    @app.post("/api/advances", status_code=201)
    def create_advance(payload: StaffAdvanceInput, _user=Depends(require_any("payroll.manage", "finance.manage"))):
        advance_date = validate_date(payload.advance_date, "Advance date", date_format=config.date_format)
        amount = Decimal(str(payload.amount))
        if db.account_balance(payload.paid_from_account_id) < amount:
            raise HTTPException(status_code=422, detail="Source account does not have sufficient balance.")

        def callback(conn):
            cur = conn.execute(
                """
                INSERT INTO teacher_advances
                (teacher_id, advance_date, amount, paid_from_account_id,
                 payment_method, reference_no, recovery_method,
                 recovery_start_month, monthly_deduction, status, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Outstanding', ?)
                """,
                (
                    payload.teacher_id, advance_date, str(amount), payload.paid_from_account_id,
                    payload.payment_method, payload.reference_no.strip(),
                    payload.recovery_method, payload.recovery_start_month.strip(),
                    str(Decimal(str(payload.monthly_deduction or 0))), payload.remarks.strip(),
                ),
            )
            advance_id = cur.lastrowid
            db.add_ledger(
                conn, advance_date, payload.paid_from_account_id, "OUT", float(amount),
                "Teacher Advance", advance_id, "Teacher advance payout",
                payload.reference_no.strip(), payload.remarks.strip(),
            )
            services.staff_finance.record_payment(
                conn, payload.teacher_id, advance_date, "Staff Advance", float(amount),
                "Teacher Advance", advance_id, payload.paid_from_account_id,
                "Recoverable staff advance", payload.reference_no.strip(),
                payload.remarks.strip(),
            )
            return advance_id
        return {"id": db.transaction(callback)}

    # -----------------------------------------------------------------------
    # Staff Salary Payouts & Payslips
    # -----------------------------------------------------------------------
    @app.get("/api/salary")
    def list_salary_payouts(_user=Depends(require_any("payroll.manage", "finance.manage"))):
        rows = db.query(
            "SELECT sp.*, t.teacher_name, t.staff_type, a.account_name "
            "FROM salary_payouts sp "
            "JOIN teachers t ON t.id=sp.teacher_id "
            "JOIN accounts a ON a.id=sp.paid_from_account_id "
            "ORDER BY sp.salary_month DESC, sp.payment_date DESC, sp.id DESC"
        )
        return records(rows)

    @app.post("/api/salary/calculate")
    def calculate_salary_attendance(payload: SalaryCalculateInput, _user=Depends(require_any("payroll.manage", "finance.manage"))):
        month = validate_month(payload.salary_month, "Salary month")
        summary = services.attendance.staff_month_summary(payload.teacher_id, month)
        routine = services.attendance.teacher_period_summary(payload.teacher_id, month)
        adv_row = db.query_one(
            "SELECT COALESCE(SUM(amount - recovered_amount), 0) total_advance "
            "FROM teacher_advances WHERE teacher_id=? AND status IN ('Outstanding', 'Partially Recovered')",
            (payload.teacher_id,),
        )
        teacher_row = db.query_one("SELECT salary_type, basic_salary FROM teachers WHERE id=?", (payload.teacher_id,))
        return {
            "summary": summary,
            "scheduled_classes": routine["scheduled_classes"],
            "outstanding_advance": float(adv_row["total_advance"] if adv_row else 0),
            "salary_type": teacher_row["salary_type"] if teacher_row else "Monthly Salary",
            "basic_salary": float(teacher_row["basic_salary"] if teacher_row else 0),
        }

    @app.post("/api/salary", status_code=201)
    def create_salary_payout(payload: SalaryPayoutInput, _user=Depends(require_any("payroll.manage", "finance.manage"))):
        month = validate_month(payload.salary_month, "Salary month")
        pay_date = validate_date(payload.payment_date, "Payment date", date_format=config.date_format)
        basic = Decimal(str(payload.basic_salary))
        extra = Decimal(str(payload.extra_payment))
        bonus = Decimal(str(payload.bonus))
        allowance = Decimal(str(payload.allowance))
        advance = Decimal(str(payload.advance_deduction))
        other = Decimal(str(payload.other_deduction))
        net = basic + extra + bonus + allowance - advance - other
        if net < 0:
            raise HTTPException(status_code=422, detail="Net salary cannot be negative.")

        if db.account_balance(payload.paid_from_account_id) < net:
            raise HTTPException(status_code=422, detail="Paid from account has insufficient balance.")

        existing = db.query_one("SELECT id FROM salary_payouts WHERE teacher_id=? AND salary_month=?", (payload.teacher_id, month))
        if existing:
            raise HTTPException(status_code=422, detail="Salary payout for this staff member and month already exists.")

        def callback(conn):
            cur = conn.execute(
                """
                INSERT INTO salary_payouts
                (teacher_id, salary_month, basic_salary, extra_payment, bonus,
                 allowance, advance_deduction, other_deduction, net_salary,
                 attendance_days, working_hours, class_count,
                 payment_date, paid_from_account_id, payment_method,
                 voucher_no, status, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Paid', ?)
                """,
                (
                    payload.teacher_id, month, str(basic), str(extra), str(bonus),
                    str(allowance), str(advance), str(other), str(net),
                    payload.attendance_days, str(payload.working_hours), payload.class_count,
                    pay_date, payload.paid_from_account_id, payload.payment_method,
                    payload.voucher_no.strip(), payload.remarks.strip(),
                ),
            )
            salary_id = cur.lastrowid
            staff_row = conn.execute("SELECT teacher_name FROM teachers WHERE id=?", (payload.teacher_id,)).fetchone()
            staff_name = staff_row["teacher_name"] if staff_row else "Staff member"
            gross_salary = basic + extra + bonus + allowance

            conn.execute(
                """
                INSERT INTO expense_records
                (expense_date, category, particular, amount, paid_from_account_id, paid_to,
                 payment_status, payment_method, reference_no, remarks)
                VALUES (?, 'Staff Salary', ?, ?, ?, ?, 'Paid', ?, ?, ?)
                """,
                (
                    pay_date, f"Salary expense for {staff_name} — {month}", str(gross_salary),
                    payload.paid_from_account_id, staff_name, payload.payment_method,
                    payload.voucher_no.strip(), payload.remarks.strip(),
                ),
            )
            db.add_ledger(
                conn, pay_date, payload.paid_from_account_id, "OUT", float(net), "Salary Payout",
                salary_id, f"Salary payment for {month}",
                payload.voucher_no.strip(), payload.remarks.strip(),
            )
            services.staff_finance.record_payment(
                conn, payload.teacher_id, pay_date, "Salary Payment", float(net),
                "Salary Payout", salary_id, payload.paid_from_account_id,
                f"Salary payment for {month}", payload.voucher_no.strip(),
                payload.remarks.strip(),
            )

            if advance > 0:
                advances = conn.execute(
                    "SELECT * FROM teacher_advances WHERE teacher_id=? AND status IN ('Outstanding','Partially Recovered') ORDER BY advance_date, id",
                    (payload.teacher_id,),
                ).fetchall()
                rem = advance
                updates = []
                for adv in advances:
                    if rem <= 0:
                        break
                    outstanding = Decimal(str(adv["amount"])) - Decimal(str(adv["recovered_amount"]))
                    applied = min(outstanding, rem)
                    new_rec = Decimal(str(adv["recovered_amount"])) + applied
                    stat = "Fully Recovered" if new_rec >= Decimal(str(adv["amount"])) else "Partially Recovered"
                    updates.append((str(new_rec), stat, adv["id"]))
                    rem -= applied
                if updates:
                    conn.executemany("UPDATE teacher_advances SET recovered_amount=?, status=? WHERE id=?", updates)
                    rec = advance - rem
                    services.staff_finance.record_payment(
                        conn, payload.teacher_id, pay_date, "Advance Recovery", float(rec),
                        "Salary Payout", salary_id, None,
                        f"Advance recovery through salary — {month}",
                        payload.voucher_no.strip(), payload.remarks.strip(),
                    )
            return salary_id
        return {"id": db.transaction(callback)}

    @app.get("/api/salary/{salary_id}/payslip/pdf")
    def download_payslip_pdf(salary_id: int, _user=Depends(require_any("payroll.manage", "finance.manage", "portal.staff"))):
        if not (auth.has_permission(_user, "payroll.manage") or auth.has_permission(_user, "finance.manage")):
            salary_row = db.query_one("SELECT teacher_id FROM salary_payouts WHERE id=?", (salary_id,))
            if not salary_row or not _user.teacher_id or int(salary_row["teacher_id"]) != int(_user.teacher_id):
                raise HTTPException(status_code=403, detail="You do not have permission for this payslip.")
        try:
            pdf_path = services.reports.payment_proof_pdf("salary", salary_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=pdf_path.name)

    # -----------------------------------------------------------------------
    # System Settings, Health & Backup
    # -----------------------------------------------------------------------
    @app.get("/api/settings")
    def list_settings(_user=Depends(require("administration.manage"))):
        settings_service = SettingsService(db)
        settings_service.ensure_defaults()
        return records(settings_service.rows())

    @app.put("/api/settings")
    def update_settings(payload: SettingsUpdateInput, _user=Depends(require("administration.manage"))):
        settings_service = SettingsService(db)
        for key, value in payload.settings.items():
            settings_service.set(key, str(value))
            if key == "gemini_api_key" and value:
                os.environ["GEMINI_API_KEY"] = str(value)
            elif key == "ai_provider" and value:
                os.environ["AI_PROVIDER"] = str(value)
            elif key == "ai_model" and value:
                os.environ["AI_MODEL"] = str(value)
        return {"ok": True}

    @app.get("/api/system/health")
    def system_health(_user=Depends(require("administration.manage"))):
        health_service = HealthService(config, db)
        rep = health_service.report()
        checks = rep.get("checks", [])
        all_ok = all(c["status"] == "ok" for c in checks)
        any_error = any(c["status"] == "error" for c in checks)
        status = "ok" if all_ok else ("error" if any_error else "warning")
        return {
            "status": status,
            "message": f"Environment: {rep.get('environment')} | Status: {rep.get('status')}",
            "checks": checks,
            "timestamp": rep.get("timestamp"),
        }

    @app.post("/api/system/backup")
    def create_database_backup(_user=Depends(require_any("administration.manage", "backup.manage"))):
        backup_service = BackupService(config)
        try:
            path = backup_service.create()
            return {
                "ok": True,
                "backup_path": str(path),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Backup failed: {exc}")

    # -----------------------------------------------------------------------
    # Proxy Class Management Helpers & Endpoints
    # -----------------------------------------------------------------------
    def _get_students_for_routine(routine_id: int) -> list[dict]:
        routine = db.query_one("SELECT * FROM class_routines WHERE id = ?", (routine_id,))
        if not routine:
            return []
        c_level_id = routine.get("class_level_id")
        c_name = str(routine.get("class_name") or "").strip()
        c_id = routine.get("course_id")

        clauses = ["s.status <> 'Archived'"]
        params = []
        if c_id:
            clauses.append("s.id IN (SELECT student_id FROM enrollments WHERE course_id = ? AND status = 'Active')")
            params.append(c_id)
        elif c_level_id:
            clauses.append("((s.class_level_id = ? AND s.class_level_id != 0) OR s.class_name = ? OR s.class_name = ?)")
            params.extend([c_level_id, c_name, f"Grade {c_name}"])
        elif c_name:
            clauses.append("(s.class_name = ? OR s.class_name = ?)")
            params.extend([c_name, f"Grade {c_name}"])

        rows = db.query(
            f"SELECT s.id, s.student_name, s.contact FROM students s WHERE {' AND '.join(clauses)}",
            tuple(params)
        )
        return records(rows)

    def _create_student_proxy_notifications(proxy_request_id: int):
        req = db.query_one("SELECT routine_id FROM proxy_class_requests WHERE id = ?", (proxy_request_id,))
        if not req:
            return
        students = _get_students_for_routine(req["routine_id"])
        for s in students:
            existing = db.query_one(
                "SELECT id FROM proxy_student_notifications WHERE proxy_request_id = ? AND student_id = ?",
                (proxy_request_id, s["id"])
            )
            if not existing:
                db.execute(
                    "INSERT INTO proxy_student_notifications (proxy_request_id, student_id, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (proxy_request_id, s["id"])
                )

    def _dispatch_proxy_sms(proxy_request_id: int) -> int:
        req = db.query_one(
            """
            SELECT p.*, r.subject_name,
                   COALESCE(ot.teacher_name, 'Teacher') AS original_teacher_name,
                   COALESCE(pt.teacher_name, 'Substitute') AS proxy_teacher_name
            FROM proxy_class_requests p
            JOIN class_routines r ON r.id = p.routine_id
            LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
            LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id
            WHERE p.id = ?
            """,
            (proxy_request_id,)
        )
        if not req:
            return 0
        students = _get_students_for_routine(req["routine_id"])
        count = 0
        for s in students:
            contact = str(s.get("contact") or "").strip()
            if not contact:
                continue
            try:
                services.notifications.notify(
                    event_key="proxy_class_notification",
                    entity_type="proxy_class_request",
                    entity_id=proxy_request_id,
                    recipient=contact,
                    context={
                        "student_name": s["student_name"],
                        "subject_name": req.get("subject_name") or "Class",
                        "class_date": str(req["class_date"]),
                        "proxy_teacher_name": req["proxy_teacher_name"],
                        "original_teacher_name": req["original_teacher_name"],
                    }
                )
                count += 1
            except Exception:
                pass
        db.execute(
            "UPDATE proxy_class_requests SET sms_sent = sms_sent + ?, sms_sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (count, proxy_request_id)
        )
        return count

    @app.get("/api/proxy/requests")
    def get_proxy_requests(
        status: str = "All",
        date: str = "",
        user: UserSession = Depends(session)
    ):
        if not (auth.has_permission(user, "portal.staff") or auth.has_permission(user, "staff.manage") or auth.has_permission(user, "dashboard.view")):
            raise HTTPException(status_code=403, detail="Permission denied.")

        clauses = []
        params = []

        is_admin = auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")
        teacher_id = user.teacher_id
        if not is_admin and teacher_id:
            clauses.append("(p.requested_by_teacher_id = ? OR p.original_teacher_id = ? OR p.proxy_teacher_id = ?)")
            params.extend([teacher_id, teacher_id, teacher_id])

        if status and status != "All":
            clauses.append("p.status = ?")
            params.append(status)

        if date:
            clauses.append("p.class_date = ?")
            params.append(date)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        rows = db.query(
            f"""
            SELECT p.*,
                   r.class_name, r.subject_name, r.period_label, r.start_time, r.end_time, r.day_of_week,
                   r.course_id, r.class_level_id,
                   COALESCE(cl.level_name, r.class_name) AS display_class_name,
                   COALESCE(ot.teacher_name, 'Unassigned') AS original_teacher_name,
                   COALESCE(pt.teacher_name, 'Unassigned') AS proxy_teacher_name,
                   COALESCE(rt.teacher_name, 'Self') AS requested_by_teacher_name,
                   COALESCE(u.display_name, u.username, 'System') AS requested_by_user_name
            FROM proxy_class_requests p
            JOIN class_routines r ON r.id = p.routine_id
            LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
            LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id
            LEFT JOIN teachers rt ON rt.id = p.requested_by_teacher_id
            LEFT JOIN app_users u ON u.id = p.requested_by_user_id
            LEFT JOIN class_levels cl ON cl.id = r.class_level_id
            {where_sql}
            ORDER BY p.class_date DESC, r.start_time ASC, p.id DESC
            """,
            tuple(params)
        )
        return records(rows)

    @app.post("/api/proxy/requests", status_code=201)
    def create_proxy_request(payload: ProxyLeaveRequestInput, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "portal.staff") or auth.has_permission(user, "staff.manage")):
            raise HTTPException(status_code=403, detail="Permission denied.")

        routine = db.query_one("SELECT * FROM class_routines WHERE id = ?", (payload.routine_id,))
        if not routine:
            raise HTTPException(status_code=404, detail="Class routine not found.")

        is_admin = auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")
        original_teacher_id = payload.original_teacher_id or routine.get("teacher_id")

        if not is_admin:
            teacher_id = user.teacher_id
            if not teacher_id:
                user_row = db.query_one("SELECT teacher_id FROM app_users WHERE id=?", (user.user_id,))
                teacher_id = user_row["teacher_id"] if user_row else None
            original_teacher_id = teacher_id or routine.get("teacher_id")
            requested_by_teacher_id = teacher_id
            init_status = "Pending"
            proxy_teacher_id = None
            proxy_status = "Pending"
        else:
            requested_by_teacher_id = original_teacher_id
            proxy_teacher_id = payload.proxy_teacher_id
            init_status = "Approved" if proxy_teacher_id else "Pending"
            proxy_status = "Pending" if proxy_teacher_id else "Pending"

        req_id = db.execute(
            """
            INSERT INTO proxy_class_requests (
                routine_id, class_date, original_teacher_id, requested_by_teacher_id,
                requested_by_user_id, reason, leave_type, status, proxy_teacher_id,
                proxy_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                payload.routine_id,
                payload.class_date,
                original_teacher_id,
                requested_by_teacher_id,
                user.user_id,
                (payload.reason or "").strip(),
                payload.leave_type or "Absent",
                init_status,
                proxy_teacher_id,
                proxy_status
            )
        )

        return {"id": req_id, "ok": True, "message": "Proxy leave request submitted successfully."}

    @app.post("/api/proxy/requests/{request_id}/approve")
    def approve_proxy_request(request_id: int, payload: ProxyStatusInput, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")):
            raise HTTPException(status_code=403, detail="Admin permission required.")

        req = db.query_one("SELECT * FROM proxy_class_requests WHERE id = ?", (request_id,))
        if not req:
            raise HTTPException(status_code=404, detail="Request not found.")

        note = (payload.admin_note or "").strip()
        db.execute(
            """
            UPDATE proxy_class_requests
            SET status = 'Approved', admin_note = ?, approved_by_user_id = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (note, user.user_id, request_id)
        )
        return {"ok": True, "message": "Leave request approved."}

    @app.post("/api/proxy/requests/{request_id}/reject")
    def reject_proxy_request(request_id: int, payload: ProxyStatusInput, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")):
            raise HTTPException(status_code=403, detail="Admin permission required.")

        req = db.query_one("SELECT * FROM proxy_class_requests WHERE id = ?", (request_id,))
        if not req:
            raise HTTPException(status_code=404, detail="Request not found.")

        note = (payload.admin_note or "").strip()
        db.execute(
            """
            UPDATE proxy_class_requests
            SET status = 'Rejected', admin_note = ?, approved_by_user_id = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (note, user.user_id, request_id)
        )
        return {"ok": True, "message": "Leave request rejected."}

    @app.post("/api/proxy/requests/{request_id}/assign-proxy")
    def assign_proxy_teacher(request_id: int, payload: ProxyAssignInput, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")):
            raise HTTPException(status_code=403, detail="Admin permission required.")

        req = db.query_one("SELECT * FROM proxy_class_requests WHERE id = ?", (request_id,))
        if not req:
            raise HTTPException(status_code=404, detail="Request not found.")

        teacher = db.query_one("SELECT id, teacher_name FROM teachers WHERE id = ?", (payload.proxy_teacher_id,))
        if not teacher:
            raise HTTPException(status_code=404, detail="Proxy teacher not found.")

        note = (payload.admin_note or "").strip()
        db.execute(
            """
            UPDATE proxy_class_requests
            SET proxy_teacher_id = ?, proxy_status = 'Pending', status = 'Approved',
                admin_note = CASE WHEN ? != '' THEN ? ELSE admin_note END
            WHERE id = ?
            """,
            (payload.proxy_teacher_id, note, note, request_id)
        )
        return {"ok": True, "message": f"Proxy request assigned to {teacher['teacher_name']}."}

    @app.post("/api/proxy/requests/{request_id}/proxy-response")
    def proxy_teacher_response(request_id: int, payload: ProxyResponseInput, user: UserSession = Depends(session)):
        req = db.query_one("SELECT * FROM proxy_class_requests WHERE id = ?", (request_id,))
        if not req:
            raise HTTPException(status_code=404, detail="Request not found.")

        is_admin = auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")
        teacher_id = user.teacher_id
        if not is_admin and (not teacher_id or int(teacher_id) != int(req["proxy_teacher_id"] or 0)):
            raise HTTPException(status_code=403, detail="Only assigned proxy teacher or admin can respond.")

        if payload.response == "Accept":
            db.execute(
                "UPDATE proxy_class_requests SET proxy_status = 'Accepted', proxy_accepted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (request_id,)
            )
            _create_student_proxy_notifications(request_id)
            sms_mode = services.notifications.settings.get("proxy_sms_mode", "disabled").lower()
            if sms_mode == "auto":
                _dispatch_proxy_sms(request_id)

            return {"ok": True, "message": "Proxy class accepted successfully."}
        else:
            db.execute(
                "UPDATE proxy_class_requests SET proxy_status = 'Declined', proxy_declined_reason = ? WHERE id = ?",
                (payload.declined_reason.strip(), request_id)
            )
            return {"ok": True, "message": "Proxy class declined."}

    @app.post("/api/proxy/requests/{request_id}/admin-confirm")
    def admin_confirm_proxy(request_id: int, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")):
            raise HTTPException(status_code=403, detail="Admin permission required.")

        req = db.query_one("SELECT * FROM proxy_class_requests WHERE id = ?", (request_id,))
        if not req:
            raise HTTPException(status_code=404, detail="Request not found.")
        if not req.get("proxy_teacher_id"):
            raise HTTPException(status_code=400, detail="No proxy teacher has been assigned yet.")

        db.execute(
            "UPDATE proxy_class_requests SET proxy_status = 'Accepted', proxy_accepted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (request_id,)
        )
        _create_student_proxy_notifications(request_id)
        sms_mode = services.notifications.settings.get("proxy_sms_mode", "disabled").lower()
        if sms_mode == "auto":
            _dispatch_proxy_sms(request_id)

        return {"ok": True, "message": "Proxy class confirmed by admin. Students notified."}

    @app.post("/api/proxy/requests/{request_id}/send-sms")
    def send_proxy_sms(request_id: int, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")):
            raise HTTPException(status_code=403, detail="Admin permission required.")

        sent_count = _dispatch_proxy_sms(request_id)
        return {"ok": True, "count": sent_count, "message": f"Proxy notification SMS queued for {sent_count} students."}

    @app.get("/api/proxy/suggestions/{routine_id}/{class_date}")
    def get_proxy_suggestions(routine_id: int, class_date: str, user: UserSession = Depends(session)):
        if not (auth.has_permission(user, "staff.manage") or user.role in ("admin", "super_admin")):
            raise HTTPException(status_code=403, detail="Admin permission required.")

        routine = db.query_one("SELECT * FROM class_routines WHERE id = ?", (routine_id,))
        if not routine:
            raise HTTPException(status_code=404, detail="Routine not found.")

        routine_subj = str(routine.get("subject_name") or "").strip().lower()
        r_period = str(routine.get("period_label") or "").strip()
        r_day = str(routine.get("day_of_week") or "").strip()
        orig_tid = routine.get("teacher_id")

        all_teachers = records(db.query(
            "SELECT id, teacher_name, subject, contact, staff_type FROM teachers WHERE status='Active' AND staff_type='Teaching' ORDER BY teacher_name"
        ))

        busy_rows = db.query(
            "SELECT DISTINCT teacher_id FROM class_routines WHERE day_of_week = ? AND period_label = ? AND status = 'Active' AND teacher_id IS NOT NULL",
            (r_day, r_period)
        )
        busy_ids = {int(r["teacher_id"]) for r in busy_rows if r["teacher_id"]}

        absent_reqs = db.query(
            "SELECT DISTINCT original_teacher_id FROM proxy_class_requests WHERE class_date = ? AND status != 'Rejected' AND original_teacher_id IS NOT NULL",
            (class_date,)
        )
        absent_ids = {int(r["original_teacher_id"]) for r in absent_reqs if r["original_teacher_id"]}

        suggestions = []
        for t in all_teachers:
            tid = int(t["id"])
            if orig_tid and tid == int(orig_tid):
                continue
            t_subj = str(t.get("subject") or "").strip().lower()

            subject_match = bool(
                routine_subj and t_subj and (
                    routine_subj in t_subj or t_subj in routine_subj or
                    any(w in t_subj for w in routine_subj.split() if len(w) > 2)
                )
            )
            is_busy = tid in busy_ids
            is_absent = tid in absent_ids

            score = 0
            if subject_match:
                score += 50
            if not is_busy:
                score += 30
            if not is_absent:
                score += 20

            suggestions.append({
                "id": tid,
                "teacher_name": t["teacher_name"],
                "subject": t.get("subject") or "General",
                "contact": t.get("contact") or "",
                "subject_match": subject_match,
                "is_busy": is_busy,
                "is_absent": is_absent,
                "is_free": not is_busy and not is_absent,
                "score": score,
            })

        suggestions.sort(key=lambda s: -s["score"])
        return suggestions

    @app.get("/api/proxy/sms-settings")
    def get_proxy_sms_settings(_user=Depends(require("administration.manage"))):
        mode = services.notifications.settings.get("proxy_sms_mode", "disabled")
        return {"mode": mode}

    @app.post("/api/proxy/sms-settings")
    def update_proxy_sms_settings(payload: ProxySmsModeInput, _user=Depends(require("administration.manage"))):
        services.notifications.settings.set("proxy_sms_mode", payload.mode)
        return {"ok": True, "mode": payload.mode, "message": f"Proxy SMS mode updated to '{payload.mode}'."}

    @app.get("/api/student/proxy-notifications")
    def get_student_proxy_notifications(user: UserSession = Depends(session)):
        if not auth.has_permission(user, "portal.student"):
            raise HTTPException(status_code=403, detail="Student portal access required.")

        student_id = user.student_id
        if not student_id:
            user_row = db.query_one("SELECT student_id FROM app_users WHERE id=?", (user.user_id,))
            student_id = user_row["student_id"] if user_row else None
        if not student_id:
            return []

        rows = db.query(
            """
            SELECT n.id AS notification_id, n.read_at, n.created_at AS notified_at,
                   p.id AS proxy_request_id, p.class_date, p.leave_type, p.proxy_status,
                   r.period_label, r.subject_name, r.start_time, r.end_time, r.day_of_week,
                   COALESCE(cl.level_name, r.class_name) AS display_class_name,
                   COALESCE(ot.teacher_name, 'Regular Faculty') AS original_teacher_name,
                   COALESCE(pt.teacher_name, 'Substitute Faculty') AS proxy_teacher_name
            FROM proxy_student_notifications n
            JOIN proxy_class_requests p ON p.id = n.proxy_request_id
            JOIN class_routines r ON r.id = p.routine_id
            LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
            LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id
            LEFT JOIN class_levels cl ON cl.id = r.class_level_id
            WHERE n.student_id = ?
            ORDER BY p.class_date DESC, r.start_time ASC
            LIMIT 20
            """,
            (student_id,)
        )
        return records(rows)

    @app.post("/api/student/proxy-notifications/{notification_id}/read")
    def mark_proxy_notification_read(notification_id: int, user: UserSession = Depends(session)):
        db.execute(
            "UPDATE proxy_student_notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ?",
            (notification_id,)
        )
        return {"ok": True}

    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    return app
