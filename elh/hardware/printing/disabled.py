from .base import ReceiptPrinterError


class DisabledReceiptPrinter:
    def print_receipt(self, receipt) -> None:
        raise ReceiptPrinterError("POS printer integration is disabled.")

    def health(self) -> tuple[bool, str]:
        return True, "POS printer integration disabled"


class UnavailableReceiptPrinter:
    """Non-fatal adapter for incomplete or invalid printer configuration."""

    def __init__(self, reason: str):
        self.reason = reason

    def print_receipt(self, receipt) -> None:
        raise ReceiptPrinterError(self.reason)

    def health(self) -> tuple[bool, str]:
        return False, self.reason
