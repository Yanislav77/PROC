"""
Тесты выплат методом mobile (type=payout, method=mobile).
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
@pytest.mark.tcid("PY-003")
def test_payout_mobile():
    """Выплата методом mobile — phone обязателен, provider необязателен."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    data = _assert_payout_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "processing":
        poll_status(tid, "processing")


@pytest.mark.tcid("PY-004")
def test_payout_mobile_with_provider():
    """Выплата mobile с необязательным полем provider."""
    body = {
        **_BASE,
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "Beeline"}},
    }
    data = _assert_payout_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "processing":
        poll_status(tid, "processing")


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — mobile
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-015")
def test_payout_mobile_missing_phone():
    """Выплата mobile без phone (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"provider": "Beeline"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-016")
def test_payout_mobile_missing_details():
    """Выплата mobile без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# MOBILE DETAILS — граничные случаи (11.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-083")
def test_payout_mobile_phone_empty():
    """mobile.phone = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": ""}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-084")
def test_payout_mobile_phone_no_country_code():
    """mobile.phone = '9991234567' (без кода страны). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "9991234567"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-085")
def test_payout_mobile_phone_8_prefix():
    """mobile.phone = '89991234567' (8 вместо +7). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "89991234567"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-086")
def test_payout_mobile_phone_too_short():
    """mobile.phone = '+7' (слишком короткий). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "+7"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-087")
def test_payout_mobile_phone_too_long():
    """mobile.phone = '+79991234567890' (слишком длинный). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567890"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-088")
def test_payout_mobile_phone_with_spaces():
    """mobile.phone = '+7 999 123-45-67' (с пробелами и дефисами). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "+7 999 123-45-67"}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-089")
def test_payout_mobile_provider_mts():
    """mobile.provider = 'MTS'. Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-090")
def test_payout_mobile_provider_custom():
    """mobile.provider = 'CustomOperator' (нестандартный). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "CustomOperator"}}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-143")
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
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_py_mob")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}},
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
