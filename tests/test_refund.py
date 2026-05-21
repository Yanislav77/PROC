"""
Тесты для операции refund (возврат средств).
POST /api/v1/transactions/{id}/refund
"""
import json
import time
import uuid

import pytest
import requests

from conftest import (
    post_transaction,
    post_operation,
    make_headers,
    make_get_headers,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_transaction_response,
    assert_error_response,
)

_REFUND_BODY = {
    "merchant_data": {
        "order_id": "order_refund_test",
        "description": "Refund test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


def _make_auto_payin(order_id: str = "order_refund_auto") -> str:
    """Создаёт Payin с capture_mode=auto и возвращает transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Auto Payin failed: {resp.text}"
    return resp.json()["transaction_id"]


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-001")
def test_refund_partial(payin_transaction_id):
    """Частичный возврат (1000 из 10000) по существующей транзакции. Ожидается 200 или 201."""
    resp = post_operation(payin_transaction_id, "refund", _REFUND_BODY)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    assert data["financial_data"]["currency"] == "RUB"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-002")
def test_refund_nonexistent_transaction():
    """Возврат по несуществующей транзакции. Ожидается 404."""
    url = f"{BASE_URL}/nonexistent-id-000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-003")
def test_refund_amount_exceeds_original(payin_transaction_id):
    """Сумма возврата (99999999) превышает оригинальную сумму транзакции. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 99999999, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-004")
def test_refund_missing_merchant_data(payin_transaction_id):
    """Возврат без merchant_data (обязательное). Ожидается 400."""
    body = {"financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-005")
def test_refund_missing_financial_data(payin_transaction_id):
    """Возврат без financial_data (обязательное). Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_refund_test"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-006")
def test_refund_missing_order_id(payin_transaction_id):
    """Возврат с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {"description": "Refund"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-007")
def test_refund_missing_currency(payin_transaction_id):
    """Возврат без поля currency в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-008")
def test_refund_missing_amount(payin_transaction_id):
    """Возврат без поля amount в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-009")
def test_refund_zero_amount(payin_transaction_id):
    """Возврат с нулевой суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-010")
def test_refund_negative_amount(payin_transaction_id):
    """Возврат с отрицательной суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": -100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-011")
def test_refund_invalid_currency(payin_transaction_id):
    """Возврат с невалидным кодом валюты. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "INVALID"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HAPPY PATH — ДОПОЛНИТЕЛЬНЫЕ КЕЙСЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-012")
def test_refund_full():
    """Полный возврат (10000 из 10000). Ожидается 200 или 201."""
    tid = _make_auto_payin("order_refund_full")
    body = {
        "merchant_data": {"order_id": "order_refund_full"},
        "financial_data": {"amount": 10000, "currency": "RUB"},
    }
    resp = post_operation(tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("RF-013")
def test_refund_with_description(payin_transaction_id):
    """Возврат с опциональным description в merchant_data. Ожидается 200 или 201."""
    body = {
        "merchant_data": {
            "order_id": "order_refund_test",
            "description": "Customer requested refund",
        },
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("RF-014")
def test_refund_without_webhook_url(payin_transaction_id):
    """Возврат без webhook_url (необязательное). Ожидается 200 или 201."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — ТИП ДАННЫХ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-015")
def test_refund_amount_as_string(payin_transaction_id):
    """Возврат с суммой как строкой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": "500", "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-016")
def test_refund_amount_as_float(payin_transaction_id):
    """Возврат с суммой как вещественным числом. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100.50, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-017")
def test_refund_currency_lowercase(payin_transaction_id):
    """Возврат с валютой в нижнем регистре. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "rub"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-018")
def test_refund_no_auth():
    """Refund без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(url, data=raw, headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-019")
def test_refund_invalid_signature():
    """Refund с подписью из нулей. Ожидается 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-020")
def test_refund_missing_terminal_id():
    """Refund без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-021")
def test_refund_missing_timestamp():
    """Refund без Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
    }
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КОНФЛИКТНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-022")
def test_refund_exceeds_remaining():
    """Второй возврат превышает оставшуюся сумму. Ожидается 400 или 409."""
    tid = _make_auto_payin("order_refund_exceed_remain")
    body_first = {
        "merchant_data": {"order_id": "order_refund_exceed_remain"},
        "financial_data": {"amount": 9500, "currency": "RUB"},
    }
    resp1 = post_operation(tid, "refund", body_first)
    assert resp1.status_code in (200, 201), f"First refund failed: {resp1.text}"
    body_second = {
        "merchant_data": {"order_id": "order_refund_exceed_remain"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp2 = post_operation(tid, "refund", body_second)
    assert resp2.status_code in (400, 409), f"Expected 400/409, got {resp2.status_code}: {resp2.text}"
    assert_error_response(resp2)


@pytest.mark.tcid("RF-023")
def test_refund_response_fields(payin_transaction_id):
    """Refund — проверка типов всех обязательных полей ответа."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["financial_data"]["currency"] == "RUB"
    assert data["type"] == "payin"
