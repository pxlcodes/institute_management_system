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

    def get_unpaid_bills_for_student(
        self,
        student_id: int,
        exclude_bill_id: int | None = None,
        before_date: str | None = None,
        before_bill_id: int | None = None,
    ) -> list[DueBill]:
        sql = (
            self._select()
            + "WHERE e.student_id=? AND (b.total_amount - b.paid_amount) > 0 "
        )
        params = [student_id]
        if exclude_bill_id:
            sql += "AND b.id != ? "
            params.append(exclude_bill_id)
        if before_date:
            if before_bill_id:
                sql += "AND (b.issue_date < ? OR (b.issue_date = ? AND b.id < ?)) "
                params.extend([before_date, before_date, before_bill_id])
            else:
                sql += "AND b.issue_date <= ? "
                params.append(before_date)
        sql += "ORDER BY b.issue_date ASC, b.id ASC"
        return [self._model(row) for row in self.db.query(sql, tuple(params))]

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

    def record_multi_payment(
        self,
        bill_ids: list[int],
        amount: Decimal,
        discount: Decimal,
        payment_date: str,
        account_id: int | None,
        method: str,
        receipt_no: str,
        remarks: str = "",
        allow_advance: bool = True,
    ) -> dict[str, Any]:
        amount = Decimal(str(amount))
        discount = Decimal(str(discount))
        bill_ids = list(dict.fromkeys(bill_ids))
        if not bill_ids:
            raise ValueError("Select at least one bill.")
        if amount < 0 or discount < 0:
            raise ValueError("Payment and discount cannot be negative.")
        if amount + discount <= 0:
            raise ValueError("Enter a payment amount or discount.")
        if amount > 0 and not account_id:
            raise ValueError("Select a payment account.")

        def callback(conn):
            lock_clause = "" if conn.__class__.__module__.startswith("sqlite3") else " FOR UPDATE"
            placeholders = ",".join("?" for _ in bill_ids)
            query = (
                f"SELECT b.*, e.student_id, s.student_name FROM due_bills b "
                f"JOIN enrollments e ON e.id=b.enrollment_id "
                f"JOIN students s ON s.id=e.student_id "
                f"WHERE b.id IN ({placeholders})" + lock_clause
            )
            rows = conn.execute(query, tuple(bill_ids)).fetchall()
            if not rows:
                raise ValueError("No bills were found.")
            if len(rows) != len(bill_ids):
                raise ValueError("One or more selected bills were not found.")

            student_ids = {int(r["student_id"]) for r in rows}
            if len(student_ids) > 1:
                raise ValueError("All selected bills must belong to the same student.")

            # Sort chronologically by issue_date, then id
            rows = sorted(rows, key=lambda r: (str(r["issue_date"] or ""), int(r["id"])))
            student_id = int(rows[0]["student_id"])
            student_name = str(rows[0]["student_name"] or "")
            first_enrollment_id = int(rows[0]["enrollment_id"])

            total_remaining = sum(
                max(Decimal("0"), Decimal(str(r["total_amount"])) - Decimal(str(r["paid_amount"])))
                for r in rows
            )
            if total_remaining <= 0 and not allow_advance:
                raise ValueError("All selected bills are already paid.")
            if not allow_advance and (amount + discount > total_remaining):
                raise ValueError(
                    f"Payment plus discount cannot exceed the total remaining balance of {total_remaining:,.2f}."
                )

            rem_discount = discount
            rem_amount = amount
            transaction_ids: list[int] = []
            updated_bills: list[dict[str, Any]] = []

            for row in rows:
                b_total = Decimal(str(row["total_amount"]))
                b_paid = Decimal(str(row["paid_amount"]))
                b_rem = max(Decimal("0"), b_total - b_paid)
                if b_rem <= 0:
                    continue

                disc_alloc = min(rem_discount, b_rem)
                rem_discount -= disc_alloc
                b_rem -= disc_alloc

                pay_alloc = min(rem_amount, b_rem)
                rem_amount -= pay_alloc

                if disc_alloc > 0 or pay_alloc > 0:
                    new_paid = b_paid + pay_alloc
                    new_total = b_total - disc_alloc
                    status = "Paid" if new_paid >= new_total else "Partially Paid"
                    cursor = conn.execute(
                        "UPDATE due_bills SET paid_amount=?,discount=discount+?,"
                        "total_amount=?,status=? WHERE id=?",
                        (str(new_paid), str(disc_alloc), str(new_total), status, row["id"]),
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
                            str(pay_alloc), str(disc_alloc), account_id, method, receipt_no, remarks,
                        ),
                    )
                    t_id = int(cursor.lastrowid)
                    cursor.close()
                    transaction_ids.append(t_id)
                    updated_bills.append({
                        "bill_id": int(row["id"]),
                        "bill_number": str(row["bill_number"]),
                        "paid": pay_alloc,
                        "discount": disc_alloc,
                        "status": status,
                    })

            advance_amount = rem_amount
            if advance_amount > 0 and allow_advance:
                adv_particular = (
                    f"Advance fee payment (Surplus after settling {len(updated_bills)} bill(s))"
                    if updated_bills else "Advance fee payment"
                )
                cursor = conn.execute(
                    "INSERT INTO student_transactions "
                    "(student_id,enrollment_id,transaction_date,transaction_type,particular,"
                    "charge_amount,payment_amount,discount_amount,account_id,payment_method,"
                    "receipt_no,remarks) VALUES (?,?,?,'Payment Received',?,0,?,0,?,?,?,?)",
                    (
                        student_id, first_enrollment_id, payment_date, adv_particular,
                        str(advance_amount), account_id, method, receipt_no,
                        remarks or "Advance payment surplus",
                    ),
                )
                adv_t_id = int(cursor.lastrowid)
                cursor.close()
                transaction_ids.append(adv_t_id)

            if amount > 0:
                bill_refs = ", ".join(u["bill_number"] for u in updated_bills)
                if len(updated_bills) > 1:
                    ledger_part = f"Payment for {len(updated_bills)} bills ({bill_refs})"
                elif len(updated_bills) == 1:
                    ledger_part = f"Payment for bill {updated_bills[0]['bill_number']}"
                else:
                    ledger_part = "Advance fee payment"

                if advance_amount > 0 and updated_bills:
                    ledger_part += f" (incl. advance Rs. {advance_amount:,.2f})"

                self.db.add_ledger(
                    conn, payment_date, account_id, "IN", str(amount),
                    "Student Transaction", transaction_ids[0] if transaction_ids else 0,
                    ledger_part, receipt_no, remarks,
                )

            return {
                "student_id": student_id,
                "student_name": student_name,
                "transaction_ids": transaction_ids,
                "updated_bills": updated_bills,
                "total_paid": amount,
                "total_discount": discount,
                "advance_amount": advance_amount,
            }

        return self.db.transaction(callback)

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
        allow_advance: bool = True,
    ) -> int:
        result = self.record_multi_payment(
            [bill_id],
            amount,
            discount,
            payment_date,
            account_id,
            method,
            receipt_no,
            remarks,
            allow_advance=allow_advance,
        )
        return result["transaction_ids"][0] if result["transaction_ids"] else 0

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
