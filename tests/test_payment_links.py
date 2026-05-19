"""
Тесты для создания платёжных ссылок.
POST /api/v1/payment-links

Обязательные поля: merchant_data (с order_id), financial_data (amount + currency), customer_data
Необязательные: flow_data
"""
import json
import time
import requests
import pytest

from conftest import (
    make_headers,
    PAYMENT_LINKS_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
)

_VALID_LINK_BODY = {
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 5000, "currency": "RUB"},
    "customer_data": CUSTOMER_DATA,
}


def post_payment_link(body: dict) -> requests.Response:
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    return requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
def test_create_payment_link():
    """Создание платёжной ссылки со всеми обязательными полями. Ожидается 201."""
    resp = post_payment_link(_VALID_LINK_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "link_id" in data,                    "Missing link_id"
    assert "merchant_data" in data,              "Missing merchant_data"
    assert "link_data" in data,                  "Missing link_data"
    assert "url" in data["link_data"],           "Missing url in link_data"


def test_create_payment_link_response_fields():
    """Проверка типов обязательных полей в ответе на создание ссылки."""
    resp = post_payment_link(_VALID_LINK_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data["link_id"], str),         "link_id must be a string"
    assert isinstance(data["link_data"]["url"], str), "url must be a string"
    assert data["link_data"]["url"].startswith("http"), "url must be a valid URL"


def test_create_payment_link_with_flow_data():
    """Создание ссылки с необязательным flow_data. Ожидается 201."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_create_payment_link_with_recurrent_flow():
    """Создание ссылки с is_recurrent=True. Ожидается 201."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_create_payment_link_with_manual_capture():
    """Создание ссылки с capture_mode=manual. Ожидается 201."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {"capture_mode": "manual"},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_create_payment_link_without_webhook_url():
    """Создание ссылки без необязательного webhook_url в merchant_data. Ожидается 201."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "webhook_url"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_create_payment_link_without_return_url():
    """Создание ссылки без необязательного return_url в merchant_data. Ожидается 201."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "return_url"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_create_payment_link_minimal_customer_data():
    """Создание ссылки с пустым customer_data — все поля CustomerData необязательны."""
    body = {**_VALID_LINK_BODY, "customer_data": {}}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_create_payment_link_rub():
    """Создание платёжной ссылки с суммой 1000 RUB. Ожидается 201."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — обязательные поля верхнего уровня
# ─────────────────────────────────────────────
@pytest.mark.parametrize("missing_field", ["merchant_data", "financial_data", "customer_data"])
def test_payment_link_missing_required_field(missing_field):
    """Отсутствие одного из трёх обязательных полей верхнего уровня. Ожидается 422."""
    body = {k: v for k, v in _VALID_LINK_BODY.items() if k != missing_field}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422 for missing {missing_field}, got {resp.status_code}: {resp.text}"


def test_payment_link_missing_order_id():
    """Создание ссылки без order_id в merchant_data (обязательное). Ожидается 422."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — финансовые данные
# ─────────────────────────────────────────────
def test_payment_link_negative_amount():
    """Создание ссылки с отрицательной суммой. Ожидается 422."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": -100, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payment_link_zero_amount():
    """Создание ссылки с нулевой суммой. Ожидается 422."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 0, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payment_link_invalid_currency():
    """Создание ссылки с невалидным кодом валюты. Ожидается 422."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 5000, "currency": "INVALID"}}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payment_link_missing_currency():
    """Создание ссылки без поля currency в financial_data. Ожидается 422."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 5000}}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payment_link_missing_amount():
    """Создание ссылки без поля amount в financial_data. Ожидается 422."""
    body = {**_VALID_LINK_BODY, "financial_data": {"currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_payment_link_invalid_capture_mode():
    """Создание ссылки с невалидным capture_mode в flow_data. Ожидается 422."""
    body = {**_VALID_LINK_BODY, "flow_data": {"capture_mode": "instant"}}
    resp = post_payment_link(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — авторизация
# ─────────────────────────────────────────────
def test_payment_link_no_auth():
    """Создание ссылки без заголовков авторизации. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    resp = requests.post(PAYMENT_LINKS_URL, data=raw,
                         headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"


def test_payment_link_invalid_signature():
    """Создание ссылки с невалидной подписью. Ожидается 401 или 403."""
    import uuid
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
