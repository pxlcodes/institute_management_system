from __future__ import annotations

from elh.models import AttendanceDeviceUser, AttendanceEvent, DeviceUserMapping
from .protocols import DatabaseGateway


class AttendanceRepository:
    def __init__(self, db: DatabaseGateway):
        self.db = db

    def mapping_for(self, device_user_id: str) -> DeviceUserMapping | None:
        row = self.db.query_one(
            "SELECT device_user_id, person_type, person_id FROM device_user_mappings "
            "WHERE device_user_id = ? AND status = 'Active'", (device_user_id,),
        )
        return DeviceUserMapping(**dict(row)) if row else None

    def mappings_for(self, device_user_ids: list[str]) -> dict[str, DeviceUserMapping]:
        device_user_ids = list(dict.fromkeys(device_user_ids))
        if not device_user_ids:
            return {}
        placeholders = ",".join("?" for _ in device_user_ids)
        rows = self.db.query(
            "SELECT device_user_id,person_type,person_id FROM device_user_mappings "
            f"WHERE status='Active' AND device_user_id IN ({placeholders})",
            tuple(device_user_ids),
        )
        return {
            row["device_user_id"]: DeviceUserMapping(**dict(row)) for row in rows
        }

    def save_event(self, event: AttendanceEvent, mapping: DeviceUserMapping | None) -> int:
        mappings = {event.device_user_id: mapping} if mapping else {}
        return self.save_events([event], mappings)

    def save_events(
        self,
        events: list[AttendanceEvent],
        mappings: dict[str, DeviceUserMapping],
    ) -> int:
        if not events:
            return 0
        device_ids = list(dict.fromkeys(event.device_user_id for event in events))
        placeholders = ",".join("?" for _ in device_ids)
        timestamps = [event.occurred_at.isoformat(sep=" ") for event in events]
        rows = self.db.query(
            "SELECT device_user_id,occurred_at,COALESCE(device_serial,'') device_serial "
            f"FROM attendance_logs WHERE device_user_id IN ({placeholders}) "
            "AND occurred_at BETWEEN ? AND ?",
            (*device_ids, min(timestamps), max(timestamps)),
        )
        existing = {
            (row["device_user_id"], str(row["occurred_at"]), row["device_serial"] or "")
            for row in rows
        }
        pending = []
        for event, timestamp in zip(events, timestamps):
            key = (event.device_user_id, timestamp, event.device_serial or "")
            if key in existing:
                continue
            mapping = mappings.get(event.device_user_id)
            pending.append(
                (
                    event.device_user_id,
                    mapping.person_type if mapping else None,
                    mapping.person_id if mapping else None,
                    timestamp,
                    event.event_type,
                    event.device_serial,
                    event.verification_mode,
                )
            )
            existing.add(key)
        if not pending:
            return 0

        def callback(conn):
            cursor = conn.executemany(
                "INSERT INTO attendance_logs "
                "(device_user_id,person_type,person_id,occurred_at,event_type,device_serial,verification_mode) "
                "VALUES (?,?,?,?,?,?,?)",
                pending,
            )
            saved = max(0, int(cursor.rowcount))
            cursor.close()
            return saved

        return self.db.transaction(callback)

    def save_mapping(self, device_user_id: str, person_type: str, person_id: int, status: str = "Active") -> None:
        existing = self.db.query_one(
            "SELECT id FROM device_user_mappings WHERE device_user_id = ?",
            (device_user_id,),
        )
        if existing:
            self.db.execute(
                "UPDATE device_user_mappings SET person_type = ?, person_id = ?, status = ? "
                "WHERE device_user_id = ?",
                (person_type, person_id, status, device_user_id),
            )
        else:
            self.db.execute(
                "INSERT INTO device_user_mappings "
                "(device_user_id, person_type, person_id, status) VALUES (?, ?, ?, ?)",
                (device_user_id, person_type, person_id, status),
            )

        # Merge attendance already imported before the device user was mapped.
        if status == "Active":
            self.db.execute(
                "UPDATE attendance_logs SET person_type = ?, person_id = ? "
                "WHERE device_user_id = ?",
                (person_type, person_id, device_user_id),
            )

    def person_exists(self, person_type: str, person_id: int) -> bool:
        table = "teachers" if person_type == "teacher" else "students"
        return self.db.query_one(f"SELECT id FROM {table} WHERE id = ?", (person_id,)) is not None

    def deactivate_person_mappings(
        self,
        person_type: str,
        person_id: int,
        except_device_user_id: str | None = None,
    ) -> None:
        sql = (
            "UPDATE device_user_mappings SET status = 'Inactive' "
            "WHERE person_type = ? AND person_id = ? AND status = 'Active'"
        )
        params: tuple = (person_type, person_id)
        if except_device_user_id:
            sql += " AND device_user_id <> ?"
            params += (except_device_user_id,)
        self.db.execute(sql, params)

    def save_device_users(self, users: list[AttendanceDeviceUser]) -> int:
        """Cache the device directory so users without punches can be mapped."""
        if not users:
            return 0
        values = [
            (
                user.device_user_id, user.name, user.uid, user.privilege,
                user.card_number, user.device_serial,
            )
            for user in users
        ]
        if self.db.__class__.__name__ == "MySQLDatabase":
            sql = (
                "INSERT INTO attendance_device_users "
                "(device_user_id,device_name,device_uid,privilege,card_number,device_serial) "
                "VALUES (?,?,?,?,?,?) ON DUPLICATE KEY UPDATE "
                "device_name=VALUES(device_name),device_uid=VALUES(device_uid),"
                "privilege=VALUES(privilege),card_number=VALUES(card_number),"
                "device_serial=VALUES(device_serial),fetched_at=CURRENT_TIMESTAMP"
            )
        else:
            sql = (
                "INSERT INTO attendance_device_users "
                "(device_user_id,device_name,device_uid,privilege,card_number,device_serial) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(device_user_id) DO UPDATE SET "
                "device_name=excluded.device_name,device_uid=excluded.device_uid,"
                "privilege=excluded.privilege,card_number=excluded.card_number,"
                "device_serial=excluded.device_serial,fetched_at=CURRENT_TIMESTAMP"
            )
        self.db.executemany(sql, values)
        return len(values)

    def device_users(self):
        return self.db.query("""
            SELECT base.device_user_id,u.device_name,u.device_uid,u.privilege,u.card_number,
              COALESCE(u.device_serial,d.device_serial) device_serial,
              m.person_type,m.person_id,COALESCE(m.status,'Unmapped') status,
              COALESCE(t.teacher_name,s.student_name,'') person_name,
              COALESCE(d.log_count,0) log_count,d.last_seen,u.fetched_at
            FROM (
              SELECT device_user_id FROM attendance_device_users
              UNION SELECT device_user_id FROM attendance_logs
            ) base
            LEFT JOIN attendance_device_users u ON u.device_user_id=base.device_user_id
            LEFT JOIN (
              SELECT device_user_id,COUNT(*) log_count,MAX(occurred_at) last_seen,
                     MAX(device_serial) device_serial
              FROM attendance_logs GROUP BY device_user_id
            ) d ON d.device_user_id=base.device_user_id
            LEFT JOIN device_user_mappings m ON m.device_user_id=base.device_user_id
            LEFT JOIN teachers t ON m.person_type='teacher' AND t.id=m.person_id
            LEFT JOIN students s ON m.person_type='student' AND s.id=m.person_id
            ORDER BY CASE WHEN m.id IS NULL THEN 0 ELSE 1 END,
                     COALESCE(u.device_name,''),base.device_user_id
        """)

    def registered_device_names(self) -> dict[str, str]:
        rows = self.db.query(
            "SELECT m.device_user_id,COALESCE(t.teacher_name,s.student_name,'') registered_name "
            "FROM device_user_mappings m "
            "LEFT JOIN teachers t ON m.person_type='teacher' AND t.id=m.person_id "
            "LEFT JOIN students s ON m.person_type='student' AND s.id=m.person_id "
            "WHERE m.status='Active' ORDER BY m.device_user_id"
        )
        return {str(row["device_user_id"]): str(row["registered_name"]).strip() for row in rows if str(row["registered_name"]).strip()}

    def mappings(self):
        return self.db.query("""
            SELECT m.*,COALESCE(t.teacher_name,s.student_name,'') person_name
            FROM device_user_mappings m
            LEFT JOIN teachers t ON m.person_type='teacher' AND t.id=m.person_id
            LEFT JOIN students s ON m.person_type='student' AND s.id=m.person_id
            ORDER BY m.device_user_id
        """)

    def logs(
        self,
        start_at: str | None = None,
        end_at: str | None = None,
        limit: int = 1000,
    ):
        where = ""
        params: list[str] = []
        if start_at and end_at:
            where = "WHERE l.occurred_at BETWEEN ? AND ?"
            params = [start_at, end_at]
        return self.db.query(f"""
            SELECT l.*,COALESCE(t.teacher_name,s.student_name,'') person_name
            FROM attendance_logs l
            LEFT JOIN teachers t ON l.person_type='teacher' AND t.id=l.person_id
            LEFT JOIN students s ON l.person_type='student' AND s.id=l.person_id
            {where} ORDER BY l.occurred_at DESC LIMIT {int(limit)}
        """, tuple(params))

    def staff_logs(self, start_at: str, end_at: str):
        return self.db.query("""
            SELECT l.person_id,t.teacher_name,l.occurred_at,l.event_type
            FROM attendance_logs l JOIN teachers t ON t.id=l.person_id
            WHERE l.person_type='teacher' AND l.occurred_at BETWEEN ? AND ?
            ORDER BY t.teacher_name,l.occurred_at
        """, (start_at, end_at))

    def staff_members(self):
        return self.db.query("SELECT id,teacher_name,staff_type FROM teachers WHERE status='Active' ORDER BY teacher_name")

    def student_logs(self, start_at: str, end_at: str):
        return self.db.query(
            """
            SELECT l.person_id,s.student_name,l.occurred_at,l.event_type
            FROM attendance_logs l JOIN students s ON s.id=l.person_id
            WHERE l.person_type='student' AND l.occurred_at BETWEEN ? AND ?
            ORDER BY s.student_name,l.occurred_at
            """,
            (start_at, end_at),
        )

    def student_members(self):
        return self.db.query(
            "SELECT id,student_name,class_name FROM students "
            "WHERE status='Active' ORDER BY student_name"
        )

    def students_present(self, start_at: str, end_at: str):
        """One row per mapped student with at least one punch in the period."""
        return self.db.query(
            """
            SELECT l.person_id,s.student_name,s.class_name,COUNT(*) punches,
                   MIN(l.occurred_at) first_seen,MAX(l.occurred_at) last_seen
            FROM attendance_logs l JOIN students s ON s.id=l.person_id
            WHERE l.person_type='student' AND l.occurred_at BETWEEN ? AND ?
            GROUP BY l.person_id,s.student_name,s.class_name
            ORDER BY s.student_name
            """,
            (start_at, end_at),
        )

    def students_absent(self, start_at: str, end_at: str):
        """Active enrolled students without a mapped attendance punch in a period."""
        return self.db.query(
            """
            SELECT s.id,s.student_name,s.class_name,s.contact,s.parent_name,
                   GROUP_CONCAT(DISTINCT c.course_name) courses,MIN(e.start_date) enrollment_start,
                   MAX(previous_log.occurred_at) last_seen,
                   CASE WHEN EXISTS (
                     SELECT 1 FROM device_user_mappings mapping
                     WHERE mapping.person_type='student' AND mapping.person_id=s.id
                       AND mapping.status='Active'
                   ) THEN 'Linked' ELSE 'Not linked' END device_status
            FROM students s
            JOIN enrollments e ON e.student_id=s.id AND e.status='Active'
            JOIN courses c ON c.id=e.course_id
            LEFT JOIN attendance_logs previous_log
              ON previous_log.person_type='student' AND previous_log.person_id=s.id
            WHERE s.status='Active'
              AND NOT EXISTS (
                SELECT 1 FROM attendance_logs today_log
                WHERE today_log.person_type='student' AND today_log.person_id=s.id
                  AND today_log.occurred_at BETWEEN ? AND ?
              )
            GROUP BY s.id,s.student_name,s.class_name,s.contact,s.parent_name
            ORDER BY s.student_name
            """,
            (start_at, end_at),
        )

    def students_with_attendance(self):
        """One row per active mapped student who has ever punched on the device."""
        return self.db.query(
            """
            SELECT l.person_id,s.student_name,s.class_name,COUNT(*) punches,
                   MIN(l.occurred_at) first_seen,MAX(l.occurred_at) last_seen
            FROM attendance_logs l JOIN students s ON s.id=l.person_id
            WHERE l.person_type='student' AND s.status='Active'
            GROUP BY l.person_id,s.student_name,s.class_name
            ORDER BY s.student_name
            """
        )
