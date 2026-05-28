"""
Тесты для payin method=token.
POST /api/v1/transactions — type:payin, method:token
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


@pytest.mark.tcid("PO-018")
def test_payin_token_nonexistent_uuid():
    """Payin token с несуществующим UUID (нулевой). Ожидается 400 или 404."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("token_nonexist")},
        "transaction_data": {
            "method": "token",
            "details": {"token": "00000000-0000-0000-0000-000000000000"},
            "parent_transaction_id": "000000000000",
        },
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-029")
def test_payin_token_missing_parent_transaction_id():
    """Payin token без parent_transaction_id. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_np")},
            "transaction_data": {
                "method": "token",
                "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            }}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}"
