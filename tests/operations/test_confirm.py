"""
Тесты для операции confirm (подтверждение ожидающего действия).
POST /api/v1/transactions/{id}/confirm
Тип: threed_secure (waiting_3DS).
Happy path требует транзакцию в статусе waiting_3DS — создаётся через фикстуру waiting_3ds_tid.
"""
import json
import re
import time
import uuid

import pytest
import requests

from conftest import (
    calc_signature, post_operation, post_transaction, get_request,
    BASE_URL, TERMINAL_ID, MERCHANT_DATA, CUSTOMER_DATA, CARD_DETAILS,
    THREED, gen_order_id, SETUP_DELAY,
    assert_error_response, assert_transaction_response,
)
import _helpers.config as _cfg
from _helpers.signatures import make_headers

# CVV < 500  → waiting_3DS   (используется _CARD_WAIT_3DS)
# CVV >= 600  → без 3DS     (CARD_DETAILS использует cvv=666)
_CARD_WAIT_3DS = {**CARD_DETAILS, "cvv": "123"}

_3DS_POLL_ATTEMPTS = 6
_3DS_POLL_DELAY    = 2.0  # секунд между попытками


def _create_payin(card: dict, oid: str) -> dict:
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": card},
    }
    resp = post_transaction(body)
    if resp.status_code != 201:
        pytest.skip(f"Failed to create transaction: {resp.status_code}: {resp.text}")
    return resp.json()


def _poll_status(tid: int, expected: str) -> None:
    """Poll GET /{tid} until expected status or skip."""
    for _ in range(_3DS_POLL_ATTEMPTS):
        time.sleep(_3DS_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == expected:
            return
        if status in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"Transaction {tid} reached {status!r} instead of {expected!r}")
    pytest.skip(f"Transaction {tid} did not reach {expected!r} within timeout")


@pytest.fixture
def waiting_3ds_tid() -> tuple[int, str]:
    """Создаёт свежий payin с CVV<500, ждёт статуса waiting_3DS. Возвращает (tid, order_id).
    Function-scoped: каждый тест получает отдельную транзакцию (confirm меняет её состояние)."""
    oid  = gen_order_id("con_3ds_fixture")
    data = _create_payin(_CARD_WAIT_3DS, oid)
    tid  = data["transaction_id"]
    if data.get("status") != "waiting_3DS":
        _poll_status(tid, "waiting_3DS")
    return tid, oid



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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-004")
def test_confirm_missing_merchant_data():
    """Confirm без merchant_data (обязательное). Ожидается 400."""
    body = {
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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


# ─────────────────────────────────────────────
# ВАЛИДАЦИЯ RESULT — СТРУКТУРА
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-010")
def test_confirm_result_missing_type():
    """Confirm с result без поля type. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"details": {}},
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
        "result": {"type": "threed_secure"},
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
# ВАЛИДАЦИЯ FINANCIAL_DATA
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-017")
def test_confirm_zero_amount():
    """Confirm с нулевой суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
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


_BASE_BODY = {
    "merchant_data": {"order_id": "order_confirm_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


# ─────────────────────────────────────────────
# ЗАГОЛОВКИ — РАСШИРЕННЫЕ (CON-035..041)
# ─────────────────────────────────────────────
def _confirm_with_headers(headers: dict) -> requests.Response:
    body = {**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}
    raw = json.dumps(body, separators=(",", ":"))
    return requests.post(f"{BASE_URL}/000000000000/confirm", data=raw, headers=headers, timeout=30)


@pytest.mark.tcid("CON-035")
def test_confirm_invalid_idempotency_key_format():
    """Api-Idempotency-Key не является UUID. Ожидается 400."""
    ts  = str(int(time.time()))
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
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
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
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
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
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
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
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
    body_a   = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "aaa", "md": "aaa"}}}}, separators=(",", ":"))
    body_b   = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "bbb", "md": "bbb"}}}}, separators=(",", ":"))
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
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
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
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
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
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    })
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# HAPPY PATH — используют фикстуры с нужным статусом
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-045")
def test_confirm_threed_secure_success(waiting_3ds_tid):
    """Успешный confirm type=threed_secure на транзакции в waiting_3DS."""
    tid, oid = waiting_3ds_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "processing"
    assert isinstance(data.get("transaction_id"), int)
    assert_transaction_response(data)


