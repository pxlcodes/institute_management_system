"""Staff-specific payment accounts and statement entries.

These accounts are a sub-ledger for staff payments.  They do not represent cash
or bank balances, so salary and advance history can be reviewed per staff member
without inflating the institution's available-cash balance.
"""

from __future__ import annotations


class StaffFinanceService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _one(connection, sql: str, params=()):
        cursor = connection.execute(sql, params)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def ensure_account(self, teacher_id: int, connection=None) -> int:
        """Return the staff member's internal payment account, creating it if needed."""
        if connection is None:
            return self.db.transaction(lambda conn: self.ensure_account(teacher_id, conn))
        existing = self._one(
            connection,
            "SELECT id FROM staff_payment_accounts WHERE teacher_id=?",
            (teacher_id,),
        )
        if existing:
            return int(existing["id"])
        staff = self._one(
            connection,
            "SELECT id,teacher_name,bank_account_number,account_holder_name,bank_name,status "
            "FROM teachers WHERE id=?",
            (teacher_id,),
        )
        if not staff:
            raise ValueError("Staff member was not found.")
        cursor = connection.execute(
            "INSERT INTO staff_payment_accounts "
            "(teacher_id,account_name,account_number,account_holder,bank_name,status) "
            "VALUES (?,?,?,?,?,?)",
            (
                teacher_id,
                f"Staff Account - {teacher_id} - {staff['teacher_name']}",
                staff["bank_account_number"],
                staff["account_holder_name"],
                staff["bank_name"],
                staff["status"],
            ),
        )
        try:
            return int(cursor.lastrowid)
        finally:
            cursor.close()

    def sync_account(self, teacher_id: int) -> int:
        """Keep the staff payment account's name and bank details in step with staff data."""
        def update(connection):
            account_id = self.ensure_account(teacher_id, connection)
            staff = self._one(
                connection,
                "SELECT teacher_name,bank_account_number,account_holder_name,bank_name,status FROM teachers WHERE id=?",
                (teacher_id,),
            )
            cursor = connection.execute(
                "UPDATE staff_payment_accounts SET account_name=?,account_number=?,account_holder=?,"
                "bank_name=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (
                    f"Staff Account - {teacher_id} - {staff['teacher_name']}",
                    staff["bank_account_number"], staff["account_holder_name"],
                    staff["bank_name"], staff["status"], account_id,
                ),
            )
            cursor.close()
            return account_id
        return self.db.transaction(update)

    def record_payment(
        self, connection, teacher_id: int, transaction_date: str, transaction_type: str,
        amount, source_type: str, source_id: int, paid_from_account_id: int,
        particular: str, reference_no: str = "", remarks: str = "",
    ) -> int:
        account_id = self.ensure_account(teacher_id, connection)
        cursor = connection.execute(
            "INSERT INTO staff_payment_transactions "
            "(staff_account_id,transaction_date,transaction_type,amount,source_type,source_id,"
            "paid_from_account_id,reference_no,particular,remarks) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (account_id, transaction_date, transaction_type, amount, source_type, source_id,
             paid_from_account_id, reference_no, particular, remarks),
        )
        try:
            return int(cursor.lastrowid)
        finally:
            cursor.close()

    def statement(self, teacher_id: int):
        account = self.db.query_one(
            "SELECT * FROM staff_payment_accounts WHERE teacher_id=?", (teacher_id,)
        )
        if not account:
            self.ensure_account(teacher_id)
            account = self.db.query_one(
                "SELECT * FROM staff_payment_accounts WHERE teacher_id=?", (teacher_id,)
            )
        transactions = self.db.query(
            "SELECT tx.*,a.account_name paid_from FROM staff_payment_transactions tx "
            "LEFT JOIN accounts a ON a.id=tx.paid_from_account_id "
            "WHERE tx.staff_account_id=? ORDER BY tx.transaction_date DESC,tx.id DESC",
            (account["id"],),
        )
        return account, transactions
