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

# Account helpers/mixins
# ---------------------------------------------------------------------------

class AccountSelectionMixin:
    account_map: dict[str, int]

    def load_accounts_into(self, combo: ttk.Combobox) -> None:
        rows = self.db.query(
            "SELECT id, account_name FROM accounts WHERE status='Active' ORDER BY account_name"
        )
        self.account_map = {f"{r['id']} - {r['account_name']}": r["id"] for r in rows}
        combo["values"] = list(self.account_map)

    def selected_account_id(self, value: str) -> int:
        account_id = self.account_map.get(value)
        if not account_id:
            raise ValueError("Please select an account.")
        return account_id

    def require_sufficient_balance(self, account_id: int, amount: float) -> None:
        if self.app.app_config.allow_negative_balance:
            return
        balance = self.db.account_balance(account_id)
        if balance < amount:
            raise ValueError(
                f"Insufficient account balance. Available: {money(balance)}"
            )


# ---------------------------------------------------------------------------
# Student Transactions

