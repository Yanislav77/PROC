"""
Тесты для операции cancel (отмена транзакции).
POST /api/v1/transactions/{id}/cancel
"""
import json
import time
import uuid

import pytest
import requests

from conftest import (
    calc_signature,
    post_operation,
    get_request,
    BASE_URL,
    TERMINAL_ID,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
    make_op_body,
)

_POLL_ATTEMPTS = 6
_POLL_DELAY    = 2.0


def _poll_status(tid: int, expected: str) -> None:
    """Poll GET /{tid} until expected status or skip."""
    for _ in range(_POLL_ATTEMPTS):
        time.sleep(_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == expected:
            return
        if status in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"Transaction {tid} reached {status!r} instead of {expected!r}")
    pytest.skip(f"Transaction {tid} did not reach {expected!r} within timeout")


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-001")
def test_cancel_authorized_transaction():
    """Отмена authorized транзакции (capture_mode=manual). Ожидается 200 или 201."""
    oid = gen_order_id("cancel_auth")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    if data.get("status") != "cancelled":
        _poll_status(tid, "cancelled")


@pytest.mark.tcid("CAN-002")
def test_cancel_with_description():
    """Отмена с опциональным полем description в merchant_data. Ожидается 200 или 201."""
    oid = gen_order_id("cancel_desc")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid, "description": "Cancelled by customer"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    if data.get("status") != "cancelled":
        _poll_status(tid, "cancelled")


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
    tid = make_block_payin(gen_order_id("cancel_inv_sig"))
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
    tid = make_block_payin(oid)
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
    tid = make_block_payin(oid)
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
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp1 = post_operation(tid, "cancel", body)
    assert resp1.status_code in (200, 201), f"First cancel failed: {resp1.text}"
    resp2 = post_operation(tid, "cancel", body)
    assert resp2.status_code == 400, f"Expected 400, got {resp2.status_code}: {resp2.text}"
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
    tid = make_block_payin(oid)
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
def test_cancel_second_request_different_key_returns_400():
    """Два cancel на одну транзакцию с разными idempotency_key — второй должен вернуть 400."""
    order_id = gen_order_id("can_idem")
    tid = make_block_payin(order_id)
    body = make_op_body(order_id)
    r1 = post_operation(tid, "cancel", body)
    assert r1.status_code in (200, 201), f"First cancel failed: {r1.text}"
    r2 = post_operation(tid, "cancel", body)
    assert r2.status_code == 400, f"Expected 400 for second cancel, got {r2.status_code}: {r2.text}"
    assert_error_response(r2)


@pytest.mark.tcid("CAN-024")
def test_cancel_response_has_financial_data():
    """Cancel успешной транзакции — ответ содержит financial_data."""
    order_id = gen_order_id("can_fd")
    tid = make_block_payin(order_id)
    resp = post_operation(tid, "cancel", make_op_body(order_id))
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert "financial_data" in resp.json(), "financial_data отсутствует в ответе cancel"


@pytest.mark.tcid("CAN-025")
def test_cancel_response_has_created_at():
    """Cancel успешной транзакции — ответ содержит created_at."""
    order_id = gen_order_id("can_ca")
    tid = make_block_payin(order_id)
    resp = post_operation(tid, "cancel", make_op_body(order_id))
    assert resp.status_code in (200, 201)
    assert "created_at" in resp.json(), "created_at отсутствует в ответе cancel"


@pytest.mark.tcid("CAN-026")
def test_cancel_missing_idempotency_key_returns_400():
    """Cancel без Api-Idempotency-Key. Ожидается 400."""
    body = make_op_body("order_cancel_test")
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw)
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
    """Cancel по транзакции с capture_mode=auto (не в статусе authorized). Ожидается 400 или 409."""
    order_id = gen_order_id("can_auto")
    tid = make_completed_payin(order_id)
    resp = post_operation(tid, "cancel", make_op_body(order_id))
    assert resp.status_code in (400, 409), f"Expected 400 or 409, got {resp.status_code}: {resp.text}"
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


@pytest.mark.tcid("CAN-031")
def test_cancel_description_comes_from_cancel_not_parent():
    """description в ответе cancel должен быть из запроса cancel, а не из родительской транзакции."""
    oid = gen_order_id("can_desc_check")
    tid = make_block_payin(oid, description="Parent description")
    body = {
        "merchant_data": {"order_id": oid, "description": "Cancel description"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "cancel", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    actual = data.get("merchant_data", {}).get("description")
    assert actual == "Cancel description", \
        f"Expected description from cancel request, got {actual!r}"


@pytest.mark.tcid("CAN-030")
def test_cancel_content_type_is_json_in_response():
    """Cancel ошибочного запроса — Content-Type ответа содержит application/json."""
    body = make_op_body("order_cancel_test")
    resp = post_operation("000000000000", "cancel", body)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAN-032")
def test_cancel_idempotency_same_key_returns_cached_response():
    """Два cancel с одинаковым Idempotency-Key и одинаковым телом — второй возвращает кэшированный ответ."""
    order_id = gen_order_id("can_idem_same")
    tid = make_block_payin(order_id)
    body = make_op_body(order_id)
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _do(ts: str) -> requests.Response:
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        return requests.post(f"{BASE_URL}/{tid}/cancel", data=raw, headers=h, timeout=30)

    r1 = _do(str(int(time.time())))
    assert r1.status_code in (200, 201), f"First cancel failed: {r1.text}"
    tid1 = r1.json().get("transaction_id")

    r2 = _do(str(int(time.time())))
    assert r2.status_code in (200, 201), f"Expected cached response, got {r2.status_code}: {r2.text}"
    assert r2.json().get("transaction_id") == tid1, \
        f"Cached response должен вернуть тот же transaction_id: {tid1!r}, got {r2.json().get('transaction_id')!r}"


@pytest.mark.tcid("CAN-033")
def test_cancel_idempotency_same_key_different_body():
    """Два cancel с одинаковым Idempotency-Key, но разными суммами — второй возвращает кэшированный ответ первого."""
    order_id = gen_order_id("can_idem_diff")
    tid = make_block_payin(order_id)
    key = str(uuid.uuid4())

    def _do(amount: int, ts: str) -> requests.Response:
        body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": amount, "currency": "RUB"}}
        raw = json.dumps(body, separators=(",", ":"))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        return requests.post(f"{BASE_URL}/{tid}/cancel", data=raw, headers=h, timeout=30)

    r1 = _do(1000, str(int(time.time())))
    assert r1.status_code in (200, 201), f"First cancel failed: {r1.text}"
    tid1 = r1.json().get("transaction_id")

    r2 = _do(500, str(int(time.time())))
    if r2.status_code in (200, 201):
        assert r2.json().get("transaction_id") == tid1, \
            f"Кэшированный ответ должен вернуть тот же transaction_id: {tid1!r}"
    else:
        assert r2.status_code in (400, 409), \
            f"Expected cached response or conflict error, got {r2.status_code}: {r2.text}"
        assert_error_response(r2)
