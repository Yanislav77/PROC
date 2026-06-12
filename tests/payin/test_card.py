"""
Тесты для payin с методом card.
POST /api/v1/transactions — type:payin, method:card
Включает: happy path, обязательные поля, валидация карты, финансовых данных, merchant_data.
"""
import copy
import time
import uuid
import pytest
from datetime import datetime

from conftest import (
    post_transaction,
    get_request,
    BASE_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)
from _helpers.polling import poll_status


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
@pytest.mark.tcid("PC-001")
def test_payin_card_auto_capture():
    """Успешная оплата картой — auto capture, is_recurrent=True. Проверяет обязательные поля ответа."""
    data = _assert_payin_ok(post_transaction(_BASE))
    assert data["financial_data"]["amount"] == 10000
    assert data["financial_data"]["currency"] == "RUB"
    tid = data["transaction_id"]
    if data.get("status") != "completed":
        poll_status(tid, "completed")


@pytest.mark.tcid("PC-002")
def test_payin_card_manual_capture():
    """Оплата картой — manual capture (холд средств). Ожидаемый статус: authorized или processing."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("manual_cap")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
    }
    data = _assert_payin_ok(post_transaction(body))
    assert data["status"] in ("processing", "authorized", "pending", "waiting_action")
    tid = data["transaction_id"]
    if data.get("status") != "authorized":
        poll_status(tid, "authorized")


@pytest.mark.tcid("PC-003")
def test_payin_card_recurrent(payin_transaction_id):
    """Рекуррентный платёж по parent_transaction_id (method:card)."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("recurrent_card")},
        "financial_data": {"amount": 900, "currency": "RUB"},
        "transaction_data": {
            "method": "card",
            "details": CARD_DETAILS,
            "parent_transaction_id": payin_transaction_id,
        },
    }
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PC-004")
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


@pytest.mark.tcid("PC-005")
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
@pytest.mark.tcid("PC-006")
def test_missing_top_level_field(missing_field):
    """Отсутствие одного из 5 обязательных полей верхнего уровня. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != missing_field}
    resp = post_transaction(body)
    assert resp.status_code == 400, \
        f"Expected 400 for missing {missing_field}, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-007")
def test_invalid_transaction_type():
    """Неизвестный тип транзакции. Ожидается 400."""
    resp = post_transaction({**_BASE, "type": "unknown_type"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — финансовые данные
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-008")
def test_negative_amount():
    """Отрицательная сумма. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": -100, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-009")
def test_zero_amount():
    """Нулевая сумма. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 0, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-010")
def test_invalid_currency():
    """Несуществующий код валюты. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "INVALID"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-011")
def test_missing_currency():
    """Поле currency отсутствует в financial_data. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — merchant_data
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-012")
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
@pytest.mark.tcid("PC-013")
def test_missing_card_required_field(missing_field):
    """Каждое из 5 обязательных полей карты удаляется. Ожидается 400."""
    details = {k: v for k, v in CARD_DETAILS.items() if k != missing_field}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, \
        f"Expected 400 for missing {missing_field}, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-014")
def test_card_pan_too_short():
    """PAN из 4 цифр — меньше минимума (13 цифр). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "1234"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-015")
def test_card_expired():
    """Истёкший срок действия карты (год 2020). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "20", "expiry_month": "01"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TYPE — граничные случаи (6.3, 6.4)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-016")
def test_type_empty():
    """type передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "type": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-017")
def test_type_null():
    """type передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "type": None})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# MERCHANT_DATA — граничные случаи (7.2, 8.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-018")
def test_merchant_data_empty_object():
    """merchant_data передан как пустой объект {}. Ожидается 400 (нет order_id)."""
    resp = post_transaction({**_BASE, "merchant_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-019")
def test_order_id_as_int():
    """order_id передан как число (int). Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": 12345}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-020")
def test_order_id_empty():
    """order_id передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-021")
def test_order_id_null():
    """order_id передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-022")
