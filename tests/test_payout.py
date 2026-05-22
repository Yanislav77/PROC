"""
Тесты для выплат (type=payout).
POST /api/v1/transactions — методы: card, token, mobile, sbp, wallet, bank_account.
Включает: happy path и негативные сценарии по каждому методу.
"""
import uuid
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
@pytest.mark.tcid("PY-001")
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
# HAPPY PATH — mobile
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-003")
def test_payout_mobile():
    """Выплата методом mobile — phone обязателен, provider необязателен."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payout_ok(post_transaction(body))


@pytest.mark.tcid("PY-004")
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
# HAPPY PATH — wallet
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
# HAPPY PATH — bank_account
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-009")
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


@pytest.mark.tcid("PY-010")
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


@pytest.mark.tcid("PY-011")
def test_payout_bank_account_minimal():
    """Выплата на банковский счёт без details — все поля BankAccountDetails необязательны."""
    body = {**_BASE, "transaction_data": {"method": "bank_account"}}
    _assert_payout_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — card
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-012")
def test_payout_card_missing_pan():
    """Выплата на карту без pan (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card", "details": {"holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-013")
def test_payout_card_missing_holder():
    """Выплата на карту без holder (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card", "details": {"pan": "4111111111111111"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-014")
def test_payout_card_missing_details():
    """Выплата на карту без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


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
# НЕГАТИВНЫЕ — общие
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-021")
def test_payout_unknown_method():
    """Неизвестный метод выплаты. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "unknown_method"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-022")
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


@pytest.mark.tcid("PY-023")
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


@pytest.mark.tcid("PY-024")
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


# База с transaction_data для валидационных тестов (sbp — нет обязательных details)
_VALID = {**_BASE, "transaction_data": {"method": "sbp"}}


# ─────────────────────────────────────────────
# TYPE — граничные случаи (2.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-025")
def test_payout_type_payin():
    """type = 'payin' вместо 'payout'. Ожидается 400."""
    resp = post_transaction({**_VALID, "type": "payin"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-026")
def test_payout_type_null():
    """type = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "type": None})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-027")
def test_payout_type_empty():
    """type = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "type": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-028")
def test_payout_type_uppercase():
    """type = 'PAYOUT' (верхний регистр). Ожидается 400."""
    resp = post_transaction({**_VALID, "type": "PAYOUT"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# MERCHANT_DATA.ORDER_ID — граничные случаи (3.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-029")
def test_payout_missing_order_id():
    """merchant_data без order_id. Ожидается 400."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    resp = post_transaction({**_VALID, "merchant_data": merchant})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-030")
def test_payout_order_id_null():
    """merchant_data.order_id = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-031")
def test_payout_order_id_empty():
    """merchant_data.order_id = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-032")
def test_payout_order_id_spaces():
    """merchant_data.order_id = '   ' (только пробелы). Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "   "}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-033")
def test_payout_order_id_special_chars():
    """merchant_data.order_id = спецсимволы ORDER#@$%^&*(). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "ORDER#@$%^&*()"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-034")
def test_payout_order_id_256_chars():
    """merchant_data.order_id = 256 символов (граничное). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 256}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-035")
def test_payout_order_id_257_chars():
    """merchant_data.order_id = 257 символов (превышение лимита). Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 257}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-036")
def test_payout_order_id_cyrillic():
    """merchant_data.order_id = кириллица 'ЗАКАЗ-12345'. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "ЗАКАЗ-12345"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-037")
def test_payout_order_id_duplicate():
    """merchant_data.order_id = дубликат уже созданного заказа. Ожидается 201 или 409."""
    body = {**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_card"}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 409), f"Expected 201 or 409, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FINANCIAL_DATA.AMOUNT — граничные случаи (4.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-038")
def test_payout_amount_missing():
    """financial_data без поля amount. Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-039")
def test_payout_amount_min():
    """financial_data.amount = 1 (минимально допустимое). Ожидается 201."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1, "currency": "RUB"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-040")
def test_payout_amount_as_string():
    """financial_data.amount = '10000' (строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": "10000", "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-041")
def test_payout_amount_float():
    """financial_data.amount = 100.50 (дробное число). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 100.50, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-042")
def test_payout_amount_large():
    """financial_data.amount = 99999999999 (очень большое). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 99999999999, "currency": "RUB"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-043")
def test_payout_amount_exceeds_balance():
    """financial_data.amount = 999999999999999 (заведомо превышает баланс). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 999999999999999, "currency": "RUB"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FINANCIAL_DATA.CURRENCY — граничные случаи (5.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-044")
def test_payout_currency_usd():
    """financial_data.currency = 'USD'. Ожидается 201 или 400 (зависит от настроек терминала)."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "USD"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-045")
def test_payout_currency_eur():
    """financial_data.currency = 'EUR'. Ожидается 201 или 400 (зависит от настроек терминала)."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "EUR"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-046")
def test_payout_currency_missing():
    """financial_data без поля currency. Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-047")
