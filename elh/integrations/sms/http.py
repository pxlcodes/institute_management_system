from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def post_form(endpoint: str, payload: dict[str, str], timeout: int) -> tuple[int, dict, str]:
    request = Request(
        endpoint,
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ELH-Management-System/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=max(2, timeout)) as response:
            status = int(response.status)
            text = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        text = exc.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        raise ConnectionError(f"SMS gateway could not be reached: {exc}") from exc
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {}
    return status, data, text[:1000]
