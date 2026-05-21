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


def test_invalid_json_body():
    """Тело запроса — невалидный JSON. Ожидается 400 или 422."""
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
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}"
    assert_error_response(resp)
