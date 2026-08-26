from __future__ import annotations

import tkinter as tk
import nepali_datetime as nepali
from tkinter import messagebox, ttk
from typing import Iterable
from elh.ui.desktop.helpers import open_or_print_pdf

# Reusable GUI components
# ---------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=225, background="#12263A")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)

        self.content.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class BasePage(ttk.Frame):
    def __init__(self, parent, app: "ManagementApp"):
        super().__init__(parent, padding=10)
        self.app = app
        self.db = app.db
        self.form_dialog = None

    def create_form_dialog(
        self,
        title: str,
        padding: int = 12,
        hint_text: str = "Double-click a row to edit",
    ) -> ttk.LabelFrame:
        """Create a hidden reusable form window and expose only a New button on the page."""
        self.form_dialog = tk.Toplevel(self)
        self.form_dialog.title(title)
        self.form_dialog.configure(background="#EEF3F8")
        self.form_dialog.withdraw()
        self.form_dialog.protocol("WM_DELETE_WINDOW", self.hide_form_dialog)
        self.form_dialog.bind("<Escape>", lambda _event: self.hide_form_dialog())
        self.form_dialog.bind("<Control-Return>", lambda _event: self._invoke_form_primary())
        self.form_dialog.resizable(True, True)
        self.page_toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(8,6))
        self.page_toolbar.pack(fill="x", pady=(8, 10))
        ttk.Button(self.page_toolbar, text=f"＋ New {title}", style="Accent.TButton", command=self.show_new_form).pack(side="left")
        ttk.Label(self.page_toolbar, text=hint_text, style="Hint.TLabel").pack(side="right", padx=8)
        return ttk.LabelFrame(self.form_dialog, text=title, padding=padding, style="Form.TLabelframe")

    def show_new_form(self):
        if hasattr(self, "clear"):
            try: self.clear()
            except Exception: pass
        self.show_form_dialog()

    def show_form_dialog(self):
        if not self.form_dialog:return
        self.form_dialog.update_idletasks()
        width=max(640,self.form_dialog.winfo_reqwidth()+30);height=max(420,self.form_dialog.winfo_reqheight()+30)
        x=max(0,(self.form_dialog.winfo_screenwidth()-width)//2);y=max(0,(self.form_dialog.winfo_screenheight()-height)//2)
        self.form_dialog.geometry(f"{width}x{height}+{x}+{y}")
        self.form_dialog.deiconify();self.form_dialog.lift();self.form_dialog.grab_set()
        self._focus_first_input(self.form_dialog)

    def hide_form_dialog(self):
        if self.form_dialog:
            try:self.form_dialog.grab_release()
            except tk.TclError:pass
            self.form_dialog.withdraw()

    @staticmethod
    def _descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from BasePage._descendants(child)

    def _focus_first_input(self, container) -> None:
        for widget in self._descendants(container):
            if isinstance(widget, (ttk.Entry, ttk.Combobox, tk.Entry, tk.Text)):
                widget.focus_set()
                return

    def _invoke_form_primary(self):
        """Save the open form with Ctrl+Enter without relying on pointer input."""
        if not self.form_dialog or not self.form_dialog.winfo_viewable():
            return "break"
        for widget in self._descendants(self.form_dialog):
            if isinstance(widget, ttk.Button) and widget.cget("text").lower().startswith(("save", "create", "submit", "receive")):
                widget.invoke()
                break
        return "break"

    def add_toolbar_menu(self, label: str, actions: list[tuple[str, object | None]]) -> ttk.Menubutton:
        """Keep secondary actions out of the main toolbar.

        Each action is a ``(caption, callback)`` pair.  A ``None`` callback adds a divider.
        Primary work stays visible; infrequent import/export and destructive actions remain
        available without making every page look like a row of unrelated buttons.
        """
        menu_button = ttk.Menubutton(self.page_toolbar, text=f"⋯ {label} ▾")
        menu = tk.Menu(menu_button, tearoff=False)
        for caption, callback in actions:
            if callback is None:
                menu.add_separator()
            else:
                menu.add_command(label=caption, command=callback)
        menu_button.configure(menu=menu)
        menu_button.pack(side="left", padx=4)
        return menu_button

    def refresh(self) -> None:
        pass

    def show_error(self, exc: Exception) -> None:
        messagebox.showerror("Error", str(exc), parent=self)

    def confirm_delete(self) -> bool:
        return messagebox.askyesno(
            "Confirm",
            "Are you sure you want to delete the selected record?",
            parent=self,
        )


class CrudPage(BasePage):
    def make_tree(self, parent, columns: list[tuple[str, str, int]]) -> ttk.Treeview:
        search_row = ttk.Frame(parent, style="Toolbar.TFrame", padding=(8, 6))
        search_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(search_row, text="⌕ Search", style="Hint.TLabel").pack(side="left")
        search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=search_var, width=24).pack(side="left", padx=(6, 6))
        ttk.Label(search_row, text="in", style="Hint.TLabel").pack(side="left")
        search_column_var = tk.StringVar(value="All columns")
        headings = {key: heading for key, heading, _width in columns}
        search_combo = ttk.Combobox(search_row, textvariable=search_column_var, state="readonly", width=16,
            values=["All columns", *headings.values()])
        search_combo.pack(side="left", padx=(4, 12))

        ttk.Label(search_row, text="⚲ Filter", style="Hint.TLabel").pack(side="left")
        filter_column_var = tk.StringVar(value="All columns")
        filter_combo = ttk.Combobox(search_row, textvariable=filter_column_var, state="readonly", width=16,
            values=["All columns", *headings.values()])
        filter_combo.pack(side="left", padx=(6, 4))
        filter_value_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=filter_value_var, width=18).pack(side="left", padx=(0, 6))

        visible_columns = {key: tk.BooleanVar(value=True) for key, _heading, _width in columns}
        columns_button = ttk.Menubutton(search_row, text="☷ Columns ▾")
        columns_menu = tk.Menu(columns_button, tearoff=False)
        def update_visible_columns():
            selected = [key for key, variable in visible_columns.items() if variable.get()]
            if not selected:
                first_key = columns[0][0]
                visible_columns[first_key].set(True)
                selected = [first_key]
            tree.configure(displaycolumns=selected)
        for key, heading, _width in columns:
            columns_menu.add_checkbutton(
                label=heading, variable=visible_columns[key], command=update_visible_columns
            )
        columns_button.configure(menu=columns_menu)
        columns_button.pack(side="left", padx=(0, 6))

        def print_current_table():
            displayed = list(tree.get_children(""))
            visible_keys = list(tree.cget("displaycolumns"))
            if visible_keys in (("#all",), ["#all"], "#all"):
                visible_keys = [key for key, _heading, _width in columns]
            visible_headers = [headings[key] for key in visible_keys]
            rows = [[tree.set(item, key) for key in visible_keys] for item in displayed]
            title = getattr(self, "print_title", self.__class__.__name__.removesuffix("Page").replace("_", " ").upper())
            try:
                path = self.app.services.reports.current_table_pdf(title, visible_headers, rows)
                if not open_or_print_pdf(path, print_now=True):
                    messagebox.showinfo(
                        "Table Report Opened",
                        "Windows does not have a direct PDF print action. The report was opened; use its Print command.",
                        parent=self,
                    )
            except Exception as exc:
                self.show_error(exc)
        ttk.Button(search_row, text="▣ Print current table", command=print_current_table).pack(side="left", padx=(0, 8))
        count_var = tk.StringVar(value="0 records")
        ttk.Label(search_row, textvariable=count_var, style="Hint.TLabel").pack(side="right")
        tree = ttk.Treeview(
            parent,
            columns=[c[0] for c in columns],
            show="headings",
            selectmode="browse",
        )
        tree.tag_configure("even", background="#F7FAFC")
        tree.tag_configure("odd", background="#FFFFFF")
        sort_reverse = {}
        all_items = []
        def sort_column(key):
            reverse = sort_reverse.get(key, False)
            def value(iid):
                raw = str(tree.set(iid, key)).replace(",", "").strip()
                try: return (0, float(raw))
                except ValueError: return (1, raw.casefold())
            all_items.sort(key=value, reverse=reverse)
            sort_reverse[key] = not reverse
            apply_filter()
        for key, heading, width in columns:
            tree.heading(key, text=heading, command=lambda k=key: sort_column(k))
            tree.column(key, width=width, minwidth=60, anchor="w")
        ybar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=1, column=0, sticky="nsew")
        ybar.grid(row=1, column=1, sticky="ns")
        xbar.grid(row=2, column=0, sticky="ew")
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        original_insert, original_delete = tree.insert, tree.delete
        filter_job = None
        def schedule_filter(*_args):
            """Coalesce bulk table updates into one filter pass.

            Page refreshes insert many rows synchronously.  Filtering on each
            insert caused an O(n²) repaint for large attendance lists.
            """
            nonlocal filter_job
            if filter_job is None:
                filter_job = tree.after_idle(run_filter)

        def tracked_insert(parent_iid, index, iid=None, **kw):
            if not kw.get("tags"): kw["tags"]=("even" if len(all_items)%2==0 else "odd",)
            created = original_insert(parent_iid, index, iid=iid, **kw); all_items.append(created); schedule_filter(); return created
        def tracked_delete(*items):
            for item in items:
                if item in all_items: all_items.remove(item)
            result = original_delete(*items); schedule_filter(); return result
        tree.insert, tree.delete = tracked_insert, tracked_delete
        def run_filter():
            nonlocal filter_job
            filter_job = None
            query = search_var.get().strip().casefold()
            search_key = next((key for key, heading in headings.items() if heading == search_column_var.get()), None)
            filter_key = next((key for key, heading in headings.items() if heading == filter_column_var.get()), None)
            filter_text = filter_value_var.get().strip().casefold()
            shown = 0
            for iid in all_items:
                search_values = [tree.set(iid, search_key)] if search_key else tree.item(iid, "values")
                filter_values = [tree.set(iid, filter_key)] if filter_key else tree.item(iid, "values")
                search_match = not query or any(query in str(value).casefold() for value in search_values)
                filter_match = not filter_text or any(filter_text in str(value).casefold() for value in filter_values)
                if search_match and filter_match:
                    tree.reattach(iid, "", "end"); shown += 1
                else: tree.detach(iid)
            count_var.set(f"{shown} record{'s' if shown != 1 else ''}")
        apply_filter = schedule_filter
        search_var.trace_add("write", schedule_filter)
        filter_value_var.trace_add("write", schedule_filter)
        search_combo.bind("<<ComboboxSelected>>", schedule_filter)
        filter_combo.bind("<<ComboboxSelected>>", schedule_filter)
        def clear_filters():
            search_var.set("")
            search_column_var.set("All columns")
            filter_column_var.set("All columns")
            filter_value_var.set("")
        ttk.Button(search_row, text="Clear", command=clear_filters).pack(side="left", padx=2)
        tree.search_var = search_var
        tree._all_items = all_items
        tree.filter_var = filter_value_var
        tree.filter_column_var = filter_column_var
        tree.visible_column_vars = visible_columns
        tree.bind("<Return>", lambda _event: tree.event_generate("<Double-1>"), add="+")
        tree.bind("<space>", lambda _event: tree.event_generate("<Double-1>"), add="+")
        return tree

    @staticmethod
    def clear_tree(tree: ttk.Treeview) -> None:
        # Filtered-out rows are detached and therefore absent from get_children().
        # Delete the tracked rows too, otherwise a later refresh can reuse an ID.
        items = list(getattr(tree, "_all_items", ())) or list(tree.get_children())
        if items:
            tree.delete(*items)


