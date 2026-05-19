"""
Негативные тесты CORE REST API.
Покрывают: отсутствие обязательных полей, невалидные значения,
неверную подпись, дедупликацию по idempotency key.
"""
import json
import time
import uuid
import hashlib
import hmac

import pytest
import requests

from conftest import (
    post_transaction,
    make_headers,
    BASE_URL,
    SERVICE_SECRET,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
VALID_PAYIN_BODY = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
    "transaction_data": {"method": "card", "details": CARD_DETAILS},
}


def assert_error(resp, expected_status: int):
    assert resp.status_code == expected_status, (
        f"Expected {expected_status}, got {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    assert isinstance(data, dict), "Error response is not a JSON object"
    return data


def post_raw(body: dict, terminal_id: str = None) -> requests.Response:
    """Собирает запрос с корректной подписью, но произвольным телом."""
    tid = terminal_id or TERMINAL_ID
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(tid, raw)
    return requests.post(BASE_URL, data=raw, headers=headers, timeout=30)


# ─────────────────────────────────────────────
# ОТСУТСТВИЕ ОБЯЗАТЕЛЬНЫХ ПОЛЕЙ ВЕРХНЕГО УРОВНЯ
# ─────────────────────────────────────────────
@pytest.mark.parametrize("missing_field", [
    "type",
    "merchant_data",
    "financial_data",
    "customer_data",
    "transaction_data",
])
def test_missing_top_level_field(missing_field):
    """Каждое из 5 обязательных полей верхнего уровня по одному удаляется из запроса. Ожидается 422."""
    body = {k: v for k, v in VALID_PAYIN_BODY.items() if k != missing_field}
    resp = post_raw(body)
    assert_error(resp, 422)


# ─────────────────────────────────────────────
# НЕВАЛИДНЫЙ ТИП ТРАНЗАКЦИИ
# ─────────────────────────────────────────────
def test_invalid_transaction_type():
    """Передаётся неизвестный тип транзакции. Ожидается 422."""
    body = {**VALID_PAYIN_BODY, "type": "unknown_type"}
    resp = post_raw(body)
    assert_error(resp, 422)


# ─────────────────────────────────────────────
# ФИНАНСОВЫЕ ДАННЫЕ — невалидные значения
# ─────────────────────────────────────────────
def test_negative_amount():
    """Отрицательная сумма. Ожидается 422."""
    body = {**VALID_PAYIN_BODY, "financial_data": {"amount": -100, "currency": "RUB"}}
    resp = post_raw(body)
    assert_error(resp, 422)


def test_zero_amount():
    """Нулевая сумма. Ожидается 422."""
    body = {**VALID_PAYIN_BODY, "financial_data": {"amount": 0, "currency": "RUB"}}
    resp = post_raw(body)
    assert_error(resp, 422)


def test_invalid_currency():
    """Несуществующий код валюты. Ожидается 422."""
    body = {**VALID_PAYIN_BODY, "financial_data": {"amount": 1000, "currency": "INVALID"}}
    resp = post_raw(body)
    assert_error(resp, 422)


def test_missing_currency():
    """Поле currency отсутствует в financial_data. Ожидается 422."""
    body = {**VALID_PAYIN_BODY, "financial_data": {"amount": 1000}}
    resp = post_raw(body)
    assert_error(resp, 422)


# ─────────────────────────────────────────────
# MERCHANT DATA — отсутствие обязательных полей
# ─────────────────────────────────────────────
def test_missing_merchant_order_id():
    """Поле order_id отсутствует в merchant_data. Ожидается 422."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    body = {**VALID_PAYIN_BODY, "merchant_data": merchant}
    resp = post_raw(body)
    assert_error(resp, 422)


# ─────────────────────────────────────────────
# ДАННЫЕ КАРТЫ — невалидные значения
# ─────────────────────────────────────────────
def test_invalid_card_pan():
    """PAN из 4 цифр — слишком короткий. Ожидается 422."""
    details = {**CARD_DETAILS, "pan": "1234"}
    body = {
        **VALID_PAYIN_BODY,
        "transaction_data": {"method": "card", "details": details},
    }
    resp = post_raw(body)
    assert_error(resp, 422)


def test_expired_card():
    """Истёкший срок карты (год 2020). Ожидается 422."""
    details = {**CARD_DETAILS, "expiry_year": "20", "expiry_month": "01"}
    body = {
        **VALID_PAYIN_BODY,
        "transaction_data": {"method": "card", "details": details},
    }
    resp = post_raw(body)
    assert_error(resp, 422)


@pytest.mark.parametrize("missing_field", ["pan", "holder", "expiry_month", "expiry_year", "cvv"])
def test_missing_card_required_field(missing_field):
    """Каждое из 5 обязательных полей карты по одному удаляется из запроса. Ожидается 422."""
    details = {k: v for k, v in CARD_DETAILS.items() if k != missing_field}
    body = {
        **VALID_PAYIN_BODY,
        "transaction_data": {"method": "card", "details": details},
    }
    resp = post_raw(body)
    assert_error(resp, 422)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ — неверная подпись
# ─────────────────────────────────────────────
def test_invalid_signature():
    """Подпись заменена на строку из нулей. Ожидается 401 или 403."""
    raw = json.dumps(VALID_PAYIN_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0000000000000000000000000000000000000000000000000000000000000000",
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), (
        f"Expected 401 or 403 for bad signature, got {resp.status_code}"
    )


def test_missing_signature_header():
    """Заголовок Api-Signature отсутствует полностью. Ожидается 400, 401 или 403."""
    raw = json.dumps(VALID_PAYIN_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), (
        f"Expected 4xx for missing signature, got {resp.status_code}"
    )


def test_missing_terminal_id_header():
    """Заголовок Api-Terminal-ID отсутствует. Ожидается 400, 401 или 403."""
    raw = json.dumps(VALID_PAYIN_BODY, separators=(",", ":"))
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type":        "application/json",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "irrelevant",
        "Api-Timestamp":       timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403)


def test_unknown_terminal_id():
    """Подпись корректно посчитана для несуществующего терминала 99999. Ожидается 401, 403 или 404."""
    raw = json.dumps(VALID_PAYIN_BODY, separators=(",", ":"))
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
    assert resp.status_code in (401, 403, 404)


# ─────────────────────────────────────────────
# ДЕДУПЛИКАЦИЯ — повтор с тем же Idempotency-Key
# ─────────────────────────────────────────────
def test_idempotency_key_deduplication():
    """Два запроса с одним Api-Idempotency-Key должны вернуть одинаковый transaction_id."""
    import copy

    body = copy.deepcopy(VALID_PAYIN_BODY)
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    idempotency_key = str(uuid.uuid4())

    def send(ts: str):
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

    resp1 = send(timestamp)
    resp2 = send(str(int(time.time())))

    assert resp1.status_code == 201
    assert resp2.status_code in (200, 201), "Idempotent repeat should succeed"

    tid1 = resp1.json().get("transaction_id")
    tid2 = resp2.json().get("transaction_id")
    assert tid1 == tid2, f"Idempotency broken: got different IDs {tid1} vs {tid2}"


# ─────────────────────────────────────────────
# НЕВАЛИДНЫЙ JSON В ТЕЛЕ
# ─────────────────────────────────────────────
def test_invalid_json_body():
    """Тело запроса — невалидный JSON при Content-Type: application/json. Ожидается 400 или 422."""
    timestamp = str(int(time.time()))
    raw = "this is not json"
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
    assert resp.status_code in (400, 422)


# ─────────────────────────────────────────────
# REFUND — граничные случаи
# ─────────────────────────────────────────────
def test_refund_nonexistent_transaction():
    """Возврат по несуществующему transaction_id. Ожидается 404 или 422."""
    url = f"{BASE_URL}/nonexistent-id-000000/refund"
    body = {
        "merchant_data": {
            "order_id": "order_9987",
            "description": "Refund",
            "webhook_url": "https://example.com/",
        },
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (404, 422)


def test_refund_amount_exceeds_original(payin_transaction_id):
    """Сумма возврата (99999999) превышает сумму оригинальной транзакции (10000). Ожидается 400 или 422."""
    url = f"{BASE_URL}/{payin_transaction_id}/refund"
    body = {
        "merchant_data": {
            "order_id": "order_9987",
            "description": "Refund",
            "webhook_url": "https://example.com/",
        },
        "financial_data": {"amount": 99999999, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (422, 400)


# ─────────────────────────────────────────────
# TIMESTAMP — устаревший запрос
# ─────────────────────────────────────────────
def test_timestamp_too_old():
    """Запрос с Api-Timestamp более чем на 5 минут раньше текущего времени. Ожидается 401 или 403."""
    raw = json.dumps(VALID_PAYIN_BODY, separators=(",", ":"))
    old_timestamp = str(int(time.time()) - 400)  # ~6.5 минут назад
    message = f"{old_timestamp}{TERMINAL_ID}{raw}"
    sig = hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       old_timestamp,
    }
    resp = requests.post(BASE_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), (
        f"Expected 401 or 403 for old timestamp, got {resp.status_code}"
    )
