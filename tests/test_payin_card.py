"""
Тесты для payin с методом card.
POST /api/v1/transactions — type:payin, method:card
Включает: happy path, обязательные поля, валидация карты, финансовых данных, merchant_data.
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
)

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
    for field in ("transaction_id", "type", "status", "merchant_data", "financial_data", "created_at"):
        assert field in data, f"Missing {field}"
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
    """Отсутствие одного из 5 обязательных полей верхнего уровня. Ожидается 422."""
    body = {k: v for k, v in _BASE.items() if k != missing_field}
    resp = post_transaction(body)
    assert resp.status_code == 422, \
        f"Expected 422 for missing {missing_field}, got {resp.status_code}: {resp.text}"


def test_invalid_transaction_type():
    """Неизвестный тип транзакции. Ожидается 422."""
    resp = post_transaction({**_BASE, "type": "unknown_type"})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — финансовые данные
# ─────────────────────────────────────────────
def test_negative_amount():
    """Отрицательная сумма. Ожидается 422."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": -100, "currency": "RUB"}})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_zero_amount():
    """Нулевая сумма. Ожидается 422."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 0, "currency": "RUB"}})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_invalid_currency():
    """Несуществующий код валюты. Ожидается 422."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000, "currency": "INVALID"}})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_missing_currency():
    """Поле currency отсутствует в financial_data. Ожидается 422."""
    resp = post_transaction({**_BASE, "financial_data": {"amount": 1000}})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — merchant_data
# ─────────────────────────────────────────────
def test_missing_merchant_order_id():
    """Поле order_id отсутствует в merchant_data. Ожидается 422."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    resp = post_transaction({**_BASE, "merchant_data": merchant})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — данные карты
# ─────────────────────────────────────────────
@pytest.mark.parametrize("missing_field", ["pan", "holder", "expiry_month", "expiry_year", "cvv"])
def test_missing_card_required_field(missing_field):
    """Каждое из 5 обязательных полей карты удаляется. Ожидается 422."""
    details = {k: v for k, v in CARD_DETAILS.items() if k != missing_field}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 422, \
        f"Expected 422 for missing {missing_field}, got {resp.status_code}: {resp.text}"


def test_card_pan_too_short():
    """PAN из 4 цифр — меньше минимума (13 цифр). Ожидается 422."""
    details = {**CARD_DETAILS, "pan": "1234"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_card_expired():
    """Истёкший срок действия карты (год 2020). Ожидается 422."""
    details = {**CARD_DETAILS, "expiry_year": "20", "expiry_month": "01"}
    resp = post_transaction({**_BASE, "transaction_data": {"method": "card", "details": details}})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