class SearchableCombobox(ttk.Combobox):
    """Editable combobox that filters its dropdown using any typed text."""

    _navigation_keys = {
        "Up", "Down", "Left", "Right", "Return", "Escape", "Tab",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Home", "End",
    }

    def __init__(self, parent, *, values=(), **kwargs):
        # A normal state is required so users can type a search. Entity forms
        # still validate the final value against their ID-to-label mapping.
        kwargs["state"] = "normal"
        super().__init__(parent, values=list(values), **kwargs)
        self._all_values = [str(value) for value in values]
        self.bind("<KeyRelease>", self._filter_dropdown, add="+")

    @staticmethod
    def matching_values(values: Iterable[str], query: str) -> list[str]:
        query = query.strip().casefold()
        choices = [str(value) for value in values]
        if not query:
            return choices
        return [value for value in choices if query in value.casefold()]

    def set_values(self, values: Iterable[str]) -> None:
        self._all_values = [str(value) for value in values]
        ttk.Combobox.configure(self, values=self._all_values)

    def configure(self, cnf=None, **kwargs):
        values = kwargs.get("values")
        if values is None and isinstance(cnf, dict):
            values = cnf.get("values")
        if values is not None:
            self._all_values = [str(value) for value in values]
            if isinstance(cnf, dict):
                cnf = dict(cnf)
                cnf["values"] = self._all_values
            else:
                kwargs["values"] = self._all_values
        return super().configure(cnf, **kwargs)

    config = configure

    def _filter_dropdown(self, event):
        if event.keysym in self._navigation_keys:
            return
        matches = self.matching_values(self._all_values, self.get())
        ttk.Combobox.configure(self, values=matches)
        # Do not post the dropdown automatically. On Windows, posting it after
        # every keypress moves focus into the list and interrupts typing after
        # one or two characters. The arrow button or Down key shows the fully
        # filtered results without stealing entry focus.


