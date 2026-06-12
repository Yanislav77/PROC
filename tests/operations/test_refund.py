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
    get_request,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    SETUP_DELAY,
    assert_transaction_response,
    assert_error_response,
    assert_idempotency_echo,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
)
from _helpers.polling import poll_status

_REFUND_BODY = {
    "merchant_data": {
        "order_id": "order_refund_test",
        "description": "Refund test",
        "webhook_url": "https://example.com/webhook",
    },
    "financial_data": {"amount": 1000, "currency": "RUB"},
}

_FAKE_TID = "000000000000"
_SIMPLE_BODY = {
    "merchant_data": {"order_id": "order_refund_test"},
    "financial_data": {"amount": 100, "currency": "RUB"},
}


def _refund_url(tid) -> str:
    return f"{BASE_URL}/{tid}/refund"


def _raw_refund(tid, body: dict, **header_overrides) -> requests.Response:
    """POST refund с произвольными заголовками поверх валидных (подпись по текущему времени)."""
    from _helpers.validators import assert_idempotency_echo
    raw = json.dumps(body, separators=(",", ":"))
    ts = str(int(time.time()))
    sig = calc_signature(TERMINAL_ID, ts, raw)
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
        **header_overrides,
    }
    r = requests.post(_refund_url(tid), data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, r)
    return r


