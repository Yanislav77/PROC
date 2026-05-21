"""
Тесты для операции refund (возврат средств).
POST /api/v1/transactions/{id}/refund
"""
import json
import requests

from conftest import (
    post_operation,
    make_headers,
    BASE_URL,
    MERCHANT_DATA,
    TERMINAL_ID,
)

_REFUND_BODY = {
    "merchant_data": {
        "order_id": "order_refund_test",
        "description": "Refund test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
def test_refund_partial(payin_transaction_id):
    """Частичный возврат (1000 из 10000) по существующей транзакции. Ожидается 200 или 201."""
    resp = post_operation(payin_transaction_id, "refund", _REFUND_BODY)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data
    assert "status" in data


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
def test_refund_nonexistent_transaction():
    """Возврат по несуществующей транзакции. Ожидается 404 или 422."""
    url = f"{BASE_URL}/nonexistent-id-000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (404, 422), f"Expected 404/422, got {resp.status_code}: {resp.text}"


def test_refund_amount_exceeds_original(payin_transaction_id):
    """Сумма возврата (99999999) превышает оригинальную сумму транзакции. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 99999999, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_merchant_data(payin_transaction_id):
    """Возврат без merchant_data (обязательное). Ожидается 400 или 422."""
    body = {"financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_financial_data(payin_transaction_id):
    """Возврат без financial_data (обязательное). Ожидается 400 или 422."""
    body = {"merchant_data": {"order_id": "order_refund_test"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_order_id(payin_transaction_id):
    """Возврат с merchant_data без order_id. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"description": "Refund"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_currency(payin_transaction_id):
    """Возврат без поля currency в financial_data. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_amount(payin_transaction_id):
    """Возврат без поля amount в financial_data. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_zero_amount(payin_transaction_id):
    """Возврат с нулевой суммой. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_negative_amount(payin_transaction_id):
    """Возврат с отрицательной суммой. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": -100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_invalid_currency(payin_transaction_id):
    """Возврат с невалидным кодом валюты. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "INVALID"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"
