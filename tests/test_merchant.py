"""
Тесты для эндпоинтов мерчанта.
GET /api/v1/merchant/balance — получение текущего баланса терминала
"""
import time

import pytest
import requests

from conftest import (
    get_request,
    MERCHANT_BALANCE_URL,
    TERMINAL_ID,
    assert_error_response,
)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("MB-001")
def test_get_merchant_balance():
    """Получение баланса мерчанта. Ожидается 200 с полями amount и currency."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "financial_data" in data,               "Missing financial_data"
    assert "amount" in data["financial_data"],      "Missing amount in financial_data"
    assert "currency" in data["financial_data"],    "Missing currency in financial_data"
    assert isinstance(data["financial_data"]["amount"], int), "amount must be an integer"


@pytest.mark.tcid("MB-002")
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
@pytest.mark.tcid("MB-003")
def test_get_merchant_balance_no_auth():
    """GET /merchant/balance без заголовков авторизации. Ожидается 400, 401 или 403."""
    resp = requests.get(MERCHANT_BALANCE_URL, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-004")
def test_get_merchant_balance_invalid_signature():
    """GET /merchant/balance с подписью из нулей. Ожидается 401 или 403."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-005")
def test_get_merchant_balance_missing_terminal_id():
    """GET /merchant/balance без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    headers = {
        "Api-Signature": "0" * 64,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-006")
def test_get_merchant_balance_missing_timestamp():
    """GET /merchant/balance без Api-Timestamp. Ожидается 400, 401 или 403."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-007")
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
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ПРОВЕРКА ПОЛЕЙ И ЛОГИКА ОТВЕТА
# ─────────────────────────────────────────────
@pytest.mark.tcid("MB-008")
def test_get_merchant_balance_amount_non_negative():
    """Баланс мерчанта — amount не может быть отрицательным."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    amount = resp.json()["financial_data"]["amount"]
    assert amount >= 0, f"Balance amount must be non-negative, got {amount}"


@pytest.mark.tcid("MB-009")
def test_get_merchant_balance_response_is_object():
    """Ответ на GET /merchant/balance — JSON объект (не массив)."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}: {resp.text[:200]}"


@pytest.mark.tcid("MB-010")
def test_get_merchant_balance_currency_is_string():
    """Баланс мерчанта — currency является строкой из 3 букв верхнего регистра."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    currency = resp.json().get("financial_data", {}).get("currency", "")
    assert isinstance(currency, str), f"currency must be str, got {type(currency).__name__}"
    assert len(currency) == 3 and currency.isalpha() and currency.isupper(), \
        f"currency must be 3-char uppercase alpha, got {currency!r}"


@pytest.mark.tcid("MB-011")
def test_get_merchant_balance_financial_data_present():
    """GET /merchant/balance — ответ содержит ключ financial_data с amount и currency."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "financial_data" in data, "Missing key 'financial_data' in response"
    fd = data["financial_data"]
    assert "amount" in fd, "Missing 'amount' in financial_data"
    assert "currency" in fd, "Missing 'currency' in financial_data"


@pytest.mark.tcid("MB-012")
def test_get_merchant_balance_stable_structure():
    """Два последовательных запроса баланса возвращают одинаковую структуру ответа."""
    resp1 = get_request(MERCHANT_BALANCE_URL)
    resp2 = get_request(MERCHANT_BALANCE_URL)
    assert resp1.status_code == 200 and resp2.status_code == 200
    keys1 = set(resp1.json().keys())
    keys2 = set(resp2.json().keys())
    assert keys1 == keys2, f"Response keys differ: {keys1} vs {keys2}"
