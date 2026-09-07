from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta

from elh.models import UserSession


ROLES = (
    "super_admin",
    "admin",
    "accountant",
    "operator",
    "staff",
    "teacher",
    "student",
    "parent",
    "maintenance",
    "viewer",
    "cms_manager",
)

PERMISSION_DEFINITIONS = (
    ("dashboard.view", "View Dashboard", "Open the application dashboard."),
    ("students.manage", "Manage Students", "Create and maintain student records."),
    ("enrollments.manage", "Manage Enrollments", "Create and maintain course enrollments."),
    ("billing.manage", "Manage Billing", "Generate bills and receive student payments."),
    ("certificates.manage", "Manage Certificates", "Issue and print course completion certificates."),
    ("reports.view", "View Reports", "View and print reports and ledgers."),
    ("devices.manage", "Manage Devices", "Use attendance and POS device screens."),
    ("master_data.manage", "Manage Master Data", "Maintain courses, schools, grades, and levels."),
    ("staff.manage", "Manage Staff", "Create and maintain staff records."),
    ("payroll.manage", "Manage Payroll", "Manage advances and salary payouts."),
    ("finance.manage", "Manage Finance", "Manage accounts, income, expenses, transfers, and ledger."),
    ("administration.manage", "System Administration", "Manage users and system configuration."),
    ("maintenance.manage", "System Maintenance", "Run migrations, cache, and maintenance checks."),
    ("backup.manage", "Database Backup", "Create or restore database backups."),
    ("portal.staff", "Staff Portal", "Access staff self-service, classes, routine, and payslips."),
    ("portal.student", "Student Portal", "Access student self-service, profile, attendance, bills, and certificates."),
    ("portal.parent", "Parent Portal", "Access parent portal and child academic progress."),
    ("assistant.view", "AI Assistant", "Access AI Assistant and query operational intelligence."),
    ("cms.manage", "Manage Website & CMS", "Update website content, hero, courses, testimonials, events, announcements, and FAQs."),
)

ALL_PERMISSIONS = frozenset(key for key, _name, _description in PERMISSION_DEFINITIONS)
ROLE_DEFAULTS = {
    "super_admin": ALL_PERMISSIONS,
    "admin": ALL_PERMISSIONS,
    "accountant": frozenset({
        "dashboard.view",
        "students.manage",
        "enrollments.manage",
        "billing.manage",
        "finance.manage",
        "payroll.manage",
        "reports.view",
    }),
    "operator": frozenset({
        "dashboard.view",
        "students.manage",
        "enrollments.manage",
        "billing.manage",
        "certificates.manage",
        "reports.view",
        "devices.manage",
    }),
    "staff": frozenset({
        "dashboard.view",
        "portal.staff",
    }),
    "teacher": frozenset({
        "dashboard.view",
        "portal.staff",
    }),
    "student": frozenset({
        "dashboard.view",
        "portal.student",
    }),
    "parent": frozenset({
        "dashboard.view",
        "portal.parent",
    }),
    "maintenance": frozenset({"devices.manage", "maintenance.manage"}),
    "viewer": frozenset({"dashboard.view", "reports.view"}),
    "cms_manager": frozenset({"dashboard.view", "cms.manage"}),
}

PASSWORD_ITERATIONS = 390_000
LEGACY_PASSWORD_ITERATIONS = 260_000


def hash_login_password(
    password: str,
    salt: bytes | None = None,
    iterations: int = PASSWORD_ITERATIONS,
) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _password_hash_parts(encoded: str) -> tuple[int, str, str] | None:
    parts = encoded.split("$")
    try:
        if len(parts) == 3 and parts[0] == "pbkdf2_sha256":
            return LEGACY_PASSWORD_ITERATIONS, parts[1], parts[2]
        if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
            iterations = int(parts[1])
            if iterations <= 0:
                return None
            return iterations, parts[2], parts[3]
    except ValueError:
        return None
    return None


def verify_login_password(password: str, encoded: str) -> bool:
    parts = _password_hash_parts(encoded)
    if parts is None:
        return False
    iterations, salt_hex, expected = parts
    try:
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            iterations,
        ).hex()
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def password_needs_rehash(encoded: str) -> bool:
    parts = _password_hash_parts(encoded)
    return parts is None or parts[0] < PASSWORD_ITERATIONS


