"""Automated cPanel web deployment bundler.

Creates a clean, self-contained deployment ZIP archive for cPanel CloudLinux
Passenger hosting environments.
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT_DIR / "release"
STAGING_DIR = ROOT_DIR / "build" / "cpanel_staging"
OUTPUT_ZIP = RELEASE_DIR / "elh_cpanel_web_deployment.zip"


def build_cpanel_package() -> int:
    print("Building cPanel Web Deployment Package...")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy elh package
    print("  Copying elh backend package...")
    shutil.copytree(
        ROOT_DIR / "elh",
        STAGING_DIR / "elh",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    # 2. Copy root Python entry points and configs
    print("  Copying root entry points and configuration templates...")
    shutil.copy2(ROOT_DIR / "web_main.py", STAGING_DIR / "web_main.py")
    shutil.copy2(ROOT_DIR / "passenger_wsgi.py", STAGING_DIR / "passenger_wsgi.py")
    shutil.copy2(ROOT_DIR / "cpanel.htaccess", STAGING_DIR / ".htaccess")
    shutil.copy2(ROOT_DIR / "requirements-cpanel.txt", STAGING_DIR / "requirements-cpanel.txt")
    shutil.copy2(ROOT_DIR / "requirements-cpanel.txt", STAGING_DIR / "requirements.txt")
    shutil.copy2(ROOT_DIR / ".env.cpanel.example", STAGING_DIR / ".env.example")
    shutil.copy2(ROOT_DIR / ".env.cpanel.example", STAGING_DIR / "environment.example")

    # 3. Copy web_dist and web frontends
    print("  Copying web_dist (modern frontend) and web (fallback)...")
    if (ROOT_DIR / "web_dist").exists():
        shutil.copytree(
            ROOT_DIR / "web_dist",
            STAGING_DIR / "web_dist",
            ignore=shutil.ignore_patterns(".git*", "*.tmp"),
        )
    if (ROOT_DIR / "web").exists():
        shutil.copytree(
            ROOT_DIR / "web",
            STAGING_DIR / "web",
            ignore=shutil.ignore_patterns(".git*", "*.tmp"),
        )

    # 4. Copy templates
    print("  Copying certificate Word templates...")
    templates_target = STAGING_DIR / "templates"
    templates_target.mkdir(parents=True, exist_ok=True)
    for f in (ROOT_DIR / "templates").glob("*.docx"):
        shutil.copy2(f, templates_target / f.name)

    # 5. Copy cPanel initial schema SQL
    schema_sql = RELEASE_DIR / "cpanel_initial_schema.sql"
    if schema_sql.exists():
        shutil.copy2(schema_sql, STAGING_DIR / "cpanel_initial_schema.sql")

    # 6. Copy deployment guide if exists
    guide_path = ROOT_DIR / "CPANEL_DEPLOYMENT_GUIDE.md"
    if guide_path.exists():
        shutil.copy2(guide_path, STAGING_DIR / "CPANEL_DEPLOYMENT_GUIDE.md")

    # 7. Create empty runtime directories with .gitkeep
    for sub in ("logs", "backups", "output/certificates", "output/pdf"):
        d = STAGING_DIR / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()

    # 8. Create ZIP archive
    print(f"  Compressing into {OUTPUT_ZIP} ...")
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(STAGING_DIR):
            for file in files:
                abs_file = Path(root) / file
                rel_path = abs_file.relative_to(STAGING_DIR)
                zf.write(abs_file, rel_path)

    zip_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"cPanel web deployment package created: {OUTPUT_ZIP} ({zip_size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(build_cpanel_package())
