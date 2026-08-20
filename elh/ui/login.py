from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from elh.models import UserSession


class LoginDialog(tk.Toplevel):
    """Username/password login; role is loaded from the dedicated user table."""

    def __init__(self, parent, auth_service, locked_session: UserSession | None = None):
        super().__init__(parent)
        self.auth_service = auth_service
        self.locked_session = locked_session
        self.session = None
        self.title("Unlock ELH" if locked_session else "ELH Login")
        self.geometry("480x420")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.configure(background="#12263A")

        banner = tk.Frame(self, bg="#12263A", height=92)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(
            banner,
            text="ELH",
            bg="#00A88F",
            fg="white",
            font=("Segoe UI", 15, "bold"),
            padx=12,
            pady=7,
        ).pack(side="left", padx=(28, 14), pady=24)
        tk.Label(
            banner,
            text="Expert Learning Hub\nManagement System",
            bg="#12263A",
            fg="white",
            justify="left",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        panel = ttk.Frame(self, padding=(34, 22, 34, 28))
        panel.pack(fill="both", expand=True)
        heading = "Application locked" if locked_session else "Welcome back"
        subtitle = (
            f"Enter the password for {locked_session.username} to continue."
            if locked_session
            else "Sign in with your username and password."
        )
        ttk.Label(
            panel,
            text=heading,
            font=("Segoe UI Variable Display", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(panel, text=subtitle).pack(anchor="w", pady=(2, 16))

        form = ttk.Frame(panel)
        form.pack(fill="x")
        self.username = tk.StringVar(
            value=locked_session.username if locked_session else ""
        )
        self.password = tk.StringVar()
        ttk.Label(form, text="Username").grid(row=0, column=0, sticky="w", pady=7)
        self.user_entry = ttk.Entry(
            form, textvariable=self.username, width=27
        )
        self.user_entry.grid(row=0, column=1, sticky="ew", pady=7)
        if locked_session:
            self.user_entry.configure(state="readonly")
        ttk.Label(form, text="Password").grid(row=1, column=0, sticky="w", pady=7)
        self.password_entry = ttk.Entry(
            form, textvariable=self.password, show="*", width=27
        )
        self.password_entry.grid(row=1, column=1, sticky="ew", pady=7)
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(20, 0))
        ttk.Button(
            actions,
            text="Unlock" if locked_session else "Sign In",
            style="Accent.TButton",
            command=self.login,
        ).pack(fill="x", pady=(0, 8))
        ttk.Button(
            actions,
            text="Exit Application" if locked_session else "Exit",
            command=self.cancel,
        ).pack(fill="x")

        self.bind("<Return>", lambda _event: self.login())
        self.update_idletasks()
        width = max(480, self.winfo_reqwidth() + 20)
        height = max(420, self.winfo_reqheight() + 20)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(
            300,
            lambda: self.attributes("-topmost", False)
            if self.winfo_exists()
            else None,
        )
        self.grab_set()
        (self.password_entry if locked_session else self.user_entry).focus_force()

    def login(self):
        session = self.auth_service.authenticate(
            self.username.get(), self.password.get()
        )
        if not session:
            messagebox.showerror(
                "Login Failed",
                "Invalid username or password, or the account is disabled or temporarily locked.",
                parent=self,
            )
            self.password.set("")
            self.password_entry.focus_force()
            return
        if self.locked_session and session.user_id != self.locked_session.user_id:
            messagebox.showerror(
                "Unlock Failed",
                "The application must be unlocked by the same user.",
                parent=self,
            )
            self.password.set("")
            return
        self.session = session
        self.destroy()

    def cancel(self):
        self.session = None
        self.destroy()


class ChangePasswordDialog(tk.Toplevel):
    def __init__(self, parent, auth_service, session, forced=False):
        super().__init__(parent)
        self.auth_service = auth_service
        self.session = session
        self.changed = False
        self.forced = forced
        self.title("Change Password")
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        form = ttk.Frame(self, padding=18)
        form.pack(fill="both", expand=True)
        ttk.Label(
            form,
            text="Change Password",
            font=("Segoe UI Variable Display", 16, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        message = (
            "A new password is required before continuing."
            if forced
            else "Confirm your current password and enter a new one."
        )
        ttk.Label(form, text=message).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        self.current = tk.StringVar()
        self.new_password = tk.StringVar()
        self.confirm = tk.StringVar()
        for row, (label, variable) in enumerate(
            (
                ("Current Password", self.current),
                ("New Password", self.new_password),
                ("Confirm Password", self.confirm),
            ),
            start=2,
        ):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(form, textvariable=variable, show="*", width=30).grid(
                row=row, column=1, sticky="ew", pady=5
            )
        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(
            actions,
            text="Change Password",
            style="Accent.TButton",
            command=self.save,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Exit" if forced else "Cancel",
            command=self.cancel,
        ).pack(side="right")
        form.columnconfigure(1, weight=1)
        self.update_idletasks()
        width = max(470, self.winfo_reqwidth() + 20)
        height = max(300, self.winfo_reqheight() + 20)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.grab_set()
        self.focus_force()

    def save(self):
        try:
            if not self.auth_service.verify_user_password(
                self.session.user_id, self.current.get()
            ):
                raise ValueError("Current password is incorrect.")
            if self.new_password.get() != self.confirm.get():
                raise ValueError("Password confirmation does not match.")
            self.auth_service.change_password(
                self.session.user_id,
                self.new_password.get(),
                self.session,
                False,
            )
            self.changed = True
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Password Error", str(exc), parent=self)

    def cancel(self):
        self.changed = False
        self.destroy()
