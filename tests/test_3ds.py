"""
Тесты 3DS-флоу.
Используется карта CARD_3DS (CVV 550), которая инициирует waiting_action с редиректом.
"""
import time

import pytest
import requests

from conftest import (
    post_transaction,
    make_headers,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_3DS,
    THREED,
    gen_order_id,
)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("3DS-001")
def test_3ds_redirect_url_not_encoded():
    """3DS-карта: redirect URL в ответе GET /transactions/{id} не должен быть URL-закодирован."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_url_check")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_3DS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    tid = resp.json()["transaction_id"]

    time.sleep(3)
    poll = requests.get(f"{BASE_URL}/{tid}", headers=make_headers(TERMINAL_ID, method="GET"), timeout=30)
    assert poll.status_code == 200, f"Poll failed: {poll.text}"
    data = poll.json()

    assert data["status"] == "waiting_action", f"Expected waiting_action, got {data['status']}"
    action_type = data["action"]["type"]
    action_data = data["action"]["details"]["data"]
    url = action_data.get("acs_url") or action_data.get("url")
    assert url, f"No redirect URL found in action.details.data: {action_data}"
    assert "://" in url, f"Redirect URL looks URL-encoded (action={action_type!r}): {url!r}"
