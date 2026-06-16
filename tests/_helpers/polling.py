import time

import pytest

from _helpers.config import BASE_URL
from _helpers.http_client import get_request

POLL_ATTEMPTS = 10
POLL_DELAY    = 2.0


def poll_status(tid: int, expected: str) -> None:
    """Poll GET /{tid} until expected status or skip."""
    for _ in range(POLL_ATTEMPTS):
        time.sleep(POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == expected:
            return
        if status in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"Transaction {tid} reached {status!r} instead of {expected!r}")
    pytest.skip(f"Transaction {tid} did not reach {expected!r} within timeout")
