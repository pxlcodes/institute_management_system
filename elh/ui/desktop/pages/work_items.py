from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from elh.ui.desktop.components import CrudPage, FormBuilder
from elh.ui.desktop.helpers import today_iso, validate_date


class WorkItemsPage(CrudPage):
    """Small operational task list and a searchable bug-report register."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.staff_map: dict[str, int] = {}
        ttk.Label(self, text="Tasks & Bug Reports", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="Assign follow-ups to staff and keep application issues in one place.", style="Hint.TLabel").pack(anchor="w", pady=(0, 4))
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 6)); toolbar.pack(fill="x", pady=(8, 10))
        ttk.Button(toolbar, text="＋ New Task", style="Accent.TButton", command=self.new_task).pack(side="left")
        ttk.Button(toolbar, text="Report a Bug", command=self.report_bug).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Mark Selected Done", command=self.complete_task).pack(side="left", padx=4)

        notebook = ttk.Notebook(self); notebook.pack(fill="both", expand=True)
        task_frame = ttk.Frame(notebook); bug_frame = ttk.Frame(notebook)
        notebook.add(task_frame, text="Tasks")
        notebook.add(bug_frame, text="Bug reports")
        self.task_tree = self.make_tree(task_frame, [
            ("id", "ID", 50), ("title", "Task", 250), ("staff", "Assigned To", 170),
            ("due", "Due Date", 105), ("priority", "Priority", 90), ("status", "Status", 105),
        ])
        self.bug_tree = self.make_tree(bug_frame, [
            ("id", "ID", 50), ("title", "Issue", 260), ("page", "Screen", 150),
            ("severity", "Severity", 90), ("status", "Status", 105), ("reported", "Reported By", 160), ("created", "Created", 150),
        ])
        self.bug_tree.bind("<Double-1>", self.open_bug)

    def refresh(self):
        self.staff_map = {
            f"{row['teacher_name']} (ID: {row['id']})": int(row["id"])
            for row in self.db.query("SELECT id,teacher_name FROM teachers WHERE status='Active' ORDER BY teacher_name")
        }
        self.clear_tree(self.task_tree)
        for row in self.db.query(
            "SELECT t.*, COALESCE(s.teacher_name,'Unassigned') staff FROM todo_items t "
            "LEFT JOIN teachers s ON s.id=t.assigned_teacher_id ORDER BY t.status='Done', t.due_date, t.id DESC"
        ):
            self.task_tree.insert("", "end", values=(row["id"], row["title"], row["staff"], row["due_date"] or "", row["priority"], row["status"]))
        self.clear_tree(self.bug_tree)
        for row in self.db.query(
            "SELECT b.*,COALESCE(u.display_name,u.username,'Unknown') reporter FROM bug_reports b "
            "LEFT JOIN app_users u ON u.id=b.reported_by_user_id ORDER BY b.status='Resolved',b.id DESC"
        ):
            self.bug_tree.insert("", "end", values=(row["id"], row["title"], row["page_name"] or "", row["severity"], row["status"], row["reporter"], str(row["created_at"])[:16]))

    def new_task(self):
        dialog = tk.Toplevel(self); dialog.title("New Task"); dialog.transient(self.winfo_toplevel()); dialog.grab_set()
        form = ttk.Frame(dialog, padding=14, style="Form.TFrame"); form.pack(fill="both", expand=True)
        values = {"title": tk.StringVar(), "staff": tk.StringVar(), "due": tk.StringVar(value=today_iso()), "priority": tk.StringVar(value="Normal"), "details": tk.StringVar()}
        fb = FormBuilder(form); fb.entry("Task *", values["title"], width=42); fb.combo("Assign To", values["staff"], list(self.staff_map), searchable=True, width=40); fb.entry("Due Date", values["due"], width=42); fb.combo("Priority", values["priority"], ["Low", "Normal", "High"], width=40); fb.entry("Details", values["details"], width=42)
        def save():
            try:
                title = values["title"].get().strip()
                if not title: raise ValueError("Task is required.")
                due = validate_date(values["due"].get(), "Due date", allow_blank=True)
                self.db.execute("INSERT INTO todo_items (title,details,assigned_teacher_id,due_date,priority,status,created_by_user_id) VALUES (?,?,?,?,?,'Open',?)", (title, values["details"].get().strip(), self.staff_map.get(values["staff"].get()), due, values["priority"].get(), self.app.session.user_id))
                dialog.destroy(); self.refresh()
            except Exception as exc: messagebox.showerror("Task", str(exc), parent=dialog)
        ttk.Button(form, text="Save Task", style="Accent.TButton", command=save).grid(row=fb.row, column=1, sticky="e", pady=10)

    def complete_task(self):
        selection = self.task_tree.selection()
        if not selection: return
        task_id = int(self.task_tree.item(selection[0], "values")[0])
        self.db.execute("UPDATE todo_items SET status='Done',completed_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,)); self.refresh()

    def report_bug(self):
        dialog = tk.Toplevel(self); dialog.title("Report a Bug"); dialog.transient(self.winfo_toplevel()); dialog.grab_set()
        form = ttk.Frame(dialog, padding=14, style="Form.TFrame"); form.pack(fill="both", expand=True)
        values = {"title": tk.StringVar(), "page": tk.StringVar(value=self.app.page_title.get()), "severity": tk.StringVar(value="Normal"), "details": tk.StringVar()}
        fb = FormBuilder(form); fb.entry("What happened? *", values["title"], width=48); fb.entry("Screen", values["page"], width=48); fb.combo("Severity", values["severity"], ["Low", "Normal", "High", "Critical"], width=46); fb.entry("Details / steps to repeat *", values["details"], width=48)
        def save():
            try:
                title, details = values["title"].get().strip(), values["details"].get().strip()
                if not title or not details: raise ValueError("Describe the issue and the steps/details.")
                self.db.execute("INSERT INTO bug_reports (title,details,page_name,severity,status,reported_by_user_id) VALUES (?,?,?,?,'Open',?)", (title, details, values["page"].get().strip(), values["severity"].get(), self.app.session.user_id))
                dialog.destroy(); self.refresh(); messagebox.showinfo("Bug report", "Thank you. The issue was saved for follow-up.", parent=self)
            except Exception as exc: messagebox.showerror("Bug report", str(exc), parent=dialog)
        ttk.Button(form, text="Submit Report", style="Accent.TButton", command=save).grid(row=fb.row, column=1, sticky="e", pady=10)

    def open_bug(self, _event=None):
        selection = self.bug_tree.selection()
        if not selection: return
        bug_id = int(self.bug_tree.item(selection[0], "values")[0]); row = self.db.query_one("SELECT * FROM bug_reports WHERE id=?", (bug_id,))
        if not row: return
        messagebox.showinfo("Bug report", f"{row['title']}\n\nScreen: {row['page_name'] or '-'}\nStatus: {row['status']}\n\n{row['details']}", parent=self)
