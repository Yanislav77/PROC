"""
Тесты для payin с методами p2p, qr, mobile и token.
POST /api/v1/transactions — type:payin, method: p2p | qr | mobile | token
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
)

_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}


def _assert_payin_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data
    assert data["type"] == "payin"
    assert "status" in data
    return data


# ─────────────────────────────────────────────
# HAPPY PATH — p2p
# ─────────────────────────────────────────────
def test_payin_p2p():
    """Payin через P2P-перевод — method=p2p, детали карты не требуются."""
    _assert_payin_ok(post_transaction({**_BASE, "transaction_data": {"method": "p2p"}}))


# ─────────────────────────────────────────────
# HAPPY PATH — qr
# ─────────────────────────────────────────────
def test_payin_qr():
    """Payin через QR-код — method=qr."""
    _assert_payin_ok(post_transaction({**_BASE, "transaction_data": {"method": "qr"}}))


# ─────────────────────────────────────────────
# HAPPY PATH — mobile
# ─────────────────────────────────────────────
def test_payin_mobile():
    """Payin через мобильный платёж — phone обязателен."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# HAPPY PATH — token (rebill)
# ─────────────────────────────────────────────
def test_payin_token_rebill(payin_transaction_id):
    """Ребилл по сохранённому токену карты (method=token), capture=auto."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_rebill"},
        "financial_data": {"amount": 1100, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            "parent_transaction_id": payin_transaction_id,
        },
    }
    _assert_payin_ok(post_transaction(body))


def test_payin_token_rebill_manual_capture(payin_transaction_id):
    """Ребилл по токену с блокировкой средств (capture=manual)."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_rebill_manual"},
        "financial_data": {"amount": 1100, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            "parent_transaction_id": payin_transaction_id,
        },
    }
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — mobile
# ─────────────────────────────────────────────
def test_payin_mobile_missing_phone():
    """Payin mobile без поля phone (обязательное). Ожидается 422."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
