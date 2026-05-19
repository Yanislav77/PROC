"""
Тесты для всех методов выплат (type=payout).
Spec: PaymentRequestPayout → методы: card, bank_account, token, mobile, sbp, wallet

Метод card (базовый happy path) покрыт в test_happy_path.py::test_payout.
Здесь — остальные методы и негативные кейсы по обязательным полям.
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
)

_PAYOUT_BASE = {
    "type": "payout",
    "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}


def assert_payout_success(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data
    assert data["type"] == "payout"
    assert "status" in data
    return data


# ─────────────────────────────────────────────
# HAPPY PATH — методы выплат
# ─────────────────────────────────────────────
def test_payout_mobile():
    """Выплата методом mobile — номер телефона обязателен, operator необязателен."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "mobile",
            "details": {"phone": "+79991234567"},
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_mobile_with_provider():
    """Выплата методом mobile с необязательным полем provider."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "mobile",
            "details": {"phone": "+79991234567", "provider": "Beeline"},
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_sbp_with_phone_and_bank():
    """Выплата через СБП (method=sbp) с phone и bank (оба необязательны по схеме)."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "sbp",
            "details": {"phone": "+79991234567", "bank": "Sberbank"},
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_sbp_without_details():
    """Выплата через СБП без details — все поля SbpDetails необязательны."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "sbp"},
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_wallet():
    """Выплата на кошелёк (method=wallet) — id обязателен, brand необязателен."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "wallet",
            "details": {"id": "wallet_abc123"},
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_wallet_with_brand():
    """Выплата на кошелёк с необязательным полем brand."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "wallet",
            "details": {"id": "wallet_abc123", "brand": "PayPal"},
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_bank_account_with_swift():
    """Выплата на банковский счёт с SWIFT (все поля BankAccountDetails необязательны)."""
    body = {
        **_PAYOUT_BASE,
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
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_bank_account_with_pix():
    """Выплата на банковский счёт через PIX (Бразилия)."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "bank_account",
            "details": {
                "pix_key": "user@example.com",
                "account_holder_name": "JOHN DOE",
            },
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_bank_account_minimal():
    """Выплата на банковский счёт без details — все поля BankAccountDetails необязательны."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "bank_account"},
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


def test_payout_token():
    """Выплата по сохранённому токену (method=token) — token обязателен."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
        },
    }
    resp = post_transaction(body)
    assert_payout_success(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — обязательные поля методов
# ─────────────────────────────────────────────
def test_payout_card_missing_pan():
    """Выплата на карту без pan (обязательное поле). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "card",
            "details": {"holder": "JOHN DOE"},
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_card_missing_holder():
    """Выплата на карту без holder (обязательное поле). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "card",
            "details": {"pan": "4111111111111111"},
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_card_missing_details():
    """Выплата на карту без details (обязательное). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "card"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_mobile_missing_phone():
    """Выплата mobile без phone (обязательное поле). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "mobile",
            "details": {"provider": "Beeline"},
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_mobile_missing_details():
    """Выплата mobile без details (обязательное). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "mobile"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_wallet_missing_id():
    """Выплата wallet без id (обязательное поле). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "wallet",
            "details": {"brand": "PayPal"},
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_wallet_missing_details():
    """Выплата wallet без details (обязательное). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "wallet"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_token_missing_token():
    """Выплата по токену без поля token (обязательное). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {
            "method": "token",
            "details": {},
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_token_missing_details():
    """Выплата по токену без details (обязательное). Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "token"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_unknown_method():
    """Выплата с неизвестным методом. Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "transaction_data": {"method": "unknown_method"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — финансовые данные (payout)
# ─────────────────────────────────────────────
def test_payout_negative_amount():
    """Выплата с отрицательной суммой. Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "financial_data": {"amount": -1000, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_zero_amount():
    """Выплата с нулевой суммой. Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "financial_data": {"amount": 0, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payout_invalid_currency():
    """Выплата с невалидным кодом валюты. Ожидается 422."""
    body = {
        **_PAYOUT_BASE,
        "financial_data": {"amount": 1000, "currency": "INVALID"},
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
