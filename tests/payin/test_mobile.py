"""
Тесты для payin method=mobile.
POST /api/v1/transactions — type:payin, method:mobile
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


@pytest.mark.tcid("PO-015")
def test_payin_mobile_with_provider():
    """Payin mobile с необязательным полем provider. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mobile_provider")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS"}},
    }
    _ok(post_transaction(body))


@pytest.mark.tcid("PO-026")
def test_payin_mobile_response_fields():
    """Payin mobile — ответ содержит все обязательные поля."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_rf")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert_transaction_response(resp.json())
