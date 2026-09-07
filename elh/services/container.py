from __future__ import annotations

from dataclasses import dataclass

from elh.config import AppConfig
from elh.hardware.factory import create_attendance_device, create_receipt_printer
from elh.repositories import AttendanceRepository, StudentRepository
from .attendance import AttendanceService
from .attendance_poller import AttendancePoller
from .people import StudentService
from .printing import PrintingService
from .billing import BillingService
from .recurring_billing import RecurringBillingService
from elh.repositories import BillingRepository
from .reports import ReportsService
from .certificates import CertificateService
from elh.repositories import CertificateRepository
from .enrollments import EnrollmentService
from .notifications import NotificationService
from elh.core.settings import SettingsService
from .staff_finance import StaffFinanceService
from .automation import AutomationScheduler
from .cms import CmsService


@dataclass(frozen=True)
class ServiceContainer:
    students: StudentService
    enrollments: EnrollmentService
    notifications: NotificationService
    attendance: AttendanceService
    attendance_poller: AttendancePoller
    printing: PrintingService
    billing: BillingService
    recurring_billing: RecurringBillingService
    reports: ReportsService
    certificates: CertificateService
    staff_finance: StaffFinanceService
    automation: AutomationScheduler
    cms: CmsService

    @classmethod
    def build(cls, config: AppConfig, db) -> "ServiceContainer":
        settings = SettingsService(db)
        existing_settings = {
            row["setting_key"] for row in db.query("SELECT setting_key FROM settings")
        }
        settings.ensure_defaults()
        runtime_defaults = {
            "app_title": config.app_title,
            "currency_symbol": config.currency_symbol,
            "certificate_number_prefix": config.certificate_number_prefix,
            "certificate_default_instructor": config.certificate_default_instructor,
            "certificate_default_principal": config.certificate_default_principal,
            "session_idle_minutes": str(config.session_idle_minutes),
            "window_width": str(config.window_width),
            "window_height": str(config.window_height),
            "min_window_width": str(config.min_window_width),
            "min_window_height": str(config.min_window_height),
            "allow_negative_balance": str(config.allow_negative_balance).lower(),
            "health_stale_backup_hours": str(config.health_stale_backup_hours),
            "gemini_api_key": config.gemini_api_key,
            "ai_provider": config.ai_provider,
            "ai_model": config.ai_model,
        }
        for key, value in runtime_defaults.items():
            if key not in existing_settings:
                settings.set(key, value)
            elif key == "gemini_api_key" and config.gemini_api_key and not settings.get("gemini_api_key"):
                settings.set("gemini_api_key", config.gemini_api_key)
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
        printing = PrintingService(create_receipt_printer(config))
        attendance_service = AttendanceService(AttendanceRepository(db), create_attendance_device(config), settings)
        attendance_poller = AttendancePoller(
            attendance_service,
            interval_seconds=config.attendance_poll_interval_seconds,
            enabled=config.attendance_auto_poll and config.attendance_driver != "disabled",
        )
        billing_service = BillingService(
            BillingRepository(db), printing, company_name, currency_symbol, notifications, settings
        )
        recurring_billing = RecurringBillingService(db, billing_service, settings)
        automation = AutomationScheduler(
            db=db,
            config=config,
            settings=settings,
            notifications=notifications,
            recurring_billing=recurring_billing,
            attendance=attendance_service,
        )
        container = cls(
            students=StudentService(StudentRepository(db), config.date_format, notifications),
            enrollments=EnrollmentService(db, notifications, config.date_format),
            notifications=notifications,
            attendance=attendance_service,
            attendance_poller=attendance_poller,
            printing=printing,
            billing=billing_service,
            recurring_billing=recurring_billing,
            reports=ReportsService(db, company_name, currency_symbol, printing, settings),
            certificates=CertificateService(CertificateRepository(db), config, notifications),
            staff_finance=StaffFinanceService(db),
            automation=automation,
            cms=CmsService(db),
        )
        if settings.get_bool("sms_enabled", False):
            notifications.dispatch_async()
        if config.attendance_driver != "disabled" and config.attendance_auto_poll:
            attendance_poller.start()
        # Start background automation scheduler (monthly invoicing, daily absence SMS, backups)
        automation.start()
        return container