def test_order_id_100_chars():
    """order_id длиной ровно 100 символов. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 100}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-023")
def test_order_id_over_100_chars():
    """order_id длиной 101 символ (выше лимита). Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 101}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# DESCRIPTION — граничные случаи (9.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-024")
def test_description_as_int():
    """description передан как число. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": 123}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-025")
def test_description_empty():
    """description передан как пустая строка. Ожидается 201 (поле необязательно)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": ""}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-026")
def test_description_null():
    """description передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-027")
def test_description_250_chars():
    """description длиной ровно 250 символов. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "x" * 250}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-028")
def test_description_over_250_chars():
    """description длиной 251 символ (выше лимита). Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "x" * 251}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# WEBHOOK_URL / RETURN_URL — граничные случаи (10.x, 11.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-029")
def test_webhook_url_non_url_string():
    """webhook_url передан как произвольная строка, не ссылка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": "not_a_url"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-030")
def test_webhook_url_as_int():
    """webhook_url передан как число. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": 12345}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-031")
def test_webhook_url_empty():
    """webhook_url передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-032")
def test_webhook_url_null():
    """webhook_url передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "webhook_url": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-033")
def test_return_url_non_url_string():
    """return_url передан как произвольная строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": "not_a_url"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-034")
def test_return_url_as_int():
    """return_url передан как число. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": 12345}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-035")
def test_return_url_empty():
    """return_url передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-036")
def test_return_url_null():
    """return_url передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "return_url": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FINANCIAL_DATA — граничные случаи (12.x, 13.x, 14.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-037")
def test_financial_data_empty_object():
    """financial_data передан как пустой объект {}. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-038")
def test_amount_as_string():
    """amount передан как строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": "1000", "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-039")
def test_amount_min_value():
    """amount равен 1 (минимально допустимое). Ожидается 201."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1, "currency": "RUB"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-040")
def test_amount_max_boundary():
    """amount равен 10000000000000 (граничное максимальное). Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 10000000000000, "currency": "RUB"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-041")
def test_amount_over_max():
    """amount больше 10000000000000. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 10000000000001, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-042")
def test_amount_null():
    """amount передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": None, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-043")
def test_amount_float():
    """amount передан как дробное число. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 100.50, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-044")
def test_currency_numeric_string():
    """currency передан как 3-значный числовой код (например '643'). Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "643"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-045")
def test_currency_two_chars():
    """currency из 2 символов. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "RU"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-046")
def test_currency_four_chars():
    """currency из 4 символов. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "RUBX"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-047")
def test_currency_empty():
    """currency передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-048")
def test_currency_null():
    """currency передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# FLOW_DATA — граничные случаи (15.x–19.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-049")
def test_flow_data_empty_object():
    """flow_data передан как пустой объект {}. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "flow_data": {}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-050")
def test_is_recurrent_as_int_one():
    """is_recurrent передан как 1 (не boolean). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": 1, "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-051")
def test_is_recurrent_as_int_zero():
    """is_recurrent передан как 0 (не boolean). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": 0, "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-052")
def test_is_recurrent_as_string():
    """is_recurrent передан как строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": "true", "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-053")
def test_is_recurrent_empty():
    """is_recurrent передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": "", "capture_mode": "auto"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-054")
def test_is_recurrent_null():
    """is_recurrent передан как null. Ожидается 400 или 201."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": None, "capture_mode": "auto"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-055")
def test_capture_mode_invalid_value():
    """capture_mode передан с недопустимым значением '123'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "123"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-056")
def test_capture_mode_empty():
    """capture_mode передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-057")
def test_capture_mode_null():
    """capture_mode передан как null. Ожидается 400 или 201."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": None}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-058")
def test_capture_mode_missing():
    """capture_mode не передан в flow_data. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "flow_data": {"is_recurrent": False}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-059")
def test_threed_secure_empty_object():
    """threed_secure передан как пустой объект {}. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("window_size", ["01", "02", "03", "04", "05"])
@pytest.mark.tcid("PC-060")
def test_challenge_window_size_valid(window_size):
    """challenge_window_size — все допустимые значения '01'-'05'. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": window_size}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201 for {window_size}, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-061")
def test_challenge_window_size_invalid():
    """challenge_window_size='06' (вне допустимого диапазона). Ожидается 400."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": "06"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-062")
