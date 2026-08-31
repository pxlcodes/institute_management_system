from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import current_month, today_iso, validate_date, validate_month


class AcademicCalendarPage(CrudPage):
    """Manage closures that must not become student absence alerts."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="Academic Calendar", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Active holidays and closures are excluded from attendance absence alerts.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 6))
        toolbar.pack(fill="x", pady=(4, 8))
        ttk.Button(toolbar, text="＋ Add Calendar Event", style="Accent.TButton", command=self.show_new_form).pack(side="left")
        ttk.Button(toolbar, text="Deactivate Selected", command=self.deactivate_selected).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left")
        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.tree = self.make_tree(area, [
            ("id", "ID", 55), ("event", "Event", 220), ("course", "Course", 180), ("type", "Type", 110),
            ("start", "Start Date", 110), ("end", "End Date", 110),
            ("status", "Status", 95), ("remarks", "Remarks", 300),
        ])
        self.tree.bind("<Double-1>", self.edit_selected)

    def refresh(self):
        self.clear_tree(self.tree)
        for row in self.db.query(
            "SELECT event.*,c.course_name FROM academic_calendar_events event "
            "LEFT JOIN courses c ON c.id=event.course_id ORDER BY event.start_date DESC,event.id DESC"
        ):
            self.tree.insert("", "end", values=(
                row["id"], row["event_name"], row["course_name"] or "All courses", row["event_type"], row["start_date"],
                row["end_date"], row["status"], row["remarks"] or "",
            ))

    def selected_row(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.db.query_one(
            "SELECT * FROM academic_calendar_events WHERE id=?",
            (int(self.tree.item(selection[0], "values")[0]),),
        )

    def show_new_form(self):
        self._event_dialog()

    def edit_selected(self, _event=None):
        row = self.selected_row()
        if row:
            self._event_dialog(row)

    def _event_dialog(self, row=None):
        dialog = tk.Toplevel(self)
        dialog.title("Edit Calendar Event" if row else "Add Calendar Event")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        form = ttk.Frame(dialog, padding=14, style="Form.TFrame")
        form.pack(fill="both", expand=True)
        event_name = tk.StringVar(value=row["event_name"] if row else "")
        event_type = tk.StringVar(value=row["event_type"] if row else "Holiday")
        courses = self.db.query("SELECT id,course_name,category FROM courses WHERE status='Active' ORDER BY course_name")
        course_map = {"All courses (institution-wide)": None}
        course_map.update({f"{item['course_name']} [{item['category']}]": int(item["id"]) for item in courses})
        course = tk.StringVar(value=next((label for label, course_id in course_map.items() if course_id == (row["course_id"] if row else None)), "All courses (institution-wide)"))
        start_date = tk.StringVar(value=row["start_date"] if row else today_iso())
        end_date = tk.StringVar(value=row["end_date"] if row else today_iso())
        status = tk.StringVar(value=row["status"] if row else "Active")
        remarks = tk.StringVar(value=(row["remarks"] or "") if row else "")
        weekend_month = tk.StringVar(value=current_month())
        saturday = tk.BooleanVar(value=False)
        sunday = tk.BooleanVar(value=False)
        builder = FormBuilder(form)
        builder.entry("Event Name *", event_name, width=42)
        builder.combo("Applies to Course", course, list(course_map), width=40, searchable=True)
        builder.combo("Type", event_type, ["Holiday", "Closure", "Working Day", "Event"], width=40)
        builder.entry("Start Date *", start_date, width=42)
        builder.entry("End Date *", end_date, width=42)
        builder.combo("Status", status, ["Active", "Inactive"], width=40)
        builder.entry("Remarks", remarks, width=42)
        builder.entry("Bulk Weekend Month", weekend_month, width=42)
        weekend_frame = ttk.Frame(form, style="Form.TFrame")
        ttk.Checkbutton(weekend_frame, text="Saturday", variable=saturday).pack(side="left")
        ttk.Checkbutton(weekend_frame, text="Sunday", variable=sunday).pack(side="left", padx=10)
        ttk.Label(form, text="Bulk Weekend (optional)", style="Form.TLabel").grid(row=builder.row, column=0, padx=5, pady=4, sticky="w")
        weekend_frame.grid(row=builder.row, column=1, padx=5, pady=4, sticky="w")
        builder.row += 1
        form.columnconfigure(1, weight=1)

        def save():
            try:
                selected_weekends = {day for day, selected in (("Saturday", saturday.get()), ("Sunday", sunday.get())) if selected}
                if selected_weekends:
                    created = self._insert_weekends(
                        weekend_month.get(), event_type.get(), selected_weekends, remarks.get(), course_map.get(course.get())
                    )
                    dialog.destroy()
                    self.app.refresh_all()
                    messagebox.showinfo("Academic Calendar", f"Added {created} weekend event(s).", parent=self)
                    return
                name = event_name.get().strip()
                if not name:
                    raise ValueError("Event name is required.")
                start = validate_date(start_date.get(), "Start date")
                end = validate_date(end_date.get(), "End date")
                if end < start:
                    raise ValueError("End date cannot be before start date.")
                values = (name, event_type.get(), course_map.get(course.get()), start, end, status.get(), remarks.get().strip())
                if row:
                    self.db.execute(
                        "UPDATE academic_calendar_events SET event_name=?,event_type=?,course_id=?,start_date=?,end_date=?,status=?,remarks=? WHERE id=?",
                        values + (row["id"],),
                    )
                else:
                    self.db.execute(
                        "INSERT INTO academic_calendar_events (event_name,event_type,course_id,start_date,end_date,status,remarks) VALUES (?,?,?,?,?,?,?)",
                        values,
                    )
                dialog.destroy()
                self.app.refresh_all()
            except Exception as exc:
                messagebox.showerror("Academic Calendar", str(exc), parent=dialog)

        ttk.Button(form, text="Save Event", style="Accent.TButton", command=save).grid(
            row=builder.row, column=1, sticky="e", pady=(12, 0)
        )

    def deactivate_selected(self):
        row = self.selected_row()
        if not row:
            messagebox.showinfo("Academic Calendar", "Select a calendar event first.", parent=self)
            return
        if not messagebox.askyesno(
            "Deactivate Calendar Event",
            f"Deactivate '{row['event_name']}'? It will no longer affect attendance alerts.",
            parent=self,
        ):
            return
        self.db.execute("UPDATE academic_calendar_events SET status='Inactive' WHERE id=?", (row["id"],))
        self.app.refresh_all()

    def _insert_weekends(self, month: str, event_type: str, selected: set[str], remarks: str, course_id: int | None) -> int:
        value = validate_month(month, "Calendar month")
        if event_type not in {"Holiday", "Closure"}:
            event_type = "Holiday"
        year, month_number = (int(part) for part in value.split("/"))
        import nepali_datetime as nepali
        first = nepali.date(year, month_number, 1)
        next_month = nepali.date(year + 1, 1, 1) if month_number == 12 else nepali.date(year, month_number + 1, 1)
        created = 0
        for day in range(1, (next_month - first).days + 1):
            date_value = nepali.date(year, month_number, day)
            weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[date_value.to_datetime_date().weekday()]
            if weekday not in selected:
                continue
            business_date = date_value.strftime("%Y/%m/%d")
            if self.db.query_one(
                "SELECT id FROM academic_calendar_events WHERE event_name=? AND event_type=? AND start_date=? AND end_date=? "
                "AND (course_id=? OR (course_id IS NULL AND ? IS NULL))",
                (f"Weekend - {weekday}", event_type, business_date, business_date, course_id, course_id),
            ):
                continue
            self.db.execute(
                "INSERT INTO academic_calendar_events (event_name,event_type,course_id,start_date,end_date,status,remarks) VALUES (?,?,?,?,?,?,?)",
                (f"Weekend - {weekday}", event_type, course_id, business_date, business_date, "Active", remarks.strip()),
            )
            created += 1
        return created
