from __future__ import annotations

from elh.hardware.printing.base import ReceiptPrinter
from elh.models import Receipt


class PrintingService:
    def __init__(self, printer: ReceiptPrinter):
        self.printer = printer

    def print_receipt(self, receipt: Receipt) -> None:
        if not receipt.lines:
            raise ValueError("Cannot print an empty receipt.")
        self.printer.print_receipt(receipt)