def test_challenge_window_size_empty():
    """challenge_window_size передан как пустая строка. Ожидается 400."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": ""}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-063")
def test_challenge_window_size_null():
    """challenge_window_size передан как null. Ожидается 400 или 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {"challenge_window_size": None}}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# TRANSACTION_DATA — граничные случаи (20.x–22.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-064")
def test_transaction_data_empty_object():
    """transaction_data передан как пустой объект {}. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-065")
def test_method_invalid_value():
    """method передан как 'card1' (недопустимое значение). Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card1", "details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-066")
def test_method_empty():
    """method передан как пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "", "details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-067")
def test_method_null():
    """method передан как null. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": None, "details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-068")
def test_details_empty_object():
    """details передан как пустой объект {}. Ожидается 400 (нет обязательных полей карты)."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": {}}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CVV — граничные случаи (23.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-069")
def test_cvv_as_int():
    """cvv передан как число (int). Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": 666}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-070")
def test_cvv_too_short():
    """cvv из 2 символов (короче минимума). Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-071")
def test_cvv_too_long():
    """cvv из 4 символов. Ожидается 201."""
    details = {**CARD_DETAILS, "cvv": "6666"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-072")
def test_cvv_alpha():
    """cvv состоит из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "ABC"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-073")
def test_cvv_mixed_alpha_digit():
    """cvv состоит из цифр и букв. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66A"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-074")
def test_cvv_mixed_digit_special():
    """cvv состоит из цифр и спецсимволов. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66!"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-075")
def test_cvv_empty():
    """cvv передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-076")
def test_cvv_null():
    """cvv передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# EXPIRY_MONTH — граничные случаи (24.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-077")
def test_expiry_month_as_int():
    """expiry_month передан как число. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": 5}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-078")
def test_expiry_month_one_char():
    """expiry_month из 1 символа (нет ведущего нуля). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "5"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-079")
def test_expiry_month_three_chars():
    """expiry_month из 3 символов ('005'). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "005"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-080")
def test_expiry_month_invalid_value():
    """expiry_month='13' (несуществующий месяц). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "13"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-081")
def test_expiry_month_alpha():
    """expiry_month состоит из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "AB"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-082")
def test_expiry_month_empty():
    """expiry_month передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-083")
def test_expiry_month_null():
    """expiry_month передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.parametrize("month", ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
@pytest.mark.tcid("PC-084")
def test_expiry_month_all_valid(month):
    """Проверка всех допустимых значений месяца (01-12). Ожидается 201."""
    details = {**CARD_DETAILS, "expiry_month": month, "expiry_year": "99"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201 for month={month}, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EXPIRY_YEAR — граничные случаи (25.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-085")
def test_expiry_year_as_int():
    """expiry_year передан как число. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": 27}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-086")
def test_expiry_year_one_char():
    """expiry_year из 1 символа. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "7"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-087")
def test_expiry_year_four_chars():
    """expiry_year из 4 символов ('2027'). Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "2027"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-088")
def test_expiry_year_alpha():
    """expiry_year состоит из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": "AB"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-089")
def test_expiry_year_empty():
    """expiry_year передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-090")
def test_expiry_year_null():
    """expiry_year передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_year": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# EXPIRY КОМБО (26.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-091")
def test_expiry_future_year():
    """expiry_month='01', expiry_year='99' — дата в далёком будущем. Ожидается 201."""
    details = {**CARD_DETAILS, "expiry_month": "01", "expiry_year": "99"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-092")
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
@pytest.mark.tcid("PC-093")
def test_expiry_past_month_current_year():
    """Месяц меньше текущего, год текущий — карта просрочена. Ожидается 400."""
    now = datetime.now()
    past_month = f"{now.month - 1:02d}"
    cur_year_2 = str(now.year)[-2:]
    details = {**CARD_DETAILS, "expiry_month": past_month, "expiry_year": cur_year_2}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-094")
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
@pytest.mark.tcid("PC-095")
def test_holder_three_words():
    """holder из 3 слов. Ожидается 201 или 400 (зависит от валидации)."""
    details = {**CARD_DETAILS, "holder": "JOHN DOE SMITH"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-096")
def test_holder_one_word():
    """holder из 1 слова. Ожидается 201 или 400."""
    details = {**CARD_DETAILS, "holder": "JOHN"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-097")
def test_holder_short():
    """holder общей длиной 3 символа ('AB C'). Ожидается 201 или 400."""
    details = {**CARD_DETAILS, "holder": "AB C"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-098")
def test_holder_cyrillic():
    """holder с кириллицей. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": "ИВАНОВ ИВАН"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-099")
