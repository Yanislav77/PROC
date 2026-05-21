"""
Тесты для выплат (type=payout).
POST /api/v1/transactions — методы: card, token, mobile, sbp, wallet, bank_account.
Включает: happy path и негативные сценарии по каждому методу.
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
)

_BASE = {
    "type": "payout",
    "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}


def _assert_payout_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payout"
    return data


# ─────────────────────────────────────────────
# HAPPY PATH — card
# ─────────────────────────────────────────────
def test_payout_card():
    """Выплата на карту — pan и holder обязательны."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_card"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# HAPPY PATH — token
# ─────────────────────────────────────────────
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
# HAPPY PATH — mobile
# ─────────────────────────────────────────────
def test_payout_mobile():
    """Выплата методом mobile — phone обязателен, provider необязателен."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payout_ok(post_transaction(body))


def test_payout_mobile_with_provider():
    """Выплата mobile с необязательным полем provider."""
    body = {
        **_BASE,
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "Beeline"}},
    }
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# HAPPY PATH — sbp
# ─────────────────────────────────────────────
def test_payout_sbp():
    """Выплата через СБП с phone и bank."""
    body = {
        **_BASE,
        "transaction_data": {"method": "sbp", "details": {"phone": "+79991234567", "bank": "Sberbank"}},
    }
    _assert_payout_ok(post_transaction(body))


def test_payout_sbp_without_details():
    """Выплата через СБП без details — все поля SbpDetails необязательны."""
    body = {**_BASE, "transaction_data": {"method": "sbp"}}
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# HAPPY PATH — wallet
# ─────────────────────────────────────────────
def test_payout_wallet():
    """Выплата на кошелёк — id обязателен, brand необязателен."""
    body = {**_BASE, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123"}}}
    _assert_payout_ok(post_transaction(body))


def test_payout_wallet_with_brand():
    """Выплата на кошелёк с необязательным полем brand."""
    body = {
        **_BASE,
        "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "PayPal"}},
    }
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# HAPPY PATH — bank_account
# ─────────────────────────────────────────────
def test_payout_bank_account():
    """Выплата на банковский счёт с SWIFT-реквизитами."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "bank_account",
            "details": {
                "account_number": "40702810000000012345",
                "swift_code": "SABRRUMM",
                "bank_name": "Sberbank",
                "account_holder_name": "JOHN DOE",
            },
        },
    }
    _assert_payout_ok(post_transaction(body))


def test_payout_bank_account_pix():
    """Выплата через PIX (Бразилия)."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "bank_account",
            "details": {"pix_key": "user@example.com", "account_holder_name": "JOHN DOE"},
        },
    }
    _assert_payout_ok(post_transaction(body))


def test_payout_bank_account_minimal():
    """Выплата на банковский счёт без details — все поля BankAccountDetails необязательны."""
    body = {**_BASE, "transaction_data": {"method": "bank_account"}}
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — card
# ─────────────────────────────────────────────
def test_payout_card_missing_pan():
    """Выплата на карту без pan (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card", "details": {"holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_card_missing_holder():
    """Выплата на карту без holder (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card", "details": {"pan": "4111111111111111"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_card_missing_details():
    """Выплата на карту без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — mobile
# ─────────────────────────────────────────────
def test_payout_mobile_missing_phone():
    """Выплата mobile без phone (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"provider": "Beeline"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_mobile_missing_details():
    """Выплата mobile без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — wallet
# ─────────────────────────────────────────────
def test_payout_wallet_missing_id():
    """Выплата wallet без id (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "wallet", "details": {"brand": "PayPal"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_wallet_missing_details():
    """Выплата wallet без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "wallet"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — token
# ─────────────────────────────────────────────
def test_payout_token_missing_token():
    """Выплата по токену без поля token. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "token", "details": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_token_missing_details():
    """Выплата по токену без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "token"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — общие
# ─────────────────────────────────────────────
def test_payout_unknown_method():
    """Неизвестный метод выплаты. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "unknown_method"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_negative_amount():
    """Выплата с отрицательной суммой. Ожидается 400."""
    body = {
        **_BASE,
        "financial_data": {"amount": -1000, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_zero_amount():
    """Выплата с нулевой суммой. Ожидается 400."""
    body = {
        **_BASE,
        "financial_data": {"amount": 0, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_payout_invalid_currency():
    """Выплата с невалидным кодом валюты. Ожидается 400."""
    body = {
        **_BASE,
        "financial_data": {"amount": 1000, "currency": "INVALID"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
