"""
Тесты для операций над существующими транзакциями:
POST /{id}/capture  — списание заблокированных средств (capture_mode=manual)
POST /{id}/cancel   — отмена транзакции
POST /{id}/confirm  — подтверждение ожидающего действия (3DS, redirect и т.д.)
POST /{id}/refund   — возврат средств (дополнительные кейсы к test_happy_path.py)
"""
import pytest

from conftest import (
    post_transaction,
    post_operation,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
)

# Тело для capture/cancel — OperationRequest по спецификации
_OP_BODY = {
    "merchant_data": {
        "order_id": "order_op_test",
        "description": "Operation test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


def _make_block_payin(order_id: str = "order_block_inline") -> str:
    """Создаёт свежий Payin с холдом и возвращает transaction_id."""
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
# CAPTURE — happy path
# ─────────────────────────────────────────────
def test_capture_after_block(payin_block_transaction_id):
    """Списание средств через /capture по транзакции с capture_mode=manual. Ожидается 200 или 201."""
    resp = post_operation(payin_block_transaction_id, "capture", _OP_BODY)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data, "Missing transaction_id in capture response"
    assert "status" in data,         "Missing status in capture response"


def test_capture_partial_amount():
    """Частичное списание (меньше заблокированной суммы). Ожидается 200 или 201."""
    tid = _make_block_payin("order_capture_partial")
    body = {
        "merchant_data": {"order_id": "order_capture_partial"},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


def test_capture_without_webhook_url():
    """Capture без необязательного webhook_url в merchant_data. Ожидается 200 или 201."""
    tid = _make_block_payin("order_capture_no_webhook")
    body = {
        "merchant_data": {"order_id": "order_capture_no_webhook"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CAPTURE — негативные сценарии
# ─────────────────────────────────────────────
def test_capture_nonexistent_transaction():
    """Capture по несуществующей транзакции. Ожидается 404."""
    resp = post_operation("000000000000", "capture", _OP_BODY)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_capture_missing_financial_data():
    """Capture без поля financial_data (обязательное). Ожидается 400 или 422."""
    body = {"merchant_data": {"order_id": "order_op_test"}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_missing_merchant_data():
    """Capture без поля merchant_data (обязательное). Ожидается 400 или 422."""
    body = {"financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_missing_order_id():
    """Capture с merchant_data без order_id (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"description": "no order_id"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_missing_amount():
    """Capture с financial_data без amount. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_missing_currency():
    """Capture с financial_data без currency. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_invalid_currency():
    """Capture с невалидным кодом валюты. Ожидается 400, 404 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "INVALID"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_zero_amount():
    """Capture с нулевой суммой. Ожидается 400, 404 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_capture_negative_amount():
    """Capture с отрицательной суммой. Ожидается 400, 404 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": -500, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CANCEL — happy path
# ─────────────────────────────────────────────
def test_cancel_transaction():
    """Отмена транзакции с холдом (authorized). Ожидается 200 или 201."""
    tid = _make_block_payin("order_cancel_test")
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data, "Missing transaction_id in cancel response"
    assert "status" in data,         "Missing status in cancel response"


def test_cancel_with_description():
    """Отмена транзакции с опциональным полем description. Ожидается 200 или 201."""
    tid = _make_block_payin("order_cancel_desc")
    body = {
        "merchant_data": {
            "order_id": "order_cancel_desc",
            "description": "Cancelled by customer",
        },
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CANCEL — негативные сценарии
# ─────────────────────────────────────────────
def test_cancel_nonexistent_transaction():
    """Cancel по несуществующей транзакции. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_cancel_missing_financial_data():
    """Cancel без financial_data (обязательное). Ожидается 400 или 422."""
    body = {"merchant_data": {"order_id": "order_op_test"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_cancel_missing_merchant_data():
    """Cancel без merchant_data (обязательное). Ожидается 400 или 422."""
    body = {"financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_cancel_missing_order_id():
    """Cancel с merchant_data без order_id. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"description": "no order_id"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CONFIRM — негативные сценарии
# (happy path требует транзакцию в статусе waiting_action, которую сложно гарантировать в тестах)
# ─────────────────────────────────────────────
def test_confirm_nonexistent_transaction():
    """Confirm по несуществующей транзакции. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares", "md": "test_md"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_confirm_missing_result():
    """Confirm без поля result (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_missing_financial_data():
    """Confirm без financial_data (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_missing_merchant_data():
    """Confirm без merchant_data (обязательное). Ожидается 400 или 422."""
    body = {
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_missing_order_id():
    """Confirm с merchant_data без order_id. Ожидается 400 или 422."""
    body = {
        "merchant_data": {},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_invalid_result_type():
    """Confirm с неизвестным типом result. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "unknown_action", "details": {}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_threed_secure_missing_pares():
    """Confirm 3DS без поля pares (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"md": "test_md"}},  # pares отсутствует
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_threed_secure_missing_md():
    """Confirm 3DS без поля md (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares"}},  # md отсутствует
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


def test_confirm_generic_missing_confirmed():
    """Confirm redirect/transfer без поля confirmed (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_op_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "redirect",
            "details": {},  # confirmed отсутствует
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# REFUND — дополнительные негативные кейсы по полям
# (базовые кейсы есть в test_negative.py и test_happy_path.py)
# ─────────────────────────────────────────────
def test_refund_missing_merchant_data(payin_transaction_id):
    """Возврат без merchant_data (обязательное). Ожидается 400 или 422."""
    body = {"financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_financial_data(payin_transaction_id):
    """Возврат без financial_data (обязательное). Ожидается 400 или 422."""
    body = {"merchant_data": {"order_id": "order_9987"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_order_id(payin_transaction_id):
    """Возврат с merchant_data без order_id (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"description": "Refund"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_currency(payin_transaction_id):
    """Возврат без поля currency в financial_data. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_9987"},
        "financial_data": {"amount": 100},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_missing_amount(payin_transaction_id):
    """Возврат без поля amount в financial_data. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_9987"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_zero_amount(payin_transaction_id):
    """Возврат с нулевой суммой. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_9987"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_negative_amount(payin_transaction_id):
    """Возврат с отрицательной суммой. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_9987"},
        "financial_data": {"amount": -100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_refund_invalid_currency(payin_transaction_id):
    """Возврат с невалидным кодом валюты. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_9987"},
        "financial_data": {"amount": 100, "currency": "INVALID"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"
