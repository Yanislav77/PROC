"""
Тесты для эндпоинтов мерчанта.
GET /api/v1/merchant/balance — получение текущего баланса терминала
"""
import time
import requests

from conftest import (
    get_request,
    MERCHANT_BALANCE_URL,
    TERMINAL_ID,
)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
def test_get_merchant_balance():
    """Получение баланса мерчанта. Ожидается 200 с полями amount и currency."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "financial_data" in data,               "Missing financial_data"
    assert "amount" in data["financial_data"],      "Missing amount in financial_data"
    assert "currency" in data["financial_data"],    "Missing currency in financial_data"
    assert isinstance(data["financial_data"]["amount"], int), "amount must be an integer"


def test_get_merchant_balance_currency_format():
    """Баланс мерчанта — currency содержит 3-символьный ISO 4217 код."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    currency = resp.json()["financial_data"]["currency"]
    assert len(currency) == 3, f"Currency must be 3 chars, got: {currency!r}"
    assert currency.isupper(), f"Currency should be uppercase, got: {currency!r}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — авторизация
# ─────────────────────────────────────────────
def test_get_merchant_balance_no_auth():
    """GET /merchant/balance без заголовков авторизации. Ожидается 400, 401 или 403."""
    resp = requests.get(MERCHANT_BALANCE_URL, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"


def test_get_merchant_balance_invalid_signature():
    """GET /merchant/balance с подписью из нулей. Ожидается 401 или 403."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_get_merchant_balance_missing_terminal_id():
    """GET /merchant/balance без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    headers = {
        "Api-Signature": "0" * 64,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"


def test_get_merchant_balance_missing_timestamp():
    """GET /merchant/balance без Api-Timestamp. Ожидается 400, 401 или 403."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"


def test_get_merchant_balance_unknown_terminal():
    """GET /merchant/balance с несуществующим терминалом. Ожидается 401, 403 или 404."""
    import hashlib
    import hmac
    from conftest import SERVICE_SECRET
    timestamp = str(int(time.time()))
    message = f"{timestamp}99999"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Api-Terminal-ID": "99999",
        "Api-Signature":   sig,
        "Api-Timestamp":   timestamp,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (401, 403, 404), f"Expected 401/403/404, got {resp.status_code}"
