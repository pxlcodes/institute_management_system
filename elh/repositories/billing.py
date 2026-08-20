from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from elh.models import DueBill


class BillingRepository:
    def __init__(self, db):
        self.db = db

    def find(self, enrollment_id: int, period: str):
        row = self.db.query_one(
            self._select() + "WHERE b.enrollment_id=? AND b.billing_period=?",
            (enrollment_id, period),
        )
        return self._model(row) if row else None

    def get(self, bill_id: int):
        row = self.db.query_one(self._select() + "WHERE b.id=?", (bill_id,))
        return self._model(row) if row else None

    def get_many(self, bill_ids: list[int]) -> dict[int, DueBill]:
        if not bill_ids:
            return {}
        placeholders = ",".join("?" for _ in bill_ids)
        rows = self.db.query(
            self._select() + f"WHERE b.id IN ({placeholders})", tuple(bill_ids)
        )
        return {int(row["id"]): self._model(row) for row in rows}

    def find_by_month(self, enrollment_id: int, month: str):
        row = self.db.query_one(
            self._select()
            + "JOIN due_bill_items bi ON bi.bill_id=b.id "
            + "WHERE b.enrollment_id=? AND bi.billing_month=?",
            (enrollment_id, month),
        )
        return self._model(row) if row else self.find(enrollment_id, month)

    def list(self):
        return [
            self._model(row)
            for row in self.db.query(
                self._select() + "ORDER BY b.issue_date DESC,b.id DESC"
            )
        ]

    def enrollment(self, enrollment_id: int):
        return self.db.query_one(
            self._enrollment_select() + "WHERE e.id=?", (enrollment_id,)
        )

    def enrollments(self, enrollment_ids: list[int]) -> dict[int, dict]:
        if not enrollment_ids:
            return {}
        placeholders = ",".join("?" for _ in enrollment_ids)
        rows = self.db.query(
            self._enrollment_select() + f"WHERE e.id IN ({placeholders})",
            tuple(enrollment_ids),
        )
        return {int(row["id"]): row for row in rows}

    def count_for_enrollment(self, enrollment_id: int) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) total FROM due_bills WHERE enrollment_id=?",
            (enrollment_id,),
        )
        return int(row["total"])

    def bill_counts(self, enrollment_ids: list[int]) -> dict[int, int]:
        if not enrollment_ids:
            return {}
        placeholders = ",".join("?" for _ in enrollment_ids)
        rows = self.db.query(
            "SELECT enrollment_id,COUNT(*) total FROM due_bills "
            f"WHERE enrollment_id IN ({placeholders}) GROUP BY enrollment_id",
            tuple(enrollment_ids),
        )
        return {int(row["enrollment_id"]): int(row["total"]) for row in rows}

    def create(self, values) -> int:
        values = tuple(str(value) if isinstance(value, Decimal) else value for value in values)
        return self.db.execute(
            "INSERT INTO due_bills "
            "(bill_number,enrollment_id,billing_period,issue_date,due_date,subtotal,"
            "discount,total_amount,status,remarks) "
            "VALUES (?,?,?,?,?,?,?,?,'Due',?)",
            values,
        )

    def billed_months(self, enrollment_id: int, months: list[str]) -> set[str]:
        mapping = self.billed_months_many([enrollment_id], months)
        return set(mapping.get(enrollment_id, {}))

    def billed_months_many(
        self, enrollment_ids: list[int], months: list[str]
    ) -> dict[int, dict[str, int]]:
        if not enrollment_ids or not months:
            return {}
        enrollment_placeholders = ",".join("?" for _ in enrollment_ids)
        month_placeholders = ",".join("?" for _ in months)
        params = (*enrollment_ids, *months)
        rows = self.db.query(
            "SELECT b.enrollment_id,bi.billing_month,b.id bill_id FROM due_bills b "
            "JOIN due_bill_items bi ON bi.bill_id=b.id "
            f"WHERE b.enrollment_id IN ({enrollment_placeholders}) "
            f"AND bi.billing_month IN ({month_placeholders})",
            params,
        )
        legacy = self.db.query(
            "SELECT enrollment_id,billing_period billing_month,id bill_id FROM due_bills "
            f"WHERE enrollment_id IN ({enrollment_placeholders}) "
            f"AND billing_period IN ({month_placeholders})",
            params,
        )
        result: dict[int, dict[str, int]] = defaultdict(dict)
        for row in (*rows, *legacy):
            result[int(row["enrollment_id"])][row["billing_month"]] = int(row["bill_id"])
        return dict(result)

    def create_combined(
        self,
        header_values,
        months: list[str],
        monthly_amount: Decimal,
    ) -> int:
        return self.create_combined_many(
            [(header_values, months, monthly_amount)]
        )[0]

    def create_combined_many(self, specs: list[tuple]) -> list[int]:
        def callback(conn):
            bill_ids: list[int] = []
            for header_values, months, monthly_amount in specs:
                cursor = conn.execute(
                    "INSERT INTO due_bills "
                    "(bill_number,enrollment_id,billing_period,issue_date,due_date,"
                    "subtotal,discount,total_amount,status,remarks) "
                    "VALUES (?,?,?,?,?,?,?,?,'Due',?)",
                    tuple(
                        str(value) if isinstance(value, Decimal) else value
                        for value in header_values
                    ),
                )
                bill_id = int(cursor.lastrowid)
                cursor.close()
                item_values = [
                    (bill_id, month, f"Course fee for {month}", str(monthly_amount))
                    for month in months
                ]
                cursor = conn.executemany(
                    "INSERT INTO due_bill_items "
                    "(bill_id,billing_month,description,amount) VALUES (?,?,?,?)",
                    item_values,
                )
                cursor.close()
                bill_ids.append(bill_id)
            return bill_ids

        return self.db.transaction(callback)

    def set_pdf(self, bill_id: int, path: str):
        self.db.execute("UPDATE due_bills SET pdf_path=? WHERE id=?", (path, bill_id))

    def student_contact(self, bill_id: int) -> str:
        row = self.db.query_one(
            "SELECT s.contact FROM due_bills b "
            "JOIN enrollments e ON e.id=b.enrollment_id "
            "JOIN students s ON s.id=e.student_id WHERE b.id=?",
            (bill_id,),
        )
        return str(row["contact"] or "") if row else ""

    def mark_pos_printed(self, bill_id: int):
        self.db.execute(
            "UPDATE due_bills SET pos_printed_at=CURRENT_TIMESTAMP WHERE id=?",
            (bill_id,),
        )

    def record_payment(
        self,
        bill_id: int,
        amount: Decimal,
        discount: Decimal,
        payment_date: str,
        account_id: int | None,
        method: str,
        receipt_no: str,
        remarks: str = "",
    ):
        amount = Decimal(str(amount))
        discount = Decimal(str(discount))

        def callback(conn):
            lock_clause = "" if conn.__class__.__module__.startswith("sqlite3") else " FOR UPDATE"
            row = conn.execute(
                "SELECT b.*,e.student_id FROM due_bills b "
                "JOIN enrollments e ON e.id=b.enrollment_id WHERE b.id=?" + lock_clause,
                (bill_id,),
            ).fetchone()
            if not row:
                raise ValueError("Bill was not found.")
            total = Decimal(str(row["total_amount"]))
            paid = Decimal(str(row["paid_amount"]))
            remaining = total - paid
            if remaining <= 0:
                raise ValueError("This bill is already paid.")
            if amount < 0 or discount < 0:
                raise ValueError("Payment and discount cannot be negative.")
            if amount + discount <= 0:
                raise ValueError("Enter a payment amount or discount.")
            if amount + discount > remaining:
                raise ValueError(
                    f"Payment plus discount cannot exceed the remaining balance of {remaining:,.2f}."
                )
            if amount > 0 and not account_id:
                raise ValueError("Select a payment account.")

            new_paid = paid + amount
            new_total = total - discount
            status = "Paid" if new_paid >= new_total else "Partially Paid"
            cursor = conn.execute(
                "UPDATE due_bills SET paid_amount=?,discount=discount+?,"
                "total_amount=?,status=? WHERE id=?",
                (str(new_paid), str(discount), str(new_total), status, bill_id),
            )
            cursor.close()
            particular = f"Payment for bill {row['bill_number']}"
            cursor = conn.execute(
                "INSERT INTO student_transactions "
                "(student_id,enrollment_id,transaction_date,transaction_type,particular,"
                "charge_amount,payment_amount,discount_amount,account_id,payment_method,"
                "receipt_no,remarks) VALUES (?,?,?,'Payment Received',?,0,?,?,?,?,?,?)",
                (
                    row["student_id"], row["enrollment_id"], payment_date, particular,
                    str(amount), str(discount), account_id, method, receipt_no, remarks,
                ),
            )
            transaction_id = int(cursor.lastrowid)
            cursor.close()
            if amount > 0:
                self.db.add_ledger(
                    conn, payment_date, account_id, "IN", str(amount),
                    "Student Transaction", transaction_id, particular,
                    receipt_no, remarks,
                )

            return transaction_id

        return self.db.transaction(callback)

    @staticmethod
    def _enrollment_select() -> str:
        return (
            "SELECT e.*,s.student_name,c.course_name,c.billing_type FROM enrollments e "
            "JOIN students s ON s.id=e.student_id "
            "JOIN courses c ON c.id=e.course_id "
        )

    @staticmethod
    def _select() -> str:
        return (
            "SELECT b.*,e.student_id,e.course_id,s.student_name,c.course_name "
            "FROM due_bills b JOIN enrollments e ON e.id=b.enrollment_id "
            "JOIN students s ON s.id=e.student_id "
            "JOIN courses c ON c.id=e.course_id "
        )

    @staticmethod
    def _model(row) -> DueBill:
        return DueBill(
            int(row["id"]), row["bill_number"], int(row["enrollment_id"]),
            int(row["student_id"]), row["student_name"], row["course_name"],
            row["billing_period"], row["issue_date"], row["due_date"],
            Decimal(str(row["subtotal"])), Decimal(str(row["discount"])),
            Decimal(str(row["total_amount"])), Decimal(str(row["paid_amount"])),
            row["status"], row["pdf_path"] or "",
        )
