from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from elh.core.validation import validate_date, validate_month
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
        enforce_fifo: bool = True,
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

            student_id = int(rows[0]["student_id"])
            student_name = str(rows[0]["student_name"] or "")
            first_enrollment_id = int(rows[0]["enrollment_id"])

            if enforce_fifo:
                earliest_period = min(str(r["billing_period"] or "") for r in rows)
                earliest_id = min(int(r["id"]) for r in rows)
                older_query = (
                    f"SELECT b.*, e.student_id, s.student_name FROM due_bills b "
                    f"JOIN enrollments e ON e.id=b.enrollment_id "
                    f"JOIN students s ON s.id=e.student_id "
                    f"WHERE e.student_id=? AND b.status<>'Paid' "
                    f"AND (b.total_amount - b.paid_amount) > 0 "
                    f"AND b.id NOT IN ({placeholders}) "
                    f"AND (b.billing_period < ? OR (b.billing_period = ? AND b.id < ?))"
                    + lock_clause
                )
                older_rows = conn.execute(
                    older_query,
                    (student_id, *bill_ids, earliest_period, earliest_period, earliest_id)
                ).fetchall()
                if older_rows:
                    rows = list(older_rows) + list(rows)

            # Sort chronologically by billing_period, then issue_date, then id
            rows = sorted(rows, key=lambda r: (str(r["billing_period"] or ""), str(r["issue_date"] or ""), int(r["id"])))

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
            "SELECT b.*,e.student_id,e.course_id,s.student_name,s.contact,c.course_name, "
            "COALESCE(cl.level_name, s.class_name, '') AS class_name "
            "FROM due_bills b JOIN enrollments e ON e.id=b.enrollment_id "
            "JOIN students s ON s.id=e.student_id "
            "LEFT JOIN class_levels cl ON cl.id=s.class_level_id "
            "JOIN courses c ON c.id=e.course_id "
        )

    @staticmethod
    def _model(row) -> DueBill:
        contact_val = ""
        try:
            contact_val = str(row["contact"] or "")
        except (KeyError, IndexError):
            pass
        class_name_val = ""
        try:
            class_name_val = str(row["class_name"] or "")
        except (KeyError, IndexError):
            pass
        remarks_val = ""
        try:
            remarks_val = str(row["remarks"] or "")
        except (KeyError, IndexError):
            pass
        return DueBill(
            int(row["id"]), row["bill_number"], int(row["enrollment_id"]),
            int(row["student_id"]), row["student_name"], row["course_name"],
            row["billing_period"], row["issue_date"], row["due_date"],
            Decimal(str(row["subtotal"])), Decimal(str(row["discount"])),
            Decimal(str(row["total_amount"])), Decimal(str(row["paid_amount"])),
            row["status"], row["pdf_path"] or "",
            contact_val,
            class_name_val,
            remarks_val,
        )

    def update_bill(
        self,
        bill_id: int,
        billing_period: str,
        issue_date: str,
        due_date: str,
        subtotal: Decimal,
        discount: Decimal,
        remarks: str = "",
    ) -> DueBill:
        """Update billing dates, amounts, and remarks on an existing due bill."""
        def callback(conn):
            bill = self.get(bill_id)
            if not bill:
                raise ValueError(f"Due bill #{bill_id} does not exist.")

            period_clean = validate_month(billing_period, "Billing period")
            issue_clean = validate_date(issue_date, "Issue date")
            due_clean = validate_date(due_date, "Due date")

            sub_val = Decimal(str(subtotal or 0))
            disc_val = Decimal(str(discount or 0))
            if sub_val < 0:
                raise ValueError("Subtotal cannot be negative.")
            if disc_val < 0:
                raise ValueError("Discount cannot be negative.")

            total_val = max(Decimal("0"), sub_val - disc_val)
            paid_val = Decimal(str(bill.paid_amount or 0))

            if paid_val >= total_val and total_val > 0:
                status = "Paid"
            elif paid_val > 0:
                status = "Partially Paid"
            else:
                status = "Due"

            # Check if another bill already exists for this enrollment & period
            if period_clean != bill.billing_period:
                existing = conn.execute(
                    "SELECT id FROM due_bills WHERE enrollment_id = ? AND billing_period = ? AND id != ?",
                    (bill.enrollment_id, period_clean, bill_id)
                ).fetchone()
                if existing:
                    raise ValueError(f"Enrollment already has another bill for {period_clean} (Bill #{existing['id']}).")

            m_slug = period_clean.replace("/", "-")
            new_bill_number = f"ELH-{bill.enrollment_id}-{m_slug}-{m_slug}"

            conn.execute(
                """
                UPDATE due_bills 
                SET bill_number = ?, billing_period = ?, issue_date = ?, due_date = ?,
                    subtotal = ?, discount = ?, total_amount = ?, status = ?, remarks = ?
                WHERE id = ?
                """,
                (
                    new_bill_number, period_clean, issue_clean, due_clean,
                    str(sub_val), str(disc_val), str(total_val), status, remarks, bill_id
                ),
            )

            # Synchronize child line item in due_bill_items
            item = conn.execute("SELECT id FROM due_bill_items WHERE bill_id = ?", (bill_id,)).fetchone()
            if item:
                conn.execute(
                    "UPDATE due_bill_items SET billing_month = ?, amount = ?, description = ? WHERE id = ?",
                    (period_clean, str(sub_val), f"Course fee for {period_clean}", int(item["id"]))
                )
            else:
                conn.execute(
                    "INSERT INTO due_bill_items (bill_id, billing_month, description, amount) VALUES (?, ?, ?, ?)",
                    (bill_id, period_clean, f"Course fee for {period_clean}", str(sub_val))
                )

            return True

        self.db.transaction(callback)
        return self.get(bill_id)

    def delete_bill(
        self,
        bill_id: int,
        actor_username: str = "admin",
        actor_user_id: int | None = None,
        force_paid: bool = False,
    ) -> dict[str, Any]:
        """Safely delete a due bill.
        If paid_amount > 0 and force_paid is True, automatically reverts and deletes
        associated payment transactions and ledger entries, adjusts account balances,
        removes the bill and items, reconciles remaining bills in FIFO order, and logs an audit record.
        """
        def callback(conn):
            bill_row = conn.execute(
                "SELECT b.*, e.student_id FROM due_bills b "
                "LEFT JOIN enrollments e ON e.id = b.enrollment_id "
                "WHERE b.id = ?",
                (bill_id,)
            ).fetchone()
            if not bill_row:
                raise ValueError(f"Bill #{bill_id} was not found.")

            bill_num = str(bill_row["bill_number"])
            student_id = int(bill_row["student_id"]) if "student_id" in bill_row.keys() and bill_row["student_id"] else None
            if not student_id and bill_row["enrollment_id"]:
                erow = conn.execute("SELECT student_id FROM enrollments WHERE id = ?", (bill_row["enrollment_id"],)).fetchone()
                if erow:
                    student_id = int(erow["student_id"])

            paid_amount = Decimal(str(bill_row["paid_amount"] or 0))
            total_amount = Decimal(str(bill_row["total_amount"] or 0))

            reverted_payments = []
            if paid_amount > Decimal("0"):
                if not force_paid:
                    raise ValueError(f"Cannot delete bill {bill_num} because it has recorded payments of Rs. {paid_amount}.")

                # Find all transactions associated with this bill
                txns = conn.execute(
                    "SELECT * FROM student_transactions WHERE (particular LIKE ? OR particular LIKE ?)",
                    (f"%{bill_num}%", f"%bill {bill_num}%")
                ).fetchall()

                # Fallback if particular didn't explicitly name the bill
                if not txns and student_id:
                    txns = conn.execute(
                        "SELECT * FROM student_transactions WHERE student_id = ? AND enrollment_id = ? AND payment_amount > 0",
                        (student_id, bill_row["enrollment_id"])
                    ).fetchall()

                for txn in txns:
                    t_id = int(txn["id"])
                    t_pay = Decimal(str(txn["payment_amount"] or 0))
                    t_disc = Decimal(str(txn["discount_amount"] or 0))
                    t_acc = int(txn["account_id"]) if txn["account_id"] else None
                    t_rec = str(txn["receipt_no"] or "").strip()
                    t_date = str(txn["transaction_date"] or "")

                    # 1. Reverse ledger entry
                    if t_pay > 0 and t_acc:
                        l_row = conn.execute(
                            "SELECT id, amount FROM ledger WHERE source_type = 'Student Transaction' AND source_id = ?",
                            (t_id,)
                        ).fetchone()
                        if not l_row and t_rec:
                            l_row = conn.execute(
                                "SELECT id, amount FROM ledger WHERE source_type = 'Student Transaction' "
                                "AND account_id = ? AND transaction_date = ? AND reference_no = ? AND direction = 'IN'",
                                (t_acc, t_date, t_rec)
                            ).fetchone()
                        if not l_row:
                            l_row = conn.execute(
                                "SELECT id, amount FROM ledger WHERE source_type = 'Student Transaction' "
                                "AND account_id = ? AND transaction_date = ? AND direction = 'IN' AND amount >= ? "
                                "ORDER BY id DESC LIMIT 1",
                                (t_acc, t_date, str(t_pay))
                            ).fetchone()
                        if l_row:
                            l_id = int(l_row["id"])
                            l_amt = Decimal(str(l_row["amount"]))
                            if l_amt <= t_pay:
                                conn.execute("DELETE FROM ledger WHERE id = ?", (l_id,))
                            else:
                                conn.execute("UPDATE ledger SET amount = ? WHERE id = ?", (str(l_amt - t_pay), l_id))
                        try:
                            conn.execute(
                                "UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?",
                                (str(t_pay), t_acc)
                            )
                        except Exception:
                            pass

                    # 2. Delete student transaction and SMS delivery logs
                    conn.execute("DELETE FROM student_transactions WHERE id = ?", (t_id,))
                    conn.execute(
                        "DELETE FROM sms_delivery_log WHERE entity_type IN ('student_transaction', 'bill_payment') AND entity_id = ?",
                        (t_id,)
                    )
                    reverted_payments.append({
                        "transaction_id": t_id,
                        "payment_amount": float(t_pay),
                        "discount_amount": float(t_disc),
                    })

            # 3. Delete bill items and the due bill itself
            conn.execute("DELETE FROM due_bill_items WHERE bill_id = ?", (bill_id,))
            conn.execute("DELETE FROM due_bills WHERE id = ?", (bill_id,))

            # 4. Reconcile remaining bills for the student in chronological FIFO order
            if student_id:
                self._reconcile_fifo_on_conn(conn, student_id)

            # 5. Administrative audit trail
            audit_detail = (
                f"Deleted bill #{bill_num} (ID #{bill_id}): Total Rs. {total_amount:,.2f}, "
                f"Paid Rs. {paid_amount:,.2f}, Reverted {len(reverted_payments)} payment transaction(s) for Student ID #{student_id}"
            )
            try:
                conn.execute(
                    "INSERT INTO auth_audit_log (user_id, username, event_type, success, detail) VALUES (?, ?, 'bill.delete', 1, ?)",
                    (actor_user_id, actor_username, audit_detail),
                )
            except Exception:
                try:
                    conn.execute(
                        "INSERT INTO auth_audit_log (username, event_type, success, detail) VALUES (?, 'bill.delete', 1, ?)",
                        (actor_username, audit_detail),
                    )
                except Exception:
                    pass

            return {
                "success": True,
                "bill_id": bill_id,
                "bill_number": bill_num,
                "student_id": student_id,
                "deleted_paid_amount": float(paid_amount),
                "reverted_payments": reverted_payments,
                "message": f"Bill #{bill_num} {'(and its associated payments/ledgers) ' if paid_amount > 0 else ''}was successfully deleted.",
            }

        return self.db.transaction(callback)

    def delete_payment(
        self,
        transaction_id: int,
        actor_username: str = "admin",
        actor_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Safely delete a payment record, reverting its effect on due bills, ledger, and student balances."""
        def callback(conn):
            txn = conn.execute(
                "SELECT * FROM student_transactions WHERE id = ?",
                (transaction_id,)
            ).fetchone()
            if not txn:
                raise ValueError(f"Payment record #{transaction_id} was not found.")

            student_id = int(txn["student_id"])
            enrollment_id = int(txn["enrollment_id"]) if txn["enrollment_id"] else None
            pay_amount = Decimal(str(txn["payment_amount"] or 0))
            disc_amount = Decimal(str(txn["discount_amount"] or 0))
            account_id = int(txn["account_id"]) if txn["account_id"] else None
            particular = str(txn["particular"] or "")
            receipt_no = str(txn["receipt_no"] or "").strip()
            payment_date = str(txn["transaction_date"] or "")

            updated_bills = []

            # 1. Determine which bill(s) to revert
            target_bill = None
            bill_match = re.search(r"bill\s+([A-Za-z0-9\-_/]+)", particular, re.IGNORECASE)
            if bill_match:
                bill_num = bill_match.group(1).strip()
                target_bill = conn.execute(
                    "SELECT b.* FROM due_bills b "
                    "JOIN enrollments e ON e.id = b.enrollment_id "
                    "WHERE b.bill_number = ? AND e.student_id = ?",
                    (bill_num, student_id)
                ).fetchone()
                if not target_bill:
                    target_bill = conn.execute(
                        "SELECT * FROM due_bills WHERE bill_number = ?",
                        (bill_num,)
                    ).fetchone()

            if target_bill:
                b_id = int(target_bill["id"])
                b_paid = Decimal(str(target_bill["paid_amount"] or 0))
                b_disc = Decimal(str(target_bill["discount"] or 0))
                b_total = Decimal(str(target_bill["total_amount"] or 0))

                revert_pay = min(b_paid, pay_amount)
                revert_disc = min(b_disc, disc_amount)
                new_paid = max(Decimal("0"), b_paid - revert_pay)
                new_disc = max(Decimal("0"), b_disc - revert_disc)
                new_total = b_total + revert_disc
                new_status = (
                    "Paid"
                    if (new_paid >= new_total and new_total > 0)
                    else ("Partially Paid" if new_paid > Decimal("0") else "Due")
                )

                conn.execute(
                    "UPDATE due_bills SET paid_amount = ?, discount = ?, total_amount = ?, status = ? WHERE id = ?",
                    (str(new_paid), str(new_disc), str(new_total), new_status, b_id),
                )
                updated_bills.append({
                    "bill_id": b_id,
                    "bill_number": str(target_bill["bill_number"]),
                    "old_paid": float(b_paid),
                    "new_paid": float(new_paid),
                    "old_status": str(target_bill["status"]),
                    "new_status": new_status,
                })
            else:
                rem_pay = pay_amount
                rem_disc = disc_amount
                if rem_pay > 0 or rem_disc > 0:
                    s_bills = conn.execute(
                        "SELECT b.* FROM due_bills b "
                        "JOIN enrollments e ON e.id = b.enrollment_id "
                        "WHERE e.student_id = ? AND (b.paid_amount > 0 OR b.discount > 0) "
                        "ORDER BY b.billing_period DESC, b.issue_date DESC, b.id DESC",
                        (student_id,),
                    ).fetchall()
                    for b in s_bills:
                        if rem_pay <= 0 and rem_disc <= 0:
                            break
                        b_paid = Decimal(str(b["paid_amount"] or 0))
                        b_disc = Decimal(str(b["discount"] or 0))
                        b_total = Decimal(str(b["total_amount"] or 0))

                        rev_p = min(b_paid, rem_pay)
                        rev_d = min(b_disc, rem_disc)
                        rem_pay -= rev_p
                        rem_disc -= rev_d

                        n_paid = max(Decimal("0"), b_paid - rev_p)
                        n_disc = max(Decimal("0"), b_disc - rev_d)
                        n_total = b_total + rev_d
                        n_status = (
                            "Paid"
                            if (n_paid >= n_total and n_total > 0)
                            else ("Partially Paid" if n_paid > Decimal("0") else "Due")
                        )

                        conn.execute(
                            "UPDATE due_bills SET paid_amount = ?, discount = ?, total_amount = ?, status = ? WHERE id = ?",
                            (str(n_paid), str(n_disc), str(n_total), n_status, b["id"]),
                        )
                        updated_bills.append({
                            "bill_id": int(b["id"]),
                            "bill_number": str(b["bill_number"]),
                            "old_paid": float(b_paid),
                            "new_paid": float(n_paid),
                            "old_status": str(b["status"]),
                            "new_status": n_status,
                        })

            # Reconcile FIFO in case other bills are impacted
            self._reconcile_fifo_on_conn(conn, student_id)

            # 2. Reverse ledger entry
            if pay_amount > 0 and account_id:
                l_row = conn.execute(
                    "SELECT id, amount FROM ledger WHERE source_type = 'Student Transaction' AND source_id = ?",
                    (transaction_id,),
                ).fetchone()
                if not l_row and receipt_no:
                    l_row = conn.execute(
                        "SELECT id, amount FROM ledger WHERE source_type = 'Student Transaction' "
                        "AND account_id = ? AND transaction_date = ? AND reference_no = ? AND direction = 'IN'",
                        (account_id, payment_date, receipt_no),
                    ).fetchone()
                if not l_row:
                    l_row = conn.execute(
                        "SELECT id, amount FROM ledger WHERE source_type = 'Student Transaction' "
                        "AND account_id = ? AND transaction_date = ? AND direction = 'IN' AND amount >= ? "
                        "ORDER BY id DESC LIMIT 1",
                        (account_id, payment_date, str(pay_amount)),
                    ).fetchone()

                if l_row:
                    l_id = int(l_row["id"])
                    l_amt = Decimal(str(l_row["amount"]))
                    if l_amt <= pay_amount:
                        conn.execute("DELETE FROM ledger WHERE id = ?", (l_id,))
                    else:
                        new_l_amt = l_amt - pay_amount
                        conn.execute("UPDATE ledger SET amount = ? WHERE id = ?", (str(new_l_amt), l_id))

                try:
                    conn.execute(
                        "UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?",
                        (str(pay_amount), account_id),
                    )
                except Exception:
                    pass

            # 3. Delete student transaction
            conn.execute("DELETE FROM student_transactions WHERE id = ?", (transaction_id,))

            # 4. Clean up any related SMS delivery logs
            conn.execute(
                "DELETE FROM sms_delivery_log WHERE entity_type IN ('student_transaction', 'bill_payment') AND entity_id = ?",
                (transaction_id,),
            )

            # 5. Audit log
            audit_detail = (
                f"Deleted student payment record #{transaction_id}: "
                f"Amount Rs. {pay_amount:,.2f}, Discount Rs. {disc_amount:,.2f}, "
                f"Receipt: '{receipt_no}', Particular: '{particular}' for Student ID #{student_id}"
            )
            try:
                conn.execute(
                    "INSERT INTO auth_audit_log (user_id, username, event_type, success, detail) VALUES (?, ?, 'payment.delete', 1, ?)",
                    (actor_user_id, actor_username, audit_detail),
                )
            except Exception:
                try:
                    conn.execute(
                        "INSERT INTO auth_audit_log (username, event_type, success, detail) VALUES (?, 'payment.delete', 1, ?)",
                        (actor_username, audit_detail),
                    )
                except Exception:
                    pass

            return {
                "success": True,
                "transaction_id": transaction_id,
                "student_id": student_id,
                "reverted_payment": float(pay_amount),
                "reverted_discount": float(disc_amount),
                "account_id": account_id,
                "updated_bills": updated_bills,
                "message": f"Payment record #{transaction_id} successfully deleted and related due bills and ledger entries updated.",
            }

        return self.db.transaction(callback)

    def record_advance_payment(
        self,
        student_id: int,
        amount: Decimal,
        payment_date: str,
        account_id: int,
        method: str = "Cash",
        receipt_no: str = "",
        remarks: str = "",
        payment_method: str | None = None,
    ) -> dict[str, Any]:
        """Record an advance tuition fee payment directly for a student.
        If the student has any current unpaid bills, it settles them first in FIFO order.
        Any remaining surplus is stored as Advance in student_transactions and credited to the account.
        """
        method = payment_method or method or "Cash"
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Advance payment amount must be greater than zero.")
        if not account_id:
            raise ValueError("Select a payment account.")

        def check_unpaid(conn):
            e_row = conn.execute(
                "SELECT id FROM enrollments WHERE student_id=? AND status='Active' ORDER BY id ASC LIMIT 1",
                (student_id,)
            ).fetchone()
            enrollment_id = int(e_row["id"]) if e_row else None
            if not enrollment_id:
                e_row2 = conn.execute(
                    "SELECT id FROM enrollments WHERE student_id=? ORDER BY id DESC LIMIT 1",
                    (student_id,)
                ).fetchone()
                enrollment_id = int(e_row2["id"]) if e_row2 else None

            unpaid = conn.execute(
                "SELECT b.id FROM due_bills b "
                "JOIN enrollments e ON e.id=b.enrollment_id "
                "WHERE e.student_id=? AND b.status<>'Paid' AND (b.total_amount - b.paid_amount) > 0 "
                "ORDER BY b.billing_period ASC, b.issue_date ASC, b.id ASC",
                (student_id,)
            ).fetchall()
            return [int(u["id"]) for u in unpaid], enrollment_id

        unpaid_ids, enrollment_id = self.db.transaction(check_unpaid)

        if unpaid_ids:
            return self.record_multi_payment(
                unpaid_ids,
                amount,
                Decimal("0"),
                payment_date,
                account_id,
                method,
                receipt_no,
                remarks or "Student Advance Payment",
                allow_advance=True,
                enforce_fifo=True,
            )
        else:
            def direct_advance(conn):
                s_row = conn.execute("SELECT student_name FROM students WHERE id=?", (student_id,)).fetchone()
                student_name = str(s_row["student_name"] or "") if s_row else ""
                particular = "Advance fee payment (Surplus credit for future months)"
                cursor = conn.execute(
                    "INSERT INTO student_transactions "
                    "(student_id,enrollment_id,transaction_date,transaction_type,particular,"
                    "charge_amount,payment_amount,discount_amount,account_id,payment_method,"
                    "receipt_no,remarks) VALUES (?,?,?,'Payment Received',?,0,?,0,?,?,?,?)",
                    (
                        student_id, enrollment_id, payment_date, particular,
                        str(amount), account_id, method, receipt_no, remarks or "Advance payment",
                    ),
                )
                t_id = int(cursor.lastrowid)
                cursor.close()

                # Update account balance
                conn.execute(
                    "UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?",
                    (str(amount), account_id)
                )
                self.db.add_ledger(
                    conn, payment_date, account_id, "IN", str(amount),
                    "Student Transaction", t_id,
                    particular, receipt_no, remarks or "Advance payment",
                )
                return {
                    "student_id": student_id,
                    "student_name": student_name,
                    "transaction_ids": [t_id],
                    "updated_bills": [],
                    "total_paid": amount,
                    "total_discount": Decimal("0"),
                    "advance_amount": amount,
                }

            return self.db.transaction(direct_advance)

    def _reconcile_fifo_on_conn(self, conn, student_id: int | None = None) -> dict[str, Any]:
        if student_id:
            s_rows = conn.execute("SELECT DISTINCT id FROM students WHERE id=?", (student_id,)).fetchall()
        else:
            s_rows = conn.execute("SELECT DISTINCT id FROM students").fetchall()

        reconciled_students = 0
        adjusted_bills = 0
        details = []

        for s_row in s_rows:
            sid = int(s_row["id"])
            bills = conn.execute(
                "SELECT b.id, b.bill_number, b.billing_period, b.total_amount, b.paid_amount, "
                "b.discount, b.status, b.issue_date "
                "FROM due_bills b "
                "JOIN enrollments e ON e.id=b.enrollment_id "
                "WHERE e.student_id=? "
                "ORDER BY b.billing_period ASC, b.issue_date ASC, b.id ASC",
                (sid,)
            ).fetchall()

            if len(bills) < 2:
                continue

            has_inversion = False
            for i, b_earlier in enumerate(bills):
                bal_earlier = Decimal(str(b_earlier["total_amount"])) - Decimal(str(b_earlier["paid_amount"]))
                if bal_earlier > Decimal("0"):
                    for b_later in bills[i+1:]:
                        if Decimal(str(b_later["paid_amount"])) > Decimal("0"):
                            has_inversion = True
                            break
                if has_inversion:
                    break

            if not has_inversion:
                continue

            total_paid = sum(Decimal(str(b["paid_amount"])) for b in bills)
            total_discount = sum(Decimal(str(b["discount"])) for b in bills)

            rem_paid = total_paid
            rem_disc = total_discount

            s_adjusted = 0
            for b in bills:
                b_id = int(b["id"])
                orig_paid = Decimal(str(b["paid_amount"]))
                orig_disc = Decimal(str(b["discount"]))
                subtotal = Decimal(str(b["total_amount"])) + orig_disc

                alloc_disc = min(rem_disc, subtotal)
                rem_disc -= alloc_disc
                new_total = subtotal - alloc_disc

                alloc_paid = min(rem_paid, new_total)
                rem_paid -= alloc_paid

                new_status = "Paid" if alloc_paid >= new_total and new_total > 0 else ("Partially Paid" if alloc_paid > Decimal("0") else "Due")

                if alloc_paid != orig_paid or alloc_disc != orig_disc or new_status != b["status"]:
                    conn.execute(
                        "UPDATE due_bills SET paid_amount=?, discount=?, total_amount=?, status=? WHERE id=?",
                        (str(alloc_paid), str(alloc_disc), str(new_total), new_status, b_id)
                    )
                    s_adjusted += 1
                    details.append({
                        "bill_id": b_id,
                        "bill_number": b["bill_number"],
                        "period": b["billing_period"],
                        "old_paid": float(orig_paid),
                        "new_paid": float(alloc_paid),
                        "old_status": b["status"],
                        "new_status": new_status,
                    })

            if s_adjusted > 0:
                reconciled_students += 1
                adjusted_bills += s_adjusted

        return {
            "reconciled_students": reconciled_students,
            "adjusted_bills": adjusted_bills,
            "details": details,
        }

    def reconcile_billing_fifo(self, student_id: int | None = None) -> dict[str, Any]:
        """Reconcile payments across due bills to strictly adhere to FIFO chronological order.
        If a student has an earlier bill unpaid while a later bill is paid, the payments
        are redistributed in chronological order so that the earlier bill is paid first.
        """
        return self.db.transaction(lambda conn: self._reconcile_fifo_on_conn(conn, student_id))

    def get_payments_for_bill(self, bill_id: int) -> list[dict[str, Any]]:
        bill = self.get(bill_id)
        if not bill:
            return []

        sql = """
            SELECT st.*, s.student_name, COALESCE(a.account_name, '') AS account_name
            FROM student_transactions st
            JOIN students s ON s.id = st.student_id
            LEFT JOIN accounts a ON a.id = st.account_id
            WHERE (st.particular LIKE ? OR st.particular LIKE ?)
              AND (st.payment_amount > 0 OR st.discount_amount > 0)
            ORDER BY st.transaction_date DESC, st.id DESC
        """
        rows = self.db.query(sql, (f"%{bill.bill_number}%", f"%bill {bill.bill_number}%"))
        if not rows and bill.paid_amount > Decimal("0"):
            sql_fallback = """
                SELECT st.*, s.student_name, COALESCE(a.account_name, '') AS account_name
                FROM student_transactions st
                JOIN students s ON s.id = st.student_id
                LEFT JOIN accounts a ON a.id = st.account_id
                WHERE st.student_id = ?
                  AND (st.enrollment_id = ? OR st.enrollment_id IS NULL)
                  AND (st.payment_amount > 0 OR st.discount_amount > 0)
                ORDER BY st.transaction_date DESC, st.id DESC
            """
            rows = self.db.query(sql_fallback, (bill.student_id, bill.enrollment_id))

        return [dict(r) for r in rows]

    def list_payment_records(self, search: str = "", period: str = "", limit: int = 500) -> list[dict[str, Any]]:
        sql = """
            SELECT st.*, s.student_name, s.contact,
                   COALESCE(cl.level_name, s.class_name, '') AS class_name,
                   c.course_name,
                   COALESCE(a.account_name, '') AS account_name
            FROM student_transactions st
            JOIN students s ON s.id = st.student_id
            LEFT JOIN class_levels cl ON cl.id = s.class_level_id
            LEFT JOIN enrollments e ON e.id = st.enrollment_id
            LEFT JOIN courses c ON c.id = e.course_id
            LEFT JOIN accounts a ON a.id = st.account_id
            WHERE (st.payment_amount > 0 OR st.discount_amount > 0)
        """
        params = []
        if search:
            sql += " AND (s.student_name LIKE ? OR st.particular LIKE ? OR st.receipt_no LIKE ? OR st.remarks LIKE ?)"
            pat = f"%{search.strip()}%"
            params.extend([pat, pat, pat, pat])
        if period and period != "All Periods":
            sql += " AND (st.transaction_date LIKE ? OR st.particular LIKE ?)"
            params.extend([f"{period}%", f"%{period}%"])
        sql += " ORDER BY st.transaction_date DESC, st.id DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.db.query(sql, tuple(params))]
