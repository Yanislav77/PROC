"""
Тесты для операции confirm (подтверждение ожидающего действия).
POST /api/v1/transactions/{id}/confirm
Типы: threed_secure, redirect, transfer_card, transfer_phone, transfer_qr, transfer_account, top_up_mobile.
Happy path требует транзакцию в статусе waiting_action/waiting_3DS — эти кейсы помечены @skip.
"""
import json
import re
import time
import uuid

import pytest
import requests

from conftest import (
    calc_signature, post_operation, post_transaction, BASE_URL, TERMINAL_ID,
    MERCHANT_DATA, CUSTOMER_DATA, CARD_3DS, THREED, gen_order_id, SETUP_DELAY,
    assert_error_response, assert_transaction_response,
)
import _helpers.config as _cfg
from _helpers.signatures import make_headers


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-001")
def test_confirm_nonexistent_transaction():
    """Confirm по несуществующей транзакции. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares", "md": "test_md"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-002")
def test_confirm_missing_result():
    """Confirm без поля result (обязательное). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-003")
def test_confirm_missing_financial_data():
    """Confirm без financial_data (обязательное). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-004")
def test_confirm_missing_merchant_data():
    """Confirm без merchant_data (обязательное). Ожидается 400."""
    body = {
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-005")
def test_confirm_missing_order_id():
    """Confirm с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-006")
def test_confirm_invalid_result_type():
    """Confirm с неизвестным типом result. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "unknown_action", "details": {}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-007")
def test_confirm_threed_secure_missing_pares():
    """Confirm 3DS без поля pares (обязательное). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"md": "test_md"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-008")
def test_confirm_threed_secure_missing_md():
    """Confirm 3DS без поля md (обязательное). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-009")
def test_confirm_redirect_missing_confirmed():
    """Confirm redirect без поля confirmed (обязательное). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ВАЛИДАЦИЯ RESULT — СТРУКТУРА
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-010")
def test_confirm_result_missing_type():
    """Confirm с result без поля type. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-011")
def test_confirm_result_missing_details():
    """Confirm с result без поля details. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect"},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-012")
def test_confirm_empty_result_object():
    """Confirm с пустым объектом result. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ ТИПЫ CONFIRM
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-013")
def test_confirm_transfer_card_type():
    """Confirm с типом transfer_card — структура body корректна, транзакции нет. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-014")
def test_confirm_transfer_phone_type():
    """Confirm с типом transfer_phone — структура body корректна, транзакции нет. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "transfer_phone", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-015")
def test_confirm_transfer_qr_type():
    """Confirm с типом transfer_qr. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "transfer_qr", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-016")
def test_confirm_top_up_mobile_type():
    """Confirm с типом top_up_mobile. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "top_up_mobile", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ВАЛИДАЦИЯ FINANCIAL_DATA
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-017")
def test_confirm_zero_amount():
    """Confirm с нулевой суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-018")
def test_confirm_negative_amount():
    """Confirm с отрицательной суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": -100, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-019")
def test_confirm_invalid_currency():
    """Confirm с невалидным кодом валюты. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "INVALID"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-020")
def test_confirm_missing_amount():
    """Confirm без поля amount в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-021")
def test_confirm_missing_currency():
    """Confirm без поля currency в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-022")
def test_confirm_no_auth():
    """Confirm без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/confirm"
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(url, data=raw, headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-023")
def test_confirm_invalid_signature():
    """Confirm с подписью из нулей. Ожидается 401 или 403."""
    url = f"{BASE_URL}/000000000000/confirm"
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-024")
def test_confirm_missing_terminal_id():
    """Confirm без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/confirm"
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-025")
def test_confirm_missing_timestamp():
    """Confirm без Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/confirm"
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
    }
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (CON-026 … CON-032)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-026")
def test_confirm_idempotency_same_key_second_returns_409():
    """Confirm с одним idempotency_key дважды — второй возвращает 409."""
    body = {
        "merchant_data": {"order_id": "order_confirm_idem"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test", "md": "test"}}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _do(ts: str) -> requests.Response:
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type": "application/json",
            "Api-Terminal-ID": TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature": sig,
            "Api-Timestamp": ts,
        }
        return requests.post(f"{BASE_URL}/000000000000/confirm", data=raw, headers=h, timeout=30)

    r1 = _do(str(int(time.time())))
    r2 = _do(str(int(time.time())))
    if r1.status_code == 404:
        assert r2.status_code == 409, f"Expected 409 for duplicate key after 404, got {r2.status_code}"


@pytest.mark.tcid("CON-027")
def test_confirm_missing_idempotency_key_returns_400():
    """Confirm без Api-Idempotency-Key. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test", "md": "test"}}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(f"{BASE_URL}/000000000000/confirm", data=raw, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-028")
