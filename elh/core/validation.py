from __future__ import annotations

import hashlib
from datetime import timedelta
import nepali_datetime as nepali
from typing import Any


def today_iso() -> str:
    return nepali.date.today().strftime("%Y/%m/%d")


def current_month() -> str:
    return nepali.date.today().strftime("%Y/%m")


def add_days(value: str, days: int) -> str:
    parsed = parse_nepali_date(value)
    converted = parsed.to_datetime_date() + timedelta(days=days)
    return nepali.date.from_datetime_date(converted).strftime("%Y/%m/%d")


def parse_nepali_date(value: str) -> nepali.date:
    try:
        year, month, day = (int(part) for part in value.strip().split("/"))
        return nepali.date(year, month, day)
    except (ValueError, TypeError) as exc:
        raise ValueError("Date must be a valid Nepali date using YYYY/MM/DD format.") from exc


def validate_month(value: str, field_name: str = "Month") -> str:
    cleaned = value.strip()
    try:
        year, month = (int(part) for part in cleaned.split("/"))
        nepali.date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must use Nepali YYYY/MM format.") from exc
    return f"{year:04d}/{month:02d}"


def parse_amount(value: str, field_name: str = "Amount", allow_zero: bool = True) -> float:
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    try:
        amount = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc
    if amount < 0 or (not allow_zero and amount == 0):
        rule = "greater than zero" if not allow_zero else "zero or greater"
        raise ValueError(f"{field_name} must be {rule}.")
    return round(amount, 2)


def validate_date(value: str, field_name: str = "Date", allow_blank: bool = False, date_format: str = "%Y/%m/%d") -> str:
    cleaned = value.strip()
    if allow_blank and not cleaned:
        return ""
    try:
        parse_nepali_date(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use a valid Nepali YYYY/MM/DD date.") from exc
    return cleaned


def normalize_phone(value: str) -> str:
    cleaned = value.strip()
    if cleaned and not cleaned.replace("+", "", 1).isdigit():
        raise ValueError("Contact number may contain digits and an optional leading + only.")
    return cleaned


def money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()
