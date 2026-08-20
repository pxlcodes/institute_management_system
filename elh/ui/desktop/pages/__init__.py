from .accounts import AccountsPage
from .advances import AdvancesPage
from .dashboard import DashboardPage
from .enrollments import EnrollmentsPage
from .ledger import LedgerPage
from .money_records import ExpensePage, IncomePage
from .salary import SalaryPage
from .student_transactions import StudentTransactionsPage
from .students import StudentsPage
from .teachers import TeachersPage
from .transfers import TransfersPage
from .courses import CoursesPage
from .schools import SchoolsPage
from .bills import DueBillsPage
from .reports import ReportsPage
from .attendance import AttendancePage
from .devices import DeviceHealthPage, PosPrinterPage
from .certificates import CertificatesPage
from .work_items import WorkItemsPage

__all__ = [
    "AccountsPage", "AdvancesPage", "DashboardPage", "EnrollmentsPage",
    "ExpensePage", "IncomePage", "LedgerPage", "SalaryPage",
    "StudentTransactionsPage", "StudentsPage", "TeachersPage", "TransfersPage", "CoursesPage", "SchoolsPage", "DueBillsPage", "ReportsPage", "AttendancePage", "DeviceHealthPage", "PosPrinterPage", "CertificatesPage", "WorkItemsPage",
]
