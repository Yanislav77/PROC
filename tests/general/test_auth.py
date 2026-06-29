"""
Тесты авторизации — заголовки и HMAC-подпись.
POST /api/v1/transactions используется как базовый эндпоинт для проверок.
"""
import copy
import hashlib
import hmac
import json
import time
import uuid

import pytest
import requests

from conftest import (
    BASE_URL,
    SERVICE_SECRET,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    calc_signature,
    assert_transaction_response,
    assert_error_response,
    assert_idempotency_echo,
)

_VALID_BODY = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
    "transaction_data": {"method": "card", "details": CARD_DETAILS},
}


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-001")
def test_idempotency_key_deduplication():
    """Два запроса с одним Api-Idempotency-Key возвращают одинаковый transaction_id."""
    body = copy.deepcopy(_VALID_BODY)
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    idempotency_key = str(uuid.uuid4())

    def _send(ts: str):
        message = f"{ts}{TERMINAL_ID}{raw}"
        sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": idempotency_key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        r = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
        assert_idempotency_echo(headers, r)
        return r

    resp1 = _send(timestamp)
    resp2 = _send(str(int(time.time())))

    assert resp1.status_code == 201
    assert resp2.status_code == 201, f"Expected cached 201 for duplicate idempotency key, got {resp2.status_code}"
    assert resp1.json().get("transaction_id") == resp2.json().get("transaction_id"), \
        f"Cached response must return same transaction_id: {resp1.json()} vs {resp2.json()}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — заголовки подписи
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-002")
def test_invalid_signature():
    """Api-Signature заменена на строку из нулей. Ожидается 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-003")
def test_missing_signature_header():
    """Заголовок Api-Signature отсутствует. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-004")
def test_missing_terminal_id_header():
    """Отсутствующий Api-Terminal-ID отклоняется как невалидный запрос."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "irrelevant",
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-005")
def test_unknown_terminal_id():
    """Подпись посчитана для несуществующего терминала 99999. Ожидается 401, 403 или 404."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    message = f"{timestamp}99999{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     "99999",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (401, 403, 404), f"Expected 401/403/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-006")
def test_timestamp_too_old():
    """Api-Timestamp более чем на 5 минут в прошлом. Ожидается 400 Bad Request."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    old_ts = str(int(time.time()) - 400)
    message = f"{old_ts}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       old_ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-007")
def test_invalid_json_body():
    """Тело запроса — невалидный JSON. Ожидается 400."""
    raw = "this is not json"
    timestamp = str(int(time.time()))
    message = f"{timestamp}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ — граничные случаи (2.3–2.5)
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-008")
def test_idempotency_key_non_uuid():
    """Api-Idempotency-Key передан в не-UUID формате. Ожидается 200 или 201 (поле необязательно)."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    message = f"{timestamp}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": "not-a-uuid-value",
        "Api-Signature":       sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (200, 201, 400), f"Expected 2xx or 400, got {resp.status_code}"


@pytest.mark.tcid("A-009")
def test_no_idempotency_key():
    """Api-Idempotency-Key не передан. Ожидается 200 или 201 (заголовок необязателен)."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    message = f"{timestamp}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":    "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   sig,
        "Api-Timestamp":   timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (200, 201, 400), f"Expected 2xx or 400, got {resp.status_code}"


@pytest.mark.tcid("A-010")
def test_empty_idempotency_key():
    """Api-Idempotency-Key передан с пустым значением. Ожидается 200, 201 или 400."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    message = f"{timestamp}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": "",
        "Api-Signature":       sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (200, 201, 400), f"Expected 2xx or 400, got {resp.status_code}"


# ─────────────────────────────────────────────
# TERMINAL ID — пустое значение (3.6)
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-011")
def test_empty_terminal_id():
    """Api-Terminal-ID передан с пустым значением. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    message = f"{timestamp}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     "",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# SIGNATURE — пустое значение (4.3)
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-012")
def test_empty_signature():
    """Api-Signature передан с пустым значением. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "",
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TIMESTAMP — граничные случаи (5.2–5.7)
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-013")
def test_no_timestamp():
    """Api-Timestamp не передан. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-014")
def test_invalid_timestamp():
    """Api-Timestamp содержит нечисловое значение. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts = "not_a_timestamp"
    message = f"{ts}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-015")
def test_timestamp_recent_past():
    """Api-Timestamp — 4 минуты назад (в допустимом окне ±5 мин). Ожидается 201."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts = str(int(time.time()) - 240)
    message = f"{ts}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("A-016")
def test_timestamp_near_future():
    """Api-Timestamp — 4 минуты в будущем (в допустимом окне ±5 мин). Ожидается 201."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts = str(int(time.time()) + 240)
    message = f"{ts}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("A-017")
def test_timestamp_far_future():
    """Api-Timestamp — 10 минут в будущем (вне окна ±5 мин). Ожидается 400 Bad Request."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts = str(int(time.time()) + 600)
    message = f"{ts}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# POST без тела (65)
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-018")
def test_post_without_body():
    """POST /transactions без тела запроса. Ожидается 400."""
    raw = ""
    timestamp = str(int(time.time()))
    message = f"{timestamp}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (A-019 … A-025)
# ─────────────────────────────────────────────
@pytest.mark.tcid("A-019")
def test_signature_computed_over_wrong_body():
    """Подпись посчитана над другим телом (тело подменено). Ожидается 401/403."""
    raw_for_sig = json.dumps({"fake": "body"}, separators=(",", ":"))
    raw_to_send = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw_for_sig)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(BASE_URL, data=raw_to_send, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-020")
def test_signature_hex_uppercase():
    """Api-Signature в верхнем регистре. Ожидается 201 или 401/403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw).upper()
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (201, 401, 403), f"Expected 2xx or 4xx, got {resp.status_code}"


