"""
Expert Learning Hub Management System
Tkinter desktop presentation adapter.

Features:
- Student records
- Multiple enrollments per student
- Student account transactions
- Teacher records
- Teacher advance payouts
- Salary payouts
- Income and expense records
- Cash, bank, personal, wallet and other accounts
- Account transfers
- Dashboard summaries
- Central account ledger and automatic balances

Python: 3.10+
Database and optional hardware dependencies are listed in the requirements files.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from elh.ui.admin import AdminPanel
from elh.config import AppConfig, load_config
from elh.core.backup import BackupError, BackupService
from elh.core.logging_config import configure_logging, install_exception_hooks
from elh.infrastructure import create_database
from elh.repositories import DatabaseGateway
from elh.services import AuthService, ServiceContainer
from elh.ui.login import ChangePasswordDialog, LoginDialog
from elh.ui.maintenance import MaintenancePanel
from elh.models import UserSession
from elh.ui.desktop.components import BasePage, ScrollableFrame
from elh.ui.desktop.pages import (
    AccountsPage, AdvancesPage, DashboardPage, EnrollmentsPage, ExpensePage,
    IncomePage, LedgerPage, SalaryPage, StudentTransactionsPage, StudentsPage,
    TeachersPage, TransfersPage, CoursesPage, SchoolsPage, DueBillsPage,
    ReportsPage,
    AttendancePage,
    DeviceHealthPage,
    PosPrinterPage,
    CertificatesPage,
    WorkItemsPage,
)

# ---------------------------------------------------------------------------

class ManagementApp(tk.Tk):
    """Tkinter presentation adapter for the reusable application services."""

    def __init__(self, config: AppConfig | None = None, db: DatabaseGateway | None = None, session: UserSession | None = None):
        super().__init__()
        # Do not use ``self.config`` here: Tk defines config() as a widget method.
        self.app_config = config or load_config()
        self.configure(background="#EEF3F8")
        self.title(self.app_config.app_title)
        self.geometry(f"{self.app_config.window_width}x{self.app_config.window_height}")
        self.minsize(self.app_config.min_window_width, self.app_config.min_window_height)
        self.db = db or create_database(self.app_config)
        self.services = ServiceContainer.build(self.app_config, self.db)
        self.auth_service = AuthService(self.db, self.app_config)
        self.auth_service.ensure_initial_users()
        self._idle_after_id = None
        self._session_transitioning = False

        self._configure_styles()
        self.withdraw()
        if session is None:
            login = LoginDialog(self, self.auth_service)
            login.update()
            self.wait_window(login)
            self.session = login.session
        else:
            self.session = session
        if self.session is None:
            self.destroy()
            return
        if self.session.must_change_password and not self._require_password_change():
            self.destroy()
            return
        self._build_menu()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Any-KeyPress>", self._record_activity, add="+")
        self.bind_all("<Any-ButtonPress>", self._record_activity, add="+")
        self._arm_idle_lock()
        self.deiconify()

    def report_callback_exception(self, exception_type, exception, traceback):
        logging.getLogger(__name__).error(
            "Unhandled desktop UI callback",
            exc_info=(exception_type, exception, traceback),
        )
        try:
            messagebox.showerror(
                "Unexpected Error",
                "The operation could not be completed. No further action was taken.\n\n"
                f"Technical details were saved in:\n{self.app_config.log_directory}",
                parent=self,
            )
        except tk.TclError:
            pass

    def can(self, permission_key: str) -> bool:
        return self.auth_service.has_permission(self.session, permission_key)

    def _require_password_change(self) -> bool:
        dialog = ChangePasswordDialog(
            self, self.auth_service, self.session, forced=True
        )
        self.wait_window(dialog)
        if dialog.changed:
            self.session = UserSession(
                self.session.user_id,
                self.session.username,
                self.session.role,
                self.session.display_name,
                self.session.permissions,
                False,
            )
        return dialog.changed

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#EEF3F8")
        style.configure("TLabel", background="#EEF3F8", foreground="#334155", font=("Segoe UI",10))
        style.configure("Title.TLabel", background="#EEF3F8", foreground="#102A43", font=("Segoe UI Variable Display", 23, "bold"))
        style.configure("Section.TLabel", background="#12263A", foreground="#FFFFFF", font=("Segoe UI", 13, "bold"))
        style.configure("Card.TLabel", background="#FFFFFF", foreground="#167D8D", font=("Segoe UI", 18, "bold"))
        style.configure("Toolbar.TFrame", background="#EEF3F8")
        style.configure("Hint.TLabel", background="#EEF3F8", foreground="#64748B", font=("Segoe UI",9,"italic"))
        style.configure("SubTitle.TLabel", background="#EEF3F8", foreground="#183B56", font=("Segoe UI Variable Display",14,"bold"))
        style.configure("DashboardCard.TFrame", background="#F8FAFC")
        style.configure("DashboardCardTitle.TLabel", background="#F8FAFC", foreground="#64748B", font=("Segoe UI",9,"bold"))
        style.configure("DashboardCardValue.TLabel", background="#F8FAFC", foreground="#087F75", font=("Segoe UI Variable Display",19,"bold"))
        style.configure("Header.TFrame", background="#FFFFFF")
        style.configure("HeaderTitle.TLabel", background="#FFFFFF", foreground="#102A43", font=("Segoe UI Variable Display",16,"bold"))
        style.configure("HeaderMeta.TLabel", background="#FFFFFF", foreground="#64748B", font=("Segoe UI",9))
        style.configure("Accent.TButton", background="#00A88F", foreground="#FFFFFF", font=("Segoe UI",10,"bold"), padding=(15,10), borderwidth=0)
        style.map("Accent.TButton", background=[("active","#008F7A"),("pressed","#007564")])
        style.configure("TButton", font=("Segoe UI",9,"bold"), padding=(12,9), background="#E3EBF3", foreground="#183B56", borderwidth=0, relief="flat", focusthickness=0, focuscolor="#E3EBF3")
        style.map("TButton", background=[("active","#D2DEE9"),("pressed","#C5D4E1"),("disabled","#EDF1F5")],foreground=[("disabled","#94A3B8")])
        style.configure("TMenubutton", font=("Segoe UI",9,"bold"), padding=(12,9), background="#E3EBF3", foreground="#183B56", borderwidth=0, relief="flat")
        style.map("TMenubutton", background=[("active", "#D2DEE9"), ("pressed", "#C5D4E1")])
        style.configure("TEntry", padding=(7,6), fieldbackground="#FFFFFF", bordercolor="#CBD5E1")
        style.configure("TCombobox", padding=(6,5), fieldbackground="#FFFFFF", bordercolor="#CBD5E1")
        style.configure("Danger.TButton", background="#DC4C4C", foreground="#FFFFFF", font=("Segoe UI",9,"bold"), padding=(12,9), borderwidth=0, relief="flat", focusthickness=0)
        style.map("Danger.TButton",background=[("active","#C83E3E"),("pressed","#B83232")])
        style.configure("Sidebar.TFrame", background="#12263A")
        style.configure("Sidebar.TLabel", background="#12263A", foreground="#7DD3C7", font=("Segoe UI",8,"bold"))
        style.configure("SidebarGroup.TLabel", background="#12263A", foreground="#7DD3C7", font=("Segoe UI",8,"bold"))
        style.configure("SidebarGroup.TButton", background="#12263A", foreground="#7DD3C7", anchor="w", font=("Segoe UI",8,"bold"), padding=(10,7), borderwidth=0)
        style.map("SidebarGroup.TButton", background=[("active","#1D3B52")], foreground=[("active","#A7F3D0")])
        style.configure("Sidebar.TButton", background="#12263A", foreground="#DCE8F2", anchor="w", font=("Segoe UI",10), padding=(15,10), borderwidth=0)
        style.map("Sidebar.TButton", background=[("active","#1D3B52"),("pressed","#00A88F")], foreground=[("active","#FFFFFF")])
        style.configure("SidebarActive.TButton", background="#00A88F", foreground="#FFFFFF", anchor="w", font=("Segoe UI",10,"bold"), padding=(15,10), borderwidth=0)
        style.configure("TLabelframe", background="#FFFFFF", bordercolor="#CBD5E1", relief="solid")
        style.configure("TLabelframe.Label", background="#FFFFFF", foreground="#17324D", font=("Segoe UI",11,"bold"))
        style.configure("Form.TLabelframe", background="#F8FAFC", bordercolor="#D7E1EA", relief="flat", borderwidth=1)
        style.configure("Form.TLabelframe.Label", background="#F8FAFC", foreground="#183B56", font=("Segoe UI Variable Display",11,"bold"))
        style.configure("Form.TFrame", background="#F8FAFC")
        style.configure("Form.TLabel", background="#F8FAFC", foreground="#334155", font=("Segoe UI",9))
        style.configure("FormValue.TLabel", background="#F8FAFC", foreground="#087F75", font=("Segoe UI Variable Display",12,"bold"))
        style.configure("Form.TRadiobutton", background="#F8FAFC", foreground="#334155", font=("Segoe UI",9))
        style.map("Form.TRadiobutton",background=[("active","#F8FAFC")])
        style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#334155", rowheight=34, borderwidth=0, font=("Segoe UI",9))
        style.map("Treeview", background=[("selected","#0F9D8A")], foreground=[("selected","#FFFFFF")])
        style.configure("Treeview.Heading", background="#183B56", foreground="#FFFFFF", font=("Segoe UI", 10, "bold"), padding=(8,10), relief="flat")
        style.map("Treeview.Heading", background=[("active","#34566F")])

    def _build_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        if self.can("backup.manage"):
            file_menu.add_command(label="Backup Database", command=self.backup_database)
            file_menu.add_command(label="Restore Database", command=self.restore_database)
        if self.can("administration.manage"):
            file_menu.add_command(label="System Administration", command=self.open_admin_panel)
            file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)

        session_menu = tk.Menu(menu, tearoff=0)
        session_menu.add_command(label="Lock", command=self.lock_application)
        session_menu.add_command(label="Change My Password", command=self.change_own_password)
        session_menu.add_command(label="Logout", command=self.logout)
        menu.add_cascade(label="Session", menu=session_menu)

        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label="Report a Bug", command=self.open_bug_report)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        if self.can("billing.manage") or self.can("finance.manage"):
            operations_menu = tk.Menu(menu, tearoff=0)
            if self.can("finance.manage"):
                operations_menu.add_command(label="Account Transfer", command=lambda: self.show_page("Account Transfers"))
            if self.can("billing.manage"):
                operations_menu.add_command(label="Due Bills", command=lambda: self.show_page("Due Bills"))
            menu.add_cascade(label="Operations", menu=operations_menu)
        self.config(menu=menu)

    def _build_layout(self):
        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True)

        if self.session.role == "maintenance" and self.can("maintenance.manage"):
            control = ttk.Frame(shell, style="Header.TFrame", padding=(16, 9))
            control.pack(fill="x")
            ttk.Label(
                control,
                text=f"{self.session.display_name or self.session.username} | Maintenance",
                style="HeaderMeta.TLabel",
            ).pack(side="left")
            ttk.Button(control, text="Lock", command=self.lock_application).pack(side="right", padx=3)
            ttk.Button(control, text="Logout", command=self.logout).pack(side="right", padx=3)
            MaintenancePanel(shell,self).pack(fill="both",expand=True)
            return

        self.sidebar_scroll = ScrollableFrame(shell)
        self.sidebar_scroll.pack(side="left", fill="y")
        self._sidebar_visible = True
        sidebar = self.sidebar_scroll.content
        sidebar.configure(style="Sidebar.TFrame", padding=(8, 12))
        ttk.Label(sidebar, text="ELH SYSTEM", style="Section.TLabel").pack(
            anchor="w", padx=8, pady=(0, 10)
        )

        workspace = ttk.Frame(shell)
        self.workspace = workspace
        workspace.pack(side="left", fill="both", expand=True)
        header = ttk.Frame(workspace, style="Header.TFrame", padding=(22,12))
        header.pack(fill="x")
        self.page_title = tk.StringVar(value="Dashboard")
        ttk.Label(header,textvariable=self.page_title,style="HeaderTitle.TLabel").pack(side="left")
        ttk.Button(header, text="☰ Menu", command=self.toggle_sidebar).pack(side="left", padx=(12, 0))
        ttk.Button(header,text="Logout",command=self.logout).pack(side="right",padx=(3,0))
        ttk.Button(header,text="Lock",command=self.lock_application).pack(side="right",padx=3)
        ttk.Label(header,text=f"{self.session.display_name or self.session.username}  |  {self.session.role.title()}",style="HeaderMeta.TLabel").pack(side="right",padx=8)
        ttk.Separator(workspace).pack(fill="x")
        content = ttk.Frame(workspace, padding=(12,8,12,12))
        content.pack(fill="both", expand=True)
        content.rowconfigure(0, weight=1);content.columnconfigure(0, weight=1)

        menu_groups = [
            ("MAIN", [
                ("Dashboard", DashboardPage, "dashboard.view"),
                ("Tasks & Bugs", WorkItemsPage, "dashboard.view"),
                ("Students", StudentsPage, "students.manage"),
                ("Enrollments", EnrollmentsPage, "enrollments.manage"),
                ("Due Bills", DueBillsPage, "billing.manage"),
                ("Certificates", CertificatesPage, "certificates.manage"),
                ("Student Accounts", StudentTransactionsPage, "billing.manage"),
                ("Reports", ReportsPage, "reports.view"),
            ]),
            ("SETUP & STAFF", [
                ("Courses", CoursesPage, "master_data.manage"),
                ("Schools", SchoolsPage, "master_data.manage"),
                ("Staff", TeachersPage, "staff.manage"),
                ("Staff Advances", AdvancesPage, "payroll.manage"),
                ("Salary Payouts", SalaryPage, "payroll.manage"),
            ]),
            ("FINANCE", [
                ("Income", IncomePage, "finance.manage"),
                ("Expenses", ExpensePage, "finance.manage"),
                ("Accounts", AccountsPage, "finance.manage"),
                ("Account Transfers", TransfersPage, "finance.manage"),
                ("Ledger", LedgerPage, "finance.manage"),
            ]),
            ("DEVICES", [
                ("Attendance Device", AttendancePage, "devices.manage"),
                ("POS Printer", PosPrinterPage, "devices.manage"),
                ("Device Health", DeviceHealthPage, "devices.manage"),
            ]),
        ]

        self.pages: dict[str, BasePage] = {};self.nav_buttons = {};self.nav_groups={};self.page_groups={}
        first_page = None
        for group_name, page_classes in menu_groups:
            page_classes = [item for item in page_classes if self.can(item[2])]
            if not page_classes:
                continue
            group_body = ttk.Frame(sidebar, style="Sidebar.TFrame")
            self.nav_groups[group_name] = group_body
            group_button = ttk.Label(
                sidebar,
                text=group_name,
                style="SidebarGroup.TLabel",
            )
            group_button.pack(fill="x", pady=(10, 2), padx=8)
            group_body.pack(fill="x")
            for name, cls, _permission in page_classes:
                page = cls(content, self)
                page.grid(row=0, column=0, sticky="nsew")
                self.pages[name] = page
                self.page_groups[name] = (group_name, group_body, group_button)
                button=ttk.Button(group_body, text=f"  {name}", style="Sidebar.TButton",
                    command=lambda n=name: self.show_page(n), width=22)
                button.pack(fill="x", pady=1);self.nav_buttons[name]=button
                if first_page is None:
                    first_page = name

        ttk.Separator(sidebar).pack(fill="x", pady=10)
        ttk.Label(sidebar,text=f"{self.session.username} ({self.session.role.title()})",style="Sidebar.TLabel").pack(anchor="w",padx=8,pady=(2,6))
        if self.can("administration.manage"):
            ttk.Button(sidebar,text="System Admin",style="Sidebar.TButton",command=self.open_admin_panel).pack(fill="x",pady=2)
        if self.can("backup.manage"):
            ttk.Button(sidebar,text="Backup Database",style="Sidebar.TButton",command=self.backup_database).pack(fill="x",pady=2)

        if first_page:
            self.show_page(first_page)
        else:
            ttk.Label(content,text="No application permissions are assigned to this account.",style="Title.TLabel").grid(row=0,column=0,padx=30,pady=30)

    def show_page(self, name: str):
        page = self.pages[name]
        page.refresh()
        page.tkraise()
        self.page_title.set(name)
        for page_name,button in self.nav_buttons.items():
            button.configure(style="SidebarActive.TButton" if page_name==name else "Sidebar.TButton")

    def toggle_sidebar(self):
        """Collapse navigation entirely; the header menu button restores it."""
        if self._sidebar_visible:
            self.sidebar_scroll.pack_forget()
        else:
            self.sidebar_scroll.pack(side="left", fill="y", before=self.workspace)
        self._sidebar_visible = not self._sidebar_visible

    def open_bug_report(self):
        if "Tasks & Bugs" in getattr(self, "pages", {}):
            self.show_page("Tasks & Bugs")
            self.pages["Tasks & Bugs"].report_bug()

    def refresh_all(self):
        for page in self.pages.values():
            try:
                page.refresh()
            except Exception:
                logging.getLogger(__name__).exception(
                    "Refresh failed for %s", type(page).__name__
                )

    def _record_activity(self, _event=None):
        self._arm_idle_lock()

    def _cancel_idle_lock(self):
        if self._idle_after_id is not None:
            try:
                self.after_cancel(self._idle_after_id)
            except tk.TclError:
                pass
            self._idle_after_id = None

    def _arm_idle_lock(self):
        self._cancel_idle_lock()
        minutes = self.app_config.session_idle_minutes
        if minutes <= 0 or self._session_transitioning or not getattr(self, "session", None):
            return
        self._idle_after_id = self.after(minutes * 60 * 1000, self._auto_lock)

    def _auto_lock(self):
        self._idle_after_id = None
        if not self._session_transitioning and getattr(self, "session", None):
            self.lock_application(auto=True)

    def _clear_interface(self):
        for child in list(self.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self.config(menu=tk.Menu(self))
        self.pages = {}
        self.nav_buttons = {}
        self.nav_groups = {}
        self.page_groups = {}

    def _activate_session(self, session: UserSession) -> bool:
        self.session = session
        if self.session.must_change_password and not self._require_password_change():
            return False
        self._build_menu()
        self._build_layout()
        self.deiconify()
        return True

    def lock_application(self, auto: bool = False):
        if self._session_transitioning:
            return
        self._session_transitioning = True
        self._cancel_idle_lock()
        current_session = self.session
        try:
            reason = "Application locked after inactivity" if auto else "Application locked by user"
            self.auth_service.record_event(
                current_session, "application_locked", True, reason
            )
            self._clear_interface()
            self.withdraw()
            dialog = LoginDialog(
                self, self.auth_service, locked_session=current_session
            )
            self.wait_window(dialog)
            if dialog.session is None:
                self.destroy()
                return
            self.auth_service.record_event(
                dialog.session, "application_unlocked", True, "Application unlocked"
            )
            if not self._activate_session(dialog.session):
                self.destroy()
        finally:
            self._session_transitioning = False
            try:
                exists = bool(self.winfo_exists())
            except tk.TclError:
                exists = False
            if exists:
                self._arm_idle_lock()

    def logout(self):
        if not messagebox.askyesno(
            "Logout", "Sign out of the current account?", parent=self
        ):
            return
        self._session_transitioning = True
        self._cancel_idle_lock()
        try:
            self.auth_service.record_event(
                self.session, "logout", True, "User logged out"
            )
            self._clear_interface()
            self.withdraw()
            dialog = LoginDialog(self, self.auth_service)
            self.wait_window(dialog)
            if dialog.session is None:
                self.destroy()
                return
            if not self._activate_session(dialog.session):
                self.destroy()
        finally:
            self._session_transitioning = False
            try:
                exists = bool(self.winfo_exists())
            except tk.TclError:
                exists = False
            if exists:
                self._arm_idle_lock()

    def change_own_password(self):
        dialog = ChangePasswordDialog(
            self, self.auth_service, self.session, forced=False
        )
        self.wait_window(dialog)
        if dialog.changed:
            messagebox.showinfo(
                "Password Changed",
                "Your password was changed successfully.",
                parent=self,
            )

    def open_admin_panel(self):
        if not self.can("administration.manage"):
            messagebox.showerror("Access Denied","Administrator login is required.",parent=self);return
        AdminPanel(
            self,
            self.db,
            self.app_config,
            auth_service=self.auth_service,
            session=self.session,
        )

    def backup_database(self):
        service = BackupService(self.app_config)
        extension = service.extension
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Backup Database",
            initialdir=str(self.app_config.backup_directory),
            initialfile=f"elh_{self.app_config.database_name}_{datetime.now():%Y%m%d_%H%M%S}{extension}",
            defaultextension=extension,
            filetypes=[("Database Backup", f"*{extension}"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            created = service.create(path)
            self.auth_service.record_event(
                self.session, "database_backup", True, f"Created backup {created.name}"
            )
            messagebox.showinfo(
                "Backup Complete",
                f"A verified database backup and checksum were created at:\n{created}",
                parent=self,
            )
        except (BackupError, OSError) as exc:
            logging.getLogger(__name__).exception("Database backup failed")
            self.auth_service.record_event(
                self.session, "database_backup", False, str(exc)[:500]
            )
            messagebox.showerror("Backup Error", str(exc), parent=self)

    def restore_database(self):
        service = BackupService(self.app_config)
        extension = service.extension
        path = filedialog.askopenfilename(
            parent=self,
            title="Restore Database",
            initialdir=str(self.app_config.backup_directory),
            filetypes=[("Database Backup", f"*{extension}"), ("All Files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Restore Database",
            "This will replace the current database contents.\n\n"
            "A safety backup will be created first. Continue?",
            parent=self,
        ):
            return
        try:
            safety_backup = service.create()
            service.restore(path)
            restored_db = create_database(self.app_config)
            restored_auth = AuthService(restored_db, self.app_config)
            restored_auth.ensure_initial_users()
            try:
                restored_auth.record_event(
                    self.session,
                    "database_restore",
                    True,
                    f"Restored {path}; safety backup {safety_backup.name}",
                )
            except Exception:
                logging.getLogger(__name__).exception("Could not audit completed restore")
            messagebox.showinfo(
                "Restore Complete",
                "The database was restored and checked successfully.\n\n"
                f"Safety backup: {safety_backup}\n\n"
                "The application will now close. Start it again to use the restored database.",
                parent=self,
            )
            self.destroy()
        except (BackupError, OSError) as exc:
            logging.getLogger(__name__).exception("Database restore failed")
            try:
                self.auth_service.record_event(
                    self.session, "database_restore", False, str(exc)[:500]
                )
            except Exception:
                pass
            messagebox.showerror("Restore Error", str(exc), parent=self)

    def show_about(self):
        messagebox.showinfo(
            "About",
            f"{self.app_config.app_title}\n\n"
            f"Desktop application using {self.app_config.database_engine.upper()}.\n"
            "Student, staff, attendance, billing, payroll and accounting modules.",
            parent=self,
        )

    def on_close(self):
        if messagebox.askokcancel("Exit", "Close the application?", parent=self):
            try:
                self.auth_service.record_event(
                    self.session, "application_exit", True, "Application closed"
                )
            except Exception:
                pass
            self._cancel_idle_lock()
            self.destroy()


def _packaging_self_test(config: AppConfig) -> int:
    """Exercise bundled dependencies and core startup without opening the app."""
    import mysql.connector  # noqa: F401 - verifies the frozen connector
    import nepali_datetime  # noqa: F401 - verifies packaged calendar data
    import reportlab  # noqa: F401 - verifies packaged PDF dependencies
    from zk import ZK  # noqa: F401 - verifies the optional hardware package

    probe = tk.Tk()
    probe.withdraw()
    probe.update_idletasks()
    probe.destroy()
    with tempfile.TemporaryDirectory(prefix="elh-self-test-") as folder:
        test_config = replace(
            config,
            environment="self-test",
            database_engine="sqlite",
            database_path=Path(folder) / "self-test.db",
            backup_directory=Path(folder) / "backups",
            log_directory=Path(folder) / "logs",
            attendance_driver="disabled",
            pos_printer_driver="disabled",
        )
        database = create_database(test_config)
        AuthService(database, test_config).ensure_initial_users()
        ServiceContainer.build(test_config, database)
        from elh.infrastructure.schema_optimizer import LATEST_SCHEMA_VERSION

        row = database.query_one("SELECT MAX(version) AS version FROM schema_migrations")
        if not row or int(row["version"] or 0) < LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged database migrations did not complete.")
    return 0


def main() -> int:
    config = load_config()
    if "--self-test" in sys.argv:
        try:
            return _packaging_self_test(config)
        except Exception:
            return 1
    log_path = configure_logging(config)
    install_exception_hooks()
    logger = logging.getLogger(__name__)
    logger.info("Starting ELH Management System (%s)", config.environment)
    try:
        app = ManagementApp(config)
        app.mainloop()
        logger.info("ELH Management System stopped normally")
        return 0
    except Exception as exc:
        logger.critical("Application startup failed", exc_info=True)
        try:
            error_root = tk.Tk()
            error_root.withdraw()
            messagebox.showerror(
                "ELH Startup Error",
                f"The application could not start.\n\n{exc}\n\n"
                f"Technical details were saved in:\n{log_path}",
                parent=error_root,
            )
            error_root.destroy()
        except tk.TclError:
            print(f"ELH startup failed: {exc}. See {log_path}")
        raise
