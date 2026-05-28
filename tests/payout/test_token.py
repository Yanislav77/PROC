"""
Тесты выплат методом token (type=payout, method=token).
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

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
    _assert_payout_ok(post_transaction(body))


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
    resp = post_transaction({**_VALID, "transaction_data": {"method": "token", "details": {"token": "00000000-0000-0000-0000-000000000000"}}})
    assert resp.status_code in (400, 404), f"Expected 400 or 404, got {resp.status_code}: {resp.text}"
