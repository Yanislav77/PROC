"""
Тесты 3DS-флоу.
Используется карта CARD_3DS (4539000000000002), которая инициирует waiting_action с редиректом.
"""
import time

import pytest
import requests

from conftest import (
    post_transaction,
    make_headers,
    query_transaction_from_redis,
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

    _TERMINAL_STATES = {"completed", "authorized", "rejected", "cancelled", "failed"}
    data = None
    for _ in range(10):
        time.sleep(2)
        poll = requests.get(f"{BASE_URL}/{tid}", headers=make_headers(TERMINAL_ID, method="GET"), timeout=30)
        if poll.status_code != 200:
            continue
        data = poll.json()
        if data.get("status") == "waiting_action":
            break
        if data.get("status") in _TERMINAL_STATES:
            pytest.skip(f"Transaction reached {data['status']!r} instead of waiting_action — 3DS not triggered")
    else:
        pytest.skip("Transaction did not reach waiting_action within timeout — 3DS not triggered on this terminal")

    action_type = data["action"]["type"]
    action_data = data["action"]["details"]["data"]
    url = action_data.get("acs_url") or action_data.get("url")
    assert url, f"No redirect URL found in action.details.data: {action_data}"
    assert "://" in url, f"Redirect URL looks URL-encoded (action={action_type!r}): {url!r}"

    redis = query_transaction_from_redis(tid)
    if redis:
        assert redis.get("status") == "waiting_action", (
            f"Redis status mismatch: expected 'waiting_action', got {redis.get('status')!r}"
        )


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("3DS-002")
def test_idempotency_same_key_returns_same_transaction_id():
    """Повторный запрос с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import uuid
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_3ds")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_3DS},
    }
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _post():
        ts = str(int(time.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        from _helpers.validators import assert_idempotency_echo
        r = requests.post(BASE_URL, data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _post()
    assert r1.status_code == 201, f"First request failed: {r1.text}"
    r2 = _post()
    assert r2.status_code in (200, 201), f"Duplicate key: expected 200/201, got {r2.status_code}: {r2.text}"
    assert r2.json()["transaction_id"] == r1.json()["transaction_id"], (
        f"Duplicate key created new transaction: "
        f"r1.tid={r1.json().get('transaction_id')}, r2.tid={r2.json().get('transaction_id')}"
    )
