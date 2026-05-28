"""
Тесты для payin method=p2p.
POST /api/v1/transactions — type:payin, method:p2p
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


@pytest.mark.tcid("PO-007")
def test_payin_p2p_missing_transaction_data():
    """Payin p2p без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-009")
def test_payin_p2p_with_description():
    """Payin p2p с опциональным description. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_desc"), "description": "P2P test"},
        "transaction_data": {"method": "p2p"},
    }
    _ok(post_transaction(body))


@pytest.mark.tcid("PO-020")
def test_payin_unknown_method():
    """Payin с неизвестным методом. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "unknown_method"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-021")
def test_payin_missing_transaction_data():
    """Payin без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-023")
def test_payin_p2p_response_fields():
    """Payin p2p — ответ содержит transaction_id, status, type, created_at."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_resp")},
        "transaction_data": {"method": "p2p"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("PO-025")
def test_payin_p2p_response_has_action_data():
    """Payin P2P — ответ может содержать action с реквизитами перевода."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_act")},
            "transaction_data": {"method": "p2p"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    data = resp.json()
    assert_transaction_response(data)


@pytest.mark.tcid("PO-027")
def test_payin_p2p_zero_amount_returns_400():
    """Payin P2P с нулевой суммой. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_z")},
            "financial_data": {"amount": 0, "currency": "RUB"},
            "transaction_data": {"method": "p2p"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)