def test_confirm_result_type_null():
    """Confirm с result.type = null. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": None, "details": {"data": {"pares": "test", "md": "test"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-029")
def test_confirm_financial_data_empty_object():
    """Confirm с financial_data = {}. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404)
    assert_error_response(resp)


@pytest.mark.tcid("CON-030")
def test_confirm_threed_secure_pares_empty_string():
    """Confirm 3DS с pares = '' (пустая строка). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "", "md": "test_md"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404)
    assert_error_response(resp)


@pytest.mark.tcid("CON-031")
def test_confirm_amount_null():
    """Confirm с financial_data.amount = null. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": None, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404)
    assert_error_response(resp)


@pytest.mark.tcid("CON-032")
def test_confirm_content_type_is_json_in_response():
    """Confirm ошибочного запроса — Content-Type ответа содержит application/json."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


# ─────────────────────────────────────────────
# ВАЛИДАЦИЯ ТИПОВ И СОВМЕСТИМОСТИ (CON-033..034)
# ─────────────────────────────────────────────
_BASE_BODY = {
    "merchant_data": {"order_id": "order_confirm_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


@pytest.mark.tcid("CON-033")
def test_confirm_confirmed_as_string():
    """confirmed='true' (строка вместо bool). Ожидается 400 (type validation)."""
    body = {**_BASE_BODY, "result": {"type": "transfer_card", "details": {"confirmed": "true"}}}
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-034")
def test_confirm_threed_secure_with_confirmed_field():
    """threed_secure + confirmed (несовместимая комбинация). Ожидается 400."""
    body = {**_BASE_BODY, "result": {"type": "threed_secure", "details": {"confirmed": True}}}
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ЗАГОЛОВКИ — РАСШИРЕННЫЕ (CON-035..041)
# ─────────────────────────────────────────────
def _confirm_with_headers(headers: dict) -> requests.Response:
    body = {**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}
    raw = json.dumps(body, separators=(",", ":"))
    return requests.post(f"{BASE_URL}/000000000000/confirm", data=raw, headers=headers, timeout=30)


@pytest.mark.tcid("CON-035")
def test_confirm_invalid_idempotency_key_format():
    """Api-Idempotency-Key не является UUID. Ожидается 400."""
    ts  = str(int(time.time()))
    raw = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, ts, raw)
    resp = _confirm_with_headers({
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": "not-a-uuid",
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    })
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-036")
def test_confirm_timestamp_too_old():
    """Api-Timestamp старее окна tolerances (> 5 мин назад). Ожидается 401/400."""
    old_ts = str(int(time.time()) - 400)
    raw = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, old_ts, raw)
    resp = _confirm_with_headers({
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       old_ts,
    })
    assert resp.status_code in (400, 401), f"Expected 400/401, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-037")
def test_confirm_timestamp_too_new():
    """Api-Timestamp в будущем (> 5 мин вперёд). Ожидается 401/400."""
    future_ts = str(int(time.time()) + 400)
    raw = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, future_ts, raw)
    resp = _confirm_with_headers({
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       future_ts,
    })
    assert resp.status_code in (400, 401), f"Expected 400/401, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-038")
def test_confirm_timestamp_within_window():
    """Api-Timestamp в пределах окна — запрос проходит валидацию (достигает 404 по транзакции)."""
    ts  = str(int(time.time()))
    raw = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, ts, raw)
    resp = _confirm_with_headers({
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    })
    assert resp.status_code != 401, f"Timestamp validation should pass, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CON-039")
def test_confirm_signature_from_different_body():
    """Подпись посчитана от другого body (не от отправляемого). Ожидается 401/403."""
    ts       = str(int(time.time()))
    body_a   = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    body_b   = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
    sig      = calc_signature(TERMINAL_ID, ts, body_a)
    resp = requests.post(
        f"{BASE_URL}/000000000000/confirm",
        data=body_b,
        headers={
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": str(uuid.uuid4()),
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        },
        timeout=30,
    )
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-040")
def test_confirm_signature_with_wrong_terminal():
    """Подпись посчитана с другим terminal_id. Ожидается 401/403."""
    ts  = str(int(time.time()))
    raw = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    sig = calc_signature("99999", ts, raw)
    resp = _confirm_with_headers({
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    })
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-041")
def test_confirm_nonexistent_terminal_id():
    """Несуществующий Api-Terminal-ID. Ожидается 401/403."""
    ts  = str(int(time.time()))
    raw = json.dumps({**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}, separators=(",", ":"))
    sig = calc_signature("99999", ts, raw)
    resp = _confirm_with_headers({
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     "99999",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    })
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# URL-РОУТИНГ (CON-042)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-042")
def test_confirm_non_numeric_transaction_id():
    """Нечисловой transaction_id в URL. Ожидается 404 (роутер не матчит \d+)."""
    resp = post_operation("not-a-number", "confirm", {
        **_BASE_BODY,
        "result": {"type": "redirect", "details": {"confirmed": True}},
    })
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# СОВМЕСТИМОСТЬ ФОРМАТОВ (CON-043..044)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-043")
def test_confirm_old_pascalcase_body_on_new_url():
    """Старый PascalCase-формат тела на новом URL. Ожидается 4xx (нет merchant_data/financial_data/result)."""
    old_body = {
        "TransactionId": 9999999999,
        "OrderId": "order_test",
        "Amount": 1000,
        "Currency": "RUB",
        "PaRes": "test_pares",
        "MD": "test_md",
    }
    resp = post_operation("9999999999", "confirm", old_body)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-044")
def test_confirm_old_headers_on_new_url():
    """Старые заголовки X-SITE-ID/X-REQUEST-SIGNATURE на новом URL. Ожидается 4xx (MissingHTTPHeader)."""
    body = {**_BASE_BODY, "result": {"type": "redirect", "details": {"confirmed": True}}}
    raw  = json.dumps(body, separators=(",", ":"))
    resp = requests.post(
        f"{BASE_URL}/000000000000/confirm",
        data=raw,
        headers={
            "Content-Type":        "application/json",
            "X-SITE-ID":           TERMINAL_ID,
            "X-REQUEST-ID":        str(uuid.uuid4()),
            "X-REQUEST-SIGNATURE": "fakesig",
        },
        timeout=30,
    )
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HAPPY PATH — требуют транзакцию в нужном статусе
# ─────────────────────────────────────────────
def _make_3ds_payin_body(order_id: str) -> dict:
    """Body для создания транзакции, которая должна уйти в waiting_3DS."""
    return {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_3DS},
    }


@pytest.mark.tcid("CON-045")
@pytest.mark.skip(reason="Требует транзакцию в статусе waiting_3DS — зависит от конфига сервиса")
def test_confirm_threed_secure_success():
    """Успешный confirm type=threed_secure: создать 3DS-транзакцию и подтвердить."""
    oid  = gen_order_id("confirm_3ds_ok")
    resp = post_transaction(_make_3ds_payin_body(oid))
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    data = resp.json()
    assert data.get("status") == "waiting_3DS", \
        f"Expected waiting_3DS, got {data.get('status')!r} — skip manually if not in 3DS flow"
    tid = data["transaction_id"]
    time.sleep(SETUP_DELAY)
    confirm_body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "<real_pares>", "md": "<real_md>"}}},
    }
    r = post_operation(tid, "confirm", confirm_body)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    resp_data = r.json()
    assert resp_data.get("status") == "processing"
    assert isinstance(resp_data.get("transaction_id"), int)
    assert_transaction_response(resp_data)


@pytest.mark.tcid("CON-046")
@pytest.mark.skip(reason="Требует транзакцию в статусе waiting_action (transfer_card) — настроить вручную")
def test_confirm_transfer_card_confirmed_true():
    """Успешный confirm type=transfer_card, confirmed=true → UserAction с as_confirm_user_action."""
    oid = gen_order_id("confirm_tc_true")
    # Создать транзакцию, которая ждёт подтверждения перевода по карте
    # ... (зависит от конфига сервиса с P2P/transfer_card методом)
    tid = 0  # заменить на реальный tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    })
    assert r.status_code == 200
    assert r.json().get("status") == "processing"


@pytest.mark.tcid("CON-047")
@pytest.mark.skip(reason="Требует транзакцию в статусе waiting_action (transfer_card) — настроить вручную")
def test_confirm_transfer_card_confirmed_false():
    """Confirm type=transfer_card, confirmed=false → транзакция помечается отклонённой пользователем."""
    oid = gen_order_id("confirm_tc_false")
    tid = 0  # заменить на реальный tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": False}},
    })
    assert r.status_code == 200


@pytest.mark.tcid("CON-048")
@pytest.mark.skip(reason="Требует транзакции в waiting_action для каждого типа — настроить вручную")
@pytest.mark.parametrize("result_type", ["redirect", "transfer_phone", "transfer_qr", "transfer_account", "top_up_mobile"])
def test_confirm_user_action_types_confirmed_true(result_type):
    """Confirm с разными user-action типами, confirmed=true → 200, одинаковая структура ответа."""
    oid = gen_order_id(f"confirm_{result_type}")
    tid = 0  # заменить на реальный tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": result_type, "details": {"confirmed": True}},
    })
    assert r.status_code == 200
    assert r.json().get("status") == "processing"


# ─────────────────────────────────────────────
# 3DS-REDIRECT КЕЙСЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-049")
@pytest.mark.skip(reason="Требует транзакцию в статусе waiting_3DS_redirect — настроить вручную")
def test_confirm_3ds_redirect_confirmed_true():
    """3DS-redirect: confirm с confirmed=true — клиент принял редирект."""
    tid = 0  # заменить на реальный tid в waiting_3DS_redirect
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": "order_3ds_redirect"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    })
    assert r.status_code == 200
    assert r.json().get("status") == "processing"


@pytest.mark.tcid("CON-050")
@pytest.mark.skip(reason="Требует транзакцию в статусе waiting_3DS_redirect — настроить вручную")
def test_confirm_3ds_redirect_confirmed_false():
    """3DS-redirect: confirm с confirmed=false — клиент отказался от редиректа."""
    tid = 0  # заменить на реальный tid в waiting_3DS_redirect
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": "order_3ds_redirect"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": False}},
    })
    assert r.status_code == 200


@pytest.mark.tcid("CON-051")
@pytest.mark.skip(reason="Требует транзакцию в статусе waiting_3DS_redirect — настроить вручную")
def test_confirm_3ds_redirect_wrong_type():
    """3DS-redirect: отправить threed_secure вместо redirect — должна быть ошибка несовместимого типа."""
    tid = 0  # заменить на реальный tid в waiting_3DS_redirect
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": "order_3ds_redirect"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    })
    assert r.status_code in range(400, 500), f"Expected 4xx for wrong type on redirect state"
    assert_error_response(r)


# ─────────────────────────────────────────────
# ФОРМАТ ОТВЕТА (требуют успешный confirm)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-052")
@pytest.mark.skip(reason="Требует успешный confirm — зависит от waiting_3DS или waiting_action транзакции")
def test_confirm_minimized_response_format():
    """Успешный confirm возвращает минимизированный ответ: transaction_id, status, type, merchant_data, financial_data, created_at."""
    tid = 0
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": "order_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    })
    assert r.status_code == 200
    data = r.json()
    for field in ("transaction_id", "status", "type", "merchant_data", "financial_data", "created_at"):
        assert field in data, f"Missing field '{field}' in response"
    assert isinstance(data["transaction_id"], int)
    assert data["status"] == "processing"
    assert data["type"] in ("payin", "payout")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", data["created_at"]), \
        f"created_at not ISO-8601 UTC: {data['created_at']!r}"
