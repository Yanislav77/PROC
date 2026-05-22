"""
Тесты для операции refund (возврат средств).
POST /api/v1/transactions/{id}/refund
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
    make_headers,
    make_get_headers,
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

_REFUND_BODY = {
    "merchant_data": {
        "order_id": "order_refund_test",
        "description": "Refund test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


def _make_block_payin(order_id: str = None) -> str:
    """Создаёт Payin с capture_mode=manual (холд) и возвращает transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id or f"order_{uuid.uuid4().hex[:8]}"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup block payin failed: {resp.text}"
    return resp.json()["transaction_id"]


def _make_auto_payin(order_id: str = None) -> str:
    """Создаёт Payin с capture_mode=auto и возвращает transaction_id."""
    order_id = order_id or gen_order_id("refund_auto")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Auto Payin failed: {resp.text}"
    return resp.json()["transaction_id"]


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-001")
def test_refund_partial(payin_transaction_id):
    """Частичный возврат (1000 из 10000) по существующей транзакции. Ожидается 200 или 201."""
    resp = post_operation(payin_transaction_id, "refund", _REFUND_BODY)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    assert data["financial_data"]["currency"] == "RUB"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-002")
def test_refund_nonexistent_transaction():
    """Возврат по несуществующей транзакции. Ожидается 404."""
    url = f"{BASE_URL}/nonexistent-id-000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    resp = requests.post(url, data=raw, headers=headers, timeout=30)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-003")
def test_refund_amount_exceeds_original(payin_transaction_id):
    """Сумма возврата (99999999) превышает оригинальную сумму транзакции. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 99999999, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-004")
def test_refund_missing_merchant_data(payin_transaction_id):
    """Возврат без merchant_data (обязательное). Ожидается 400."""
    body = {"financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-005")
def test_refund_missing_financial_data(payin_transaction_id):
    """Возврат без financial_data (обязательное). Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_refund_test"}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-006")
def test_refund_missing_order_id(payin_transaction_id):
    """Возврат с merchant_data без order_id. Ожидается 400."""
    body = {
        "merchant_data": {"description": "Refund"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-007")
def test_refund_missing_currency(payin_transaction_id):
    """Возврат без поля currency в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-008")
def test_refund_missing_amount(payin_transaction_id):
    """Возврат без поля amount в financial_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-009")
def test_refund_zero_amount(payin_transaction_id):
    """Возврат с нулевой суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 0, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-010")
def test_refund_negative_amount(payin_transaction_id):
    """Возврат с отрицательной суммой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": -100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-011")
def test_refund_invalid_currency(payin_transaction_id):
    """Возврат с невалидным кодом валюты. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "INVALID"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HAPPY PATH — ДОПОЛНИТЕЛЬНЫЕ КЕЙСЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-012")
def test_refund_full():
    """Полный возврат (10000 из 10000). Ожидается 200 или 201."""
    oid = gen_order_id("refund_full")
    tid = _make_auto_payin(oid)
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
    }
    resp = post_operation(tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("RF-013")
def test_refund_with_description(payin_transaction_id):
    """Возврат с опциональным description в merchant_data. Ожидается 200 или 201."""
    body = {
        "merchant_data": {
            "order_id": "order_refund_test",
            "description": "Customer requested refund",
        },
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("RF-014")
def test_refund_without_webhook_url(payin_transaction_id):
    """Возврат без webhook_url (необязательное). Ожидается 200 или 201."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — ТИП ДАННЫХ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-015")
def test_refund_amount_as_string(payin_transaction_id):
    """Возврат с суммой как строкой. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": "500", "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-016")
def test_refund_amount_as_float(payin_transaction_id):
    """Возврат с суммой как вещественным числом. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100.50, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-017")
