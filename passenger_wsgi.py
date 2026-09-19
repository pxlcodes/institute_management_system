"""Phusion Passenger WSGI entry point for cPanel deployment.

cPanel 'Setup Python App' uses CloudLinux Passenger to serve Python applications.
This file converts the FastAPI ASGI application into a WSGI application using
a2wsgi, while providing comprehensive startup error trapping.
"""

from __future__ import annotations

import os
import sys
import traceback

# 1. Add application directory to sys.path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# 2. Ensure log folder exists
LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
ERROR_LOG_PATH = os.path.join(LOG_DIR, "passenger_error.log")

try:
    from a2wsgi import ASGIMiddleware
    from elh.config import load_config
    from elh.web.app import create_app

    config = load_config()
    asgi_app = create_app(config)
    application = ASGIMiddleware(asgi_app)

except Exception as exc:
    err_text = traceback.format_exc()
    try:
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n--- ELH Startup Error ---\n{err_text}\n")
    except Exception:
        pass

    def application(environ, start_response):
        status = "500 Internal Server Error"
        output = (
            f"<!doctype html><html><head><title>ELH Startup Error</title></head>"
            f"<body style='font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; padding: 40px; line-height: 1.6; color: #1e293b;'>"
            f"<h2 style='color: #dc2626;'>Expert Learning Hub - Application Startup Error</h2>"
            f"<p>The application encountered an error while launching under cPanel Passenger:</p>"
            f"<pre style='background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; font-size: 14px; overflow-x: auto;'>{exc}</pre>"
            f"<h3>Common Solutions:</h3>"
            f"<ol>"
            f"<li>Verify required dependencies are installed: <code>pip install -r requirements-cpanel.txt</code></li>"
            f"<li>Verify your MySQL database settings inside <code>.env</code></li>"
            f"<li>Check <code>logs/passenger_error.log</code> for the complete diagnostic traceback.</li>"
            f"</ol>"
            f"</body></html>"
        ).encode("utf-8")
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(output))),
        ]
        start_response(status, headers)
        return [output]
