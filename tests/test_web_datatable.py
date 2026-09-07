import asyncio
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request

class WebDataTableTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            secret_key="test-secret-key-123456",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.app = create_app(self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_datatable_assets(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        self.assertIn("class AdvancedDataTable", js)
        self.assertIn("parseNumeric", js)
        self.assertIn("copyToClipboard", js)
        self.assertIn("exportCsv", js)
        self.assertIn("printTable", js)
        self.assertIn("dt-table", js)
        self.assertIn("dt-toolbar", js)
        self.assertIn("dt-pagination", js)

        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/styles.css"))
        self.assertEqual(status, 200)
        css = body.decode("utf-8")
        self.assertIn(".advanced-datatable-container", css)
        self.assertIn(".dt-toolbar", css)
        self.assertIn("th.dt-sortable", css)
        self.assertIn(".dt-page-btn", css)
        self.assertIn(".dt-toast", css)


if __name__ == "__main__":
    unittest.main()

