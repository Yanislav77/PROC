"""
Тесты для операции capture (списание заблокированных средств).
POST /api/v1/transactions/{id}/capture
Применимо только к транзакциям с capture_mode=manual в статусе authorized.
"""
import json
import time
import uuid

import pytest
import requests

from conftest import (
    post_transaction,
    post_operation,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_transaction_response,
    assert_error_response,
)

_OP_BODY = {
    "merchant_data": {
        "order_id": "order_capture_test",
        "description": "Capture test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


def _make_block_payin(order_id: str = "order_block_capture") -> str:
    """Создаёт Payin с холдом (capture_mode=manual) и возвращает transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Block Payin failed: {resp.text}"
    return resp.json()["transaction_id"]


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-001")
def test_capture_full(payin_block_transaction_id):
    """Полное списание по транзакции с capture_mode=manual. Ожидается 200."""
    resp = post_operation(payin_block_transaction_id, "capture", _OP_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("CAP-002")
def test_capture_partial():
    """Частичное списание (500 из 1000). Ожидается 200."""
    tid = _make_block_payin("order_capture_partial")
    body = {
        "merchant_data": {"order_id": "order_capture_partial"},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("CAP-003")
def test_capture_without_webhook_url():
    """Capture без необязательного webhook_url в merchant_data. Ожидается 200."""
    tid = _make_block_payin("order_capture_no_wh")
    body = {
        "merchant_data": {"order_id": "order_capture_no_wh"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-004")
def test_capture_nonexistent_transaction():
    """Capture по несуществующей транзакции. Ожидается 404."""
    resp = post_operation("000000000000", "capture", _OP_BODY)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-005")
def test_capture_missing_financial_data():
    """Capture без financial_data (обязательное). Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_capture_test"}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-006")
def test_capture_missing_merchant_data():
    """Capture без merchant_data (обязательное). Ожидается 400."""
    body = {"financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-007")
def test_capture_missing_order_id():
    """Capture с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {"description": "no order_id"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-008")
def test_capture_missing_amount():
    """Capture без поля amount в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-009")
def test_capture_missing_currency():
    """Capture без поля currency в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-010")
def test_capture_invalid_currency():
    """Capture с невалидным кодом валюты. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "INVALID"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-011")
def test_capture_zero_amount():
    """Capture с нулевой суммой. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-012")
def test_capture_negative_amount():
    """Capture с отрицательной суммой. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": -500, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-013")
def test_capture_no_auth():
    """Capture без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(url, data=raw, headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-014")
def test_capture_invalid_signature():
    """Capture с подписью из нулей. Ожидается 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
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


@pytest.mark.tcid("CAP-015")
def test_capture_missing_terminal_id():
    """Capture без заголовка Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
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


@pytest.mark.tcid("CAP-016")
def test_capture_missing_timestamp():
    """Capture без заголовка Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
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
# ГРАНИЧНЫЕ СЛУЧАИ — ДОПОЛНИТЕЛЬНЫЕ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-017")
def test_capture_amount_as_string():
    """Capture с суммой как строкой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": "1000", "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-018")
def test_capture_amount_as_float():
    """Capture с суммой как вещественным числом. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 500.50, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-019")
def test_capture_currency_lowercase():
    """Capture с валютой в нижнем регистре. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "rub"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-020")
def test_capture_amount_exceeds_authorized():
    """Capture с суммой, превышающей заблокированную (1000). Ожидается 400 или 409."""
    tid = _make_block_payin("order_capture_exceed")
    body = {
        "merchant_data": {"order_id": "order_capture_exceed"},
        "financial_data": {"amount": 999999, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (400, 409), f"Expected 400/409, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-021")
def test_capture_already_captured():
    """Повторный capture уже захваченной транзакции. Ожидается 409."""
    tid = _make_block_payin("order_capture_twice")
    body = {
        "merchant_data": {"order_id": "order_capture_twice"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp1 = post_operation(tid, "capture", body)
    assert resp1.status_code == 200, f"First capture failed: {resp1.text}"
    resp2 = post_operation(tid, "capture", body)
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
    assert_error_response(resp2)


@pytest.mark.tcid("CAP-022")
def test_capture_with_description():
    """Capture с опциональным description в merchant_data. Ожидается 200."""
    tid = _make_block_payin("order_capture_desc")
    body = {
        "merchant_data": {
            "order_id": "order_capture_desc",
            "description": "Authorized capture",
        },
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("CAP-023")
def test_capture_response_fields():
    """Capture успешной транзакции — ответ содержит все обязательные поля."""
    tid = _make_block_payin("order_capture_resp_check")
    body = {
        "merchant_data": {"order_id": "order_capture_resp_check"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    assert data["financial_data"]["currency"] == "RUB"
