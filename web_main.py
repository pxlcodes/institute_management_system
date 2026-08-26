"""Browser application entry point: python -m uvicorn web_main:app --host 0.0.0.0 --port 8080."""

from elh.web.app import create_app

app = create_app()
