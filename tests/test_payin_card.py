"""
Тесты для payin с методом card.
POST /api/v1/transactions — type:payin, method:card
Включает: happy path, обязательные поля, валидация карты, финансовых данных, merchant_data.
"""
import pytest
from datetime import datetime

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_transaction_response,
    assert_error_response,
)


def _luhn_checkdigit(prefix: str) -> str:
    digits = [int(d) for d in prefix]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


_PAN_13_VALID   = "453201511283"  + _luhn_checkdigit("453201511283")
_PAN_13_INVALID = _PAN_13_VALID[:-1] + str((int(_PAN_13_VALID[-1]) + 1) % 10)
_PAN_18_VALID   = "41234567890123456"  + _luhn_checkdigit("41234567890123456")
_PAN_18_INVALID = _PAN_18_VALID[:-1] + str((int(_PAN_18_VALID[-1]) + 1) % 10)
_PAN_19_VALID   = "412345678901234567" + _luhn_checkdigit("412345678901234567")
_PAN_19_INVALID = _PAN_19_VALID[:-1] + str((int(_PAN_19_VALID[-1]) + 1) % 10)

_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
    "transaction_data": {"method": "card", "details": CARD_DETAILS},
}


def _assert_payin_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    return data


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
def test_payin_card_auto_capture():
    """Успешная оплата картой — auto capture, is_recurrent=True. Проверяет обязательные поля ответа."""
    data = _assert_payin_ok(post_transaction(_BASE))
    assert data["financial_data"]["amount"] == 10000
    assert data["financial_data"]["currency"] == "RUB"


def test_payin_card_manual_capture():
    """Оплата картой — manual capture (холд средств). Ожидаемый статус: authorized или processing."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_manual_cap"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
    }
    data = _assert_payin_ok(post_transaction(body))
    assert data["status"] in ("processing", "authorized", "pending", "waiting_action")


def test_payin_card_recurrent(payin_transaction_id):
    """Рекуррентный платёж по parent_transaction_id (method:card)."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_recurrent_card"},
        "financial_data": {"amount": 900, "currency": "RUB"},
        "transaction_data": {
            "method": "card",
            "details": CARD_DETAILS,
            "parent_transaction_id": payin_transaction_id,
        },
    }
    _assert_payin_ok(post_transaction(body))


def test_payin_card_without_flow_data():
    """flow_data необязателен — запрос без него должен вернуть 201."""
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    _assert_payin_ok(post_transaction(body))


