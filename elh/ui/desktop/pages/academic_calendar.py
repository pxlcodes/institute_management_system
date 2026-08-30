from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import today_iso, validate_date


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
            ("id", "ID", 55), ("event", "Event", 250), ("type", "Type", 110),
            ("start", "Start Date", 110), ("end", "End Date", 110),
            ("status", "Status", 95), ("remarks", "Remarks", 300),
        ])
        self.tree.bind("<Double-1>", self.edit_selected)

    def refresh(self):
        self.clear_tree(self.tree)
        for row in self.db.query(
            "SELECT * FROM academic_calendar_events ORDER BY start_date DESC,id DESC"
        ):
            self.tree.insert("", "end", values=(
                row["id"], row["event_name"], row["event_type"], row["start_date"],
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
        start_date = tk.StringVar(value=row["start_date"] if row else today_iso())
        end_date = tk.StringVar(value=row["end_date"] if row else today_iso())
        status = tk.StringVar(value=row["status"] if row else "Active")
        remarks = tk.StringVar(value=(row["remarks"] or "") if row else "")
        builder = FormBuilder(form)
        builder.entry("Event Name *", event_name, width=42)
        builder.combo("Type", event_type, ["Holiday", "Closure", "Working Day", "Event"], width=40)
        builder.entry("Start Date *", start_date, width=42)
        builder.entry("End Date *", end_date, width=42)
        builder.combo("Status", status, ["Active", "Inactive"], width=40)
        builder.entry("Remarks", remarks, width=42)
        form.columnconfigure(1, weight=1)

        def save():
            try:
                name = event_name.get().strip()
                if not name:
                    raise ValueError("Event name is required.")
                start = validate_date(start_date.get(), "Start date")
                end = validate_date(end_date.get(), "End date")
                if end < start:
                    raise ValueError("End date cannot be before start date.")
                values = (name, event_type.get(), start, end, status.get(), remarks.get().strip())
                if row:
                    self.db.execute(
                        "UPDATE academic_calendar_events SET event_name=?,event_type=?,start_date=?,end_date=?,status=?,remarks=? WHERE id=?",
                        values + (row["id"],),
                    )
                else:
                    self.db.execute(
                        "INSERT INTO academic_calendar_events (event_name,event_type,start_date,end_date,status,remarks) VALUES (?,?,?,?,?,?)",
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
