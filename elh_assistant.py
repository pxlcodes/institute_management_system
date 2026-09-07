"""
ELH Management System — AI Assistant & Interactive Query Console
Standalone Entry Point (Read-Only & Zero Mutation Safe)

Run:
  python elh_assistant.py         # Launches the High-Density Assistant GUI
  python elh_assistant.py --cli   # Runs Interactive Terminal CLI mode in command prompt
"""

from __future__ import annotations

import argparse
import sys

from elh.config import load_config
from elh.infrastructure import create_database
from elh.services.assistant import InstituteAssistant
from elh.services.container import ServiceContainer


def run_cli(assistant: InstituteAssistant) -> None:
    """Interactive command-line read-only query loop."""
    print("=" * 70)
    print("⚡ ELH Management System — AI Assistant & Query Console (CLI Mode)")
    print("   Database: Active Live Connection  ·  Safe Mode: READ-ONLY")
    print("=" * 70)
    print("Type /help for command shortcuts, or type 'exit' / 'quit' to close.\n")

    while True:
        try:
            prompt = input("elh-ai> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit", "q"}:
            print("Session ended.")
            break

        resp = assistant.execute(prompt)
        print(f"\n[{resp.title}] — {resp.badge}")
        print("-" * 50)
        print(resp.content)
        if resp.suggested_actions:
            print("\nSuggested: " + ", ".join(resp.suggested_actions))
        print("\n" + "=" * 70 + "\n")


def run_gui(config, db, services) -> None:
    """Launches the dedicated modern assistant GUI window."""
    import tkinter as tk
    from elh.models import UserSession
    from elh.services.auth import AuthService, ALL_PERMISSIONS
    from elh.ui.desktop.app import ManagementApp

    auth_service = AuthService(db, config)
    auth_service.ensure_initial_users()
    admin_row = db.query_one("SELECT * FROM app_users WHERE username = ?", (config.admin_username,))
    if admin_row:
        perms = auth_service.permissions_for_user(int(admin_row["id"]), admin_row["role"])
        session = UserSession(
            user_id=int(admin_row["id"]),
            username=admin_row["username"],
            role=admin_row["role"],
            display_name=admin_row["display_name"] or "Administrator",
            permissions=perms,
            must_change_password=bool(admin_row["must_change_password"]),
        )
    else:
        session = UserSession(
            user_id=2,
            username=config.admin_username or "admin",
            role="admin",
            display_name="Administrator",
            permissions=ALL_PERMISSIONS,
        )
    app = ManagementApp(config=config, db=db, session=session)
    app.title("ELH Management System — AI Assistant Console")
    app.show_page("AI Assistant")
    app.mainloop()


def main():
    parser = argparse.ArgumentParser(description="ELH Institute AI Assistant & Query Console")
    parser.add_argument("--cli", action="store_true", help="Launch in interactive command-line terminal mode")
    args = parser.parse_args()

    config = load_config()
    db = create_database(config)
    services = ServiceContainer.build(config, db)
    assistant = InstituteAssistant(services, db)

    if args.cli:
        run_cli(assistant)
    else:
        run_gui(config, db, services)


if __name__ == "__main__":
    main()
