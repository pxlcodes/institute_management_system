from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from elh.config import ROOT_DIR, load_config
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


class EnrollmentInput(BaseModel):
    student_id: int
    course_id: int
    level: str = ""
    start_date: str
    end_date: str = ""
    monthly_fee: float = 0
    admission_fee: float = 0
    discount: float = 0


def create_app() -> FastAPI:
    """Create the web adapter without changing the existing business services."""
    config = load_config()
    db = create_database(config)
    services = ServiceContainer.build(config, db)
    auth = AuthService(db, config)
    auth.ensure_initial_users()
    # Tokens intentionally live only in process memory. A server restart signs users out.
    sessions: dict[str, object] = {}
    app = FastAPI(title="ELH Web", version="0.1.0")
    static_dir = ROOT_DIR / "web"

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
        return {"metrics": result, "punched_not_enrolled": [dict(row) for row in services.attendance.students_punched_not_enrolled()]}

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
        return [dict(row) for row in rows]

    @app.post("/api/students", status_code=201)
    def create_student(payload: StudentInput, _user=Depends(require("students.manage"))):
        student = Student(name=payload.name, class_name=payload.class_name, school_id=payload.school_id, contact=payload.contact, gender=payload.gender, joining_date=payload.joining_date)
        student_id = services.students.register(student)
        if payload.class_name:
            level = db.query_one("SELECT id FROM class_levels WHERE level_name=?", (payload.class_name,))
            db.execute("UPDATE students SET class_level_id=? WHERE id=?", (level["id"] if level else None, student_id))
        return {"id": student_id}

    @app.get("/api/courses")
    def courses(_user=Depends(require("enrollments.manage"))):
        return [dict(row) for row in db.query("SELECT id,course_name,category,default_fee FROM courses WHERE status='Active' ORDER BY category,course_name")]

    @app.get("/api/lookups")
    def lookups(_user=Depends(session)):
        return {"schools": [dict(row) for row in db.query("SELECT id,school_name FROM schools WHERE status='Active' ORDER BY school_name")], "classes": [dict(row) for row in db.query("SELECT id,level_name FROM class_levels WHERE status='Active' ORDER BY level_name")]}

    @app.get("/api/enrollments")
    def enrollments(_user=Depends(require("enrollments.manage"))):
        rows = db.query("SELECT e.id,s.student_name,c.course_name,e.level,e.start_date,e.end_date,e.monthly_fee,e.status FROM enrollments e JOIN students s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id ORDER BY e.start_date DESC,s.student_name")
        return [dict(row) for row in rows]

    @app.post("/api/enrollments", status_code=201)
    def create_enrollment(payload: EnrollmentInput, _user=Depends(require("enrollments.manage"))):
        enrollment_id = services.enrollments.create(payload.student_id, payload.course_id, payload.level, payload.start_date, payload.end_date, payload.monthly_fee, payload.admission_fee, payload.discount, "Active", "")
        return {"id": enrollment_id}

    @app.get("/api/attendance/punched-not-enrolled")
    def punched_not_enrolled(_user=Depends(require("enrollments.manage"))):
        return [dict(row) for row in services.attendance.students_punched_not_enrolled()]

    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_dir / "index.html")

    return app
