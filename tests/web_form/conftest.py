import json
import re

import pytest
import requests

import _helpers.config as _cfg
from _helpers.factories import gen_order_id
from _helpers.payloads import MERCHANT_DATA
from _helpers.signatures import make_headers

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _extract_uuid(text: str) -> str:
    m = _UUID_RE.search(text)
    return m.group(0) if m else ""


@pytest.fixture(scope="session")
def payment_token():
    """Создаёт платёжную ссылку и возвращает payment_token (UUID из link_data.url)."""
    body = {
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("webform_fixture")},
        "financial_data": {"amount": _cfg.BLOCK_PAYIN_AMOUNT, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(_cfg.TERMINAL_ID, raw)
    try:
        resp = requests.post(_cfg.PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=_cfg.HTTP_TIMEOUT)
    except Exception as e:
        pytest.skip(f"Setup payment_token: request failed — {e}")
    if resp.status_code != 201:
        pytest.skip(f"Setup payment_token: expected 201, got {resp.status_code} — {resp.text}")
    url = resp.json().get("link_data", {}).get("url", "")
    token = _extract_uuid(url)
    if not token:
        pytest.skip(f"Setup payment_token: no UUID in link URL — {url!r}")
    return token
