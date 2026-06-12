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
    get_request,
    BASE_URL,
    TERMINAL_ID,
    assert_transaction_response,
    assert_error_response,
    assert_idempotency_echo,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
    make_op_body,
)
from _helpers.polling import poll_status

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
    if data.get("status") != "completed":
        poll_status(payin_block_transaction_id, "completed")


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
    data = resp.json()
    assert_transaction_response(data)
    if data.get("status") != "completed":
        poll_status(tid, "completed")


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
    data = resp.json()
    assert_transaction_response(data)
    if data.get("status") != "completed":
        poll_status(tid, "completed")


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
    oid = gen_order_id("cap_inv_sig")
    tid = make_block_payin(oid)
    url = f"{BASE_URL}/{tid}/capture"
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
    assert_idempotency_echo(headers, resp)
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
    assert_idempotency_echo(headers, resp)
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
    assert_idempotency_echo(headers, resp)
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
def test_capture_idempotency_same_key_returns_cached_response():
    """Capture с одним idempotency_key дважды — второй возвращает кэшированный ответ."""
    order_id = gen_order_id("cap_idem")
    tid = make_block_payin(order_id)
    body = make_op_body(order_id)
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _do(ts: str) -> requests.Response:
        from _helpers.validators import assert_idempotency_echo
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        r = requests.post(f"{BASE_URL}/{tid}/capture", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _do(str(int(time.time())))
    assert r1.status_code == 200, f"First capture failed: {r1.text}"
    tid1 = r1.json().get("transaction_id")

    r2 = _do(str(int(time.time())))
    assert r2.status_code == 200, f"Expected cached 200, got {r2.status_code}: {r2.text}"
    assert r2.json().get("transaction_id") == tid1, \
        f"Кэшированный ответ должен вернуть тот же transaction_id: {tid1!r}, got {r2.json().get('transaction_id')!r}"


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


@pytest.mark.tcid("CAP-032")
def test_capture_idempotency_same_key_different_body():
    """Capture с одним Idempotency-Key, но разными суммами — второй возвращает кэшированный ответ первого."""
    order_id = gen_order_id("cap_idem_diff")
    tid = make_block_payin(order_id)
    key = str(uuid.uuid4())

    def _do(amount: int, ts: str) -> requests.Response:
        from _helpers.validators import assert_idempotency_echo
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
        r = requests.post(f"{BASE_URL}/{tid}/capture", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _do(1000, str(int(time.time())))
    assert r1.status_code == 200, f"First capture failed: {r1.text}"
    tid1 = r1.json().get("transaction_id")

    r2 = _do(500, str(int(time.time())))
    if r2.status_code == 200:
        assert r2.json().get("transaction_id") == tid1, \
            f"Кэшированный ответ должен вернуть тот же transaction_id: {tid1!r}"
    else:
        assert r2.status_code in (400, 409), \
            f"Expected cached response or conflict error, got {r2.status_code}: {r2.text}"
        assert_error_response(r2)


# ═════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ КОНСТАНТЫ И HELPER ДЛЯ HEADER-ТЕСТОВ
# ═════════════════════════════════════════════════════════

_FAKE_TID_CAP   = "000000000000"
_SIMPLE_BODY_CAP = {
    "merchant_data": {"order_id": "order_cap_hdr_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


def _raw_capture(tid: str, body: dict | None = None, **h_override) -> requests.Response:
    """Capture с возможностью переопределить отдельные заголовки.
    Подпись вычисляется с учётом переопределённых Api-Terminal-ID / Api-Timestamp."""
    b   = body or _SIMPLE_BODY_CAP
    raw = json.dumps(b, separators=(",", ":"))
    terminal_id = h_override.get("Api-Terminal-ID", TERMINAL_ID)
    ts          = h_override.get("Api-Timestamp",   str(int(time.time())))
    sig = calc_signature(terminal_id, ts, raw)
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     terminal_id,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    headers.update(h_override)
    return requests.post(f"{BASE_URL}/{tid}/capture", data=raw, headers=headers, timeout=30)


# ═════════════════════════════════════════════════════════
# 1. Api-Terminal-ID (CAP-033 … CAP-036)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-033")
def test_capture_empty_terminal_id():
    """Api-Terminal-ID = '' (пустая строка) → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Terminal-ID": ""})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-034")
def test_capture_nonexistent_terminal_id():
    """Api-Terminal-ID = несуществующий сервис ('99999999') → 401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Terminal-ID": "99999999"})
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-035")
def test_capture_special_chars_terminal_id():
    """Api-Terminal-ID = спецсимволы/буквы ('hfkjRETGG%^&*(') → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Terminal-ID": "hfkjRETGG%^&*("})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-036")
def test_capture_very_long_terminal_id():
    """Api-Terminal-ID = 1000 символов → 400/401/403."""
    oid = gen_order_id("cap_long_tid")
    tid = make_block_payin(oid)
    r = _raw_capture(tid, **{"Api-Terminal-ID": "1" * 1000})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════════════════
# 2. Api-Idempotency-Key (CAP-037 … CAP-039)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-037")
def test_capture_empty_idempotency_key():
    """Api-Idempotency-Key = '' (пустая строка) → 400."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Idempotency-Key": ""})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-038")
def test_capture_non_uuid_idempotency_key():
    """Api-Idempotency-Key не в формате UUID ('8762c97713384ec') → 400."""
    oid = gen_order_id("cap_non_uuid")
    tid = make_block_payin(oid)
    r = _raw_capture(tid, **{"Api-Idempotency-Key": "8762c97713384ec"})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-039")
@pytest.mark.parametrize("key,label", [
    ("abc",     "too_short"),
    ("x" * 500, "too_long"),
])
def test_capture_invalid_length_idempotency_key(key, label):
    """Api-Idempotency-Key слишком короткий/длинный → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Idempotency-Key": key})
    assert r.status_code in (400, 401, 403), \
        f"[{label}] Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════════════════
# 3. Api-Timestamp (CAP-040 … CAP-044)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-040")
def test_capture_empty_timestamp():
    """Api-Timestamp = '' (пустая строка) → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Timestamp": ""})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-041")
def test_capture_stale_timestamp():
    """Api-Timestamp = сутки назад → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Timestamp": str(int(time.time()) - 86400)})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-042")
def test_capture_future_timestamp():
    """Api-Timestamp = сутки вперёд → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Timestamp": str(int(time.time()) + 86400)})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-043")
