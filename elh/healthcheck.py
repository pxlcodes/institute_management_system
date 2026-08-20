"""Headless deployment health check: ``python -m elh.healthcheck``."""

from __future__ import annotations

import json

from elh.config import load_config
from elh.core.health import HealthService


def main() -> int:
    report = HealthService(load_config()).report()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