def test_payout_currency_null():
    """financial_data.currency = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-048")
def test_payout_currency_lowercase():
    """financial_data.currency = 'rub' (нижний регистр). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "rub"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-049")
def test_payout_currency_rur():
    """financial_data.currency = 'RUR' (старый код рубля). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "RUR"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-050")
def test_payout_currency_numeric_code():
    """financial_data.currency = '643' (цифровой код). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "643"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CUSTOMER_DATA — граничные случаи (6.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-051")
def test_payout_missing_customer_data():
    """customer_data отсутствует. Ожидается 400."""
    body = {k: v for k, v in _VALID.items() if k != "customer_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-052")
def test_payout_invalid_email():
    """customer_data.contact_info.email = невалидный email. Ожидается 400."""
    customer = {**CUSTOMER_DATA, "contact_info": {"email": "not_an_email", "phone": "+79991234567"}}
    resp = post_transaction({**_VALID, "customer_data": customer})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-053")
def test_payout_invalid_phone_format():
    """customer_data.contact_info.phone не в формате E.164. Ожидается 400."""
    customer = {**CUSTOMER_DATA, "contact_info": {"email": "test@test.com", "phone": "89991234567"}}
    resp = post_transaction({**_VALID, "customer_data": customer})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TRANSACTION_DATA.METHOD — граничные случаи (7.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-054")
def test_payout_method_missing():
    """transaction_data без поля method. Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-055")
def test_payout_method_null():
    """transaction_data.method = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-056")
def test_payout_method_uppercase():
    """transaction_data.method = 'CARD' (верхний регистр). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "CARD"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ОПЦИОНАЛЬНЫЕ ПОЛЯ MERCHANT_DATA (8.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-057")
def test_payout_description_long():
    """merchant_data.description = 1000 символов. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "description": "x" * 1000}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-058")
def test_payout_description_special_chars():
    """merchant_data.description = спецсимволы. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "description": "Test!@#$%^&*()_+[]{}|;':\",.<>?"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-059")
def test_payout_webhook_url_valid_https():
    """merchant_data.webhook_url = валидный HTTPS URL. Ожидается 201."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "https://example.com/webhook"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-060")
def test_payout_webhook_url_invalid():
    """merchant_data.webhook_url = невалидный URL. Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "not_a_url"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-061")
def test_payout_webhook_url_http():
    """merchant_data.webhook_url = HTTP URL (небезопасный). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "http://example.com/webhook"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-062")
def test_payout_return_url_valid_https():
    """merchant_data.return_url = валидный HTTPS URL. Ожидается 201."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "return_url": "https://example.com/return"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-063")
def test_payout_return_url_with_query_params():
    """merchant_data.return_url = URL с query-параметрами. Ожидается 201."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "return_url": "https://example.com/return?order=123&status=ok"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CARD DETAILS — граничные случаи (9.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-064")
def test_payout_card_pan_empty():
    """card.pan = '' (пустая строка). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-065")
def test_payout_card_pan_invalid_luhn():
    """card.pan не проходит проверку Luhn. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111111111111112", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-066")
def test_payout_card_pan_too_short():
    """card.pan менее 13 цифр. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "411111111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-067")
def test_payout_card_pan_too_long():
    """card.pan более 19 цифр. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "41111111111111111111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-068")
def test_payout_card_pan_with_spaces():
    """card.pan = '4111 1111 1111 1111' (с пробелами). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111 1111 1111 1111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-069")
def test_payout_card_pan_with_dashes():
    """card.pan = '4111-1111-1111-1111' (с дефисами). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111-1111-1111-1111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-070")
def test_payout_card_holder_empty():
    """card.holder = '' (пустая строка). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": ""}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-071")
def test_payout_card_holder_spaces():
    """card.holder = '   ' (только пробелы). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "   "}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-072")
def test_payout_card_holder_cyrillic():
    """card.holder = 'ИВАН ПЕТРОВ' (кириллица). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "ИВАН ПЕТРОВ"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-073")
def test_payout_card_holder_with_dot():
    """card.holder = 'JOHN DOE JR.' (с точкой). Ожидается 201 или 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE JR."}}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-074")
def test_payout_card_expiry_month_13():
    """card.expiry_month = '13' (невалидный месяц). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "4111111111111111", "holder": "JOHN DOE",
        "expiry_month": "13", "expiry_year": "30", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-075")
def test_payout_card_expiry_month_00():
    """card.expiry_month = '00'. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "4111111111111111", "holder": "JOHN DOE",
        "expiry_month": "00", "expiry_year": "30", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-076")
def test_payout_card_expiry_month_single_digit():
    """card.expiry_month = '5' (без ведущего нуля). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "4111111111111111", "holder": "JOHN DOE",
        "expiry_month": "5", "expiry_year": "30", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-077")
def test_payout_card_expired():
    """Истёкший срок действия карты (год 20). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "4111111111111111", "holder": "JOHN DOE",
        "expiry_month": "01", "expiry_year": "20", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-078")
