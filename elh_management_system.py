"""Backward-compatible import; new code should import from ``elh.ui.desktop``."""

from elh.ui.desktop import ManagementApp, main

__all__ = ["ManagementApp", "main"]
