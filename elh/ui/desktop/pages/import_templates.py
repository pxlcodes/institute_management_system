from __future__ import annotations
import csv
from tkinter import filedialog,messagebox


class ImportTemplateMixin:
    def download_csv_template(self,filename:str,headers:list[str],notes:str=""):
        path=filedialog.asksaveasfilename(parent=self,title="Save Import Template",initialfile=filename,defaultextension=".csv",filetypes=[("CSV files","*.csv")])
        if not path:return
        with open(path,"w",newline="",encoding="utf-8-sig") as target:csv.writer(target).writerow(headers)
        messagebox.showinfo("Template Saved",f"Blank import template saved to:\n{path}"+(f"\n\n{notes}" if notes else ""),parent=self)

    @staticmethod
    def require_headers(reader,required:list[str]):
        present=set(reader.fieldnames or []);missing=[name for name in required if name not in present]
        if missing:raise ValueError("Invalid import format. Missing columns: "+", ".join(missing))
