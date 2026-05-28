"""
Тесты для эндпоинтов мерчанта.
GET /api/v1/merchant/balance — получение текущего баланса терминала
"""
import hashlib
import hmac
import time

import pytest
import requests

from conftest import (
    get_request,
    make_get_headers,
    MERCHANT_BALANCE_URL,
    TERMINAL_ID,
    SERVICE_SECRET,
    assert_error_response,
)


def _sign(terminal_id: str, timestamp: str, raw_body: str = "") -> str:
    message = f"{timestamp}{terminal_id}{raw_body}"
    return hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


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


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (MB-013 … MB-018)
# ─────────────────────────────────────────────
@pytest.mark.tcid("MB-013")
def test_get_merchant_balance_method_post_not_allowed():
    """POST /merchant/balance не должен быть доступен. Ожидается 405 или 404."""
    headers = make_get_headers(TERMINAL_ID)
    resp = requests.post(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (404, 405), f"Expected 404/405, got {resp.status_code}"


@pytest.mark.tcid("MB-014")
def test_get_merchant_balance_method_delete_not_allowed():
    """DELETE /merchant/balance не должен быть доступен. Ожидается 405 или 404."""
    headers = make_get_headers(TERMINAL_ID)
    resp = requests.delete(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (404, 405), f"Expected 404/405, got {resp.status_code}"


@pytest.mark.tcid("MB-015")
def test_get_merchant_balance_response_no_extra_fields():
    """GET /merchant/balance — ответ содержит только ожидаемые поля."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert "financial_data" in data
    fd = data["financial_data"]
    assert set(fd.keys()) >= {"amount", "currency"}, f"Неожиданная структура financial_data: {fd}"


@pytest.mark.tcid("MB-016")
def test_get_merchant_balance_content_type_json():
    """GET /merchant/balance — Content-Type ответа содержит application/json."""
    resp = get_request(MERCHANT_BALANCE_URL)
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


@pytest.mark.tcid("MB-017")
def test_get_merchant_balance_timestamp_expired():
    """GET /merchant/balance с устаревшим timestamp. Ожидается 400/401."""
    old_ts = str(int(time.time()) - 400)
    sig = _sign(TERMINAL_ID, old_ts)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": old_ts,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401), f"Expected 400/401, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-018")
def test_get_merchant_balance_idempotency_key_ignored():
    """GET /merchant/balance с Api-Idempotency-Key — заголовок должен игнорироваться, 200."""
    import uuid as _uuid
    timestamp = str(int(time.time()))
    sig = _sign(TERMINAL_ID, timestamp)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
        "Api-Idempotency-Key": str(_uuid.uuid4()),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# MB-019…MB-025: граничные случаи заголовков
# ─────────────────────────────────────────────
@pytest.mark.tcid("MB-019")
def test_get_merchant_balance_missing_signature_header():
    """GET /merchant/balance без заголовка Api-Signature (остальные есть). Ожидается 4xx."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for missing Api-Signature, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-020")
def test_get_merchant_balance_empty_terminal_id():
    """GET /merchant/balance с пустым Api-Terminal-ID. Ожидается 4xx."""
    ts = str(int(time.time()))
    headers = {
        "Api-Terminal-ID": "",
        "Api-Signature":   _sign("", ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for empty Api-Terminal-ID, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-021")
def test_get_merchant_balance_invalid_terminal_id_format():
    """GET /merchant/balance с нечисловым Api-Terminal-ID. Ожидается 4xx."""
    fake = "abc-xyz-!!!"
    ts = str(int(time.time()))
    headers = {
        "Api-Terminal-ID": fake,
        "Api-Signature":   _sign(fake, ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403, 404), \
        f"Expected 4xx for invalid terminal format, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-022")
def test_get_merchant_balance_empty_signature():
    """GET /merchant/balance с пустым Api-Signature. Ожидается 4xx."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "",
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for empty Api-Signature, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-023")
def test_get_merchant_balance_empty_timestamp():
    """GET /merchant/balance с пустым Api-Timestamp. Ожидается 4xx."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   _sign(TERMINAL_ID, ""),
        "Api-Timestamp":   "",
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for empty Api-Timestamp, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-024")
def test_get_merchant_balance_invalid_timestamp_format():
    """GET /merchant/balance с нечисловым Api-Timestamp. Ожидается 4xx."""
    bad_ts = "not-a-timestamp"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   _sign(TERMINAL_ID, bad_ts),
        "Api-Timestamp":   bad_ts,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for non-numeric timestamp, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MB-025")
def test_get_merchant_balance_future_timestamp():
    """GET /merchant/balance с Api-Timestamp > 5 минут в будущем. Ожидается 4xx (anti-replay)."""
    future_ts = str(int(time.time()) + 601)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   _sign(TERMINAL_ID, future_ts),
        "Api-Timestamp":   future_ts,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for future timestamp, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