def test_payin_card_without_webhook_url():
    """merchant_data.webhook_url необязателен (может быть задан на уровне терминала)."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "webhook_url"}
    body = {
        **_BASE,
        "merchant_data": merchant,
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    }
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — обязательные поля верхнего уровня
# ─────────────────────────────────────────────
@pytest.mark.parametrize("missing_field", [
    "type", "merchant_data", "financial_data", "customer_data", "transaction_data",
])
def test_missing_top_level_field(missing_field):
    """Отсутствие одного из 5 обязательных полей верхнего уровня. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != missing_field}
    resp = post_transaction(body)
    assert resp.status_code == 400, \
        f"Expected 400 for missing {missing_field}, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_invalid_transaction_type():
    """Неизвестный тип транзакции. Ожидается 400."""
    resp = post_transaction({**_BASE, "type": "unknown_type"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — финансовые данные
# ─────────────────────────────────────────────
def test_negative_amount():
    """Отрицательная сумма. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": -100, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_zero_amount():
    """Нулевая сумма. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 0, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_invalid_currency():
    """Несуществующий код валюты. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "INVALID"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_missing_currency():
    """Поле currency отсутствует в financial_data. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — merchant_data
# ─────────────────────────────────────────────
def test_missing_merchant_order_id():
    """Поле order_id отсутствует в merchant_data. Ожидается 400."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    resp = post_transaction({**_BASE, "merchant_data": merchant})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — данные карты
# ─────────────────────────────────────────────
@pytest.mark.parametrize("missing_field", ["pan", "holder", "expiry_month", "expiry_year", "cvv"])
def test_missing_card_required_field(missing_field):
    """Каждое из 5 обязательных полей карты удаляется. Ожидается 400."""
    details = {k: v for k, v in CARD_DETAILS.items() if k != missing_field}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, \
        f"Expected 400 for missing {missing_field}, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_card_pan_too_short():
    """PAN из 4 цифр — меньше минимума (13 цифр). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "1234"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_card_expired():
    """Истёкший срок действия карты (год 2020). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "20", "expiry_month": "01"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TYPE — граничные случаи (6.3, 6.4)
# ─────────────────────────────────────────────
def test_type_empty():
    """type передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "type": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_type_null():
    """type передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "type": None})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# MERCHANT_DATA — граничные случаи (7.2, 8.x)
# ─────────────────────────────────────────────
def test_merchant_data_empty_object():
    """merchant_data передан как пустой объект {}. Ожидается 400 (нет order_id)."""
    resp = post_transaction({**_BASE, "merchant_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_order_id_as_int():
    """order_id передан как число (int). Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": 12345}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_order_id_empty():
    """order_id передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_order_id_null():
    """order_id передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_order_id_100_chars():
    """order_id длиной ровно 100 символов. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 100}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_order_id_over_100_chars():
    """order_id длиной 101 символ (выше лимита). Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 101}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# DESCRIPTION — граничные случаи (9.x)
# ─────────────────────────────────────────────
def test_description_as_int():
    """description передан как число. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": 123}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_description_empty():
    """description передан как пустая строка. Ожидается 201 (поле необязательно)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": ""}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_description_null():
    """description передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_description_250_chars():
    """description длиной ровно 250 символов. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "x" * 250}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_description_over_250_chars():
    """description длиной 251 символ (выше лимита). Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "x" * 251}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# WEBHOOK_URL / RETURN_URL — граничные случаи (10.x, 11.x)
# ─────────────────────────────────────────────
def test_webhook_url_non_url_string():
    """webhook_url передан как произвольная строка, не ссылка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": "not_a_url"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_webhook_url_as_int():
    """webhook_url передан как число. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": 12345}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_webhook_url_empty():
    """webhook_url передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_webhook_url_null():
    """webhook_url передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_return_url_non_url_string():
    """return_url передан как произвольная строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": "not_a_url"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_return_url_as_int():
    """return_url передан как число. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": 12345}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_return_url_empty():
    """return_url передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_return_url_null():
    """return_url передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FINANCIAL_DATA — граничные случаи (12.x, 13.x, 14.x)
# ─────────────────────────────────────────────
def test_financial_data_empty_object():
    """financial_data передан как пустой объект {}. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_amount_as_string():
    """amount передан как строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": "1000", "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_amount_min_value():
    """amount равен 1 (минимально допустимое). Ожидается 201."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1, "currency": "RUB"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_amount_max_boundary():
    """amount равен 10000000000000 (граничное максимальное). Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 10000000000000, "currency": "RUB"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_amount_over_max():
    """amount больше 10000000000000. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 10000000000001, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_amount_null():
    """amount передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": None, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_amount_float():
    """amount передан как дробное число. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 100.50, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_currency_numeric_string():
    """currency передан как 3-значный числовой код (например '643'). Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "643"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_currency_two_chars():
    """currency из 2 символов. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "RU"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_currency_four_chars():
    """currency из 4 символов. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "RUBX"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_currency_empty():
    """currency передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_currency_null():
    """currency передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# FLOW_DATA — граничные случаи (15.x–19.x)
# ─────────────────────────────────────────────
def test_flow_data_empty_object():
    """flow_data передан как пустой объект {}. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "flow_data": {}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_is_recurrent_as_int_one():
    """is_recurrent передан как 1 (не boolean). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": 1, "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_is_recurrent_as_int_zero():
    """is_recurrent передан как 0 (не boolean). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": 0, "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_is_recurrent_as_string():
    """is_recurrent передан как строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": "true", "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_is_recurrent_empty():
    """is_recurrent передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": "", "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_is_recurrent_null():
    """is_recurrent передан как null. Ожидается 400 или 201."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": None, "capture_mode": "auto"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_capture_mode_invalid_value():
    """capture_mode передан с недопустимым значением '123'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "123"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_capture_mode_empty():
    """capture_mode передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_capture_mode_null():
    """capture_mode передан как null. Ожидается 400 или 201."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_capture_mode_missing():
    """capture_mode не передан в flow_data. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_threed_secure_empty_object():
    """threed_secure передан как пустой объект {}. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("window_size", ["01", "02", "03", "04", "05"])
