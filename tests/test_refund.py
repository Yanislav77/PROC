"""
Тесты для операции refund (возврат средств).
POST /api/v1/transactions/{id}/refund
"""
import json
import time
import uuid

import pytest
import requests

from conftest import (
    calc_signature,
    post_transaction,
    post_operation,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    SETUP_DELAY,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
)

_REFUND_BODY = {
    "merchant_data": {
        "order_id": "order_refund_test",
        "description": "Refund test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}


@pytest.fixture
def refund_tid():
    """Создаёт новую Payin-транзакцию (auto) перед каждым тестом возврата."""
    return make_completed_payin(gen_order_id("rf_fixture"))


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-001")
def test_refund_partial(refund_tid):
    """Частичный возврат (1000 из 10000) по существующей транзакции. Ожидается 200 или 201."""
    resp = post_operation(refund_tid, "refund", _REFUND_BODY)
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
    """Возврат по несуществующей транзакции. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation("nonexistent-id-000000", "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-003")
def test_refund_amount_exceeds_original(refund_tid):
    """Сумма возврата (99999999) превышает оригинальную сумму транзакции. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test", "webhook_url": "https://example.com/"},
        "financial_data": {"amount": 99999999, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.parametrize("body", [
    pytest.param(
        {"financial_data": {"amount": 100, "currency": "RUB"}},
        marks=pytest.mark.tcid("RF-004"), id="missing_merchant_data",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}},
        marks=pytest.mark.tcid("RF-005"), id="missing_financial_data",
    ),
    pytest.param(
        {"merchant_data": {"description": "Refund"}, "financial_data": {"amount": 100, "currency": "RUB"}},
        marks=pytest.mark.tcid("RF-006"), id="missing_order_id",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": 100}},
        marks=pytest.mark.tcid("RF-007"), id="missing_currency",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"currency": "RUB"}},
        marks=pytest.mark.tcid("RF-008"), id="missing_amount",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": 0, "currency": "RUB"}},
        marks=pytest.mark.tcid("RF-009"), id="zero_amount",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": -100, "currency": "RUB"}},
        marks=pytest.mark.tcid("RF-010"), id="negative_amount",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": 100, "currency": "INVALID"}},
        marks=pytest.mark.tcid("RF-011"), id="invalid_currency",
    ),
])
def test_refund_invalid_body(refund_tid, body):
    """Возврат с невалидным телом запроса. Ожидается 400."""
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HAPPY PATH — ДОПОЛНИТЕЛЬНЫЕ КЕЙСЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-012")
def test_refund_full():
    """Полный возврат (10000 из 10000). Ожидается 200 или 201."""
    oid = gen_order_id("refund_full")
    tid = make_completed_payin(oid)
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
def test_refund_with_description(refund_tid):
    """Возврат с опциональным description в merchant_data. Ожидается 200 или 201."""
    body = {
        "merchant_data": {
            "order_id": "order_refund_test",
            "description": "Customer requested refund",
        },
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("RF-014")
def test_refund_without_webhook_url(refund_tid):
    """Возврат без webhook_url (необязательное). Ожидается 200 или 201."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — ТИП ДАННЫХ
# ─────────────────────────────────────────────
@pytest.mark.parametrize("amount", [
    pytest.param("500",   marks=pytest.mark.tcid("RF-015"), id="str"),
    pytest.param(100.50,  marks=pytest.mark.tcid("RF-016"), id="float"),
])
def test_refund_invalid_amount_type(refund_tid, amount):
    """Возврат с суммой невалидного типа. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": amount, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-017")
def test_refund_currency_lowercase(refund_tid):
    """Возврат с валютой в нижнем регистре. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "rub"},
    }
    resp = post_operation(refund_tid, "refund", body)
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
    """Refund с подписью из нулей по реальной транзакции. Ожидается 401 или 403."""
    tid = make_completed_payin(gen_order_id("rf_bad_sig"))
    url = f"{BASE_URL}/{tid}/refund"
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
    """Платёж 10000: первый возврат 5000 (успех), второй возврат 6000 > остаток 5000 (ошибка)."""
    oid = gen_order_id("refund_exceed_remain")
    tid = make_completed_payin(oid)  # 10000 RUB
    resp1 = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 5000, "currency": "RUB"},
    })
    assert resp1.status_code in (200, 201), f"First refund (5000) failed: {resp1.text}"
    resp2 = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 6000, "currency": "RUB"},
    })
    assert resp2.status_code in (400, 409), f"Expected 400/409, got {resp2.status_code}: {resp2.text}"
    assert_error_response(resp2)


@pytest.mark.tcid("RF-023")
def test_refund_response_fields(refund_tid):
    """Refund — проверка типов всех обязательных полей ответа."""
    body = {
        "merchant_data": {"order_id": "order_refund_test"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["financial_data"]["currency"] == "RUB"
    assert data["type"] == "payin"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (RF-024 … RF-035)
# ─────────────────────────────────────────────
@pytest.mark.tcid("RF-024")
def test_refund_idempotency_same_key_second_returns_409(refund_tid):
    """Refund с одним idempotency_key дважды — второй возвращает 409."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
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
        return requests.post(f"{BASE_URL}/{refund_tid}/refund", data=raw, headers=h, timeout=30)

    r1 = _do(str(int(time.time())))
    assert r1.status_code in (200, 201), f"First refund failed: {r1.text}"
    r2 = _do(str(int(time.time())))
    assert r2.status_code == 409, f"Expected 409 for duplicate key, got {r2.status_code}"


