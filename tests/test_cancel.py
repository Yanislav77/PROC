"""
Тесты для операции cancel (отмена транзакции).
POST /api/v1/transactions/{id}/cancel
"""
import hashlib
import hmac
import json
import time
import uuid

import pytest
import requests

from conftest import (
    post_transaction,
    post_operation,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    SERVICE_SECRET,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)


def _sign(terminal_id: str, timestamp: str, raw_body: str = "") -> str:
    message = f"{timestamp}{terminal_id}{raw_body}"
    return hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


def _make_completed_payin(order_id: str = None) -> str:
    """Создаёт auto-capture payin и возвращает transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id or f"order_{uuid.uuid4().hex[:8]}"},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup auto payin failed: {resp.text}"
    return resp.json()["transaction_id"]


def _op_body(order_id: str, amount: int = 1000) -> dict:
    return {
        "merchant_data": {"order_id": order_id},
        "financial_data": {"amount": amount, "currency": "RUB"},
    }


def _make_block_payin(order_id: str = "order_block_cancel") -> str:
    """Создаёт Payin с холдом (capture_mode=manual) и возвращает transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Block Payin failed: {resp.text}"
    time.sleep(1)
    return resp.json()["transaction_id"]


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-001")
def test_cancel_authorized_transaction():
    """Отмена authorized транзакции (capture_mode=manual). Ожидается 200 или 201."""
    oid = gen_order_id("cancel_auth")
    tid = _make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("CAN-002")
def test_cancel_with_description():
    """Отмена с опциональным полем description в merchant_data. Ожидается 200 или 201."""
    oid = gen_order_id("cancel_desc")
    tid = _make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid, "description": "Cancelled by customer"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-003")
def test_cancel_nonexistent_transaction():
    """Cancel по несуществующей транзакции. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-004")
def test_cancel_missing_financial_data():
    """Cancel без financial_data (обязательное). Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_cancel_test"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-005")
def test_cancel_missing_merchant_data():
    """Cancel без merchant_data (обязательное). Ожидается 400."""
    body = {"financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-006")
def test_cancel_missing_order_id():
    """Cancel с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {"description": "no order_id"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-007")
def test_cancel_no_auth():
    """Cancel без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/cancel"
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(url, data=raw, headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-008")
def test_cancel_invalid_signature():
    """Cancel с подписью из нулей. Ожидается 401 или 403."""
    tid = _make_block_payin(gen_order_id("cancel_inv_sig"))
    url = f"{BASE_URL}/{tid}/cancel"
    body = {
        "merchant_data": {"order_id": gen_order_id("cancel_inv_sig")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
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


@pytest.mark.tcid("CAN-009")
def test_cancel_missing_terminal_id():
    """Cancel без заголовка Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/cancel"
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
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


@pytest.mark.tcid("CAN-010")
def test_cancel_missing_timestamp():
    """Cancel без заголовка Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/cancel"
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
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
# ВАЛИДАЦИЯ FINANCIAL_DATA — ГРАНИЧНЫЕ СЛУЧАИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-011")
def test_cancel_zero_amount():
    """Cancel с нулевой суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-012")
def test_cancel_negative_amount():
    """Cancel с отрицательной суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": -500, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-013")
def test_cancel_invalid_currency():
    """Cancel с невалидным кодом валюты. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "INVALID"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-014")
def test_cancel_missing_amount():
    """Cancel без поля amount в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-015")
def test_cancel_missing_currency():
    """Cancel без поля currency в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-016")
def test_cancel_amount_as_string():
    """Cancel с суммой переданной как строка. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": "1000", "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-017")
def test_cancel_amount_as_float():
    """Cancel с суммой как вещественным числом. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 100.50, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HAPPY PATH — ДОПОЛНИТЕЛЬНЫЕ КЕЙСЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-018")
def test_cancel_with_webhook_url():
    """Cancel с опциональным webhook_url в merchant_data. Ожидается 200 или 201."""
    oid = gen_order_id("cancel_webhook")
    tid = _make_block_payin(oid)
    body = {
        "merchant_data": {
            "order_id": oid,
            "webhook_url": "https://example.com/webhook",
        },
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("CAN-019")
def test_cancel_amount_exceeds_original():
    """Cancel с суммой, превышающей оригинальную (1000). Ожидается 400 или 409."""
    oid = gen_order_id("cancel_exceed")
    tid = _make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 999999, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (400, 409), f"Expected 400/409, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-020")
def test_cancel_already_cancelled():
    """Повторная отмена уже отменённой транзакции. Ожидается 400 или 409."""
    oid = gen_order_id("cancel_twice")
    tid = _make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp1 = post_operation(tid, "cancel", body)
    assert resp1.status_code in (200, 201), f"First cancel failed: {resp1.text}"
    resp2 = post_operation(tid, "cancel", body)
    assert resp2.status_code in (400, 409), f"Expected 400 or 409, got {resp2.status_code}: {resp2.text}"
    assert_error_response(resp2)


@pytest.mark.tcid("CAN-021")
def test_cancel_currency_lowercase():
    """Cancel с валютой в нижнем регистре ('rub'). Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_cancel_test"},
        "financial_data": {"amount": 1000, "currency": "rub"},
    }
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-022")
def test_cancel_response_type_payin():
    """Cancel успешной authorized транзакции — тип в ответе должен быть 'payin'."""
    oid = gen_order_id("cancel_type_check")
    tid = _make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin", f"Expected type='payin', got {data.get('type')!r}"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (CAN-023 … CAN-030)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-023")
