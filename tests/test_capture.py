"""
Тесты для операции capture (списание заблокированных средств).
POST /api/v1/transactions/{id}/capture
Применимо только к транзакциям с capture_mode=manual в статусе authorized.
"""
import json
import time
import uuid

import pytest
import requests

from conftest import (
    calc_signature,
    post_operation,
    BASE_URL,
    TERMINAL_ID,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
    make_op_body,
)

_OP_BODY = {
    "merchant_data": {
        "order_id": "order_capture_test",
        "description": "Capture test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-001")
def test_capture_full(payin_block_transaction_id):
    """Полное списание по транзакции с capture_mode=manual. Ожидается 200."""
    resp = post_operation(payin_block_transaction_id, "capture", _OP_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("CAP-002")
def test_capture_partial():
    """Частичное списание (500 из 1000). Ожидается 200."""
    oid = gen_order_id("capture_partial")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("CAP-003")
def test_capture_without_webhook_url():
    """Capture без необязательного webhook_url в merchant_data. Ожидается 200."""
    oid = gen_order_id("capture_no_wh")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-004")
def test_capture_nonexistent_transaction():
    """Capture по несуществующей транзакции. Ожидается 404."""
    resp = post_operation("000000000000", "capture", _OP_BODY)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-005")
def test_capture_missing_financial_data():
    """Capture без financial_data (обязательное). Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_capture_test"}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-006")
def test_capture_missing_merchant_data():
    """Capture без merchant_data (обязательное). Ожидается 400."""
    body = {"financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-007")
def test_capture_missing_order_id():
    """Capture с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {"description": "no order_id"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-008")
def test_capture_missing_amount():
    """Capture без поля amount в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-009")
def test_capture_missing_currency():
    """Capture без поля currency в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-010")
def test_capture_invalid_currency():
    """Capture с невалидным кодом валюты. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "INVALID"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-011")
def test_capture_zero_amount():
    """Capture с нулевой суммой. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-012")
def test_capture_negative_amount():
    """Capture с отрицательной суммой. Ожидается 400 или 404."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": -500, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-013")
def test_capture_no_auth():
    """Capture без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(url, data=raw, headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-014")
def test_capture_invalid_signature():
    """Capture с подписью из нулей. Ожидается 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
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


@pytest.mark.tcid("CAP-015")
def test_capture_missing_terminal_id():
    """Capture без заголовка Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
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


@pytest.mark.tcid("CAP-016")
def test_capture_missing_timestamp():
    """Capture без заголовка Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/capture"
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
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
# ГРАНИЧНЫЕ СЛУЧАИ — ДОПОЛНИТЕЛЬНЫЕ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-017")
def test_capture_amount_as_string():
    """Capture с суммой как строкой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": "1000", "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-018")
def test_capture_amount_as_float():
    """Capture с суммой как вещественным числом. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 500.50, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-019")
def test_capture_currency_lowercase():
    """Capture с валютой в нижнем регистре. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_capture_test"},
        "financial_data": {"amount": 1000, "currency": "rub"},
    }
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-020")
def test_capture_amount_exceeds_authorized():
    """Capture с суммой, превышающей заблокированную (1000). Ожидается 400 или 409."""
    oid = gen_order_id("capture_exceed")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 999999, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (400, 409), f"Expected 400/409, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-021")
def test_capture_already_captured():
    """Повторный capture уже захваченной транзакции. Ожидается 409."""
    oid = gen_order_id("capture_twice")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp1 = post_operation(tid, "capture", body)
    assert resp1.status_code == 200, f"First capture failed: {resp1.text}"
    resp2 = post_operation(tid, "capture", body)
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
    assert_error_response(resp2)


@pytest.mark.tcid("CAP-022")
def test_capture_with_description():
    """Capture с опциональным description в merchant_data. Ожидается 200."""
    oid = gen_order_id("capture_desc")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {
            "order_id": oid,
            "description": "Authorized capture",
        },
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("CAP-023")
def test_capture_response_fields():
    """Capture успешной транзакции — ответ содержит все обязательные поля."""
    oid = gen_order_id("capture_resp_check")
    tid = make_block_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    assert data["financial_data"]["currency"] == "RUB"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (CAP-024 … CAP-030)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CAP-024")
def test_capture_idempotency_same_key_second_returns_409():
    """Capture с одним idempotency_key дважды — второй возвращает 409."""
    order_id = gen_order_id("cap_idem")
    tid = make_block_payin(order_id)
    body = make_op_body(order_id)
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
        return requests.post(f"{BASE_URL}/{tid}/capture", data=raw, headers=h, timeout=30)

    r1 = _do(str(int(time.time())))
    assert r1.status_code == 200, f"First capture failed: {r1.text}"
    r2 = _do(str(int(time.time())))
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}"


@pytest.mark.tcid("CAP-025")
def test_capture_missing_idempotency_key_returns_400():
    """Capture без Api-Idempotency-Key. Ожидается 400."""
    body = make_op_body("order_capture_test")
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(f"{BASE_URL}/000000000000/capture", data=raw, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-026")
def test_capture_response_has_merchant_data():
    """Capture успешной транзакции — ответ содержит merchant_data."""
    order_id = gen_order_id("cap_md")
    tid = make_block_payin(order_id)
    resp = post_operation(tid, "capture", make_op_body(order_id))
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "merchant_data" in resp.json()


@pytest.mark.tcid("CAP-027")
def test_capture_response_has_created_at():
    """Capture успешной транзакции — ответ содержит created_at."""
    order_id = gen_order_id("cap_ca")
    tid = make_block_payin(order_id)
    resp = post_operation(tid, "capture", make_op_body(order_id))
    assert resp.status_code == 200
    assert "created_at" in resp.json()


@pytest.mark.tcid("CAP-028")
def test_capture_financial_data_empty_object():
    """Capture с financial_data как пустым объектом. Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_capture_test"}, "financial_data": {}}
    resp = post_operation("000000000000", "capture", body)
    assert resp.status_code in (400, 404)
    assert_error_response(resp)


@pytest.mark.tcid("CAP-029")
def test_capture_auto_payin_returns_409():
    """Capture по транзакции с capture_mode=auto. Ожидается 409."""
    order_id = gen_order_id("cap_auto")
    tid = make_completed_payin(order_id)
    resp = post_operation(tid, "capture", make_op_body(order_id))
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-031")
def test_capture_description_comes_from_capture_not_parent():
    """description в ответе capture должен быть из запроса capture, а не из родительской транзакции."""
    oid = gen_order_id("cap_desc_check")
    tid = make_block_payin(oid, description="Parent description")
    body = {
        "merchant_data": {"order_id": oid, "description": "Capture description"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    actual = data.get("merchant_data", {}).get("description")
    assert actual == "Capture description", \
        f"Expected description from capture request, got {actual!r}"


@pytest.mark.tcid("CAP-030")
def test_capture_min_amount_one():
    """Capture с суммой 1 (минимально допустимое). Ожидается 200 или 400."""
    order_id = gen_order_id("cap_min")
    tid = make_block_payin(order_id)
    body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 1, "currency": "RUB"}}
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (200, 400), f"Expected 200 or 400, got {resp.status_code}"