@pytest.mark.tcid("RF-025")
def test_refund_missing_idempotency_key_returns_400(refund_tid):
    """Refund без Api-Idempotency-Key. Ожидается 400."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, timestamp, raw)
    headers = {
        "Content-Type":    "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   sig,
        "Api-Timestamp":   timestamp,
    }
    resp = requests.post(f"{BASE_URL}/{refund_tid}/refund", data=raw, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-026")
def test_refund_response_content_type_is_json(refund_tid):
    """Refund — Content-Type ответа содержит application/json."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


@pytest.mark.tcid("RF-027")
def test_refund_financial_data_empty_object(refund_tid):
    """Refund с financial_data как пустым объектом. Ожидается 400."""
    body = {"merchant_data": {"order_id": MERCHANT_DATA["order_id"]}, "financial_data": {}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-028")
def test_refund_on_cancelled_transaction():
    """Refund по отменённой транзакции (cancelled). Ожидается 409."""
    order_id = gen_order_id("rf_cancelled")
    tid = make_block_payin(order_id)
    cancel_body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 1000, "currency": "RUB"}}
    resp_cancel = post_operation(tid, "cancel", cancel_body)
    assert resp_cancel.status_code in (200, 201), f"Cancel setup failed: {resp_cancel.text}"

    body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(tid, "refund", body)
    assert resp.status_code == 409, f"Expected 409 for refund on cancelled, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-029")
def test_refund_currency_mismatch(refund_tid):
    """Refund с валютой, отличной от оригинальной транзакции. Ожидается 400 или 409."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "USD"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (400, 409), f"Expected 400/409, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-030")
def test_refund_min_amount_one(refund_tid):
    """Refund с суммой 1 (минимально допустимое). Ожидается 200 или 201."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 1, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("RF-031")
def test_refund_response_has_financial_data(refund_tid):
    """Refund — ответ содержит financial_data с amount и currency."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    if resp.status_code in (200, 201):
        fd = resp.json().get("financial_data", {})
        assert "amount" in fd
        assert "currency" in fd


@pytest.mark.tcid("RF-032")
def test_refund_response_transaction_id_is_int(refund_tid):
    """Refund — transaction_id в ответе является целым числом."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    if resp.status_code in (200, 201):
        assert isinstance(resp.json().get("transaction_id"), int)


@pytest.mark.parametrize("body", [
    pytest.param(
        {"merchant_data": {"order_id": None}, "financial_data": {"amount": 100, "currency": "RUB"}},
        marks=pytest.mark.tcid("RF-033"), id="null_order_id",
    ),
    pytest.param(
        {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": None, "currency": "RUB"}},
        marks=pytest.mark.tcid("RF-035"), id="null_amount",
    ),
])
def test_refund_null_field(refund_tid, body):
    """Refund с null в обязательном поле. Ожидается 400."""
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-036")
def test_refund_description_comes_from_refund_not_parent():
    """description в ответе refund должен быть из запроса refund, а не из родительской транзакции."""
    oid = gen_order_id("rf_desc_check")
    parent_body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid, "description": "Parent description"},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp_parent = post_transaction(parent_body)
    assert resp_parent.status_code == 201, f"Parent payin failed: {resp_parent.text}"
    time.sleep(SETUP_DELAY)
    tid = resp_parent.json()["transaction_id"]

    refund_body = {
        "merchant_data": {"order_id": oid, "description": "Refund description"},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
    resp = post_operation(tid, "refund", refund_body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    actual = data.get("merchant_data", {}).get("description")
    assert actual == "Refund description", \
        f"Expected description from refund request, got {actual!r}"


@pytest.mark.tcid("RF-034")
def test_refund_payout_transaction_returns_409():
    """Refund по payout-транзакции. Ожидается 409."""
    payout_body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("payout_rf")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
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
