"""
Тесты выплат методом wallet (type=payout, method=wallet).
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
@pytest.mark.tcid("PY-007")
def test_payout_wallet():
    """Выплата на кошелёк — id обязателен, brand необязателен."""
    body = {**_BASE, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123"}}}
    _assert_payout_ok(post_transaction(body))


@pytest.mark.tcid("PY-008")
def test_payout_wallet_with_brand():
    """Выплата на кошелёк с необязательным полем brand."""
    body = {
        **_BASE,
        "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "PayPal"}},
    }
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — wallet
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-017")
def test_payout_wallet_missing_id():
    """Выплата wallet без id (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "wallet", "details": {"brand": "PayPal"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-018")
def test_payout_wallet_missing_details():
    """Выплата wallet без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "wallet"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# WALLET DETAILS — граничные случаи (13.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-095")
def test_payout_wallet_id_empty():
    """wallet.id = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": ""}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-096")
def test_payout_wallet_id_email():
    """wallet.id = email-адрес. Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "user@example.com"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-097")
def test_payout_wallet_id_phone():
    """wallet.id = номер телефона. Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "+79991234567"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-098")
def test_payout_wallet_brand_skrill():
    """wallet.brand = 'Skrill'. Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "Skrill"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-099")
def test_payout_wallet_brand_unknown():
    """wallet.brand = неизвестный провайдер. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "UnknownWallet"}}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-100")
def test_payout_wallet_brand_uppercase():
    """wallet.brand = 'PAYPAL' (верхний регистр). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "PAYPAL"}}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-109")
def test_payout_wallet_brand_neteller():
    """wallet.brand = 'Neteller'. Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "Neteller"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