def test_payout_card_expiry_year_far_future():
    """card.expiry_year = '50' (слишком далёкий год). Ожидается 201 или 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "4111111111111111", "holder": "JOHN DOE",
        "expiry_month": "01", "expiry_year": "50", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


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


# ─────────────────────────────────────────────
# ПОЛЯ ОТВЕТА (16.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-101")
def test_payout_response_merchant_order_id():
    """В ответе merchant_data.order_id совпадает с отправленным значением."""
    body = {**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "order_resp_check_py"}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("merchant_data", {}).get("order_id") == "order_resp_check_py"


@pytest.mark.tcid("PY-102")
def test_payout_response_financial_data():
    """В ответе financial_data.amount и currency соответствуют запросу."""
    resp = post_transaction(_VALID)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    fd = data.get("financial_data", {})
    assert fd.get("amount") == 1000
    assert fd.get("currency") == "RUB"


@pytest.mark.tcid("PY-103")
def test_payout_response_created_at():
    """В ответе присутствует created_at в формате ISO 8601."""
    from datetime import datetime
    resp = post_transaction(_VALID)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    created_at = data.get("created_at")
    assert created_at is not None, "created_at отсутствует в ответе"
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"created_at не является валидным ISO 8601: {created_at}")


@pytest.mark.tcid("PY-104")
def test_payout_response_mode():
    """В ответе transaction_data.mode равен 'test' или 'live'."""
    resp = post_transaction(_VALID)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    mode = data.get("transaction_data", {}).get("mode")
    assert mode in ("test", "live"), f"Неожиданное значение mode: {mode}"


@pytest.mark.tcid("PY-105")
def test_payout_response_method():
    """В ответе transaction_data.method совпадает с отправленным методом."""
    resp = post_transaction(_VALID)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    method = data.get("transaction_data", {}).get("method")
    assert method == "sbp", f"Ожидался method='sbp', получен: {method}"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ КЕЙСЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-106")
def test_payout_type_missing():
    """type полностью отсутствует в теле запроса. Ожидается 400."""
    body = {k: v for k, v in _VALID.items() if k != "type"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-107")
def test_payout_description_emoji():
    """merchant_data.description = эмодзи. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "description": "Выплата 🎉💳✅"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-108")
def test_payout_webhook_url_localhost():
    """merchant_data.webhook_url = localhost URL. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "http://localhost:8080/webhook"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-109")
def test_payout_wallet_brand_neteller():
    """wallet.brand = 'Neteller'. Ожидается 201."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "wallet", "details": {"id": "wallet_abc123", "brand": "Neteller"}}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-110")
def test_payout_bank_account_no_account_number():
    """bank_account.details без account_number — все поля необязательны. Ожидается 201."""
    body = {**_VALID, "transaction_data": {"method": "bank_account", "details": {
        "swift_code": "SABRRUMM",
        "bank_name": "Sberbank",
        "account_holder_name": "JOHN DOE",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (PY-111 … PY-120)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-111")
def test_payout_response_type_is_payout():
    """Payout — type в ответе равен 'payout'."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_type_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert resp.json().get("type") == "payout"


@pytest.mark.tcid("PY-112")
def test_payout_response_content_type_is_json():
    """Payout — Content-Type ответа содержит application/json."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_ct_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert "application/json" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("PY-113")
def test_payout_card_without_expiry_fields():
    """Payout card без expiry_month/expiry_year — поля опциональны для payout. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_no_exp_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-114")
def test_payout_sbp_holder_field():
    """Payout SBP с полем holder в details. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_sbp_h_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "sbp", "details": {
                "phone": "+79991234567", "bank": "Sberbank", "holder": "IVAN IVANOV"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-115")
def test_payout_sbp_missing_details():
    """Payout SBP без details. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_sbp_nd_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-116")
def test_payout_financial_data_null_returns_400():
    """Payout с financial_data = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_fd_null_{uuid.uuid4().hex[:6]}"},
            "financial_data": None, "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-117")
def test_payout_customer_data_null_returns_400():
    """Payout с customer_data = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_cd_null_{uuid.uuid4().hex[:6]}"},
            "customer_data": None, "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-118")
def test_payout_merchant_data_null_returns_400():
    """Payout с merchant_data = null. Ожидается 400."""
    body = {**_BASE, "merchant_data": None, "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-119")
def test_payout_transaction_data_null_returns_400():
    """Payout с transaction_data = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_td_null_{uuid.uuid4().hex[:6]}"},
            "transaction_data": None}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-120")
def test_payout_card_response_has_transaction_id():
    """Payout card — ответ содержит transaction_id."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_py_tid_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert "transaction_id" in resp.json(), "transaction_id отсутствует в ответе payout"