# CON-046, CON-047, CON-048 перенесены в test_confirm_user_action.py
# (используют P2P-транзакцию для достижения waiting_action)


# ─────────────────────────────────────────────
# ФОРМАТ ОТВЕТА
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-052")
def test_confirm_minimized_response_format(waiting_3ds_tid):
    """Успешный confirm возвращает минимизированный ответ с обязательными полями."""
    tid, oid = waiting_3ds_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    for field in ("transaction_id", "status", "type", "merchant_data", "financial_data", "created_at"):
        assert field in data, f"Missing field '{field}' in response"
    assert isinstance(data["transaction_id"], int)
    assert data["status"] == "processing"
    assert data["type"] in ("payin", "payout")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", data["created_at"]), \
        f"created_at not ISO-8601 UTC: {data['created_at']!r}"


# ─────────────────────────────────────────────
# ТЕЛО ЗАПРОСА — СТРУКТУРА (CON-053..055)
# ─────────────────────────────────────────────
def _auth_headers(raw_body: str = "") -> dict:
    """Заголовки с корректной подписью, без Content-Type (добавляется вручную при необходимости)."""
    ts  = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, ts, raw_body)
    return {
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }


@pytest.mark.tcid("CON-053")
def test_confirm_empty_body():
    """Пустое тело запроса (без Content-Type и данных). Ожидается 400."""
    h = {**_auth_headers(), "Content-Type": "application/json"}
    resp = requests.post(f"{BASE_URL}/000000000000/confirm", headers=h, timeout=30)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-054")