class FormBuilder:
    def __init__(self, parent: ttk.Frame, start_row: int = 0):
        self.parent = parent
        self.row = start_row

    def entry(self, label: str, variable: tk.StringVar, width: int = 28) -> ttk.Entry:
        ttk.Label(self.parent, text=label, style="Form.TLabel").grid(
            row=self.row, column=0, padx=5, pady=4, sticky="w"
        )
        if "date" in label.lower():
            widget = DateEntry(self.parent, variable, width)
        elif "time" in label.lower():
            widget = TimeEntry(self.parent, variable, width)
        else:
            widget = ttk.Entry(self.parent, textvariable=variable, width=width)
        widget.grid(row=self.row, column=1, padx=5, pady=4, sticky="ew")
        self.row += 1
        return widget

    def combo(
        self,
        label: str,
        variable: tk.StringVar,
        values: Iterable[str],
        width: int = 26,
        state: str = "readonly",
        searchable: bool = False,
    ) -> tk.Widget:
        ttk.Label(self.parent, text=label, style="Form.TLabel").grid(
            row=self.row, column=0, padx=5, pady=4, sticky="w"
        )
        if label.strip().lower().startswith("status"):
            widget = StatusRadio(self.parent, variable, list(values))
        elif searchable:
            widget = SearchableCombobox(
                self.parent,
                textvariable=variable,
                values=list(values),
                width=width,
            )
        else:
            widget = ttk.Combobox(
                self.parent, textvariable=variable, values=list(values),
                width=width, state=state,
            )
        widget.grid(row=self.row, column=1, padx=5, pady=4, sticky="ew")
        self.row += 1
        return widget


