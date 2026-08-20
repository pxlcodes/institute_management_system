"""Small formatting/validation helpers shared by desktop pages."""

from __future__ import annotations

from typing import Any

from elh.config import load_config
from elh.core import validation


def today_iso() -> str:
    return validation.today_iso()


def current_month() -> str:
    return validation.current_month()


def add_days(value: str, days: int) -> str:
    return validation.add_days(value, days)


def validate_month(value: str, field_name: str = "Month") -> str:
    return validation.validate_month(value, field_name)


def parse_amount(value: str, field_name: str = "Amount", allow_zero: bool = True) -> float:
    return validation.parse_amount(value, field_name, allow_zero)


def validate_date(value: str, field_name: str = "Date", allow_blank: bool = False) -> str:
    return validation.validate_date(value, field_name, allow_blank, load_config().date_format)


def normalize_phone(value: str) -> str:
    return validation.normalize_phone(value)


def money(value: Any) -> str:
    return validation.money(value)


def hash_password(password: str) -> str:
    return validation.hash_password(password)