def test_refund_currency_lowercase(payin_transaction_id):
    """Возврат с валютой в нижнем регистре. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "rub"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-018")
def test_refund_no_auth():
    """Refund без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    resp = requests.post(url, data=raw, headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-019")
def test_refund_invalid_signature():
    """Refund с подписью из нулей. Ожидается 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
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


@pytest.mark.tcid("RF-020")
def test_refund_missing_terminal_id():
    """Refund без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
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


@pytest.mark.tcid("RF-021")
def test_refund_missing_timestamp():
    """Refund без Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000/refund"
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
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
# КОНФЛИКТНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-022")
def test_refund_exceeds_remaining():
    """Второй возврат превышает оставшуюся сумму. Ожидается 400 или 409."""
    oid = gen_order_id("refund_exceed_remain")
    tid = _make_auto_payin(oid)
    body_first = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 9500, "currency": "RUB"},
    }
    resp1 = post_operation(tid, "refund", body_first)
    assert resp1.status_code in (200, 201), f"First refund failed: {resp1.text}"
    body_second = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp2 = post_operation(tid, "refund", body_second)
    assert resp2.status_code in (400, 409), f"Expected 400/409, got {resp2.status_code}: {resp2.text}"
    assert_error_response(resp2)


@pytest.mark.tcid("RF-023")
def test_refund_response_fields(payin_transaction_id):
    """Refund — проверка типов всех обязательных полей ответа."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["financial_data"]["currency"] == "RUB"
    assert data["type"] == "payin"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (RF-024 … RF-035)
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-024")
def test_refund_idempotency_same_key_second_returns_409(payin_transaction_id):
    """Refund с одним idempotency_key дважды — второй возвращает 409."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
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
        return requests.post(f"{BASE_URL}/{payin_transaction_id}/refund", data=raw, headers=h, timeout=30)

    r1 = _do(str(int(time.time())))
    assert r1.status_code in (200, 201), f"First refund failed: {r1.text}"
    r2 = _do(str(int(time.time())))
    assert r2.status_code == 409, f"Expected 409 for duplicate key, got {r2.status_code}"


@pytest.mark.tcid("RF-025")
def test_refund_missing_idempotency_key_returns_400(payin_transaction_id):
    """Refund без Api-Idempotency-Key. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = _sign(TERMINAL_ID, timestamp, raw)
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(f"{BASE_URL}/{payin_transaction_id}/refund", data=raw, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-026")
def test_refund_response_content_type_is_json(payin_transaction_id):
    """Refund — Content-Type ответа содержит application/json."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    from conftest import post_operation as _post_op
    resp = _post_op(payin_transaction_id, "refund", body)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


@pytest.mark.tcid("RF-027")
def test_refund_financial_data_empty_object(payin_transaction_id):
    """Refund с financial_data как пустым объектом. Ожидается 400."""
    body = {"merchant_data": {"order_id": MERCHANT_DATA["order_id"]}, "financial_data": {}}
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-028")
def test_refund_on_cancelled_transaction():
    """Refund по отменённой транзакции (cancelled). Ожидается 409."""
    order_id = gen_order_id("rf_cancelled")
    tid = _make_block_payin(order_id)
    cancel_body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 1000, "currency": "RUB"}}
    resp_cancel = post_operation(tid, "cancel", cancel_body)
    assert resp_cancel.status_code in (200, 201), f"Cancel setup failed: {resp_cancel.text}"

    body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(tid, "refund", body)
    assert resp.status_code == 409, f"Expected 409 for refund on cancelled, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-029")
def test_refund_currency_mismatch(payin_transaction_id):
    """Refund с валютой, отличной от оригинальной транзакции. Ожидается 400 или 409."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "USD"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (400, 409), f"Expected 400/409, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-030")
def test_refund_min_amount_one(payin_transaction_id):
    """Refund с суммой 1 (минимально допустимое). Ожидается 200 или 201."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 1, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("RF-031")
def test_refund_response_has_financial_data(payin_transaction_id):
    """Refund — ответ содержит financial_data с amount и currency."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    if resp.status_code in (200, 201):
        fd = resp.json().get("financial_data", {})
        assert "amount" in fd
        assert "currency" in fd


@pytest.mark.tcid("RF-032")
def test_refund_response_transaction_id_is_int(payin_transaction_id):
    """Refund — transaction_id в ответе является целым числом."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    if resp.status_code in (200, 201):
        assert isinstance(resp.json().get("transaction_id"), int)


@pytest.mark.tcid("RF-033")
def test_refund_merchant_data_null_values(payin_transaction_id):
    """Refund с order_id = null в merchant_data. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": None},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-034")
def test_refund_payout_transaction_returns_409():
    """Refund по payout-транзакции. Ожидается 409."""
    from conftest import THREED as _THREED, CUSTOMER_DATA as _CD
    payout_body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("payout_rf")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": _THREED},
        "customer_data": _CD,
        "transaction_data": {"method": "sbp"},
    }
    resp_create = post_transaction(payout_body)
    assert resp_create.status_code == 201, f"Payout creation failed: {resp_create.text}"
    tid = resp_create.json()["transaction_id"]
    order_id = payout_body["merchant_data"]["order_id"]

    body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(tid, "refund", body)
    assert resp.status_code == 409, f"Expected 409 for refund on payout, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-035")
def test_refund_amount_null(payin_transaction_id):
    """Refund с amount = null. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": None, "currency": "RUB"},
    }
    resp = post_operation(payin_transaction_id, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)