class StatusRadio(ttk.Frame):
    def __init__(self, parent, variable: tk.StringVar, values: list[str]):
        super().__init__(parent, style="Form.TFrame")
        for value in values:
            ttk.Radiobutton(self, text=value, value=value, variable=variable, style="Form.TRadiobutton").pack(side="left", padx=(0, 10))


class DateEntry(ttk.Frame):
    """Nepali Bikram Sambat YYYY/MM/DD entry with a calendar popup."""

    def __init__(self, parent, variable: tk.StringVar, width: int = 28):
        super().__init__(parent, style="Form.TFrame")
        self.variable = variable
        ttk.Entry(self, textvariable=variable, width=max(10, width - 4)).pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="📅", width=3, command=self.open_picker).pack(side="left", padx=(3, 0))

    def open_picker(self):
        DatePickerDialog(self, self.variable)


class TimeEntry(ttk.Frame):
    """A keyboard-friendly time field with a 12-hour time selector."""

    def __init__(self, parent, variable: tk.StringVar, width: int = 28):
        super().__init__(parent, style="Form.TFrame")
        self.variable = variable
        ttk.Entry(self, textvariable=variable, width=max(10, width - 4)).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(self, text="🕘", width=3, command=self.open_picker).pack(
            side="left", padx=(3, 0)
        )

    def open_picker(self):
        TimePickerDialog(self, self.variable)