def test_capture_non_numeric_timestamp():
    """Api-Timestamp = нечисловое значение ('not-a-timestamp') → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Timestamp": "not-a-timestamp"})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("CAP-044")
def test_capture_negative_timestamp():
    """Api-Timestamp = отрицательное значение ('-1') → 400/401/403."""
    r = _raw_capture(_FAKE_TID_CAP, **{"Api-Timestamp": "-1"})
    assert r.status_code in (400, 401, 403), f"Expected 4xx, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════════════════
# 4. transaction_id в URL (CAP-045 … CAP-047)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-045")
def test_capture_cancelled_transaction():
    """Capture отменённой транзакции → 409."""
    oid = gen_order_id("cap_cancelled")
    tid = make_block_payin(oid)
    cancel = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    if cancel.status_code not in (200, 201):
        pytest.skip(f"Failed to cancel transaction {tid}: {cancel.text}")
    time.sleep(2)
    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code in (400, 409), \
        f"Expected 4xx for cancelled transaction, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-046")
def test_capture_alphabetic_transaction_id():
    """transaction_id = буквы в URL ('abc123xyz') → 400/404."""
    r = _raw_capture("abc123xyz")
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"


@pytest.mark.tcid("CAP-047")
def test_capture_path_without_transaction_id():
    """URL без transaction_id (/transactions/capture вместо /transactions/{id}/capture) → 400/404/405."""
    raw = json.dumps(_SIMPLE_BODY_CAP, separators=(",", ":"))
    ts  = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, ts, raw)
    h = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    r = requests.post(f"{BASE_URL}/capture", data=raw, headers=h, timeout=30)
    assert r.status_code in (400, 404, 405), f"Expected 4xx, got {r.status_code}: {r.text}"


# ═════════════════════════════════════════════════════════
# 5. amount — дополнительный кейс (CAP-048)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-048")
def test_capture_null_amount():
    """amount = null → 400."""
    body = {
        "merchant_data": {"order_id": "order_cap_null_amt"},
        "financial_data": {"amount": None, "currency": "RUB"},
    }
    resp = post_operation(_FAKE_TID_CAP, "capture", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ═════════════════════════════════════════════════════════
# 6. currency — дополнительные кейсы (CAP-049 … CAP-051)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-049")
def test_capture_empty_currency():
    """currency = '' (пустая строка) → 400."""
    body = {
        "merchant_data": {"order_id": "order_cap_empty_cur"},
        "financial_data": {"amount": 1000, "currency": ""},
    }
    resp = post_operation(_FAKE_TID_CAP, "capture", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-050")
def test_capture_currency_mismatch():
    """currency не совпадает с валютой транзакции (USD вместо RUB) → 4xx."""
    oid = gen_order_id("cap_cur_mismatch")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "USD"},
    })
    assert resp.status_code in (400, 409, 422), \
        f"Expected 4xx for currency mismatch, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-051")
def test_capture_numeric_currency():
    """currency = цифры ('123') вместо ISO-кода → 400."""
    body = {
        "merchant_data": {"order_id": "order_cap_num_cur"},
        "financial_data": {"amount": 1000, "currency": "123"},
    }
    resp = post_operation(_FAKE_TID_CAP, "capture", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ═════════════════════════════════════════════════════════
# 7. order_id (CAP-052 … CAP-054)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-052")
def test_capture_empty_order_id():
    """order_id = '' (пустая строка) → 400."""
    body = {
        "merchant_data": {"order_id": ""},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(_FAKE_TID_CAP, "capture", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CAP-053")
def test_capture_special_chars_order_id():
    """order_id содержит спецсимволы — фиксируем поведение: 200/404 (принять) или 400 (отклонить)."""
    body = {
        "merchant_data": {"order_id": "order!@#$%^"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(_FAKE_TID_CAP, "capture", body)
    assert resp.status_code in (200, 400, 404), \
        f"Unexpected status for special chars order_id: {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CAP-054")
def test_capture_very_long_order_id():
    """order_id = 500+ символов → 400 или 404."""
    body = {
        "merchant_data": {"order_id": "o" * 500},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation(_FAKE_TID_CAP, "capture", body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ═════════════════════════════════════════════════════════
# 8. webhook_url (CAP-055 … CAP-057)
# ═════════════════════════════════════════════════════════

@pytest.mark.tcid("CAP-055")
def test_capture_empty_webhook_url():
    """webhook_url = '' — пустая строка: принять (200) или отклонить (400)."""
    oid = gen_order_id("cap_wh_empty")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid, "webhook_url": ""},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 400), \
        f"Expected 200 or 400 for empty webhook_url, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CAP-056")
def test_capture_non_https_webhook_url():
    """webhook_url без https:// ('http://example.com/webhook') → 400 или принять (200)."""
    oid = gen_order_id("cap_wh_http")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid, "webhook_url": "http://example.com/webhook"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 400), \
        f"Expected 200 or 400 for non-https webhook_url, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CAP-057")
def test_capture_nonexistent_domain_webhook_url():
    """webhook_url с несуществующим доменом → 200 (webhook асинхронный, доставка не блокирует capture)."""
    oid = gen_order_id("cap_wh_domain")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid, "webhook_url": "https://nonexistent-xyz123456.example/wh"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code == 200, \
        f"Expected 200 (webhook is async), got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# РЕГРЕСС — копейки
# ─────────────────────────────────────────────

@pytest.mark.tcid("CAP-058")
def test_capture_amount_with_kopecks():
    """Capture с суммой, содержащей копейки (505 = 5.05 руб). Ожидается 200."""
    oid = gen_order_id("cap_kopecks")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 505, "currency": "RUB"},
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())