@pytest.mark.tcid("A-021")
def test_signature_wrong_length_32_chars():
    """Api-Signature длиной 32 символа вместо 64. Ожидается 400/401/403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature": "a" * 32,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-022")
def test_timestamp_boundary_exactly_5min_ago():
    """Api-Timestamp ровно 5 минут назад (граничное значение). Ожидается 400 или 201."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts = str(int(time.time()) - 300)
    sig = calc_signature(TERMINAL_ID, ts, raw)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature": sig,
        "Api-Timestamp": ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}"


@pytest.mark.tcid("A-023")
def test_timestamp_as_float():
    """Api-Timestamp содержит дробное значение. Ожидается 400/401/403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts = f"{int(time.time())}.5"
    sig = calc_signature(TERMINAL_ID, ts, raw)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature": sig,
        "Api-Timestamp": ts,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-024")
def test_idempotency_key_different_bodies_same_key():
    """Два разных тела с одним idempotency_key. Второй возвращает 201."""
    key = str(uuid.uuid4())
    body2 = copy.deepcopy(_VALID_BODY)
    body2["financial_data"]["amount"] = 5000

    raw1 = json.dumps(_VALID_BODY, separators=(",", ":"))
    ts1 = str(int(time.time()))
    h1 = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": calc_signature(TERMINAL_ID, ts1, raw1),
        "Api-Timestamp": ts1,
    }
    resp1 = requests.post(BASE_URL, data=raw1, headers=h1, timeout=30)
    assert_idempotency_echo(h1, resp1)
    assert resp1.status_code == 201, f"First request failed: {resp1.text}"

    raw2 = json.dumps(body2, separators=(",", ":"))
    ts2 = str(int(time.time()))
    h2 = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": calc_signature(TERMINAL_ID, ts2, raw2),
        "Api-Timestamp": ts2,
    }
    resp2 = requests.post(BASE_URL, data=raw2, headers=h2, timeout=30)
    assert_idempotency_echo(h2, resp2)
    assert resp2.status_code == 201, f"Expected 201 for same key different body, got {resp2.status_code}: {resp2.text}"


@pytest.mark.tcid("A-025")
def test_content_type_not_json():
    """Content-Type: text/plain вместо application/json. Ожидается 201."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw)
    headers = {
        "Content-Type": "text/plain",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, resp)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"


# ─────────────────────────────────────────────
# GET-ЗАПРОСЫ — АУТЕНТИФИКАЦИЯ (A-026 … A-033)
# Для GET: Api-Terminal-ID, Api-Signature, Api-Timestamp обязательны.
# Api-Idempotency-Key для GET не требуется — намеренно не включаем.
# Используем несуществующий ID /000000000000: если auth прошла → 404, иначе → 4xx auth-ошибка.
# ─────────────────────────────────────────────
_GET_URL = f"{BASE_URL}/000000000000"


@pytest.mark.tcid("A-026")
def test_get_empty_signature():
    """GET с пустым Api-Signature. Ожидается 400, 401 или 403."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "",
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-027")
def test_get_empty_terminal_id():
    """GET с пустым Api-Terminal-ID. Ожидается 400, 401 или 403."""
    ts = str(int(time.time()))
    headers = {
        "Api-Terminal-ID": "",
        "Api-Signature":   calc_signature("", ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-028")
def test_get_empty_timestamp():
    """GET с пустым Api-Timestamp. Ожидается 400, 401 или 403."""
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
        "Api-Timestamp":   "",
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-029")
def test_get_invalid_timestamp_non_numeric():
    """GET с нечисловым Api-Timestamp. Ожидается 400, 401 или 403."""
    ts = "not_a_timestamp"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   calc_signature(TERMINAL_ID, ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-030")
def test_get_timestamp_as_float():
    """GET с дробным Api-Timestamp. Ожидается 400, 401 или 403."""
    ts = f"{int(time.time())}.5"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   calc_signature(TERMINAL_ID, ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-031")
def test_get_timestamp_boundary_exactly_5min_ago():
    """GET с Api-Timestamp ровно 5 минут назад (граничное значение). Ожидается 400 или 404."""
    ts = str(int(time.time()) - 300)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   calc_signature(TERMINAL_ID, ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code in (400, 404), f"Expected 400 or 404, got {resp.status_code}"


@pytest.mark.tcid("A-032")
def test_get_timestamp_recent_past_within_window():
    """GET с Api-Timestamp 4 минуты назад (внутри окна ±5 мин). Auth должна пройти → 404."""
    ts = str(int(time.time()) - 240)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   calc_signature(TERMINAL_ID, ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code == 404, f"Expected 404 (auth OK, tx not found), got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("A-033")
def test_get_timestamp_near_future_within_window():
    """GET с Api-Timestamp 4 минуты в будущем (внутри окна ±5 мин). Auth должна пройти → 404."""
    ts = str(int(time.time()) + 240)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   calc_signature(TERMINAL_ID, ts),
        "Api-Timestamp":   ts,
    }
    resp = requests.get(_GET_URL, headers=headers, timeout=30)
    assert resp.status_code == 404, f"Expected 404 (auth OK, tx not found), got {resp.status_code}: {resp.text}"
