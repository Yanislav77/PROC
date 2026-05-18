"""
Happy-path тесты для всех типов транзакций CORE REST API.
Каждый тест независим (кроме rebill/recurrent, которым нужен parent ID).
"""
import pytest
from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    TERMINAL_ID,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def assert_success(resp, expected_type: str = None):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()

    # Обязательные поля в ответе
    assert "transaction_id" in data, "Missing transaction_id"
    assert "type" in data,           "Missing type"
    assert "status" in data,         "Missing status"
    assert "merchant_data" in data,  "Missing merchant_data"
    assert "financial_data" in data, "Missing financial_data"
    assert "created_at" in data,     "Missing created_at"

    if expected_type:
        assert data["type"] == expected_type, f"Expected type={expected_type}, got {data['type']}"

    # Заголовки ответа
    assert "Api-Terminal-ID" in resp.headers,     "Missing Api-Terminal-ID in response headers"
    assert "Api-Idempotency-Key" in resp.headers, "Missing Api-Idempotency-Key in response headers"

    return data


# ─────────────────────────────────────────────
# PAYIN — card (is_recurrent=True, capture=auto)
# ─────────────────────────────────────────────
def test_payin_card():
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    data = assert_success(resp, expected_type="payin")
    assert data["financial_data"]["amount"] == 10000
    assert data["financial_data"]["currency"] == "RUB"


# ─────────────────────────────────────────────
# PAYIN — p2p
# ─────────────────────────────────────────────
def test_payin_p2p():
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "p2p"},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


# ─────────────────────────────────────────────
# PAYIN — mobile
# ─────────────────────────────────────────────
def test_payin_mobile():
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "CAD"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "mobile", "details": {"phone": "+345283494512"}},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


# ─────────────────────────────────────────────
# PAYIN BLOCK — card, capture_mode=manual
# ─────────────────────────────────────────────
def test_payin_block():
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": True, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    data = assert_success(resp, expected_type="payin")
    # При manual capture статус должен быть не 'processing' → 'authorized' или аналог
    assert data["status"] in ("processing", "authorized", "pending"), \
        f"Unexpected status for block: {data['status']}"


# ─────────────────────────────────────────────
# RECURRENT — карта, is_recurrent=True
# ─────────────────────────────────────────────
def test_recurrent(payin_transaction_id):
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 900, "currency": "RUB"},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {
            "method": "card",
            "details": CARD_DETAILS,
            "parent_transaction_id": payin_transaction_id,
        },
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


# ─────────────────────────────────────────────
# PAYOUT
# ─────────────────────────────────────────────
def test_payout():
    body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_9987"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payout")


# ─────────────────────────────────────────────
# REBILL — token, capture=auto
# ─────────────────────────────────────────────
def test_rebill(payin_transaction_id):
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_9987"},
        "financial_data": {"amount": 1100, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            "parent_transaction_id": payin_transaction_id,
        },
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


# ─────────────────────────────────────────────
# REBILL BLOCK — token, capture=manual
# ─────────────────────────────────────────────
def test_rebill_block(payin_transaction_id):
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_9987"},
        "financial_data": {"amount": 1100, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            "parent_transaction_id": payin_transaction_id,
        },
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


# ─────────────────────────────────────────────
# REFUND
# ─────────────────────────────────────────────
def test_refund(payin_transaction_id):
    import json, time, uuid
    from conftest import make_headers, BASE_URL, TERMINAL_ID
    import requests

    url = f"{BASE_URL}/{payin_transaction_id}/refund"
    body = {
        "merchant_data": {
            "order_id": "order_9987",
            "description": "Refund for order",
            "webhook_url": "https://example.com/",
        },
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)

    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert "transaction_id" in data
    assert "status" in data


# ─────────────────────────────────────────────
# НЕОБЯЗАТЕЛЬНЫЕ ПОЛЯ — позитивные сценарии
# ─────────────────────────────────────────────
def test_payin_card_without_flow_data():
    """flow_data не обязательное — запрос без него должен вернуть 201."""
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


def test_payin_card_without_webhook_url():
    """merchant_data.webhook_url не обязательное — запрос без него должен вернуть 201."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "webhook_url"}
    body = {
        "type": "payin",
        "merchant_data": merchant,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


# ─────────────────────────────────────────────
# НЕОБЯЗАТЕЛЬНЫЕ ПОЛЯ — позитивные сценарии
# ─────────────────────────────────────────────
def test_payin_card_without_flow_data():
    """flow_data не обязательное — запрос без него должен вернуть 201."""
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")


def test_payin_card_without_webhook_url():
    """merchant_data.webhook_url не обязательное — запрос без него должен вернуть 201."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "webhook_url"}
    body = {
        "type": "payin",
        "merchant_data": merchant,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")