def _raw_refund_with_ts(tid, body: dict, ts: str) -> requests.Response:
    """POST refund с подписью, вычисленной по переданному timestamp."""
    from _helpers.validators import assert_idempotency_echo
    raw = json.dumps(body, separators=(",", ":"))
    sig = calc_signature(TERMINAL_ID, ts, raw)
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts,
    }
    r = requests.post(_refund_url(tid), data=raw, headers=headers, timeout=30)
    assert_idempotency_echo(headers, r)
    return r


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
    if data.get("status") != "completed":
        poll_status(refund_tid, "completed")


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
    assert_idempotency_echo(headers, resp)
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
    assert_idempotency_echo(headers, resp)
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
    assert_idempotency_echo(headers, resp)
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
    time.sleep(SETUP_DELAY)
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
def test_refund_idempotency_same_key_returns_cached_response(refund_tid):
    """Refund с одним idempotency_key дважды — второй возвращает кэшированный ответ первого (200)."""
    body = {
        "merchant_data": {"order_id": MERCHANT_DATA["order_id"]},
        "financial_data": {"amount": 100, "currency": "RUB"},
    }
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
        r = requests.post(f"{BASE_URL}/{refund_tid}/refund", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _do(str(int(time.time())))
    assert r1.status_code in (200, 201), f"First refund failed: {r1.text}"
    r2 = _do(str(int(time.time())))
    assert r2.status_code in (200, 201), f"Expected cached 200/201 for duplicate key, got {r2.status_code}"
    assert r1.json().get("transaction_id") == r2.json().get("transaction_id"), \
        f"Cached response must return same transaction_id: {r1.json()} vs {r2.json()}"


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
    assert_idempotency_echo(headers, resp)
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
    time.sleep(SETUP_DELAY)
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
    time.sleep(SETUP_DELAY)
    body = {"merchant_data": {"order_id": order_id}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(tid, "refund", body)
    assert resp.status_code == 409, f"Expected 409 for refund on payout, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-035")
def test_refund_idempotency_same_key_different_body():
    """Payin → refund → повторный refund с тем же Idempotency-Key, но другой суммой.
    Сервер должен либо вернуть кэшированный ответ первого рефанда (200, та же transaction_id),
    либо вернуть 4xx (конфликт идемпотентности). Новый рефанд создаваться не должен."""
    oid = gen_order_id("rf_idem_diff")
    tid = make_completed_payin(oid)

    body1 = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 500, "currency": "RUB"},
    }
    body2 = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 999, "currency": "RUB"},
    }
    key = str(uuid.uuid4())

    def _do(raw: str) -> requests.Response:
        from _helpers.validators import assert_idempotency_echo
        sig = calc_signature(TERMINAL_ID, str(int(time.time())), raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       str(int(time.time())),
        }
        r = requests.post(f"{BASE_URL}/{tid}/refund", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _do(json.dumps(body1, separators=(",", ":")))
    assert r1.status_code in (200, 201), f"First refund failed: {r1.text}"
    tid_r1 = r1.json().get("transaction_id")

    r2 = _do(json.dumps(body2, separators=(",", ":")))
    assert r2.status_code in (200, 201, 400, 409), \
        f"Expected cached 200/201 or 4xx conflict, got {r2.status_code}: {r2.text}"

    if r2.status_code in (200, 201):
        assert r2.json().get("transaction_id") == tid_r1, (
            f"Same key + different body returned a NEW transaction_id — "
            f"server processed the second refund instead of returning cache: "
            f"r1.tid={tid_r1}, r2.tid={r2.json().get('transaction_id')}"
        )


# ─────────────────────────────────────────────
# ЗАГОЛОВКИ — ГРАНИЧНЫЕ КЕЙСЫ (RF-037 … RF-045)
# ─────────────────────────────────────────────

@pytest.mark.tcid("RF-037")
def test_refund_idempotency_key_non_uuid():
    """Api-Idempotency-Key с произвольной строкой (не UUID) — принимается или отклоняется."""
    resp = _raw_refund(_FAKE_TID, _SIMPLE_BODY, **{"Api-Idempotency-Key": "abc123"})
    assert resp.status_code in (200, 201, 400, 404), f"Unexpected {resp.status_code}"


@pytest.mark.tcid("RF-038")
def test_refund_idempotency_key_empty():
    """Пустой Api-Idempotency-Key принимается или отклоняется."""
    resp = _raw_refund(_FAKE_TID, _SIMPLE_BODY, **{"Api-Idempotency-Key": ""})
    assert resp.status_code in (200, 201, 400, 404), f"Unexpected {resp.status_code}"


@pytest.mark.tcid("RF-039")
def test_refund_nonexistent_terminal_id():
    """Несуществующий Api-Terminal-ID отклоняется с ошибкой авторизации."""
    resp = _raw_refund(_FAKE_TID, _SIMPLE_BODY, **{"Api-Terminal-ID": "99999999"})
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-040")
def test_refund_empty_terminal_id():
    """Пустой Api-Terminal-ID отклоняется с ошибкой авторизации."""
    resp = _raw_refund(_FAKE_TID, _SIMPLE_BODY, **{"Api-Terminal-ID": ""})
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-041")
def test_refund_empty_signature():
    """Пустой Api-Signature отклоняется с ошибкой авторизации."""
    resp = _raw_refund(_FAKE_TID, _SIMPLE_BODY, **{"Api-Signature": ""})
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-042")
def test_refund_timestamp_invalid_string():
    """Нечисловое значение Api-Timestamp отклоняется с ошибкой валидации."""
    resp = _raw_refund(_FAKE_TID, _SIMPLE_BODY, **{"Api-Timestamp": "abc"})
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-043")
def test_refund_timestamp_too_old():
    """Api-Timestamp старше 5 минут отклоняется как просроченный."""
    old_ts = str(int(time.time()) - 400)
    resp = _raw_refund_with_ts(_FAKE_TID, _SIMPLE_BODY, old_ts)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-044")
def test_refund_timestamp_near_future(refund_tid):
    """Api-Timestamp 4 минуты в будущем — в пределах допустимого окна, запрос принимается."""
    future_ts = str(int(time.time()) + 240)
    resp = _raw_refund_with_ts(refund_tid, _SIMPLE_BODY, future_ts)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("RF-045")
def test_refund_timestamp_far_future():
    """Api-Timestamp 10 минут в будущем — вне допустимого окна, запрос отклоняется."""
    far_ts = str(int(time.time()) + 600)
    resp = _raw_refund_with_ts(_FAKE_TID, _SIMPLE_BODY, far_ts)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# BODY — MERCHANT DATA / ORDER ID (RF-046 … RF-050)
# ─────────────────────────────────────────────

@pytest.mark.tcid("RF-046")
def test_refund_merchant_data_empty_object(refund_tid):
    """merchant_data как пустой объект {} отклоняется из-за отсутствия order_id. Ожидается 400."""
    body = {"merchant_data": {}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-047")
def test_refund_order_id_int_type(refund_tid):
    """order_id с типом int отклоняется. Ожидается 400."""
    body = {"merchant_data": {"order_id": 12345}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-048")
def test_refund_order_id_empty_string(refund_tid):
    """order_id с пустым значением отклоняется. Ожидается 400."""
    body = {"merchant_data": {"order_id": ""}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-049")
def test_refund_order_id_100_chars(refund_tid):
    """order_id ровно 100 символов принимается. Ожидается 200 или 201."""
    body = {"merchant_data": {"order_id": "a" * 100}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("RF-050")
def test_refund_order_id_over_100_chars(refund_tid):
    """order_id длиннее 100 символов отклоняется. Ожидается 400."""
    body = {"merchant_data": {"order_id": "a" * 101}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# BODY — AMOUNT (RF-051 … RF-052)
# ─────────────────────────────────────────────

@pytest.mark.tcid("RF-051")
def test_refund_amount_very_large(refund_tid):
    """amount = 10_000_000_000_000 — превышает оригинальную транзакцию. Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": 10_000_000_000_000, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-052")
def test_refund_amount_above_max(refund_tid):
    """amount > 10_000_000_000_000 — проверка поведения на превышении возможного максимума. Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": 99_999_999_999_999, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# BODY — CURRENCY (RF-053 … RF-056)
# ─────────────────────────────────────────────

@pytest.mark.parametrize("currency", [
    pytest.param("840",  marks=pytest.mark.tcid("RF-053"), id="numeric_3_chars"),
    pytest.param("RU",   marks=pytest.mark.tcid("RF-054"), id="alpha_2_chars"),
    pytest.param("RUBR", marks=pytest.mark.tcid("RF-055"), id="alpha_4_chars"),
    pytest.param("",     marks=pytest.mark.tcid("RF-056"), id="empty"),
])
def test_refund_invalid_currency_format(refund_tid, currency):
    """Невалидный формат currency (не 3-буквенный ISO 4217) отклоняется. Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_refund_test"}, "financial_data": {"amount": 100, "currency": currency}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400 for currency={currency!r}, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# BODY — WEBHOOK URL (RF-057 … RF-059)
# ─────────────────────────────────────────────

@pytest.mark.tcid("RF-057")
def test_refund_webhook_url_invalid_string(refund_tid):
    """webhook_url с произвольной строкой (не URL) — принимается или отклоняется."""
    body = {"merchant_data": {"order_id": "order_refund_test", "webhook_url": "not-a-url"}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201, 400), f"Unexpected {resp.status_code}"


@pytest.mark.tcid("RF-058")
def test_refund_webhook_url_int_type(refund_tid):
    """webhook_url с типом int отклоняется. Ожидается 400."""
    body = {"merchant_data": {"order_id": "order_refund_test", "webhook_url": 12345}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("RF-059")
def test_refund_webhook_url_empty_string(refund_tid):
    """webhook_url с пустой строкой — принимается или отклоняется."""
    body = {"merchant_data": {"order_id": "order_refund_test", "webhook_url": ""}, "financial_data": {"amount": 100, "currency": "RUB"}}
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201, 400), f"Unexpected {resp.status_code}"


# ─────────────────────────────────────────────
# РЕГРЕСС — копейки
# ─────────────────────────────────────────────

@pytest.mark.tcid("RF-060")
def test_refund_amount_with_kopecks(refund_tid):
    """Частичный возврат с суммой, содержащей копейки (5050 = 50.50 руб). Ожидается 200 или 201."""
    body = {
        "merchant_data": {"order_id": gen_order_id("kopecks"), "webhook_url": "https://example.com/webhook"},
        "financial_data": {"amount": 5050, "currency": "RUB"},
    }
    resp = post_operation(refund_tid, "refund", body)
    assert resp.status_code in (200, 201), f"Expected 200/201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())