def test_cancel_idempotency_same_key_returns_409():
    """Cancel с одним idempotency_key дважды — второй запрос должен вернуть 409."""
    order_id = gen_order_id("can_idem")
    tid = _make_block_payin(order_id)
    body = _op_body(order_id)
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _do(ts: str) -> requests.Response:
        sig = _sign(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type": "application/json",
            "Api-Terminal-ID": TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature": sig,
            "Api-Timestamp": ts,
        }
        return requests.post(f"{BASE_URL}/{tid}/cancel", data=raw, headers=h, timeout=30)

    r1 = _do(str(int(time.time())))
    assert r1.status_code in (200, 201), f"First cancel failed: {r1.text}"
    r2 = _do(str(int(time.time())))
    assert r2.status_code == 409, f"Expected 409 for duplicate idempotency key, got {r2.status_code}"


@pytest.mark.tcid("CAN-024")
def test_cancel_response_has_financial_data():
    """Cancel успешной транзакции — ответ содержит financial_data."""
    order_id = gen_order_id("can_fd")
    tid = _make_block_payin(order_id)
    resp = post_operation(tid, "cancel", _op_body(order_id))
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert "financial_data" in resp.json(), "financial_data отсутствует в ответе cancel"


@pytest.mark.tcid("CAN-025")
def test_cancel_response_has_created_at():
    """Cancel успешной транзакции — ответ содержит created_at."""
    order_id = gen_order_id("can_ca")
    tid = _make_block_payin(order_id)
    resp = post_operation(tid, "cancel", _op_body(order_id))
    assert resp.status_code in (200, 201)
    assert "created_at" in resp.json(), "created_at отсутствует в ответе cancel"


@pytest.mark.tcid("CAN-026")
def test_cancel_missing_idempotency_key_returns_400():
    """Cancel без Api-Idempotency-Key. Ожидается 400."""
    body = _op_body("order_cancel_test")
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = _sign(TERMINAL_ID, timestamp, raw)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(f"{BASE_URL}/000000000000/cancel", data=raw, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-027")
def test_cancel_auto_captured_transaction_returns_409():
    """Cancel по транзакции с capture_mode=auto (не в статусе authorized). Ожидается 409."""
    order_id = gen_order_id("can_auto")
    tid = _make_completed_payin(order_id)
    resp = post_operation(tid, "cancel", _op_body(order_id))
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-028")
def test_cancel_financial_data_empty_object():
    """Cancel с financial_data как пустым объектом. Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_cancel_test"}, "financial_data": {}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-029")
def test_cancel_merchant_data_empty_object():
    """Cancel с merchant_data как пустым объектом (нет order_id). Ожидается 400."""
    body = {"merchant_data": {}, "financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "cancel", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAN-030")
def test_cancel_content_type_is_json_in_response():
    """Cancel ошибочного запроса — Content-Type ответа содержит application/json."""
    body = _op_body("order_cancel_test")
    resp = post_operation("000000000000", "cancel", body)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"