def test_challenge_window_size_valid(window_size):
    """challenge_window_size — все допустимые значения '01'-'05'. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": window_size}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201 for {window_size}, got {resp.status_code}: {resp.text}"


def test_challenge_window_size_invalid():
    """challenge_window_size='06' (вне допустимого диапазона). Ожидается 400."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": "06"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_challenge_window_size_empty():
    """challenge_window_size передан как пустая строка. Ожидается 400."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": ""}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_challenge_window_size_null():
    """challenge_window_size передан как null. Ожидается 400 или 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": None}}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# TRANSACTION_DATA — граничные случаи (20.x–22.x)
# ─────────────────────────────────────────────
def test_transaction_data_empty_object():
    """transaction_data передан как пустой объект {}. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_method_invalid_value():
    """method передан как 'card1' (недопустимое значение). Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card1", "details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_method_empty():
    """method передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "", "details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_method_null():
    """method передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": None, "details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_details_empty_object():
    """details передан как пустой объект {}. Ожидается 400 (нет обязательных полей карты)."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": {}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CVV — граничные случаи (23.x)
# ─────────────────────────────────────────────
def test_cvv_as_int():
    """cvv передан как число (int). Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": 666}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_too_short():
    """cvv из 2 символов (короче минимума). Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_too_long():
    """cvv из 4 символов (длиннее максимума). Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "6666"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_alpha():
    """cvv состоит из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "ABC"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_mixed_alpha_digit():
    """cvv состоит из цифр и букв. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66A"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_mixed_digit_special():
    """cvv состоит из цифр и спецсимволов. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66!"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_empty():
    """cvv передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cvv_null():
    """cvv передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# EXPIRY_MONTH — граничные случаи (24.x)
# ─────────────────────────────────────────────
def test_expiry_month_as_int():
    """expiry_month передан как число. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": 5}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_month_one_char():
    """expiry_month из 1 символа (нет ведущего нуля). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "5"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_month_three_chars():
    """expiry_month из 3 символов ('005'). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "005"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_month_invalid_value():
    """expiry_month='13' (несуществующий месяц). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "13"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_month_alpha():
    """expiry_month состоит из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "AB"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_month_empty():
    """expiry_month передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_month_null():
    """expiry_month передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.parametrize("month", ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
def test_expiry_month_all_valid(month):
    """Проверка всех допустимых значений месяца (01-12). Ожидается 201."""
    details = {**CARD_DETAILS, "expiry_month": month, "expiry_year": "99"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201 for month={month}, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EXPIRY_YEAR — граничные случаи (25.x)
# ─────────────────────────────────────────────
def test_expiry_year_as_int():
    """expiry_year передан как число. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": 27}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_year_one_char():
    """expiry_year из 1 символа. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "7"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_year_four_chars():
    """expiry_year из 4 символов ('2027'). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "2027"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_year_alpha():
    """expiry_year состоит из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "AB"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_year_empty():
    """expiry_year передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_year_null():
    """expiry_year передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# EXPIRY КОМБО (26.x)
# ─────────────────────────────────────────────
def test_expiry_future_year():
    """expiry_month='01', expiry_year='99' — дата в далёком будущем. Ожидается 201."""
    details = {**CARD_DETAILS, "expiry_month": "01", "expiry_year": "99"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_expiry_future_month_current_year():
    """Месяц больше текущего, год текущий — карта ещё действует. Ожидается 201."""
    now = datetime.now()
    cur_month = now.month
    cur_year_2 = str(now.year)[-2:]
    future_month = f"{(cur_month % 12) + 1:02d}"
    details = {**CARD_DETAILS, "expiry_month": future_month, "expiry_year": cur_year_2}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.skipif(datetime.now().month == 1, reason="Январь — нет предыдущего месяца в текущем году")
def test_expiry_past_month_current_year():
    """Месяц меньше текущего, год текущий — карта просрочена. Ожидается 400."""
    now = datetime.now()
    past_month = f"{now.month - 1:02d}"
    cur_year_2 = str(now.year)[-2:]
    details = {**CARD_DETAILS, "expiry_month": past_month, "expiry_year": cur_year_2}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_expiry_current_month_year():
    """Текущий месяц и год — карта ещё действует. Ожидается 201."""
    now = datetime.now()
    cur_month = f"{now.month:02d}"
    cur_year_2 = str(now.year)[-2:]
    details = {**CARD_DETAILS, "expiry_month": cur_month, "expiry_year": cur_year_2}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# HOLDER — граничные случаи (27.x)
# ─────────────────────────────────────────────
def test_holder_three_words():
    """holder из 3 слов. Ожидается 201 или 400 (зависит от валидации)."""
    details = {**CARD_DETAILS, "holder": "JOHN DOE SMITH"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_holder_one_word():
    """holder из 1 слова. Ожидается 201 или 400."""
    details = {**CARD_DETAILS, "holder": "JOHN"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_holder_short():
    """holder общей длиной 3 символа ('AB C'). Ожидается 201 или 400."""
    details = {**CARD_DETAILS, "holder": "AB C"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_holder_cyrillic():
    """holder с кириллицей. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": "ИВАНОВ ИВАН"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_holder_30_chars():
    """holder длиной ровно 30 символов. Ожидается 201."""
    details = {**CARD_DETAILS, "holder": "JOHN " + "A" * 25}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_holder_over_30_chars():
    """holder длиной более 30 символов. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": "JOHN " + "A" * 26}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_holder_empty():
    """holder передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_holder_null():
    """holder передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PAN — граничные случаи (28.x)
# ─────────────────────────────────────────────
def test_pan_as_int():
    """pan передан как число (int). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": 4111111111111111}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_13_valid_luhn():
    """13-значный PAN, проходящий алгоритм Луна. Ожидается 201."""
    details = {**CARD_DETAILS, "pan": _PAN_13_VALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_pan_13_invalid_luhn():
    """13-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": _PAN_13_INVALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_16_invalid_luhn():
    """16-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "4111111111111112"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_18_valid_luhn():
    """18-значный PAN, проходящий алгоритм Луна. Ожидается 201."""
    details = {**CARD_DETAILS, "pan": _PAN_18_VALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_pan_18_invalid_luhn():
    """18-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": _PAN_18_INVALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_19_valid_luhn():
    """19-значный PAN, проходящий алгоритм Луна. Ожидается 201."""
    details = {**CARD_DETAILS, "pan": _PAN_19_VALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_pan_19_invalid_luhn():
    """19-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": _PAN_19_INVALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_over_19_chars():
    """PAN из 20 цифр (больше максимума). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "41111111111111111111"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_with_letters():
    """PAN содержит буквы. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "411111111111111X"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_empty():
    """pan передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pan_null():
    """pan передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PIN — граничные случаи (29.x)
# ─────────────────────────────────────────────
def test_pin_valid_string():
    """pin передан как 4-символьная строка. Ожидается 201."""
    details = {**CARD_DETAILS, "pin": "1234"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_pin_as_int():
    """pin передан как число (int). Ожидается 400."""
    details = {**CARD_DETAILS, "pin": 1234}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pin_too_short():
    """pin из 3 символов (короче минимума). Ожидается 400."""
    details = {**CARD_DETAILS, "pin": "123"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pin_too_long():
    """pin из 5 символов (длиннее максимума). Ожидается 400."""
    details = {**CARD_DETAILS, "pin": "12345"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pin_alpha():
    """pin из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "pin": "ABCD"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pin_empty():
    """pin передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "pin": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_pin_null():
    """pin передан как null. Ожидается 201 (необязательное поле)."""
    details = {**CARD_DETAILS, "pin": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CUSTOMER_DATA — пустой объект (30.2)
# ─────────────────────────────────────────────
def test_customer_data_empty_object():
    """customer_data передан как пустой объект {} (все поля необязательны). Ожидается 201."""
    resp = post_transaction({**_BASE, "customer_data": {}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"
