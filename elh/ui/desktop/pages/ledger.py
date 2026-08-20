from __future__ import annotations

import csv
import sqlite3
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Iterable, Optional

from elh.models import Student
from elh.ui.desktop.helpers import money, normalize_phone, parse_amount, today_iso, validate_date
from elh.ui.desktop.components import BasePage, CrudPage, FormBuilder, ScrollableFrame

# Ledger
# ---------------------------------------------------------------------------

class LedgerPage(CrudPage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="Central Account Ledger", style="Title.TLabel").pack(anchor="w")
        area = ttk.Frame(self)
        area.pack(fill="both", expand=True, pady=8)
        self.tree = self.make_tree(
            area,
            [
                ("id", "ID", 50), ("date", "Date", 95), ("account", "Account", 160),
                ("direction", "Direction", 75), ("amount", "Amount", 100),
                ("source", "Source", 130), ("particular", "Particular", 200),
                ("reference", "Reference", 110),
            ],
        )

    def refresh(self):
        self.clear_tree(self.tree)
        rows = self.db.query(
            """
            SELECT l.*, a.account_name
            FROM ledger l JOIN accounts a ON a.id=l.account_id
            ORDER BY l.transaction_date DESC, l.id DESC
            """
        )
        for r in rows:
            self.tree.insert(
                "", "end",
                values=(r["id"], r["transaction_date"], r["account_name"], r["direction"],
                        money(r["amount"]), r["source_type"], r["particular"], r["reference_no"])
            )


# ---------------------------------------------------------------------------
# App shell

