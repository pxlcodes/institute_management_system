from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from elh.services.auth import ROLES


class UserManagementFrame(ttk.Frame):
    """Administrator UI for authentication, authorization, and audit records."""

    def __init__(self, parent, auth_service, session):
        super().__init__(parent)
        self.auth_service = auth_service
        self.session = session
        self.selected_id: int | None = None
        self.selected_locked = False
        self.permission_vars: dict[str, tk.BooleanVar] = {}
        self._configure_styles()

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        self.accounts_tab = ttk.Frame(tabs, padding=8)
        self.audit_tab = ttk.Frame(tabs, padding=8)
        tabs.add(self.accounts_tab, text="User Accounts & Permissions")
        tabs.add(self.audit_tab, text="Access Audit")
        self._build_accounts()
        self._build_audit()
        self.refresh()

    def _configure_styles(self):
        """Keep the editor visually flat instead of highlighting label text."""
        style = ttk.Style(self)
        background = "#FFFFFF"
        foreground = "#334155"
        style.configure("AdminUser.TFrame", background=background)
        style.configure(
            "AdminUser.TLabel",
            background=background,
            foreground=foreground,
            font=("Segoe UI", 9),
        )
        style.configure(
            "AdminUser.TLabelframe",
            background=background,
            bordercolor="#D7E1EA",
            borderwidth=1,
            relief="flat",
        )
        style.configure(
            "AdminUser.TLabelframe.Label",
            background=background,
            foreground="#183B56",
            font=("Segoe UI Variable Display", 11, "bold"),
        )
        style.configure(
            "AdminUser.TCheckbutton",
            background=background,
            foreground=foreground,
            font=("Segoe UI", 9),
            padding=(0, 4),
        )
        style.map(
            "AdminUser.TCheckbutton",
            background=[
                ("active", background),
                ("pressed", background),
                ("selected", background),
                ("!disabled", background),
            ],
        )
        style.configure(
            "AdminUser.TRadiobutton",
            background=background,
            foreground=foreground,
            font=("Segoe UI", 9),
        )
        style.map(
            "AdminUser.TRadiobutton",
            background=[
                ("active", background),
                ("selected", background),
                ("!disabled", background),
            ],
        )

    def _build_accounts(self):
        toolbar = ttk.Frame(self.accounts_tab)
        toolbar.pack(fill="x", pady=(0, 7))
        ttk.Button(
            toolbar, text="New User", style="Accent.TButton", command=self.clear
        ).pack(side="left", padx=(0, 4))
        ttk.Button(toolbar, text="Save User", command=self.save_user).pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Change Password", command=self.change_password).pack(
            side="left", padx=4
        )
        self.toggle_button = ttk.Button(
            toolbar, text="Disable User", command=self.toggle_status
        )
        self.toggle_button.pack(side="left", padx=4)
        ttk.Button(
            toolbar, text="Use Role Defaults", command=self.apply_role_defaults
        ).pack(side="left", padx=4)

        tree_area = ttk.Frame(self.accounts_tab)
        tree_area.pack(fill="x")
        tree_area.columnconfigure(0, weight=1)
        self.user_tree = ttk.Treeview(
            tree_area,
            columns=("id", "username", "display", "role", "status", "last_login"),
            show="headings",
            height=3,
        )
        for key, title, width in (
            ("id", "ID", 45),
            ("username", "Username", 130),
            ("display", "Display Name", 170),
            ("role", "Role", 100),
            ("status", "Status", 110),
            ("last_login", "Last Login", 155),
        ):
            self.user_tree.heading(key, text=title)
            self.user_tree.column(key, width=width, anchor="w")
        user_scrollbar = ttk.Scrollbar(
            tree_area, orient="vertical", command=self.user_tree.yview
        )
        self.user_tree.configure(yscrollcommand=user_scrollbar.set)
        self.user_tree.grid(row=0, column=0, sticky="nsew")
        user_scrollbar.grid(row=0, column=1, sticky="ns")
        self.user_tree.bind("<<TreeviewSelect>>", self.select_user)

        editor = ttk.Frame(self.accounts_tab, style="AdminUser.TFrame")
        editor.pack(fill="both", expand=True, pady=(8, 0))
        profile = ttk.LabelFrame(
            editor,
            text="Account",
            padding=(12, 8),
            style="AdminUser.TLabelframe",
        )
        profile.pack(fill="x", pady=(0, 8))
        permissions = ttk.LabelFrame(
            editor,
            text="Permissions",
            padding=(12, 7),
            style="AdminUser.TLabelframe",
        )
        permissions.pack(fill="both", expand=True)

        self.username = tk.StringVar()
        self.display_name = tk.StringVar()
        self.email = tk.StringVar()
        self.role = tk.StringVar(value="operator")
        self.status = tk.StringVar(value="Active")
        self.password = tk.StringVar()
        self.confirm_password = tk.StringVar()
        self.must_change_password = tk.BooleanVar(value=True)

        fields = (
            ("Username *", self.username, False),
            ("Display Name", self.display_name, False),
            ("Email", self.email, False),
            ("New Password", self.password, True),
            ("Confirm Password", self.confirm_password, True),
        )
        for index, (label, variable, secret) in enumerate(fields):
            row_index = index // 2
            column_index = (index % 2) * 2
            ttk.Label(profile, text=label, style="AdminUser.TLabel").grid(
                row=row_index,
                column=column_index,
                sticky="w",
                pady=3,
                padx=(0, 8),
            )
            entry = ttk.Entry(profile, textvariable=variable, width=24)
            if secret:
                entry.configure(show="*")
            entry.grid(
                row=row_index,
                column=column_index + 1,
                sticky="ew",
                pady=3,
                padx=(0, 18) if column_index == 0 else (0, 0),
            )
            if index == 0:
                self.username_entry = entry

        ttk.Label(profile, text="Role *", style="AdminUser.TLabel").grid(
            row=2, column=2, sticky="w", pady=3, padx=(0, 8)
        )
        role_combo = ttk.Combobox(
            profile,
            textvariable=self.role,
            values=[role.title() for role in ROLES],
            state="readonly",
            width=22,
        )
        role_combo.grid(row=2, column=3, sticky="ew", pady=3)
        role_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_role_defaults())
        ttk.Label(profile, text="Status", style="AdminUser.TLabel").grid(
            row=3, column=0, sticky="w", pady=3, padx=(0, 8)
        )
        status_frame = ttk.Frame(profile, style="AdminUser.TFrame")
        status_frame.grid(row=3, column=1, sticky="w", pady=3)
        ttk.Radiobutton(
            status_frame,
            text="Active",
            variable=self.status,
            value="Active",
            style="AdminUser.TRadiobutton",
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            status_frame,
            text="Disabled",
            variable=self.status,
            value="Disabled",
            style="AdminUser.TRadiobutton",
        ).pack(side="left")
        ttk.Checkbutton(
            profile,
            text="Require password change at next login",
            variable=self.must_change_password,
            style="AdminUser.TCheckbutton",
        ).grid(row=3, column=2, columnspan=2, sticky="w", pady=3)
        profile.columnconfigure(1, weight=1)
        profile.columnconfigure(3, weight=1)

        for index, permission in enumerate(self.auth_service.list_permissions()):
            variable = tk.BooleanVar()
            self.permission_vars[permission["key"]] = variable
            checkbox = ttk.Checkbutton(
                permissions,
                text=permission["name"],
                variable=variable,
                style="AdminUser.TCheckbutton",
            )
            checkbox.grid(
                row=index // 4,
                column=index % 4,
                sticky="w",
                padx=(0, 14),
                pady=2,
            )
        for column in range(4):
            permissions.columnconfigure(column, weight=1)

    def _build_audit(self):
        bar = ttk.Frame(self.audit_tab)
        bar.pack(fill="x", pady=(0, 7))
        ttk.Label(
            bar, text="Authentication and administration activity"
        ).pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh_audit).pack(side="right")
        self.audit_tree = ttk.Treeview(
            self.audit_tab,
            columns=("time", "username", "event", "result", "detail"),
            show="headings",
        )
        for key, title, width in (
            ("time", "Time", 155),
            ("username", "Username", 120),
            ("event", "Event", 140),
            ("result", "Result", 80),
            ("detail", "Details", 390),
        ):
            self.audit_tree.heading(key, text=title)
            self.audit_tree.column(key, width=width, anchor="w")
        self.audit_tree.pack(fill="both", expand=True)

    @staticmethod
    def _role_value(value: str) -> str:
        return value.strip().lower()

    def selected_permissions(self) -> set[str]:
        return {
            key for key, variable in self.permission_vars.items() if variable.get()
        }

    def apply_role_defaults(self):
        selected = self.auth_service.role_permissions(self._role_value(self.role.get()))
        for key, variable in self.permission_vars.items():
            variable.set(key in selected)

    def clear(self):
        self.selected_id = None
        self.selected_locked = False
        self.username_entry.configure(state="normal")
        self.username.set("")
        self.display_name.set("")
        self.email.set("")
        self.role.set("Operator")
        self.status.set("Active")
        self.password.set("")
        self.confirm_password.set("")
        self.must_change_password.set(True)
        self.toggle_button.configure(text="Disable User")
        self.user_tree.selection_remove(self.user_tree.selection())
        self.apply_role_defaults()

    def refresh(self):
        self.refresh_users()
        self.refresh_audit()
        if self.selected_id is None:
            self.clear()

    def refresh_users(self):
        self.user_tree.delete(*self.user_tree.get_children())
        now = datetime.now()
        for row in self.auth_service.list_users():
            status = row["status"]
            locked = self.auth_service._parse_datetime(row["locked_until"])
            if status == "Active" and locked and locked > now:
                status = "Locked"
            self.user_tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["username"],
                    row["display_name"] or "",
                    str(row["role"]).title(),
                    status,
                    row["last_login_at"] or "",
                ),
            )

    def select_user(self, _event=None):
        selected = self.user_tree.selection()
        if not selected:
            return
        user_id = int(self.user_tree.item(selected[0], "values")[0])
        row = self.auth_service.get_user(user_id)
        if not row:
            return
        self.selected_id = user_id
        locked_until = self.auth_service._parse_datetime(row["locked_until"])
        self.selected_locked = bool(
            row["status"] == "Active"
            and locked_until
            and locked_until > datetime.now()
        )
        self.username_entry.configure(state="normal")
        self.username.set(row["username"])
        self.username_entry.configure(state="readonly")
        self.display_name.set(row["display_name"] or "")
        self.email.set(row["email"] or "")
        self.role.set(str(row["role"]).title())
        self.status.set(row["status"])
        self.must_change_password.set(bool(row["must_change_password"]))
        self.password.set("")
        self.confirm_password.set("")
        effective = self.auth_service.permissions_for_user(user_id, row["role"])
        for key, variable in self.permission_vars.items():
            variable.set(key in effective)
        self.toggle_button.configure(
            text=(
                "Unlock User"
                if self.selected_locked
                else "Disable User"
                if row["status"] == "Active"
                else "Enable User"
            )
        )

    def _validated_password(self, required: bool) -> str | None:
        password = self.password.get()
        confirmation = self.confirm_password.get()
        if not password and not confirmation and not required:
            return None
        if password != confirmation:
            raise ValueError("Password confirmation does not match.")
        self.auth_service.validate_password(password)
        return password

    def save_user(self):
        try:
            role = self._role_value(self.role.get())
            permissions = self.selected_permissions()
            if self.selected_id is None:
                password = self._validated_password(required=True)
                self.auth_service.create_user(
                    self.username.get(),
                    password,
                    self.display_name.get(),
                    self.email.get(),
                    role,
                    self.status.get(),
                    permissions,
                    self.session,
                    self.must_change_password.get(),
                )
            else:
                self.auth_service.update_user(
                    self.selected_id,
                    self.display_name.get(),
                    self.email.get(),
                    role,
                    self.status.get(),
                    permissions,
                    self.session,
                    self.must_change_password.get(),
                )
                password = self._validated_password(required=False)
                if password:
                    self.auth_service.change_password(
                        self.selected_id,
                        password,
                        self.session,
                        self.must_change_password.get(),
                    )
            self.clear()
            self.refresh()
            messagebox.showinfo("Users", "User account saved.", parent=self)
        except Exception as exc:
            messagebox.showerror("User Error", str(exc), parent=self)

    def change_password(self):
        if self.selected_id is None:
            messagebox.showwarning("Users", "Select a user first.", parent=self)
            return
        try:
            password = self._validated_password(required=True)
            self.auth_service.change_password(
                self.selected_id,
                password,
                self.session,
                self.must_change_password.get(),
            )
            self.password.set("")
            self.confirm_password.set("")
            self.refresh_audit()
            messagebox.showinfo("Users", "Password changed.", parent=self)
        except Exception as exc:
            messagebox.showerror("Password Error", str(exc), parent=self)

    def toggle_status(self):
        if self.selected_id is None:
            messagebox.showwarning("Users", "Select a user first.", parent=self)
            return
        new_status = (
            "Active"
            if self.selected_locked
            else "Disabled"
            if self.status.get() == "Active"
            else "Active"
        )
        self.status.set(new_status)
        self.save_user()

    def refresh_audit(self):
        self.audit_tree.delete(*self.audit_tree.get_children())
        for row in self.auth_service.list_audit():
            self.audit_tree.insert(
                "",
                "end",
                values=(
                    row["occurred_at"],
                    row["username"] or "",
                    str(row["event_type"]).replace("_", " ").title(),
                    "SUCCESS" if int(row["success"]) else "FAILED",
                    row["detail"] or "",
                ),
            )
