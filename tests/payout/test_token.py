"""
Тесты выплат методом token (type=payout, method=token).
"""
import pytest

from conftest import (
    post_transaction,
    get_request,
    BASE_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)
from _helpers.polling import poll_status

_BASE = {
    "type": "payout",
    "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}

_VALID = {**_BASE, "transaction_data": {"method": "sbp"}}


def _assert_payout_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payout"
    return data


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-002")
def test_payout_token():
    """Выплата по сохранённому токену (method=token)."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
        },
    }
    data = _assert_payout_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "processing":
        poll_status(tid, "processing")


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — token
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-019")
def test_payout_token_missing_token():
    """Выплата по токену без поля token. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "token", "details": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-020")
def test_payout_token_missing_details():
    """Выплата по токену без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "token"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TOKEN DETAILS — граничные случаи (10.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-079")
def test_payout_token_empty_string():
    """token = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "token", "details": {"token": ""}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-080")
def test_payout_token_not_uuid():
    """token = произвольная строка, не UUID. Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "token", "details": {"token": "not-a-valid-uuid-format"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-081")
def test_payout_token_uppercase_uuid():
    """token = UUID с заглавными буквами. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "token", "details": {"token": "B928586B-E6EC-4400-9039-E36F19C0094C"}}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-082")
def test_payout_token_nonexistent():
    """token = несуществующий UUID (все нули). Ожидается 400 или 404."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "token", "details": {"token": "00000000-0000-4000-8000-000000000000"}}})
    assert resp.status_code in (400, 404), f"Expected 400 or 404, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-147")
def test_idempotency_same_key_returns_same_transaction_id():
    """Повторный запрос с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import time
    import uuid
    import requests as _req
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_py_tok")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
        },
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
        r = _req.post(BASE_URL, data=raw, headers=h, timeout=30)
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


# ─────────────────────────────────────────────
# РЕГРЕСС — копейки
# ─────────────────────────────────────────────

@pytest.mark.tcid("PY-153")
def test_payout_token_amount_with_kopecks():
    """Выплата по токену — сумма с копейками (1050 = 10.50 руб). Ожидается 201 и amount=1050 в ответе."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("kopecks")},
        "financial_data": {"amount": 1050, "currency": "RUB"},
        "transaction_data": {"method": "token", "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"}},
    }
    data = _assert_payout_ok(post_transaction(body))
    assert data["financial_data"]["amount"] == 1050
