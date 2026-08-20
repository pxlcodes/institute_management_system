"""Dedicated system configuration and health-monitoring UI adapter."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from elh.config import AppConfig, DEFAULT_ENV_FILE, EDITABLE_ENV_KEYS, load_config, write_env
from elh.core.health import HealthService
from elh.core.settings import SettingsService
from elh.ui.user_management import UserManagementFrame
from elh.services.notifications import NotificationService, SMS_EVENT_FIELDS


class AdminPanel(tk.Toplevel):
    """Desktop adapter over the framework-independent config/health services."""

    def __init__(self, parent: tk.Misc, db, config: AppConfig, auth_service=None, session=None, on_config_saved: Callable[[], None] | None = None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        # Tk widgets already expose config(); keep application settings separate.
        self.app_config = config
        self.on_config_saved = on_config_saved
        self.auth_service = auth_service
        self.session = session
        self.notifications = (
            getattr(getattr(parent, "services", None), "notifications", None)
            or NotificationService(db, config)
        )
        self.title("ELH System Administration")
        self.geometry("920x650")
        self.minsize(760, 520)
        self.transient(parent)

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.health_tab = ttk.Frame(tabs, padding=12)
        self.config_tab = ttk.Frame(tabs, padding=12)
        self.runtime_tab = ttk.Frame(tabs, padding=12)
        self.company_tab = ttk.Frame(tabs, padding=12)
        self.sms_tab = ttk.Frame(tabs, padding=12)
        self.users_tab = ttk.Frame(tabs, padding=12)
        tabs.add(self.health_tab, text="Health Monitor")
        tabs.add(self.config_tab, text="Environment Configuration")
        tabs.add(self.runtime_tab, text="Application Settings")
        tabs.add(self.company_tab, text="Company Details")
        tabs.add(self.sms_tab, text="SMS & Notifications")
        if self.auth_service is not None and self.session is not None:
            tabs.add(self.users_tab, text="Users & Access")
        self._build_health()
        self._build_config()
        self._build_runtime()
        self._build_company()
        self._build_sms()
        if self.auth_service is not None and self.session is not None:
            UserManagementFrame(
                self.users_tab, self.auth_service, self.session
            ).pack(fill="both", expand=True)
        self.refresh_health()
        self.refresh_runtime()
        self.refresh_sms()

    def _build_company(self) -> None:
        ttk.Label(self.company_tab,text="Company details used on bills, certificates, and printable reports.",font=("Segoe UI",14,"bold")).pack(anchor="w",pady=(0,14))
        profile=self.db.query_one("SELECT * FROM company_profile WHERE id=1")
        fields=(("company_name","Company Name"),("pan_number","PAN Number"),("registration_number","Registration Number"),("address","Address"),("phone","Phone"),("email","Email"),("website","Website"),("principal_name","Principal / Director Name"),("report_footer","Report Footer"))
        form=ttk.Frame(self.company_tab);form.pack(fill="x");self.company_vars={}
        for row,(key,label) in enumerate(fields):
            ttk.Label(form,text=label,width=24).grid(row=row,column=0,sticky="w",padx=5,pady=6)
            var=tk.StringVar(value=(profile[key] if profile and profile[key] is not None else (self.app_config.app_title if key=="company_name" else "")))
            ttk.Entry(form,textvariable=var,width=65).grid(row=row,column=1,sticky="ew",padx=5,pady=6);self.company_vars[key]=var
        form.columnconfigure(1,weight=1);ttk.Button(form,text="Save Company Details",style="Accent.TButton",command=self.save_company).grid(row=len(fields),column=1,sticky="e",pady=14)

    def save_company(self) -> None:
        values={key:var.get().strip() for key,var in self.company_vars.items()}
        if not values["company_name"]:messagebox.showerror("Company Details","Company name is required.",parent=self);return
        params=(values["company_name"],values["pan_number"],values["registration_number"],values["address"],values["phone"],values["email"],values["website"],values["principal_name"],values["report_footer"])
        if self.db.query_one("SELECT id FROM company_profile WHERE id=1"):
            self.db.execute("UPDATE company_profile SET company_name=?,pan_number=?,registration_number=?,address=?,phone=?,email=?,website=?,principal_name=?,report_footer=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",params)
        else:self.db.execute("INSERT INTO company_profile (id,company_name,pan_number,registration_number,address,phone,email,website,principal_name,report_footer) VALUES (1,?,?,?,?,?,?,?,?,?)",params)
        services = getattr(self.parent_app, "services", None)
        if services is not None:
            services.billing.app_title = values["company_name"]
            services.reports.app_title = values["company_name"]
        messagebox.showinfo("Company Details","Company details saved successfully.",parent=self)

    def _build_sms(self) -> None:
        settings = ttk.LabelFrame(
            self.sms_tab, text="Gateway Settings", padding=10
        )
        settings.pack(fill="x", pady=(0, 8))
        self.sms_enabled = tk.BooleanVar()
        self.sms_provider = tk.StringVar(value="aakash")
        self.sms_sender = tk.StringVar()
        self.sms_timeout = tk.StringVar(value="10")
        ttk.Checkbutton(
            settings, text="Enable automatic SMS notifications", variable=self.sms_enabled
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        ttk.Label(settings, text="Provider").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.sms_provider,
            values=("aakash", "sparrow"),
            state="readonly",
            width=18,
        ).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(settings, text="Sender ID (Sparrow)").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(settings, textvariable=self.sms_sender, width=22).grid(
            row=1, column=3, sticky="w", padx=4, pady=4
        )
        ttk.Label(settings, text="Timeout seconds").grid(row=1, column=4, sticky="w", padx=4, pady=4)
        ttk.Entry(settings, textvariable=self.sms_timeout, width=8).grid(
            row=1, column=5, sticky="w", padx=4, pady=4
        )
        ttk.Button(
            settings, text="Save SMS Settings", style="Accent.TButton",
            command=self.save_sms_config,
        ).grid(row=0, column=5, rowspan=1, sticky="e", padx=4, pady=4)
        ttk.Label(
            settings,
            text="API tokens are secrets and remain under Environment Configuration / .env.",
        ).grid(row=2, column=0, columnspan=6, sticky="w", padx=4, pady=(4, 0))

        test = ttk.Frame(self.sms_tab)
        test.pack(fill="x", pady=(0, 8))
        self.sms_test_phone = tk.StringVar()
        self.sms_test_message = tk.StringVar(value="Test SMS from Expert Learning Hub")
        ttk.Label(test, text="Test mobile").pack(side="left")
        ttk.Entry(test, textvariable=self.sms_test_phone, width=18).pack(side="left", padx=5)
        ttk.Entry(test, textvariable=self.sms_test_message, width=48).pack(
            side="left", fill="x", expand=True, padx=5
        )
        ttk.Button(test, text="Send Test SMS", command=self.send_test_sms).pack(side="right")

        detail_tabs = ttk.Notebook(self.sms_tab)
        detail_tabs.pack(fill="both", expand=True)
        template_tab = ttk.Frame(detail_tabs, padding=8)
        log_tab = ttk.Frame(detail_tabs, padding=8)
        detail_tabs.add(template_tab, text="Event Templates")
        detail_tabs.add(log_tab, text="Delivery Log")

        self.sms_template_tree = ttk.Treeview(
            template_tab,
            columns=("event", "name", "enabled"),
            show="headings",
            height=6,
        )
        for key, heading, width in (
            ("event", "Event", 150),
            ("name", "Description", 240),
            ("enabled", "Enabled", 80),
        ):
            self.sms_template_tree.heading(key, text=heading)
            self.sms_template_tree.column(key, width=width, anchor="w")
        self.sms_template_tree.pack(fill="x")
        self.sms_template_tree.bind("<<TreeviewSelect>>", self._select_sms_template)
        self.sms_template_enabled = tk.BooleanVar()
        self.sms_template_key = tk.StringVar()
        self.sms_template_name = tk.StringVar()
        heading = ttk.Frame(template_tab)
        heading.pack(fill="x", pady=(8, 3))
        ttk.Label(heading, textvariable=self.sms_template_name).pack(side="left")
        ttk.Checkbutton(
            heading, text="Send automatically for this event", variable=self.sms_template_enabled
        ).pack(side="right")
        self.sms_template_text = tk.Text(template_tab, height=4, wrap="word")
        self.sms_template_text.pack(fill="x")
        self.sms_fields_hint = ttk.Label(template_tab, text="")
        self.sms_fields_hint.pack(fill="x", pady=4)
        ttk.Button(
            template_tab,
            text="Save Template",
            style="Accent.TButton",
            command=self.save_sms_template,
        ).pack(anchor="e", pady=4)

        toolbar = ttk.Frame(log_tab)
        toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(toolbar, text="Refresh", command=self.refresh_sms_logs).pack(side="left")
        ttk.Button(toolbar, text="Retry Selected", command=self.retry_sms).pack(
            side="left", padx=5
        )
        self.sms_log_tree = ttk.Treeview(
            log_tab,
            columns=("id", "event", "recipient", "provider", "status", "attempts", "created"),
            show="headings",
        )
        for key, heading, width in (
            ("id", "ID", 55),
            ("event", "Event", 120),
            ("recipient", "Mobile", 110),
            ("provider", "Provider", 90),
            ("status", "Status", 80),
            ("attempts", "Attempts", 65),
            ("created", "Created", 150),
        ):
            self.sms_log_tree.heading(key, text=heading)
            self.sms_log_tree.column(key, width=width, anchor="w")
        self.sms_log_tree.pack(fill="both", expand=True)

    def refresh_sms(self) -> None:
        settings = SettingsService(self.db)
        settings.ensure_defaults()
        self.sms_enabled.set(settings.get_bool("sms_enabled", False))
        self.sms_provider.set(settings.get("sms_provider", "aakash"))
        self.sms_sender.set(settings.get("sms_sender_id", ""))
        self.sms_timeout.set(settings.get("sms_timeout_seconds", "10"))
        self.sms_template_tree.delete(*self.sms_template_tree.get_children())
        for row in self.db.query(
            "SELECT event_key,event_name,enabled FROM sms_event_templates ORDER BY event_name"
        ):
            self.sms_template_tree.insert(
                "", "end", values=(row["event_key"], row["event_name"], "Yes" if row["enabled"] else "No")
            )
        self.refresh_sms_logs()

    def save_sms_config(self, show_message: bool = True) -> None:
        try:
            timeout = int(self.sms_timeout.get())
            if timeout < 2 or timeout > 60:
                raise ValueError("SMS timeout must be between 2 and 60 seconds.")
            settings = SettingsService(self.db)
            settings.set("sms_enabled", "true" if self.sms_enabled.get() else "false")
            settings.set("sms_provider", self.sms_provider.get())
            settings.set("sms_sender_id", self.sms_sender.get())
            settings.set("sms_timeout_seconds", str(timeout))
            self.refresh_runtime()
            if show_message:
                messagebox.showinfo("SMS Settings", "SMS settings saved.", parent=self)
        except ValueError as exc:
            if show_message:
                messagebox.showerror("SMS Settings", str(exc), parent=self)
            raise

    def _select_sms_template(self, _event=None) -> None:
        selected = self.sms_template_tree.selection()
        if not selected:
            return
        event_key = self.sms_template_tree.item(selected[0], "values")[0]
        row = self.db.query_one(
            "SELECT * FROM sms_event_templates WHERE event_key=?", (event_key,)
        )
        if not row:
            return
        self.sms_template_key.set(event_key)
        self.sms_template_name.set(row["event_name"])
        self.sms_template_enabled.set(bool(row["enabled"]))
        self.sms_template_text.delete("1.0", "end")
        self.sms_template_text.insert("1.0", row["template_text"])
        fields = "  ".join(f"{{{field}}}" for field in sorted(SMS_EVENT_FIELDS[event_key]))
        self.sms_fields_hint.configure(text=f"Available fields: {fields}")

    def save_sms_template(self) -> None:
        event_key = self.sms_template_key.get()
        if not event_key:
            messagebox.showwarning("SMS Template", "Select an event first.", parent=self)
            return
        template = self.sms_template_text.get("1.0", "end").strip()
        try:
            self.notifications.validate_template(event_key, template)
            self.db.execute(
                "UPDATE sms_event_templates SET enabled=?,template_text=?,"
                "updated_at=CURRENT_TIMESTAMP WHERE event_key=?",
                (1 if self.sms_template_enabled.get() else 0, template, event_key),
            )
            self.refresh_sms()
            messagebox.showinfo("SMS Template", "Template saved.", parent=self)
        except ValueError as exc:
            messagebox.showerror("SMS Template", str(exc), parent=self)

    def send_test_sms(self) -> None:
        try:
            self.save_sms_config(show_message=False)
            log_id = self.notifications.send_test(
                self.sms_test_phone.get(), self.sms_test_message.get()
            )
            row = self.db.query_one(
                "SELECT status,response_message FROM sms_delivery_log WHERE id=?", (log_id,)
            )
            self.refresh_sms_logs()
            if row and row["status"] == "Sent":
                messagebox.showinfo("Test SMS", "Test SMS was queued successfully.", parent=self)
            else:
                raise ValueError((row["response_message"] if row else None) or "SMS send failed.")
        except Exception as exc:
            messagebox.showerror("Test SMS", str(exc), parent=self)

    def refresh_sms_logs(self) -> None:
        self.sms_log_tree.delete(*self.sms_log_tree.get_children())
        for row in self.notifications.recent(100):
            self.sms_log_tree.insert(
                "",
                "end",
                values=(
                    row["id"], row["event_key"], row["recipient"], row["provider"],
                    row["status"], row["attempt_count"], row["created_at"],
                ),
            )

    def retry_sms(self) -> None:
        selected = self.sms_log_tree.selection()
        if not selected:
            messagebox.showwarning("SMS Delivery", "Select a delivery first.", parent=self)
            return
        log_id = int(self.sms_log_tree.item(selected[0], "values")[0])
        try:
            self.notifications.retry(log_id)
            self.after(500, self.refresh_sms_logs)
        except ValueError as exc:
            messagebox.showerror("SMS Delivery", str(exc), parent=self)

    def _build_health(self) -> None:
        bar = ttk.Frame(self.health_tab)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="System health", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh_health).pack(side="right")
        self.health_summary = ttk.Label(self.health_tab, text="")
        self.health_summary.pack(anchor="w", pady=(0, 8))
        self.health_tree = ttk.Treeview(self.health_tab, columns=("component", "status", "detail"), show="headings")
        for column, heading, width in (("component", "Component", 150), ("status", "Status", 100), ("detail", "Detail", 540)):
            self.health_tree.heading(column, text=heading)
            self.health_tree.column(column, width=width, anchor="w")
        self.health_tree.pack(fill="both", expand=True)

    def _build_config(self) -> None:
        ttk.Label(
            self.config_tab,
            text="Values are stored in .env and take effect after restarting the application.",
        ).pack(anchor="w", pady=(0, 10))
        canvas = tk.Canvas(self.config_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.config_tab, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas)
        form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.config_vars: dict[str, tk.StringVar] = {}
        current = self.app_config.public_values()
        # Login accounts are managed in the dedicated Users & Access tab.
        # The legacy environment values remain bootstrap-only for a fresh DB.
        bootstrap_login_fields = {
            "operator_username", "operator_password",
            "admin_username", "admin_password",
            "maintenance_username", "maintenance_password",
        }
        editable_fields = [
            field_name
            for field_name in EDITABLE_ENV_KEYS
            if field_name not in bootstrap_login_fields
        ]
        for row, field_name in enumerate(editable_fields):
            ttk.Label(form, text=field_name.replace("_", " ").title(), width=28).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            variable = tk.StringVar(value=current[field_name])
            entry = ttk.Entry(form, textvariable=variable, width=62)
            if "password" in field_name or "token" in field_name:
                entry.configure(show="*")
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=4)
            self.config_vars[field_name] = variable
        form.columnconfigure(1, weight=1)
        ttk.Button(form, text="Save .env Configuration", command=self.save_config).grid(
            row=len(editable_fields), column=1, sticky="e", padx=4, pady=12
        )

    def _build_runtime(self) -> None:
        editor = ttk.Frame(self.runtime_tab)
        editor.pack(fill="x", pady=(0, 8))
        self.setting_category = tk.StringVar(value="General")
        self.setting_key = tk.StringVar()
        self.setting_value = tk.StringVar()
        ttk.Label(editor, text="Category").grid(row=0, column=0, sticky="w")
        ttk.Combobox(editor,textvariable=self.setting_category,values=("General","Certificates","Notifications","Reports"),width=18).grid(row=1,column=0,padx=(0,6))
        ttk.Label(editor, text="Key").grid(row=0, column=1, sticky="w")
        ttk.Entry(editor, textvariable=self.setting_key, width=26).grid(row=1, column=1, padx=(0, 6))
        ttk.Label(editor, text="Value").grid(row=0, column=2, sticky="w")
        ttk.Entry(editor, textvariable=self.setting_value, width=36).grid(row=1, column=2, padx=(0, 6))
        ttk.Button(editor, text="Save", command=self.save_runtime).grid(row=1, column=3, padx=3)
        ttk.Button(editor, text="Delete", command=self.delete_runtime).grid(row=1, column=4, padx=3)
        self.settings_tree = ttk.Treeview(self.runtime_tab, columns=("category","label","key", "value"), show="headings")
        self.settings_tree.heading("category", text="Category")
        self.settings_tree.heading("label", text="Setting")
        self.settings_tree.heading("key", text="Setting Key")
        self.settings_tree.heading("value", text="Value")
        self.settings_tree.column("category", width=120)
        self.settings_tree.column("label", width=210)
        self.settings_tree.column("key", width=200)
        self.settings_tree.column("value", width=250)
        self.settings_tree.pack(fill="both", expand=True)
        self.settings_tree.bind("<<TreeviewSelect>>", self._select_runtime)

    def refresh_health(self) -> None:
        report = HealthService(self.app_config, self.db).report()
        self.health_tree.delete(*self.health_tree.get_children())
        for check in report["checks"]:
            self.health_tree.insert("", "end", values=(check["name"], check["status"].upper(), check["detail"]))
        self.health_summary.configure(text=f"Overall status: {str(report['status']).upper()}   Environment: {report['environment']}")

    def save_config(self) -> None:
        updates = {key: variable.get().strip() for key, variable in self.config_vars.items()}
        try:
            # Validate types before writing an invalid environment file.
            temp = DEFAULT_ENV_FILE.with_name(".env.admin.tmp")
            write_env(updates, temp)
            load_config(temp)
            temp.unlink(missing_ok=True)
            write_env(updates)
            if self.on_config_saved:
                self.on_config_saved()
            messagebox.showinfo("Configuration Saved", "Configuration saved. Restart the application to apply all values.", parent=self)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Configuration Error", str(exc), parent=self)

    def refresh_runtime(self) -> None:
        self.settings_tree.delete(*self.settings_tree.get_children())
        for row in SettingsService(self.db).rows():
            self.settings_tree.insert("", "end", values=(row["category"],row["setting_label"] or row["setting_key"],row["setting_key"],row["setting_value"] or ""))

    def save_runtime(self) -> None:
        try:
            SettingsService(self.db).set(self.setting_key.get(), self.setting_value.get(),self.setting_category.get())
            if self.setting_key.get().strip() == "currency_symbol":
                services = getattr(self.parent_app, "services", None)
                if services is not None:
                    services.billing.currency_symbol = self.setting_value.get().strip()
                    services.reports.currency_symbol = self.setting_value.get().strip()
            self.refresh_runtime()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Setting Error", str(exc), parent=self)

    def delete_runtime(self) -> None:
        key = self.setting_key.get().strip()
        if key:
            SettingsService(self.db).delete(key)
            self.setting_key.set("")
            self.setting_value.set("")
            self.setting_category.set("General")
            self.refresh_runtime()

    def _select_runtime(self, _event=None) -> None:
        selected = self.settings_tree.selection()
        if selected:
            category, _label, key, value = self.settings_tree.item(selected[0], "values")
            self.setting_category.set(category)
            self.setting_key.set(key)
            self.setting_value.set(value)
