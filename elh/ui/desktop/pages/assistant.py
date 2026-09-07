from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from elh.services.assistant import AssistantResponse, InstituteAssistant
from elh.ui.desktop.components import BasePage

if TYPE_CHECKING:
    from elh.ui.desktop.app import ManagementApp


class AssistantPage(BasePage):
    """Modern, high-density AI Assistant and Interactive Institute Query Console."""

    def __init__(self, parent: tk.Widget, app: "ManagementApp"):
        super().__init__(parent, app)
        self.assistant = InstituteAssistant(app.services, app.db)
        self.history: list[str] = []
        self.history_index: int = -1

        self._build_ui()
        self._print_welcome()

    def _build_ui(self):
        self.configure(style="TFrame")

        # 1. Top Header Bar
        header = ttk.Frame(self, style="Header.TFrame", padding=(12, 10))
        header.pack(fill="x", pady=(0, 10))

        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.pack(side="left")

        ttk.Label(
            title_box,
            text="🤖 AI Assistant & Institute Query Console",
            style="Title.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            title_box,
            text="Interactive natural language queries, instant student lookups, live fee summaries, and diagnostics.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # Read-Only Safety Badge on top right
        safety_badge = ttk.Label(
            header,
            text="🔒 Safe Read-Only Mode (Zero Data Mutation)",
            style="Badge.TLabel",
        )
        safety_badge.pack(side="right", padx=6)

        # 2. Main Body Split: Left Quick Prompts Sidebar + Right Terminal Console
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        # Sidebar (210px width)
        sidebar = ttk.LabelFrame(body, text="Quick Commands", style="Form.TLabelframe", padding=8)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.configure(width=220)

        quick_actions = [
            ("📊 Institute Overview", "/stats"),
            ("👥 Absent Today", "/absent"),
            ("🕒 Present Today", "/present"),
            ("💰 Top Fee Dues", "/dues"),
            ("🏦 Account Balances", "/accounts"),
            ("📚 Course Catalog", "/courses"),
            ("👨‍🏫 Staff Directory", "/staff"),
            ("🩺 System Health", "/health"),
            ("⏱️ Poller Telemetry", "/poller"),
            ("❔ Command Palette", "/help"),
        ]

        for label, cmd in quick_actions:
            btn = ttk.Button(
                sidebar,
                text=label,
                style="Toolbar.TButton",
                command=lambda c=cmd: self._run_prompt(c),
            )
            btn.pack(fill="x", pady=2)

        ttk.Separator(sidebar).pack(fill="x", pady=8)

        clear_btn = ttk.Button(
            sidebar,
            text="🗑️ Clear Console",
            style="Toolbar.TButton",
            command=self._clear_console,
        )
        clear_btn.pack(fill="x", pady=2)

        # Right Terminal Workspace
        workspace = ttk.Frame(body)
        workspace.pack(side="left", fill="both", expand=True)

        # Terminal Console Box
        console_frame = tk.Frame(workspace, bg="#181825", bd=1, relief="solid", highlightbackground="#313244", highlightthickness=1)
        console_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.console = tk.Text(
            console_frame,
            bg="#14141E",
            fg="#CDD6F4",
            insertbackground="#89B4FA",
            font=("Consolas", 10),
            padx=12,
            pady=12,
            wrap="word",
            bd=0,
            highlightthickness=0,
        )
        scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.console.pack(side="left", fill="both", expand=True)

        # Text Highlighting Tags
        self.console.tag_configure("timestamp", foreground="#6C7086")
        self.console.tag_configure("user_tag", foreground="#F38BA8", font=("Consolas", 10, "bold"))
        self.console.tag_configure("user_prompt", foreground="#FFFFFF", font=("Consolas", 10, "bold"))
        self.console.tag_configure("assistant_tag", foreground="#89B4FA", font=("Consolas", 10, "bold"))
        self.console.tag_configure("badge", foreground="#11111B", background="#A6E3A1", font=("Consolas", 9, "bold"))
        self.console.tag_configure("table_header", foreground="#89B4FA", font=("Consolas", 10, "bold"))
        self.console.tag_configure("success", foreground="#A6E3A1")
        self.console.tag_configure("error", foreground="#F38BA8")
        self.console.tag_configure("hint", foreground="#CBA6F7")

        # Lower Input & Action Panel
        input_panel = ttk.Frame(workspace, style="Form.TFrame", padding=6)
        input_panel.pack(fill="x")

        self.input_entry = ttk.Entry(input_panel, font=("Segoe UI", 10))
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_entry.bind("<Return>", lambda _e: self._submit_entry())
        self.input_entry.bind("<Up>", self._history_up)
        self.input_entry.bind("<Down>", self._history_down)

        self.exec_button = ttk.Button(
            input_panel,
            text="Ask Assistant ⚡",
            style="Accent.TButton",
            command=self._submit_entry,
        )
        self.exec_button.pack(side="right")

    def _print_welcome(self):
        welcome = (
            "========================================================================================\n"
            "⚡ ELH Management System — AI Assistant & Interactive Query Console [v2.5 Pro]\n"
            "   Database: Active Live Connection  ·  Safe Mode: READ-ONLY (Zero Mutation Guarantee)\n"
            "========================================================================================\n"
            "Type natural questions (e.g. \"Who is absent today?\", \"Show top fee dues\") or slash commands.\n"
            "Type /help for command shortcuts.\n\n"
        )
        self.console.insert("end", welcome, "hint")
        self.console.see("end")

    def _clear_console(self):
        self.console.delete("1.0", "end")
        self._print_welcome()

    def _run_prompt(self, prompt: str):
        self.input_entry.delete(0, "end")
        self.input_entry.insert(0, prompt)
        self._submit_entry()

    def _submit_entry(self):
        query = self.input_entry.get().strip()
        if not query:
            return

        self.input_entry.delete(0, "end")
        self.history.append(query)
        self.history_index = len(self.history)

        timestamp = time.strftime("%H:%M:%S")

        # Echo User Query
        self.console.insert("end", f"[{timestamp}] ", "timestamp")
        self.console.insert("end", "user@elh:~$ ", "user_tag")
        self.console.insert("end", f"{query}\n", "user_prompt")

        if getattr(self.app, "session", None) and self.app.session.role not in ("super_admin", "admin"):
            self.console.insert("end", "❌ Access Denied: The AI Assistant is only available for Administrator accounts.\n\n", "error")
            self.console.see("end")
            return

        # Execute read-only assistant query
        try:
            resp: AssistantResponse = self.assistant.execute(query)
            self._render_response(resp)
        except Exception as exc:
            self.console.insert("end", f"❌ Error executing query: {exc}\n\n", "error")

        self.console.see("end")

    def _render_response(self, resp: AssistantResponse):
        # Badge line
        self.console.insert("end", f"🤖 [{resp.title}] ", "assistant_tag")
        if resp.badge:
            self.console.insert("end", f" {resp.badge} \n", "badge")
        else:
            self.console.insert("end", "\n")

        self.console.insert("end", f"{resp.content}\n\n")

        if resp.suggested_actions:
            self.console.insert("end", "Suggested next actions: ", "timestamp")
            self.console.insert("end", ", ".join(resp.suggested_actions) + "\n\n", "hint")

    def _history_up(self, _event):
        if not self.history:
            return
        if self.history_index > 0:
            self.history_index -= 1
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, self.history[self.history_index])

    def _history_down(self, _event):
        if not self.history:
            return
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, self.history[self.history_index])
        else:
            self.history_index = len(self.history)
            self.input_entry.delete(0, "end")

    def refresh(self):
        """Called automatically when switching to this page."""
        pass
