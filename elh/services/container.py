from __future__ import annotations

from dataclasses import dataclass

from elh.config import AppConfig
from elh.hardware.factory import create_attendance_device, create_receipt_printer
from elh.repositories import AttendanceRepository, StudentRepository
from .attendance import AttendanceService
from .people import StudentService
from .printing import PrintingService
from .billing import BillingService
from elh.repositories import BillingRepository
from .reports import ReportsService
from .certificates import CertificateService
from elh.repositories import CertificateRepository
from .enrollments import EnrollmentService
from .notifications import NotificationService
from elh.core.settings import SettingsService


@dataclass(frozen=True)
class ServiceContainer:
    students: StudentService
    enrollments: EnrollmentService
    notifications: NotificationService
    attendance: AttendanceService
    printing: PrintingService
    billing: BillingService
    reports: ReportsService
    certificates: CertificateService

    @classmethod
    def build(cls, config: AppConfig, db) -> "ServiceContainer":
        settings = SettingsService(db)
        existing_settings = {
            row["setting_key"] for row in db.query("SELECT setting_key FROM settings")
        }
        settings.ensure_defaults()
        if "currency_symbol" not in existing_settings:
            settings.set("currency_symbol", config.currency_symbol)
        if "certificate_number_prefix" not in existing_settings:
            settings.set("certificate_number_prefix", config.certificate_number_prefix)
        profile = db.query_one(
            "SELECT company_name,principal_name FROM company_profile WHERE id=1"
        )
        if config.certificate_default_principal.strip():
            if profile and not str(profile["principal_name"] or "").strip():
                db.execute(
                    "UPDATE company_profile SET principal_name=? WHERE id=1",
                    (config.certificate_default_principal.strip(),),
                )
                profile = db.query_one(
                    "SELECT company_name,principal_name FROM company_profile WHERE id=1"
                )
            elif not profile:
                db.execute(
                    "INSERT INTO company_profile (id,company_name,principal_name) VALUES (1,?,?)",
                    (config.app_title, config.certificate_default_principal.strip()),
                )
                profile = db.query_one(
                    "SELECT company_name,principal_name FROM company_profile WHERE id=1"
                )
        if config.certificate_default_instructor.strip():
            db.execute(
                "UPDATE courses SET instructor_name=? "
                "WHERE instructor_name IS NULL OR instructor_name=''",
                (config.certificate_default_instructor.strip(),),
            )
        company_name = (profile["company_name"] if profile else None) or config.app_title
        currency_symbol = settings.get("currency_symbol", config.currency_symbol)
        notifications = NotificationService(db, config)
        printing=PrintingService(create_receipt_printer(config))
        container = cls(
            students=StudentService(StudentRepository(db), config.date_format, notifications),
            enrollments=EnrollmentService(db, notifications, config.date_format),
            notifications=notifications,
            attendance=AttendanceService(AttendanceRepository(db), create_attendance_device(config)),
            printing=printing,
            billing=BillingService(BillingRepository(db),printing,company_name,currency_symbol,notifications),
            reports=ReportsService(db,company_name,currency_symbol,printing),
            certificates=CertificateService(CertificateRepository(db),config,notifications),
        )
        if settings.get_bool("sms_enabled", False):
            notifications.dispatch_async()
        return container
