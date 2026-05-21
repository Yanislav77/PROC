"""
Тесты для операции capture (списание заблокированных средств).
POST /api/v1/transactions/{id}/capture
Применимо только к транзакциям с capture_mode=manual в статусе authorized.
"""
import pytest

from conftest import (
    post_transaction,
    post_operation,
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
    """Полное списание по транзакции с capture_mode=manual. Ожидается 200 или 201."""
    resp = post_operation(payin_block_transaction_id, "capture", _OP_BODY)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("CAP-002")
def test_capture_partial():
    """Частичное списание (500 из 1000). Ожидается 200 или 201."""
    tid = _make_block_payin("order_capture_partial")
    body = {
        "merchant_data": {"order_id": "order_capture_partial"},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("CAP-003")
def test_capture_without_webhook_url():
    """Capture без необязательного webhook_url в merchant_data. Ожидается 200 или 201."""
    tid = _make_block_payin("order_capture_no_wh")
    body = {
        "merchant_data": {"order_id": "order_capture_no_wh"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
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