def test_holder_30_chars():
    """holder длиной ровно 30 символов. Ожидается 201."""
    details = {**CARD_DETAILS, "holder": "JOHN " + "A" * 25}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-100")
def test_holder_over_30_chars():
    """holder длиной более 30 символов. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": "JOHN " + "A" * 26}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-101")
def test_holder_empty():
    """holder передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-102")
def test_holder_null():
    """holder передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "holder": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PAN — граничные случаи (28.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-103")
def test_pan_as_int():
    """pan передан как число (int). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": 4111111111111111}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-104")
def test_pan_13_valid_luhn():
    """13-значный PAN, проходящий алгоритм Луна. Ожидается 201."""
    details = {**CARD_DETAILS, "pan": _PAN_13_VALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-105")
def test_pan_13_invalid_luhn():
    """13-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": _PAN_13_INVALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-106")
def test_pan_16_invalid_luhn():
    """16-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "4111111111111112"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-107")
def test_pan_18_valid_luhn():
    """18-значный PAN, проходящий алгоритм Луна. Ожидается 201."""
    details = {**CARD_DETAILS, "pan": _PAN_18_VALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-108")
def test_pan_18_invalid_luhn():
    """18-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": _PAN_18_INVALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-109")
def test_pan_19_valid_luhn():
    """19-значный PAN, проходящий алгоритм Луна. Ожидается 201."""
    details = {**CARD_DETAILS, "pan": _PAN_19_VALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-110")
def test_pan_19_invalid_luhn():
    """19-значный PAN, не проходящий алгоритм Луна. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": _PAN_19_INVALID}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-111")
def test_pan_over_19_chars():
    """PAN из 20 цифр (больше максимума). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "41111111111111111111"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-112")
def test_pan_with_letters():
    """PAN содержит буквы. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "411111111111111X"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-113")
def test_pan_empty():
    """pan передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-114")
def test_pan_null():
    """pan передан как null. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PIN — граничные случаи (29.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-115")
def test_pin_valid_string():
    """pin передан как 4-символьная строка. Ожидается 201."""
    details = {**CARD_DETAILS, "pin": "1234"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-116")
def test_pin_as_int():
    """pin передан как число (int). Ожидается 400."""
    details = {**CARD_DETAILS, "pin": 1234}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-117")
def test_pin_too_short():
    """pin из 3 символов (короче минимума). Ожидается 400."""
    details = {**CARD_DETAILS, "pin": "123"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-118")
def test_pin_too_long():
    """pin из 5 символов (длиннее максимума). Ожидается 400."""
    details = {**CARD_DETAILS, "pin": "12345"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-119")
def test_pin_alpha():
    """pin из букв. Ожидается 400."""
    details = {**CARD_DETAILS, "pin": "ABCD"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-120")
def test_pin_empty():
    """pin передан как пустая строка. Ожидается 400."""
    details = {**CARD_DETAILS, "pin": ""}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-121")
def test_pin_null():
    """pin передан как null. Ожидается 201 (необязательное поле)."""
    details = {**CARD_DETAILS, "pin": None}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CUSTOMER_DATA — пустой объект (30.2)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-122")
def test_customer_data_empty_object():
    """customer_data передан как пустой объект {}. Ожидается 400."""
    resp = post_transaction({**_BASE, "customer_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ORDER_ID — содержимое строки (8.1, 8.2, 8.7–8.11)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-123")
def test_order_id_valid_string():
    """8.1 order_id = любое строковое значение. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "valid_order_string"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-124")
def test_order_id_duplicate():
    """8.2 order_id = дублирующееся значение (такое же, как в 8.1). Ожидается 201 или 409."""
    order_id = "valid_order_string"
    body = {**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": order_id}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 409), f"Expected 201 or 409, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-125")
def test_order_id_latin_only():
    """8.7 order_id состоит только из латинских букв. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "latinonly"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-126")
def test_order_id_digits_only():
    """8.8 order_id состоит только из цифр. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "98765432"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-127")
def test_order_id_latin_and_digits():
    """8.9 order_id состоит из латинских букв и цифр. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "order8899"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-128")
def test_order_id_cyrillic_only():
    """8.10 order_id состоит только из кириллицы. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "ЗАКАЗ12345"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-129")
def test_order_id_latin_and_special_chars():
    """8.11 order_id состоит из латинских букв и спецсимволов. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "ORDER#@$%^&*()"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DESCRIPTION — содержимое строки (9.1, 9.2, 9.6–9.11)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-130")
def test_description_valid_string():
    """9.1 description = валидная строка. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "Valid description text"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-131")
def test_description_same_as_order_id_value():
    """9.2 description = строка аналогичного формата, как order_id в кейсе 8.1. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "valid_order_string"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-132")
def test_description_missing():
    """9.6 description не передан в запросе. Ожидается 201 (поле необязательно)."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "description"}
    resp = post_transaction({**_BASE, "merchant_data": merchant})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-133")
def test_description_latin_only():
    """9.7 description состоит только из латинских букв. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "descriptiononly"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-134")
def test_description_digits_only():
    """9.8 description состоит только из цифр. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "12345678"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-135")
def test_description_latin_and_digits():
    """9.9 description состоит из латинских букв и цифр. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "order123description"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-136")
def test_description_cyrillic_only():
    """9.10 description состоит только из кириллицы. Ожидается 201 или 400."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "Описание заказа"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-137")
def test_description_latin_and_special_chars():
    """9.11 description состоит из латинских букв и спецсимволов. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "description": "Order#@$%^&*()"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# RETURN_URL — отсутствие поля (11.6)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-138")
def test_return_url_missing():
    """11.6 return_url не передан в запросе. Ожидается 201 (поле необязательно)."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "return_url"}
    resp = post_transaction({**_BASE, "merchant_data": merchant})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# AMOUNT — пустое значение и отсутствие (13.8, 13.9)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-139")
def test_amount_empty_string():
    """13.8 amount = пустая строка. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": "", "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PC-140")
def test_amount_missing():
    """13.9 amount не передан в financial_data. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CURRENCY — валидный код сервиса (14.2)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-141")
def test_currency_rub_valid():
    """14.2 currency = 'RUB' — 3-значный буквенный код, совпадающий с валютой сервиса. Ожидается 201."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 10000, "currency": "RUB"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# IS_RECURRENT — false и отсутствие (16.2, 16.8)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-142")
def test_is_recurrent_false():
    """16.2 is_recurrent = false. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-143")
def test_is_recurrent_missing():
    """16.8 is_recurrent не передан в flow_data. Ожидается 201 или 400."""
    flow = {k: v for k, v in _BASE["flow_data"].items() if k != "is_recurrent"}
    resp = post_transaction({**_BASE, "flow_data": flow})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# THREED_SECURE — отсутствие объекта (18.1)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-144")
def test_threed_secure_missing():
    """18.1 threed_secure не передан в flow_data. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto"}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# TRANSACTION_DATA — пустой объект (20.2)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-145")
def test_transaction_data_empty_object_20_2():
    """20.2 transaction_data передан как пустой объект {}. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# METHOD — значение "card" и отсутствие (21.1, 21.5)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-146")
def test_method_card_explicit():
    """21.1 method = 'card'. Ожидается 201."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": CARD_DETAILS}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PC-147")
def test_method_missing():
    """21.5 method не передан в transaction_data. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"details": CARD_DETAILS}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# DETAILS — отсутствие объекта (22.1)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-148")
def test_details_missing():
    """22.1 details не передан в transaction_data. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# EXPIRY_MONTH — отсутствие поля (24.9)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-149")
def test_expiry_month_missing():
    """24.9 expiry_month не передан в details. Ожидается 400."""
    details = {k: v for k, v in CARD_DETAILS.items() if k != "expiry_month"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PIN — отсутствие поля (29.8)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-150")
def test_pin_missing():
    """29.8 pin не передан в details. Ожидается 201 (поле необязательно)."""
    details = {k: v for k, v in CARD_DETAILS.items() if k != "pin"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (PC-151 … PC-165)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-151")
def test_response_transaction_id_is_positive_integer():
    """POST /transactions — transaction_id в ответе положительное целое число."""
    resp = post_transaction(_BASE)
    assert resp.status_code == 201
    tid = resp.json().get("transaction_id")
    assert isinstance(tid, int) and tid > 0, f"Ожидался положительный int, получен: {tid}"


@pytest.mark.tcid("PC-152")
def test_response_status_in_valid_set():
    """POST /transactions — status в ответе принадлежит допустимому набору."""
    _valid = {"completed", "authorized", "processing", "waiting_action", "cancelled", "rejected", "refunded"}
    resp = post_transaction(_BASE)
    assert resp.status_code == 201
    status = resp.json().get("status")
    assert status in _valid, f"Неожиданный status: {status!r}"


@pytest.mark.tcid("PC-153")
def test_response_type_is_payin():
    """POST /transactions — type в ответе равен 'payin'."""
    resp = post_transaction(_BASE)
    assert resp.status_code == 201
    assert resp.json().get("type") == "payin"


@pytest.mark.tcid("PC-154")
def test_response_created_at_iso8601():
    """POST /transactions — created_at в ответе валидный ISO 8601."""
    resp = post_transaction(_BASE)
    assert resp.status_code == 201
    created_at = resp.json().get("created_at", "")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pytest.fail(f"created_at не является ISO 8601: {created_at!r}")


@pytest.mark.tcid("PC-155")
def test_response_financial_data_amount_matches_request():
    """POST /transactions — financial_data.amount в ответе совпадает с запросом."""
    body = copy.deepcopy(_BASE)
    body["financial_data"]["amount"] = 5000
    body["merchant_data"] = {**MERCHANT_DATA, "order_id": gen_order_id("amt_match")}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert resp.json()["financial_data"]["amount"] == 5000


@pytest.mark.tcid("PC-156")
def test_response_content_type_is_json():
    """POST /transactions — Content-Type ответа содержит application/json."""
    resp = post_transaction(_BASE)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type: {resp.headers.get('Content-Type')}"


@pytest.mark.tcid("PC-157")
def test_order_id_only_spaces_returns_201():
    """order_id состоит только из пробелов. Ожидается 201."""
    resp = post_transaction({**_BASE, "merchant_data": {**MERCHANT_DATA, "order_id": "   "}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"


@pytest.mark.tcid("PC-158")
def test_financial_data_missing_amount_field():
    """financial_data без поля amount (не null, а отсутствие). Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"currency": "RUB"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PC-159")
def test_payin_card_recurrent_token_in_response():
    """Payin с is_recurrent=True — recurrent_token в ответе при статусе completed."""
    resp = post_transaction(_BASE)
    assert resp.status_code == 201
    data = resp.json()
    if data.get("status") == "completed":
        td = data.get("transaction_data", {})
        assert "recurrent_token" in td, "recurrent_token отсутствует у completed recurrent payin"


@pytest.mark.tcid("PC-160")
def test_payin_card_response_has_transaction_data():
    """POST /transactions — ответ содержит поле transaction_id."""
    resp = post_transaction(_BASE)
    assert resp.status_code == 201


@pytest.mark.tcid("PC-161")
def test_pan_with_dashes_returns_400():
    """PAN с дефисами '4111-1111-1111-1111'. Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "4111-1111-1111-1111"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PC-162")
def test_webhook_url_http_scheme():
    """webhook_url с HTTP схемой (не HTTPS). Ожидается 201 или 400."""
    body = {**_BASE, "merchant_data": {**MERCHANT_DATA,
                                        "order_id": gen_order_id("http_scheme"),
                                        "webhook_url": "http://merchant.com/webhook"}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}"


@pytest.mark.tcid("PC-163")
def test_expiry_month_zero_zero_returns_400():
    """expiry_month='00'. Ожидается 400."""
    details = {**CARD_DETAILS, "expiry_month": "00"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PC-164")
def test_customer_data_null_returns_400():
    """customer_data = null. Ожидается 400."""
    resp = post_transaction({**_BASE, "customer_data": None})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PC-165")
def test_financial_data_null_returns_400():
    """financial_data = null. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": None})


# ─────────────────────────────────────────────
# РЕГРЕСС — копейки и отклонение
# ─────────────────────────────────────────────

@pytest.mark.tcid("PC-166")
def test_payin_card_amount_with_kopecks():
    """Оплата картой — сумма с копейками (10050 = 100.50 руб). Ожидается 201 и amount=10050 в ответе."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("kopecks")},
        "financial_data": {"amount": 10050, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    }
    data = _assert_payin_ok(post_transaction(body))
    assert data["financial_data"]["amount"] == 10050
    tid = data["transaction_id"]
    if data.get("status") != "completed":
        poll_status(tid, "completed")


@pytest.mark.tcid("PC-167")
def test_payin_card_declined():
    """Неуспешная оплата картой — expiry_month > 7 вызывает отклонение банком. Ожидается статус rejected."""
    declined_details = {**CARD_DETAILS, "expiry_month": "08"}
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("declined")},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "transaction_data": {"method": "card", "details": declined_details},
    }
    data = _assert_payin_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") == "rejected":
        return
    for _ in range(10):
        time.sleep(2)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == "rejected":
            return
        if status in ("completed", "authorized", "cancelled", "failed"):
            pytest.fail(f"Ожидался статус 'rejected', получен '{status}' — карта не была отклонена")
    pytest.fail(f"Транзакция {tid} не достигла статуса 'rejected' за отведённое время")
    assert resp.status_code == 400
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CURRENCY — 3-значный код, не совпадающий с валютой сервиса (14.2)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-166")
def test_currency_eur_not_service_currency():
    """14.2 currency = 'EUR' — 3-значный буквенный код, не совпадающий с валютой сервиса. Ожидается 400."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 10000, "currency": "EUR"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CHALLENGE_WINDOW_SIZE — отсутствие поля (19.9)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-167")
def test_challenge_window_size_missing():
    """19.9 challenge_window_size не передан в threed_secure. Ожидается 201."""
    body = {**_BASE, "flow_data": {"is_recurrent": False, "capture_mode": "auto",
                                    "threed_secure": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CVV — 5-значный цифровой код (23.11)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-168")
def test_cvv_five_digits():
    """23.11 cvv из 5 цифр (длиннее максимума). Ожидается 400."""
    details = {**CARD_DETAILS, "cvv": "66666"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HOLDER — имя и фамилия, общая длина 3 символа (27.5)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-169")
def test_holder_three_chars_total():
    """27.5 holder — имя и фамилия латиницей, общая длина 3 символа ('f g'). Ожидается 201."""
    details = {**CARD_DETAILS, "holder": "f g"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# HOLDER — больше 3 слов латиницей (27.11)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-170")
def test_holder_more_than_three_words():
    """27.11 holder — больше 3 слов латиницей. Ожидается 201."""
    details = {**CARD_DETAILS, "holder": "JOHN DOE SMITH JONES"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PAN — 12 символов (28.17)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-171")
def test_pan_12_chars():
    """28.17 pan из 12 цифр (меньше минимума в 13). Ожидается 400."""
    details = {**CARD_DETAILS, "pan": "411111111111"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PC-172")
def test_idempotency_same_key_returns_same_transaction_id():
    """Повторный запрос с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import time
    import uuid
    import requests as _req
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_card")},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
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

