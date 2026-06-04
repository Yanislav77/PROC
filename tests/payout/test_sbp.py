"""
Тесты выплат методом sbp (type=payout, method=sbp).
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
@pytest.mark.tcid("PY-005")
def test_payout_sbp():
    """Выплата через СБП с phone и bank."""
    body = {
        **_BASE,
        "transaction_data": {"method": "sbp", "details": {"phone": "+79991234567", "bank": "Sberbank"}},
    }
    data = _assert_payout_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "processing":
        poll_status(tid, "processing")


@pytest.mark.tcid("PY-006")
def test_payout_sbp_without_details():
    """Выплата через СБП без details — все поля SbpDetails необязательны."""
    body = {**_BASE, "transaction_data": {"method": "sbp"}}
    data = _assert_payout_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "processing":
        poll_status(tid, "processing")


# ─────────────────────────────────────────────
# SBP DETAILS — граничные случаи (12.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-091")
def test_payout_sbp_phone_only():
    """sbp с только phone (bank отсутствует). Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "sbp", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-092")
def test_payout_sbp_bank_only():
    """sbp с только bank (phone отсутствует). Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "sbp", "details": {"bank": "Sberbank"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-093")
def test_payout_sbp_phone_not_e164():
    """sbp.phone = '89998887766' (не E.164 формат). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "sbp", "details": {"phone": "89998887766"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-094")
def test_payout_sbp_bank_long_name():
    """sbp.bank = длинное официальное название. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "sbp", "details": {"bank": "Public Joint Stock Company Sberbank"}}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-114")
def test_payout_sbp_holder_field():
    """Payout SBP с полем holder в details. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_sbp_h")},
            "transaction_data": {"method": "sbp", "details": {
                "phone": "+79991234567", "bank": "Sberbank", "holder": "IVAN IVANOV"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-115")
def test_payout_sbp_missing_details():
    """Payout SBP без details. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_sbp_nd")},
            "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-144")
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
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_py_sbp")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "sbp", "details": {"phone": "+79991234567", "bank": "Sberbank"}},
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
