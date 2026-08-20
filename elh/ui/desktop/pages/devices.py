from __future__ import annotations

import threading
from tkinter import ttk

from elh.core.health import HealthService
from elh.ui.desktop.components import BasePage


class PosPrinterPage(BasePage):
    """Read-only POS printer configuration and connection test."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="POS Printer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="View the configured receipt printer and check whether it is reachable.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        card = ttk.LabelFrame(self, text="Printer Configuration", style="Form.TLabelframe", padding=16)
        card.pack(fill="x")
        self.value_labels = {}
        fields = (
            ("driver", "Driver"),
            ("host", "IP Address / Host"),
            ("port", "Port"),
            ("width", "Characters Per Line"),
        )
        for row_index, (key, title) in enumerate(fields):
            ttk.Label(card, text=title, style="Form.TLabel").grid(
                row=row_index, column=0, sticky="w", padx=(0, 18), pady=5
            )
            label = ttk.Label(card, text="-")
            label.grid(row=row_index, column=1, sticky="w", pady=5)
            self.value_labels[key] = label

        actions = ttk.Frame(self, style="Toolbar.TFrame", padding=8)
        actions.pack(fill="x", pady=(12, 8))
        self.check_button = ttk.Button(
            actions,
            text="Check POS Printer",
            style="Accent.TButton",
            command=self.check_printer,
        )
        self.check_button.pack(side="left")
        self.status_label = ttk.Label(actions, text="Not checked", style="Hint.TLabel")
        self.status_label.pack(side="left", padx=14)

    def refresh(self):
        config = self.app.app_config
        values = {
            "driver": config.pos_printer_driver,
            "host": config.pos_printer_host or "Not configured",
            "port": str(config.pos_printer_port),
            "width": str(config.pos_printer_chars_per_line),
        }
        for key, value in values.items():
            self.value_labels[key].configure(text=value)

    def check_printer(self):
        self.check_button.configure(state="disabled", text="Checking...")
        self.status_label.configure(text="Connecting to printer...")

        def work():
            try:
                ok, detail = self.app.services.printing.printer.health()
            except Exception as exc:
                ok, detail = False, str(exc)
            self.after(0, lambda: self.check_finished(ok, detail))

        threading.Thread(target=work, daemon=True).start()

    def check_finished(self, ok, detail):
        self.check_button.configure(state="normal", text="Check POS Printer")
        prefix = "Connected" if ok else "Not connected"
        self.status_label.configure(text=f"{prefix}: {detail}")


class DeviceHealthPage(BasePage):
    """Health overview for every registered system device and dependency."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="Device Health", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Check attendance, POS printing, and other registered system components.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=8)
        toolbar.pack(fill="x", pady=(0, 8))
        self.check_button = ttk.Button(
            toolbar,
            text="Check All Devices",
            style="Accent.TButton",
            command=self.refresh,
        )
        self.check_button.pack(side="left")

        self.tree = ttk.Treeview(
            self,
            columns=("component", "status", "detail"),
            show="headings",
        )
        for key, title, width in (
            ("component", "Component / Device", 190),
            ("status", "Status", 100),
            ("detail", "Details", 650),
        ):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)

    def refresh(self):
        if str(self.check_button.cget("state")) == "disabled":
            return
        self.check_button.configure(state="disabled", text="Checking...")
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", values=("System", "CHECKING", "Please wait..."))

        def work():
            try:
                report = HealthService(self.app.app_config).report()
                error = None
            except Exception as exc:
                report = None
                error = exc
            self.after(0, lambda: self.checks_finished(report, error))

        threading.Thread(target=work, daemon=True).start()

    def checks_finished(self, report, error):
        self.check_button.configure(state="normal", text="Check All Devices")
        self.tree.delete(*self.tree.get_children())
        if error:
            self.tree.insert("", "end", values=("System", "ERROR", str(error)))
            return
        for check in report["checks"]:
            name = str(check["name"]).replace("_", " ").title()
            self.tree.insert(
                "",
                "end",
                values=(name, str(check["status"]).upper(), check["detail"]),
            )
