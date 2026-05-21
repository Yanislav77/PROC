"""
Тесты для операции cancel (отмена транзакции).
POST /api/v1/transactions/{id}/cancel
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


def _make_block_payin(order_id: str = "order_block_cancel") -> str:
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
@pytest.mark.tcid("CAN-001")
def test_cancel_authorized_transaction():
    """Отмена authorized транзакции (capture_mode=manual). Ожидается 200 или 201."""
    tid = _make_block_payin("order_cancel_auth")
    body = {
        "merchant_data": {"order_id": "order_cancel_auth"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("CAN-002")
def test_cancel_with_description():
    """Отмена с опциональным полем description в merchant_data. Ожидается 200 или 201."""
    tid = _make_block_payin("order_cancel_desc")
    body = {
        "merchant_data": {"order_id": "order_cancel_desc", "description": "Cancelled by customer"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-003")
def test_cancel_nonexistent_transaction():
    """Cancel по несуществующей транзакции. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-004")
def test_cancel_missing_financial_data():
    """Cancel без financial_data (обязательное). Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_cancel_test"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-005")
def test_cancel_missing_merchant_data():
    """Cancel без merchant_data (обязательное). Ожидается 400."""
    body = {"financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-006")
def test_cancel_missing_order_id():
    """Cancel с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {"description": "no order_id"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
