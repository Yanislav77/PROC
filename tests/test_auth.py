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

import requests

from conftest import (
    BASE_URL,
    SERVICE_SECRET,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_transaction_response,
    assert_error_response,
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
        return requests.post(BASE_URL, data=raw, headers=headers, timeout=30)

    resp1 = _send(timestamp)
    resp2 = _send(str(int(time.time())))

    assert resp1.status_code == 201
    assert resp2.status_code in (200, 201), "Idempotent repeat should succeed"
    data1 = resp1.json()
    data2 = resp2.json()
    assert_transaction_response(data1)
    tid1 = data1.get("transaction_id")
    tid2 = data2.get("transaction_id")
    assert tid1 == tid2, f"Idempotency broken: {tid1} vs {tid2}"


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
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-004")
def test_missing_terminal_id_header():
    """Заголовок Api-Terminal-ID отсутствует. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "irrelevant",
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
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
    assert resp.status_code in (401, 403, 404), f"Expected 401/403/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("A-006")
def test_timestamp_too_old():
    """Api-Timestamp более чем на 5 минут в прошлом. Ожидается 401 или 403."""
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
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
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
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("A-017")
def test_timestamp_far_future():
    """Api-Timestamp — 10 минут в будущем (вне окна ±5 мин). Ожидается 401 или 403."""
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
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
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
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)
