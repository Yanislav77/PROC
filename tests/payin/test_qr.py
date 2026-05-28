"""
Тесты для payin method=qr.
POST /api/v1/transactions — type:payin, method:qr
"""

import pytest
from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}


def _ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    return data


@pytest.mark.tcid("PO-010")
def test_payin_qr_missing_transaction_data():
    """Payin qr без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-022")
def test_payin_qr_response_fields():
    """Payin qr — ответ содержит все обязательные поля согласно спецификации."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_resp")},
        "transaction_data": {"method": "qr"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    assert data["financial_data"]["currency"] == "RUB"


@pytest.mark.tcid("PO-024")
def test_payin_qr_response_has_action_data():
    """Payin QR — ответ для QR может содержать action с QR-кодом (если waiting_action)."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_act")},
            "transaction_data": {"method": "qr"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    data = resp.json()
    assert_transaction_response(data)
    if data.get("status") == "waiting_action":
        assert "action" in data, "action отсутствует при status=waiting_action"


@pytest.mark.tcid("PO-028")
def test_payin_qr_negative_amount_returns_400():
    """Payin QR с отрицательной суммой. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_neg")},
            "financial_data": {"amount": -1, "currency": "RUB"},
            "transaction_data": {"method": "qr"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)
