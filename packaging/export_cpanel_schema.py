"""Export a clean MySQL initialization script for cPanel hosting.

This script queries the current schema and essential configuration seeds
(permissions, initial roles, settings, CMS defaults, subject list, migrations)
so a new cPanel MySQL database can be set up in 1-click via phpMyAdmin.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from elh.config import load_config
from elh.infrastructure import create_database


def export_cpanel_schema(output_path: Path) -> int:
    config = load_config()
    db = create_database(config)

    tables_rows = db.query("SHOW TABLES")
    if not tables_rows:
        print("No tables found in database.")
        return 1

    tables = [list(r.values())[0] for r in tables_rows]
    lines: list[str] = [
        "-- =====================================================================",
        "-- Expert Learning Hub (ELH) - cPanel Production Initial MySQL Database",
        "-- Import directly into phpMyAdmin on your cPanel account.",
        "-- =====================================================================",
        "SET FOREIGN_KEY_CHECKS=0;",
        "SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';",
        "SET NAMES utf8mb4;",
        "",
    ]

    for table in tables:
        create_row = db.query_one(f"SHOW CREATE TABLE `{table}`")
        if create_row:
            create_sql = create_row.get("Create Table") or list(create_row.values())[1]
            lines.append(f"DROP TABLE IF EXISTS `{table}`;")
            lines.append(f"{create_sql};")
            lines.append("")

    # Seed essential master and setup tables
    seed_tables = [
        "schema_migrations",
        "permissions",
        "role_permissions",
        "settings",
        "website_cms",
        "class_levels",
        "grades",
        "subjects",
        "routine_plans",
        "company_profile",
    ]

    for st in seed_tables:
        if st not in tables:
            continue
        rows = db.query(f"SELECT * FROM `{st}`")
        if not rows:
            continue
        cols = list(rows[0].keys())
        col_str = ", ".join(f"`{c}`" for c in cols)
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("\\", "\\\\").replace("'", "''")
                    vals.append(f"'{escaped}'")
            val_str = ", ".join(vals)
            lines.append(f"INSERT INTO `{st}` ({col_str}) VALUES ({val_str});")
        lines.append("")

    lines.append("SET FOREIGN_KEY_CHECKS=1;")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Successfully generated cPanel SQL schema: {output_path} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    target = Path("release") / "cpanel_initial_schema.sql"
    sys.exit(export_cpanel_schema(target))