class AuthService:
    MAX_FAILED_ATTEMPTS = 5
    LOCK_MINUTES = 15

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def ensure_initial_users(self) -> None:
        self.ensure_authorization_metadata()
        users = (
            (
                self.config.operator_username,
                self.config.operator_password,
                "operator",
                "Operator",
            ),
            (
                self.config.admin_username,
                self.config.admin_password,
                "admin",
                "Administrator",
            ),
            (
                self.config.maintenance_username,
                self.config.maintenance_password,
                "maintenance",
                "Maintenance",
            ),
        )
        configured = [user for user in users if user[0] and user[1]]
        if not configured:
            return
        placeholders = ",".join("?" for _user in configured)
        existing_rows = self.db.query(
            f"SELECT id,username,display_name,role FROM app_users WHERE username IN ({placeholders})",
            tuple(user[0] for user in configured),
        )
        existing = {row["username"]: row for row in existing_rows}
        inserts = []
        updates = []
        for username, password, role, display_name in configured:
            row = existing.get(username)
            if row is None:
                inserts.append(
                    (username, display_name, hash_login_password(password), role)
                )
            elif not row["display_name"] or row["role"] != role:
                updates.append((display_name or row["display_name"], role, row["id"]))
        self.db.executemany(
            "INSERT INTO app_users "
            "(username,display_name,password_hash,role,status,password_changed_at) "
            "VALUES (?,?,?,?,'Active',CURRENT_TIMESTAMP)",
            inserts,
        )
        if updates:
            self.db.executemany(
                "UPDATE app_users SET display_name = COALESCE(NULLIF(?, ''), display_name), role = ? WHERE id = ?",
                updates,
            )

    def ensure_authorization_metadata(self) -> None:
        existing_permissions = {
            row["permission_key"]
            for row in self.db.query("SELECT permission_key FROM permissions")
        }
        self.db.executemany(
            "UPDATE permissions SET permission_name = ?, description = ? "
            "WHERE permission_key = ?",
            (
                (name, description, key)
                for key, name, description in PERMISSION_DEFINITIONS
                if key in existing_permissions
            ),
        )
        self.db.executemany(
            "INSERT INTO permissions "
            "(permission_key,permission_name,description) VALUES (?,?,?)",
            (
                (key, name, description)
                for key, name, description in PERMISSION_DEFINITIONS
                if key not in existing_permissions
            ),
        )
        existing_role_permissions = {
            (row["role"], row["permission_key"])
            for row in self.db.query("SELECT role,permission_key FROM role_permissions")
        }
        self.db.executemany(
            "INSERT INTO role_permissions (role,permission_key) VALUES (?,?)",
            (
                (role, permission_key)
                for role, permissions in ROLE_DEFAULTS.items()
                for permission_key in permissions
                if (role, permission_key) not in existing_role_permissions
            ),
        )

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters.")
        if not any(character.islower() for character in password):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not any(character.isupper() for character in password):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(character.isdigit() for character in password):
            raise ValueError("Password must contain at least one number.")
        if not any(not character.isalnum() for character in password):
            raise ValueError("Password must contain at least one symbol.")

    @staticmethod
    def _parse_datetime(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def permissions_for_user(self, user_id: int, role: str) -> frozenset[str]:
        role_rows = self.db.query(
            "SELECT permission_key FROM role_permissions WHERE role = ?",
            (role,),
        )
        permissions = {row["permission_key"] for row in role_rows}
        if not role_rows:
            permissions.update(ROLE_DEFAULTS.get(role, frozenset()))
        overrides = self.db.query(
            "SELECT permission_key,allowed FROM user_permissions WHERE user_id = ?",
            (user_id,),
        )
        for row in overrides:
            if int(row["allowed"]):
                permissions.add(row["permission_key"])
            else:
                permissions.discard(row["permission_key"])
        return frozenset(permissions)

    def has_permission(self, session: UserSession, permission_key: str) -> bool:
        if session.permissions:
            return session.can(permission_key)
        return permission_key in ROLE_DEFAULTS.get(session.role, frozenset())

    def authenticate(self, username: str, password: str) -> UserSession | None:
        username = username.strip()
        row = self.db.query_one(
            "SELECT * FROM app_users WHERE username = ?",
            (username,),
        )
        if not row:
            self._audit(None, username, "login", False, "Unknown username")
            return None
        if row["status"] != "Active":
            self._audit(row["id"], row["username"], "login", False, "Account disabled")
            return None

        locked_until = self._parse_datetime(row["locked_until"])
        if locked_until and locked_until > datetime.now():
            self._audit(row["id"], row["username"], "login", False, "Account temporarily locked")
            return None

        if not verify_login_password(password, row["password_hash"]):
            attempts = int(row["failed_attempts"] or 0) + 1
            new_lock = None
            detail = "Invalid password"
            if attempts >= self.MAX_FAILED_ATTEMPTS:
                new_lock = datetime.now() + timedelta(minutes=self.LOCK_MINUTES)
                detail = f"Locked after {attempts} failed attempts"
            self.db.execute(
                "UPDATE app_users SET failed_attempts = ?, locked_until = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (attempts, new_lock.isoformat(sep=" ") if new_lock else None, row["id"]),
            )
            self._audit(row["id"], row["username"], "login", False, detail)
            return None

        upgraded_hash = hash_login_password(password) if password_needs_rehash(row["password_hash"]) else None
        self.db.execute(
            "UPDATE app_users SET failed_attempts = 0, locked_until = NULL, "
            "password_hash = COALESCE(?, password_hash), "
            "last_login_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (upgraded_hash, row["id"]),
        )
        permissions = self.permissions_for_user(int(row["id"]), row["role"])
        self._audit(row["id"], row["username"], "login", True, "Login successful")
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

    def list_permissions(self):
        return [
            {"key": key, "name": name, "description": description}
            for key, name, description in PERMISSION_DEFINITIONS
        ]

    def role_permissions(self, role: str) -> frozenset[str]:
        return ROLE_DEFAULTS.get(role, frozenset())

    def list_users(self):
        return self.db.query(
            "SELECT u.id, u.username, u.display_name, u.email, "
            "COALESCE(u.phone, '') AS phone, u.role, u.status, "
            "u.student_id, u.teacher_id, u.must_change_password, u.failed_attempts, "
            "u.locked_until, u.last_login_at, u.created_at, "
            "s.student_name, t.teacher_name "
            "FROM app_users u "
            "LEFT JOIN students s ON s.id = u.student_id "
            "LEFT JOIN teachers t ON t.id = u.teacher_id "
            "ORDER BY u.id DESC"
        )

    def get_user(self, user_id: int):
        return self.db.query_one("SELECT * FROM app_users WHERE id = ?", (user_id,))

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str,
        email: str,
        role: str,
        status: str,
        permissions: set[str] | None,
        actor: UserSession,
        must_change_password: bool = True,
        phone: str = "",
        student_id: int | None = None,
        teacher_id: int | None = None,
    ) -> int:
        self._require_administration(actor)
        username = username.strip()
        if not username:
            raise ValueError("Username is required.")
        if " " in username:
            raise ValueError("Username cannot contain spaces.")
        if role not in ROLES:
            raise ValueError("Select a valid role.")
        if status not in {"Active", "Disabled"}:
            raise ValueError("Select Active or Disabled status.")
        if student_id and not self.db.query_one("SELECT id FROM students WHERE id = ?", (student_id,)):
            raise ValueError("Selected student was not found.")
        if teacher_id and not self.db.query_one("SELECT id FROM teachers WHERE id = ?", (teacher_id,)):
            raise ValueError("Selected staff member was not found.")
        self.validate_password(password)
        if self.db.query_one("SELECT id FROM app_users WHERE username = ?", (username,)):
            raise ValueError("That username already exists.")
        user_id = self.db.execute(
            "INSERT INTO app_users "
            "(username,display_name,email,phone,password_hash,role,status,student_id,teacher_id,must_change_password,password_changed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (
                username,
                display_name.strip(),
                email.strip(),
                phone.strip(),
                hash_login_password(password),
                role,
                status,
                student_id,
                teacher_id,
                1 if must_change_password else 0,
            ),
        )
        if permissions is not None:
            self.set_permissions(user_id, role, permissions)
        self.record_event(actor, "user_created", True, f"Created user {username} ({role})")
        return user_id

    def update_user(
        self,
        user_id: int,
        display_name: str,
        email: str,
        role: str,
        status: str,
        permissions: set[str],
        actor: UserSession,
        must_change_password: bool | None = None,
        phone: str = "",
        student_id: int | None = None,
        teacher_id: int | None = None,
    ) -> None:
        self._require_administration(actor)
        row = self.get_user(user_id)
        if not row:
            raise ValueError("User account was not found.")
        if role not in ROLES:
            raise ValueError("Select a valid role.")
        if status not in {"Active", "Disabled"}:
            raise ValueError("Select Active or Disabled status.")
        if int(user_id) == int(actor.user_id) and (
            status != "Active" or role != row["role"]
        ):
            raise ValueError("You cannot disable your own account or change your own role.")
        if int(user_id) == int(actor.user_id):
            permissions.add("administration.manage")
        if student_id and not self.db.query_one("SELECT id FROM students WHERE id = ?", (student_id,)):
            raise ValueError("Selected student was not found.")
        if teacher_id and not self.db.query_one("SELECT id FROM teachers WHERE id = ?", (teacher_id,)):
            raise ValueError("Selected staff member was not found.")
        self._protect_last_admin(row, role, status)
        self.db.execute(
            "UPDATE app_users SET display_name = ?, email = ?, phone = ?, role = ?, status = ?, "
            "student_id = ?, teacher_id = ?, "
            "must_change_password = COALESCE(?, must_change_password), "
            "failed_attempts = CASE WHEN ? = 'Active' THEN 0 ELSE failed_attempts END, "
            "locked_until = CASE WHEN ? = 'Active' THEN NULL ELSE locked_until END, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                display_name.strip(),
                email.strip(),
                phone.strip(),
                role,
                status,
                student_id,
                teacher_id,
                1 if must_change_password else 0 if must_change_password is not None else None,
                status,
                status,
                user_id,
            ),
        )
        self.set_permissions(user_id, role, permissions)
        self.record_event(
            actor,
            "user_updated",
            True,
            f"Updated user {row['username']} ({role}, {status})",
        )

    def unlock_user(self, user_id: int, actor: UserSession) -> None:
        self._require_administration(actor)
        row = self.get_user(user_id)
        if not row:
            raise ValueError("User account was not found.")
        self.db.execute(
            "UPDATE app_users SET failed_attempts = 0, locked_until = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        self.record_event(actor, "user_unlocked", True, f"Unlocked user account {row['username']}")

    def toggle_user_status(self, user_id: int, status: str, actor: UserSession) -> None:
        self._require_administration(actor)
        row = self.get_user(user_id)
        if not row:
            raise ValueError("User account was not found.")
        if status not in {"Active", "Disabled"}:
            raise ValueError("Select Active or Disabled status.")
        if int(user_id) == int(actor.user_id):
            raise ValueError("You cannot change the status of your own account.")
        self._protect_last_admin(row, row["role"], status)
        self.db.execute(
            "UPDATE app_users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, user_id),
        )
        self.record_event(actor, "user_status_changed", True, f"Changed user {row['username']} status to {status}")

    def _protect_last_admin(self, existing_row, new_role: str, new_status: str) -> None:
        if existing_row["role"] not in {"admin", "super_admin"} or existing_row["status"] != "Active":
            return
        if new_role in {"admin", "super_admin"} and new_status == "Active":
            return
        count = self.db.query_one(
            "SELECT COUNT(*) total FROM app_users WHERE role IN ('admin', 'super_admin') AND status = 'Active'"
        )
        if count and int(count["total"]) <= 1:
            raise ValueError("At least one active administrator account is required.")

    def set_permissions(self, user_id: int, role: str, selected: set[str]) -> None:
        unknown = selected - ALL_PERMISSIONS
        if unknown:
            raise ValueError(f"Unknown permission: {sorted(unknown)[0]}")
        self.db.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
        defaults = ROLE_DEFAULTS.get(role, frozenset())
        self.db.executemany(
            "INSERT INTO user_permissions (user_id,permission_key,allowed) VALUES (?,?,?)",
            (
                (user_id, permission_key, 1 if permission_key in selected else 0)
                for permission_key in ALL_PERMISSIONS
                if (permission_key in selected) != (permission_key in defaults)
            ),
        )

    def change_password(
        self,
        user_id: int,
        new_password: str,
        actor: UserSession,
        must_change_password: bool = False,
    ) -> None:
        if int(user_id) != int(actor.user_id):
            self._require_administration(actor)
        row = self.get_user(user_id)
        if not row:
            raise ValueError("User account was not found.")
        self.validate_password(new_password)
        self.db.execute(
            "UPDATE app_users SET password_hash = ?, must_change_password = ?, "
            "failed_attempts = 0, locked_until = NULL, password_changed_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (hash_login_password(new_password), 1 if must_change_password else 0, user_id),
        )
        self.record_event(actor, "password_changed", True, f"Changed password for {row['username']}")

    def update_password(
        self,
        actor: UserSession,
        user_id: int,
        new_password: str,
        must_change_password: bool = False,
    ) -> None:
        self.change_password(user_id, new_password, actor, must_change_password=must_change_password)

    def verify_user_password(self, user_id: int, password: str) -> bool:
        row = self.get_user(user_id)
        return bool(row and verify_login_password(password, row["password_hash"]))

    def _require_administration(self, actor: UserSession) -> None:
        if not self.has_permission(actor, "administration.manage"):
            raise PermissionError("System-administration permission is required.")

    def record_event(
        self,
        session: UserSession,
        event_type: str,
        success: bool = True,
        detail: str = "",
    ) -> None:
        self._audit(
            session.user_id,
            session.username,
            event_type,
            success,
            detail,
        )

    def _audit(
        self,
        user_id: int | None,
        username: str,
        event_type: str,
        success: bool,
        detail: str,
    ) -> None:
        self.db.execute(
            "INSERT INTO auth_audit_log "
            "(user_id,username,event_type,success,detail) VALUES (?,?,?,?,?)",
            (user_id, username, event_type, 1 if success else 0, detail),
        )

    def list_audit(self, limit: int = 500):
        return self.db.query(
            "SELECT id,username,event_type,success,detail,occurred_at "
            f"FROM auth_audit_log ORDER BY occurred_at DESC,id DESC LIMIT {int(limit)}"
        )
