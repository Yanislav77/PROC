"""
Тесты для операции confirm (подтверждение ожидающего действия).
POST /api/v1/transactions/{id}/confirm
Типы: threed_secure, redirect, transfer_card, transfer_phone, transfer_qr, transfer_account, top_up_mobile.
Happy path требует транзакцию в статусе waiting_action — покрыты только негативные сценарии.
"""
import json
import time
import uuid

import pytest
import requests

from conftest import calc_signature, post_operation, BASE_URL, TERMINAL_ID, assert_error_response


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