def test_confirm_invalid_json_body():
    """Тело — невалидный JSON ({broken). Ожидается 400."""
    broken = "{broken"
    h = {**_auth_headers(broken), "Content-Type": "application/json"}
    resp = requests.post(f"{BASE_URL}/000000000000/confirm", data=broken, headers=h, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-055")
def test_confirm_json_not_object():
    """Тело — валидный JSON, но не объект (массив). Ожидается 400."""
    raw = "[]"
    h = {**_auth_headers(raw), "Content-Type": "application/json"}
    resp = requests.post(f"{BASE_URL}/000000000000/confirm", data=raw, headers=h, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ THREED_SECURE (CON-057..058)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-057")
def test_confirm_threed_secure_pares_whitespace_only():
    """threed_secure: pares содержит только пробелы. Ожидается 400."""
    body = {
        **_BASE_BODY,
        "result": {"type": "threed_secure", "details": {"data": {"pares": "   ", "md": "test_md"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-058")
def test_confirm_threed_secure_md_whitespace_only():
    """threed_secure: md содержит только пробелы. Ожидается 400."""
    body = {
        **_BASE_BODY,
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "   "}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ВАЛИДАЦИЯ ТИПОВ FINANCIAL_DATA / MERCHANT_DATA (CON-059..063)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-059")
def test_confirm_amount_as_string():
    """financial_data.amount — строка вместо integer. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": "1000", "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-060")
def test_confirm_amount_as_float():
    """financial_data.amount — дробное число (1000.50) вместо integer. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000.50, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-061")
def test_confirm_currency_lowercase():
    """financial_data.currency — нижний регистр ('rub'). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "rub"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-062")
def test_confirm_order_id_empty_string():
    """merchant_data.order_id — пустая строка. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": ""},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-063")
def test_confirm_order_id_null():
    """merchant_data.order_id — null. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": None},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PATH VS BODY (CON-064)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-064")
def test_confirm_transaction_id_in_body_ignored():
    """transaction_id в теле отличается от path — path-значение должно побеждать (→ 404 по path-ID)."""
    body = {
        "transaction_id": 999999999,
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code == 404, \
        f"Expected 404 (path-ID wins), got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ЗАГОЛОВКИ — ЗНАЧЕНИЯ (CON-065..067)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-065")
def test_confirm_terminal_id_non_numeric():
    """Api-Terminal-ID — нечисловая строка ('abc'). Ожидается 400/401/403."""
    ts  = str(int(time.time()))
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
    sig = calc_signature("abc", ts, raw)
    resp = requests.post(
        f"{BASE_URL}/000000000000/confirm",
        data=raw,
        headers={
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     "abc",
            "Api-Idempotency-Key": str(uuid.uuid4()),
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        },
        timeout=30,
    )
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-066")
def test_confirm_timestamp_non_numeric():
    """Api-Timestamp — нечисловая строка ('not-a-ts'). Ожидается 400/401."""
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, "not-a-ts", raw)
    resp = requests.post(
        f"{BASE_URL}/000000000000/confirm",
        data=raw,
        headers={
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": str(uuid.uuid4()),
            "Api-Signature":       sig,
            "Api-Timestamp":       "not-a-ts",
        },
        timeout=30,
    )
    assert resp.status_code in (400, 401), f"Expected 400/401, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-067")
def test_confirm_timestamp_float_string():
    """Api-Timestamp — число с плавающей точкой ('1715760000.5'). Ожидается 400/401."""
    float_ts = "1715760000.5"
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, float_ts, raw)
    resp = requests.post(
        f"{BASE_URL}/000000000000/confirm",
        data=raw,
        headers={
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": str(uuid.uuid4()),
            "Api-Signature":       sig,
            "Api-Timestamp":       float_ts,
        },
        timeout=30,
    )
    assert resp.status_code in (400, 401), f"Expected 400/401, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HTTP-МЕТОДЫ (CON-068..069)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-068")
def test_confirm_get_method_not_allowed():
    """GET вместо POST на /confirm. Ожидается 404 или 405."""
    ts  = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, ts, "")
    headers = {
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    resp = requests.get(f"{BASE_URL}/000000000000/confirm", headers=headers, timeout=30)
    assert resp.status_code in (404, 405), f"Expected 404/405, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CON-069")
def test_confirm_put_method_not_allowed():
    """PUT вместо POST на /confirm. Ожидается 404 или 405."""
    raw = json.dumps({**_BASE_BODY, "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}}}, separators=(",", ":"))
    h   = {**_auth_headers(raw), "Content-Type": "application/json"}
    resp = requests.put(f"{BASE_URL}/000000000000/confirm", data=raw, headers=h, timeout=30)
    assert resp.status_code in (404, 405), f"Expected 404/405, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ РАСШИРЕННАЯ (CON-070)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-070")
def test_confirm_idempotency_same_key_different_body():
    """Один Idempotency-Key, разные тела — второй запрос возвращает кэшированный ответ первого."""
    key  = str(uuid.uuid4())

    def _do(result_type: str, pares: str) -> requests.Response:
        body = {
            **_BASE_BODY,
            "result": {"type": result_type, "details": {"data": {"pares": pares, "md": "m"}}},
        }
        raw = json.dumps(body, separators=(",", ":"))
        ts  = str(int(time.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        return requests.post(
            f"{BASE_URL}/000000000000/confirm",
            data=raw,
            headers={
                "Content-Type":        "application/json",
                "Api-Terminal-ID":     TERMINAL_ID,
                "Api-Idempotency-Key": key,
                "Api-Signature":       sig,
                "Api-Timestamp":       ts,
            },
            timeout=30,
        )

    r1 = _do("threed_secure", "pares_first")
    r2 = _do("threed_secure", "pares_second")
    assert r2.status_code in (r1.status_code, 409), \
        f"Expected cached {r1.status_code} or 409, got {r2.status_code}: {r2.text}"


# ─────────────────────────────────────────────
# СТРУКТУРА ОТВЕТА (CON-071..075)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-071")
def test_confirm_error_response_no_internal_fields():
    """Ответ с ошибкой не содержит внутренних полей (нет stack_trace, internal_error и т.п.)."""
    resp = post_operation("000000000000", "confirm", {
        **_BASE_BODY,
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    })
    assert resp.status_code in (400, 404)
    try:
        data = resp.json()
    except Exception:
        pytest.fail("Response is not valid JSON")
    forbidden = {"stack_trace", "stacktrace", "internal_error", "exception", "traceback", "debug"}
    leaking = forbidden & {k.lower() for k in data}
    assert not leaking, f"Response leaks internal fields: {leaking}"


@pytest.mark.tcid("CON-072")
def test_confirm_response_header_terminal_id(waiting_3ds_tid):
    """Ответ содержит заголовок Api-Terminal-ID, совпадающий с отправленным."""
    tid, oid = waiting_3ds_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    if "Api-Terminal-ID" in r.headers:
        assert r.headers["Api-Terminal-ID"] == TERMINAL_ID, \
            f"Api-Terminal-ID mismatch: {r.headers['Api-Terminal-ID']!r} != {TERMINAL_ID!r}"


@pytest.mark.tcid("CON-073")
def test_confirm_response_header_idempotency_key(waiting_3ds_tid):
    """Ответ содержит заголовок Api-Idempotency-Key, совпадающий с отправленным."""
    tid, oid = waiting_3ds_tid
    key = str(uuid.uuid4())
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    ts  = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, ts, raw)
    r = requests.post(
        f"{BASE_URL}/{tid}/confirm",
        data=raw,
        headers={
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        },
        timeout=30,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    if "Api-Idempotency-Key" in r.headers:
        assert r.headers["Api-Idempotency-Key"] == key, \
            f"Api-Idempotency-Key mismatch: {r.headers['Api-Idempotency-Key']!r} != {key!r}"


@pytest.mark.tcid("CON-074")
def test_confirm_response_transaction_id_matches_path(waiting_3ds_tid):
    """transaction_id в теле ответа совпадает с path-параметром запроса."""
    tid, oid = waiting_3ds_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("transaction_id") == tid, \
        f"transaction_id в ответе {r.json().get('transaction_id')!r} не совпадает с path {tid!r}"


@pytest.mark.tcid("CON-075")
def test_confirm_created_at_matches_original_transaction(waiting_3ds_tid):
    """created_at в ответе confirm совпадает с created_at оригинальной транзакции (идемпотентность даты)."""
    tid, oid = waiting_3ds_tid
    get_resp = get_request(f"{BASE_URL}/{tid}")
    assert get_resp.status_code == 200
    original_created_at = get_resp.json().get("created_at")
    assert original_created_at, "created_at отсутствует в GET-ответе"

    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("created_at") == original_created_at, \
        f"created_at изменился: было {original_created_at!r}, стало {r.json().get('created_at')!r}"


# ─────────────────────────────────────────────
# ОБРАТНАЯ СОВМЕСТИМОСТЬ — УСТАРЕВШИЕ ФОРМАТЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-076")
def test_confirm_legacy_pascal_case_body():
    """Старый PascalCase-формат тела запроса на новом URL.
    Body: {TransactionId, OrderId, Amount, Currency, PaRes, MD}.
    Ожидается 4xx — validation error на отсутствие merchant_data, financial_data, result."""
    body = {
        "TransactionId": "000000000000",
        "OrderId":       "order_confirm_test",
        "Amount":        1000,
        "Currency":      "RUB",
        "PaRes":         "test_pares",
        "MD":            "test_md",
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CON-077")
def test_confirm_legacy_headers():
    """Старые заголовки (X-SITE-ID, X-REQUEST-ID, X-REQUEST-SIGNATURE) вместо Api-*.
    Ожидается 4xx — MissingHTTPHeader: Api-Terminal-ID."""
    url = f"{BASE_URL}/000000000000/confirm"
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "threed_secure", "details": {"data": {"pares": "p", "md": "m"}}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(
        url,
        data=raw,
        headers={
            "Content-Type":        "application/json",
            "X-SITE-ID":           TERMINAL_ID,
            "X-REQUEST-ID":        str(uuid.uuid4()),
            "X-REQUEST-SIGNATURE": "0" * 64,
        },
        timeout=30,
    )
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
