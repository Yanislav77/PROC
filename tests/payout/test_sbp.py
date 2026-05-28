"""
Тесты выплат методом sbp (type=payout, method=sbp).
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
@pytest.mark.tcid("PY-005")
def test_payout_sbp():
    """Выплата через СБП с phone и bank."""
    body = {
        **_BASE,
        "transaction_data": {"method": "sbp", "details": {"phone": "+79991234567", "bank": "Sberbank"}},
    }
    _assert_payout_ok(post_transaction(body))


@pytest.mark.tcid("PY-006")
def test_payout_sbp_without_details():
    """Выплата через СБП без details — все поля SbpDetails необязательны."""
    body = {**_BASE, "transaction_data": {"method": "sbp"}}
    _assert_payout_ok(post_transaction(body))


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