class TimePickerDialog(tk.Toplevel):
    """Choose a consistent ``h:mm AM/PM`` value without manual typing."""

    def __init__(self, parent, variable: tk.StringVar):
        super().__init__(parent)
        self.variable = variable
        self.title("Select Time")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.configure(background="#EEF3F8")
        hour, minute, meridiem = self._parts(variable.get())
        self.hour = tk.StringVar(value=hour)
        self.minute = tk.StringVar(value=minute)
        self.meridiem = tk.StringVar(value=meridiem)

        body = ttk.Frame(self, padding=12, style="Form.TFrame")
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Hour", style="Form.TLabel").grid(row=0, column=0, padx=4, pady=4)
        hour_box = ttk.Combobox(body, textvariable=self.hour, values=[str(i) for i in range(1, 13)], width=5, state="readonly")
        hour_box.grid(row=1, column=0, padx=4, pady=(0, 10))
        ttk.Label(body, text="Minute", style="Form.TLabel").grid(row=0, column=1, padx=4, pady=4)
        ttk.Combobox(body, textvariable=self.minute, values=[f"{i:02d}" for i in range(60)], width=5, state="readonly").grid(row=1, column=1, padx=4, pady=(0, 10))
        ttk.Label(body, text="AM / PM", style="Form.TLabel").grid(row=0, column=2, padx=4, pady=4)
        ttk.Combobox(body, textvariable=self.meridiem, values=("AM", "PM"), width=5, state="readonly").grid(row=1, column=2, padx=4, pady=(0, 10))
        ttk.Button(body, text="Clear", command=self.clear).grid(row=2, column=0, sticky="w", padx=4)
        ttk.Button(body, text="Cancel", command=self.destroy).grid(row=2, column=1, padx=4)
        ttk.Button(body, text="Use Time", style="Accent.TButton", command=self.select).grid(row=2, column=2, sticky="e", padx=4)
        hour_box.focus_set()
        self.bind("<Return>", lambda _event: self.select())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.grab_set()

    @staticmethod
    def _parts(value: str) -> tuple[str, str, str]:
        try:
            time_part, meridiem = value.strip().upper().split()
            hour, minute = time_part.split(":")
            hour_value, minute_value = int(hour), int(minute)
            if 1 <= hour_value <= 12 and 0 <= minute_value <= 59 and meridiem in {"AM", "PM"}:
                return str(hour_value), f"{minute_value:02d}", meridiem
        except (AttributeError, ValueError):
            pass
        return "8", "00", "AM"

    def clear(self):
        self.variable.set("")
        self.destroy()

    def select(self):
        self.variable.set(f"{int(self.hour.get())}:{self.minute.get()} {self.meridiem.get()}")
        self.destroy()


class DatePickerDialog(tk.Toplevel):
    def __init__(self, parent, variable: tk.StringVar):
        super().__init__(parent)
        self.variable = variable
        self.title("Select Date")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        try:
            year,month,day=(int(part) for part in variable.get().split("/"));selected=nepali.date(year,month,day)
        except (ValueError,TypeError):
            selected = nepali.date.today()
        self.year, self.month = selected.year, selected.month
        self.header = ttk.Frame(self, padding=6)
        self.header.pack(fill="x")
        ttk.Button(self.header, text="‹", width=3, command=lambda: self.change_month(-1)).pack(side="left")
        self.title_label = ttk.Label(self.header, anchor="center")
        self.title_label.pack(side="left", fill="x", expand=True)
        ttk.Button(self.header, text="›", width=3, command=lambda: self.change_month(1)).pack(side="right")
        self.days = ttk.Frame(self, padding=(6, 0, 6, 6))
        self.days.pack()
        self.render()
        self.grab_set()

    def change_month(self, amount: int):
        value = self.month + amount
        self.year += (value - 1) // 12
        self.month = (value - 1) % 12 + 1
        self.render()

    def render(self):
        for child in self.days.winfo_children():
            child.destroy()
        month_names=("Baisakh","Jestha","Ashadh","Shrawan","Bhadra","Ashwin","Kartik","Mangsir","Poush","Magh","Falgun","Chaitra")
        self.title_label.configure(text=f"{month_names[self.month-1]} {self.year} BS")
        for column, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            ttk.Label(self.days, text=name, width=4, anchor="center").grid(row=0, column=column)
        first_weekday=nepali.date(self.year,self.month,1).weekday()
        days_in_month=32
        while days_in_month>27:
            try:nepali.date(self.year,self.month,days_in_month);break
            except ValueError:days_in_month-=1
        for day in range(1,days_in_month+1):
            position=first_weekday+day-1;row=position//7+1;column=position%7
            ttk.Button(self.days,text=str(day),width=3,command=lambda d=day:self.select(d)).grid(row=row,column=column,padx=1,pady=1)

    def select(self, day: int):
        self.variable.set(nepali.date(self.year, self.month, day).strftime("%Y/%m/%d"))
        self.destroy()


# ---------------------------------------------------------------------------
# Dashboard
