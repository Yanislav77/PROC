"""
Тесты для GET-эндпоинтов транзакций.
GET /api/v1/transactions?order_id=  — поиск по order_id мерчанта
GET /api/v1/transactions/{id}       — получение транзакции по числовому ID
"""
import hashlib
import hmac
import time
import uuid
import requests
import pytest

from conftest import (
    calc_signature,
    get_request,
    make_get_headers,
    post_transaction,
    post_operation,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    SERVICE_SECRET,
    CARD_DETAILS,
    CARD_ASYNC,
    MERCHANT_BALANCE_URL,
    assert_transaction_response,
    assert_error_response,
    make_block_payin,
    make_completed_payin,
    make_op_body,
    gen_order_id,
    query_transaction_from_redis,
    SETUP_DELAY,
)


def _sign(terminal_id: str, timestamp: str, raw_body: str = "") -> str:
    message = f"{timestamp}{terminal_id}{raw_body}"
    return hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-001")
def test_get_transaction_by_id(payin_transaction_id):
    """GET /{id} по реальному transaction_id. Ожидается 200 со всеми обязательными полями ответа."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["transaction_id"] == payin_transaction_id, "transaction_id mismatch"


@pytest.mark.tcid("GT-002")
def test_get_transaction_fields(payin_transaction_id):
    """GET /{id} — проверка типов и формата всех полей ответа по спецификации."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("GT-003")
def test_get_transactions_by_order_id(payin_transaction_id):
    """GET ?order_id= по реальному order_id мерчанта. Ожидается 200 и массив транзакций."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list), f"Expected a list, got {type(data)}"
    assert len(data) > 0, "Expected at least one transaction"
    item = data[0]
    assert_transaction_response(item)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-004")
def test_get_transaction_not_found():
    """GET по несуществующему числовому transaction_id. Ожидается 404."""
    url = f"{BASE_URL}/9999999999"
    resp = get_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-005")
def test_get_by_order_id_not_found():
    """GET ?order_id= с несуществующим order_id. Ожидается 404."""
    resp = get_request(BASE_URL, params={"order_id": "nonexistent_order_xyz_000"})
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-006")
def test_get_by_order_id_missing_param():
    """GET /transactions без параметра order_id. Ожидается 400."""
    resp = get_request(BASE_URL)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-007")
def test_get_transaction_no_auth():
    """GET /{id} без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    resp = requests.get(url, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-008")
def test_get_transaction_invalid_signature(payin_transaction_id):
    """GET /{id} по реальному ID с подписью от другого timestamp. Ожидается 401 или 403."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    ts_header = str(int(time.time()))
    ts_signed = str(int(time.time()) - 1)  # подпись от другого timestamp — формат верный, значение нет
    sig = calc_signature(TERMINAL_ID, ts_signed)
    headers = {
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       sig,
        "Api-Timestamp":       ts_header,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-009")
def test_get_transaction_missing_terminal_id():
    """GET /{id} без заголовка Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Signature": "0" * 64,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-010")
def test_get_transaction_missing_timestamp():
    """GET /{id} без заголовка Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ПРОВЕРКА ПОЛЕЙ ОТВЕТА
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-011")
def test_get_transaction_type_is_payin(payin_transaction_id):
    """GET /{id} — поле type в ответе должно быть 'payin'."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("type") == "payin", f"Expected type='payin', got {data.get('type')!r}"


@pytest.mark.tcid("GT-012")
def test_get_transaction_financial_data_fields(payin_transaction_id):
    """GET /{id} — financial_data содержит amount (int) и currency (3 буквы)."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    fd = resp.json().get("financial_data", {})
    assert isinstance(fd.get("amount"), int), f"amount must be int, got {fd.get('amount')!r}"
    currency = fd.get("currency", "")
    assert isinstance(currency, str) and len(currency) == 3, f"currency must be 3-char, got {currency!r}"


@pytest.mark.tcid("GT-013")
def test_get_transaction_merchant_data_order_id(payin_transaction_id):
    """GET /{id} — merchant_data.order_id присутствует и является непустой строкой."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    md = resp.json().get("merchant_data", {})
    assert isinstance(md.get("order_id"), str) and md["order_id"], "order_id must be non-empty string"


@pytest.mark.tcid("GT-014")
def test_get_transaction_created_at_iso8601(payin_transaction_id):
    """GET /{id} — поле created_at валидно как ISO 8601."""
    from datetime import datetime
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    created_at = resp.json().get("created_at", "")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pytest.fail(f"created_at не является ISO 8601: {created_at!r}")


@pytest.mark.tcid("GT-015")
def test_get_transaction_status_is_valid(payin_transaction_id):
    """GET /{id} — поле status принадлежит допустимому набору значений."""
    _valid_statuses = {"completed", "authorized", "processing", "waiting_action",
                       "cancelled", "rejected", "refunded"}
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    status = resp.json().get("status")
    assert status in _valid_statuses, f"Неожиданный status: {status!r}"


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — ПАРАМЕТРЫ ЗАПРОСА
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-016")
def test_get_by_order_id_empty_value():
    """GET ?order_id= (пустая строка). Ожидается 400."""
    resp = get_request(BASE_URL, params={"order_id": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-017")
def test_get_transaction_non_numeric_id():
    """GET /transactions/not-a-number — не числовой ID. Ожидается 404 (роутер возвращает не-JSON)."""
    url = f"{BASE_URL}/not-a-valid-id"
    resp = get_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("GT-018")
def test_get_by_order_id_list_structure(payin_transaction_id):
    """GET ?order_id= — каждый элемент массива содержит transaction_id и status."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list) and len(data) > 0, "Expected non-empty list"
    for item in data:
        assert "transaction_id" in item, f"Missing transaction_id in item: {item}"
        assert "status" in item, f"Missing status in item: {item}"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (GT-019 … GT-030)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-019")
def test_get_by_id_raw_pan_not_in_response(payin_transaction_id):
    """GET /{id} — открытый PAN карты не должен присутствовать в ответе."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    assert CARD_DETAILS["pan"] not in resp.text, "Raw PAN exposed in GET response"


@pytest.mark.tcid("GT-020")
def test_get_by_id_cvv_not_in_response(payin_transaction_id):
    """GET /{id} — CVV карты не должен присутствовать в ответе."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    assert CARD_DETAILS["cvv"] not in resp.text, "CVV exposed in GET response"


@pytest.mark.tcid("GT-021")
def test_get_by_id_masked_pan_format(payin_transaction_id):
    """GET /{id} — sender_info.masked_pan содержит маску (* или X)."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    sender = resp.json().get("transaction_data", {}).get("sender_info", {})
    if "masked_pan" in sender:
        assert any(c in sender["masked_pan"] for c in ("*", "X")), \
            f"masked_pan не маскирован: {sender['masked_pan']}"


@pytest.mark.tcid("GT-022")
def test_get_by_order_id_response_is_array(payin_transaction_id):
    """GET ?order_id= — ответ всегда список, даже если одна транзакция."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list), "Ответ должен быть массивом"


@pytest.mark.tcid("GT-023")
def test_get_by_id_transaction_id_is_integer(payin_transaction_id):
    """GET /{id} — transaction_id в ответе является целым числом."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    assert isinstance(resp.json()["transaction_id"], int), "transaction_id должен быть int"


@pytest.mark.tcid("GT-024")
def test_get_by_id_zero_id_returns_404():
    """GET /transactions/0 — нулевой ID. Ожидается 400 или 404."""
    url = f"{BASE_URL}/0"
    resp = get_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-025")
def test_get_transaction_content_type_is_json(payin_transaction_id):
    """GET /{id} — Content-Type ответа содержит application/json."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


@pytest.mark.tcid("GT-026")
def test_get_by_order_id_each_item_has_created_at():
    """GET ?order_id= — каждый элемент массива содержит created_at."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200
    for item in resp.json():
        assert "created_at" in item, f"created_at отсутствует в item: {item}"


@pytest.mark.tcid("GT-027")
def test_get_by_order_id_transaction_data_has_method():
    """GET ?order_id= — transaction_data.method присутствует в каждом элементе."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200
    for item in resp.json():
        td = item.get("transaction_data", {})
        assert "method" in td, f"method отсутствует в transaction_data: {td}"


@pytest.mark.tcid("GT-028")
def test_get_transaction_invalid_signature_for_get():
    """GET /merchant/balance с подписью, посчитанной как POST (с телом). Ожидается 401/403."""
    timestamp = str(int(time.time()))
    wrong_sig = _sign(TERMINAL_ID, timestamp, "fakebody")
    headers = {
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       wrong_sig,
        "Api-Timestamp":       timestamp,
    }
    resp = requests.get(MERCHANT_BALANCE_URL, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-029")
def test_get_by_id_very_large_id():
    """GET /transactions/99999999999999999999 — очень большой ID. Ожидается 400/404."""
    url = f"{BASE_URL}/99999999999999999999"
    resp = get_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-030")
def test_get_by_order_id_special_chars_in_param():
    """GET ?order_id= со спецсимволами в значении параметра. Ожидается 400 или 404."""
    resp = get_request(BASE_URL, params={"order_id": "order<script>alert(1)</script>"})
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"


# ─────────────────────────────────────────────
# СТАТУСЫ ТРАНЗАКЦИЙ (GT-031 … GT-034)
# ─────────────────────────────────────────────
def _assert_redis_status_matches(tid: int, api_status: str) -> None:
    """Проверяет, что статус в Redis совпадает с api_status (если Redis доступен)."""
    redis = query_transaction_from_redis(tid)
    if redis:
        assert redis.get("status") == api_status, (
            f"Redis status mismatch: expected {api_status!r}, got {redis.get('status')!r}"
        )


@pytest.mark.tcid("GT-031")
def test_get_cancelled_transaction_status():
    """GET /{id} — отменённая транзакция имеет status='cancelled', Redis совпадает."""
    oid = gen_order_id("gt_cancelled")
    tid = make_block_payin(oid)
    cancel = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert cancel.status_code in (200, 201), f"Cancel failed: {cancel.text}"
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    api_status = resp.json().get("status")
    assert api_status == "cancelled", f"Expected 'cancelled', got {api_status!r}"
    _assert_redis_status_matches(tid, api_status)


@pytest.mark.tcid("GT-032")
def test_get_authorized_transaction_status():
    """GET /{id} — hold-транзакция (manual capture, до capture) имеет status='authorized', Redis совпадает."""
    tid = make_block_payin(gen_order_id("gt_auth"))
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    api_status = resp.json().get("status")
    assert api_status == "authorized", f"Expected 'authorized', got {api_status!r}"
    _assert_redis_status_matches(tid, api_status)


@pytest.mark.tcid("GT-033")
def test_get_refunded_transaction_status():
    """GET /{id} — полностью возвращённая транзакция имеет status='refunded'/'completed', Redis совпадает."""
    oid = gen_order_id("gt_refunded")
    tid = make_completed_payin(oid)
    refund = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
    })
    assert refund.status_code in (200, 201), f"Refund failed: {refund.text}"
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    api_status = resp.json().get("status")
    assert api_status in ("refunded", "completed"), \
        f"Expected 'refunded' or 'completed', got {api_status!r}"
    _assert_redis_status_matches(tid, api_status)


@pytest.mark.tcid("GT-034")
def test_get_payout_transaction_type():
    """GET /{id} — payout-транзакция имеет type='payout', Redis совпадает."""
    body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("gt_payout")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": {"pan": "4111111111111111", "holder": "JOHN DOE"}},
    }
    payout = post_transaction(body)
    assert payout.status_code == 201, f"Payout creation failed: {payout.text}"
    tid = payout.json()["transaction_id"]
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("type") == "payout", f"Expected type='payout', got {data.get('type')!r}"
    assert_transaction_response(data)
    _assert_redis_status_matches(tid, data.get("status"))


# ─────────────────────────────────────────────
# АУТЕНТИФИКАЦИЯ: ГРАНИЧНЫЕ СЛУЧАИ (GT-035 … GT-038)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-035")
def test_get_transaction_missing_signature():
    """GET /{id} без заголовка Api-Signature. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-036")
def test_get_transaction_timestamp_too_old():
    """GET /{id} с Api-Timestamp старше 5 минут (now - 400 сек). Ожидается 4xx."""
    url = f"{BASE_URL}/000000000000"
    old_ts = str(int(time.time()) - 400)
    sig = _sign(TERMINAL_ID, old_ts)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": old_ts,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx (InvalidTimestamp), got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-037")
def test_get_transaction_timestamp_in_future():
    """GET /{id} с Api-Timestamp в будущем больше 5 минут (now + 400 сек). Ожидается 4xx."""
    url = f"{BASE_URL}/000000000000"
    future_ts = str(int(time.time()) + 400)
    sig = _sign(TERMINAL_ID, future_ts)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": future_ts,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx (InvalidTimestamp), got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-038")
def test_get_transaction_unknown_terminal_id():
    """GET /{id} с корректно подписанным запросом, но несуществующим Terminal-ID. Ожидается 4xx."""
    url = f"{BASE_URL}/000000000000"
    unknown_tid = "999999"
    ts = str(int(time.time()))
    sig = _sign(unknown_tid, ts)
    headers = {
        "Api-Terminal-ID": unknown_tid,
        "Api-Signature": sig,
        "Api-Timestamp": ts,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403, 404), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ФОРМАТ ОТВЕТА (GT-039)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-039")
def test_get_transaction_created_at_utc_z_format(payin_transaction_id):
    """GET /{id} — created_at должен строго соответствовать формату '%Y-%m-%dT%H:%M:%SZ' (UTC, суффикс Z)."""
    import re
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    created_at = resp.json().get("created_at", "")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at), \
        f"created_at не соответствует формату '%Y-%m-%dT%H:%M:%SZ': {created_at!r}"


# ─────────────────────────────────────────────
# СТАТУС: processing (GT-040)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-040")
def test_get_processing_status_no_extra_fields():
    """GET /{id} — статус processing не содержит transaction_data, action, rejected_data, available_amount.
    Карта 4242424242424242 (async, non-3DS): NEW->PENDING->(CHARGED|REJECTED), задержка = сумма в RUB (5 сек).
    Гарантированное окно в 5 секунд позволяет надёжно поймать статус processing."""
    oid = gen_order_id("gt_processing")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 5, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_ASYNC},
    }
    create_resp = post_transaction(body)
    assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
    tid = create_resp.json()["transaction_id"]
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    if data.get("status") != "processing":
        pytest.skip(f"Транзакция уже покинула processing: {data.get('status')!r}")
    assert not data.get("transaction_data"), "processing не должен содержать transaction_data"
    assert "action" not in data, "processing не должен содержать action"
    assert "rejected_data" not in data, "processing не должен содержать rejected_data"
    fd = data.get("financial_data", {})
    assert fd.get("available_amount") is None, "processing не должен содержать ненулевой available_amount"


# ─────────────────────────────────────────────
# ПОЛЯ ТЕРМИНАЛЬНЫХ СТАТУСОВ (GT-041 … GT-045)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-041")
def test_get_completed_transaction_mode_is_live(payin_transaction_id):
    """GET /{id} — transaction_data.mode = 'live' на препроде."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    data = resp.json()
    if data.get("status") not in ("completed", "authorized"):
        pytest.skip(f"Транзакция не в completed/authorized: {data.get('status')!r}")
    td = data.get("transaction_data", {}) or {}
    assert td.get("mode") == "live", f"Expected mode='live', got {td.get('mode')!r}"


@pytest.mark.tcid("GT-042")
def test_get_authorized_contains_transaction_data():
    """GET /{id} — authorized-транзакция содержит непустой transaction_data."""
    tid = make_block_payin(gen_order_id("gt_auth_td"))
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "authorized", f"Expected 'authorized', got {data.get('status')!r}"
    td = data.get("transaction_data")
    assert isinstance(td, dict) and td, \
        f"transaction_data должен быть непустым dict для authorized, got {td!r}"


@pytest.mark.tcid("GT-043")
def test_get_cancelled_contains_transaction_data():
    """GET /{id} — cancelled-транзакция содержит непустой transaction_data."""
    oid = gen_order_id("gt_cancel_td")
    tid = make_block_payin(oid)
    cancel = post_operation(tid, "cancel", make_op_body(oid))
    assert cancel.status_code in (200, 201), f"Cancel failed: {cancel.text}"
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "cancelled", f"Expected 'cancelled', got {data.get('status')!r}"
    td = data.get("transaction_data")
    assert isinstance(td, dict) and td, \
        f"transaction_data должен быть непустым dict для cancelled, got {td!r}"


@pytest.mark.tcid("GT-044")
def test_get_refunded_contains_transaction_data():
    """GET /{id} — refunded-транзакция содержит непустой transaction_data."""
    oid = gen_order_id("gt_refund_td")
    tid = make_completed_payin(oid)
    refund = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
    })
    assert refund.status_code in (200, 201), f"Refund failed: {refund.text}"
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("refunded", "completed"), \
        f"Expected 'refunded'/'completed', got {data.get('status')!r}"
    td = data.get("transaction_data")
    assert isinstance(td, dict) and td, \
        f"transaction_data должен быть непустым dict для refunded, got {td!r}"


_REJECT_CARD = {**CARD_DETAILS, "expiry_month": "08"}


@pytest.mark.tcid("GT-045")
def test_get_rejected_transaction_has_rejected_data():
    """GET /{id} — rejected-транзакция содержит transaction_data и rejected_data с кодом из диапазона 1001–1028."""
    oid = gen_order_id("gt_rejected")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _REJECT_CARD},
    }
    create_resp = post_transaction(body)
    assert create_resp.status_code in (200, 201, 422), f"Create failed: {create_resp.text}"
    if create_resp.status_code == 422:
        pytest.skip("Карта отклонена синхронно при создании, опрос статуса невозможен")
    tid = create_resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    resp = get_request(f"{BASE_URL}/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "rejected", f"Expected 'rejected', got {data.get('status')!r}"
    td = data.get("transaction_data")
    assert isinstance(td, dict) and td, \
        f"transaction_data должен быть непустым dict для rejected, got {td!r}"
    rd = data.get("rejected_data")
    assert isinstance(rd, dict), f"rejected_data должен быть dict для rejected, got {rd!r}"
    assert rd.get("code"), f"rejected_data.code должен быть непустым, got {rd.get('code')!r}"
    assert rd.get("message"), f"rejected_data.message должен быть непустым, got {rd.get('message')!r}"


# ─────────────────────────────────────────────
# financial_data.available_amount (GT-046 … GT-047)
# ─────────────────────────────────────────────
_REFUND_POLL_ATTEMPTS = 8
_REFUND_POLL_DELAY    = 2.0


def _poll_financial_data(tid: int) -> dict:
    """Поллим GET /{tid} пока статус не выйдет из processing/refunded."""
    for _ in range(_REFUND_POLL_ATTEMPTS):
        time.sleep(_REFUND_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code == 200:
            return r.json().get("financial_data", {})
    return get_request(f"{BASE_URL}/{tid}").json().get("financial_data", {})


@pytest.mark.tcid("GT-046")
def test_get_available_amount_after_partial_refund():
    """GET /{id} — financial_data.available_amount корректен после частичного рефанда."""
    oid = gen_order_id("gt_partial_refund")
    tid = make_completed_payin(oid)  # amount = 10000
    refund = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 3000, "currency": "RUB"},
    })
    assert refund.status_code in (200, 201), f"Refund failed: {refund.text}"
    fd = _poll_financial_data(tid)
    assert "available_amount" in fd, \
        "financial_data.available_amount должен присутствовать после частичного рефанда"
    assert isinstance(fd["available_amount"], int), \
        f"available_amount должен быть int, got {fd['available_amount']!r}"
    assert fd["available_amount"] == 7000, \
        f"Ожидалось available_amount=7000 (10000 - 3000), got {fd['available_amount']}"


@pytest.mark.tcid("GT-047")
def test_get_no_available_amount_after_full_refund():
    """GET /{id} — financial_data.available_amount отсутствует после полного рефанда."""
    oid = gen_order_id("gt_full_refund_avail")
    tid = make_completed_payin(oid)  # amount = 10000
    refund = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
    })
    assert refund.status_code in (200, 201), f"Refund failed: {refund.text}"
    fd = _poll_financial_data(tid)
    assert fd.get("available_amount") is None, \
        f"available_amount не должен быть ненулевым при нулевом остатке, got {fd.get('available_amount')!r}"


# ─────────────────────────────────────────────
# amount в минорных единицах (GT-048)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-048")
def test_get_amount_in_minor_units(payin_transaction_id):
    """GET /{id} — financial_data.amount отражает сумму в минорных единицах: 100.00 RUB → 10000."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    fd = resp.json().get("financial_data", {})
    assert fd.get("amount") == 10000, \
        f"Ожидалось amount=10000 (100.00 RUB в копейках), got {fd.get('amount')!r}"
    assert fd.get("currency") == "RUB", f"Ожидалось currency='RUB', got {fd.get('currency')!r}"


# ─────────────────────────────────────────────
# customer_data (GT-049)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-049")
def test_get_customer_data_echo_in_terminal_status(payin_transaction_id):
    """GET /{id} — customer_data присутствует в терминальном статусе и эхоирует переданный contact_info."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    data = resp.json()
    status = data.get("status")
    if status not in ("completed", "authorized", "cancelled", "refunded", "rejected"):
        pytest.skip(f"Транзакция не в терминальном статусе: {status!r}")
    assert "customer_data" in data, "customer_data должен присутствовать в терминальном статусе"
    cd = data.get("customer_data")
    if cd is None:
        pytest.skip("customer_data = null, эхо-проверка невозможна")
    ci = (cd or {}).get("contact_info", {}) or {}
    expected = CUSTOMER_DATA["contact_info"]
    assert ci.get("email") == expected["email"], \
        f"contact_info.email: ожидалось {expected['email']!r}, got {ci.get('email')!r}"
    assert ci.get("phone") == expected["phone"], \
        f"contact_info.phone: ожидалось {expected['phone']!r}, got {ci.get('phone')!r}"


# ─────────────────────────────────────────────
# Несколько транзакций по одному order_id (GT-050)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-050")
def test_get_by_order_id_returns_all_transactions():
    """GET ?order_id= — возвращает все транзакции с указанным order_id, если их несколько."""
    shared_oid = gen_order_id("gt_multi_tx")
    tx_body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": shared_oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    r1 = post_transaction(tx_body)
    assert r1.status_code == 201, f"First transaction failed: {r1.text}"
    r2 = post_transaction(tx_body)
    assert r2.status_code == 201, f"Second transaction failed: {r2.text}"
    tid1 = r1.json()["transaction_id"]
    tid2 = r2.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    resp = get_request(BASE_URL, params={"order_id": shared_oid})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list), "Ответ должен быть массивом"
    found_ids = {item.get("transaction_id") for item in data}
    assert tid1 in found_ids, f"transaction_id {tid1} не найден в ответе: {found_ids}"
    assert tid2 in found_ids, f"transaction_id {tid2} не найден в ответе: {found_ids}"


# ─────────────────────────────────────────────
# GET /api/v1/transactions — ошибки по order_id (TC-REST-400..402)
# ─────────────────────────────────────────────

def _get_error_code(resp) -> str | None:
    body = resp.json()
    return body.get("error", {}).get("code") or body.get("code")


@pytest.mark.tcid("TC-REST-400")
def test_get_missing_order_id():
    """GET без параметра ?order_id=. Ожидается 400.
    API возвращает code='invalid_order_id' (отсутствие параметра обрабатывается как невалидный)."""
    resp = requests.get(BASE_URL, headers=make_get_headers(TERMINAL_ID), timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
    assert _get_error_code(resp) in ("missing_order_id", "invalid_order_id", "invalid_field"), \
        f"Unexpected error code: {_get_error_code(resp)!r}"


@pytest.mark.tcid("TC-REST-401")
def test_get_invalid_order_id():
    """GET с невалидным order_id (спецсимволы). Ожидается 400, code='invalid_order_id'."""
    resp = requests.get(
        BASE_URL,
        params={"order_id": "<invalid!@#$%^&*()>"},
        headers=make_get_headers(TERMINAL_ID),
        timeout=30,
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert _get_error_code(resp) == "invalid_order_id", \
        f"Expected 'invalid_order_id', got {_get_error_code(resp)!r}"


@pytest.mark.tcid("TC-REST-402")
def test_get_order_not_found():
    """GET с корректным форматом order_id, которого нет в базе. Ожидается 404, code='order_not_found'."""
    import uuid as _uuid
    resp = requests.get(
        BASE_URL,
        params={"order_id": f"nonexistent_{_uuid.uuid4().hex}"},
        headers=make_get_headers(TERMINAL_ID),
        timeout=30,
    )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert _get_error_code(resp) == "order_not_found", \
        f"Expected 'order_not_found', got {_get_error_code(resp)!r}"


# ─────────────────────────────────────────────
# GET /api/v1/transactions/<transaction_id> — ошибки (TC-REST-410..411)
# ─────────────────────────────────────────────

@pytest.mark.tcid("TC-REST-410")
def test_get_invalid_transaction_id():
    """GET с transaction_id в неверном формате (не числовой). Ожидается 400 или 404, code='invalid_transaction_id'."""
    url = f"{BASE_URL}/not-a-valid-id"
    resp = requests.get(url, headers=make_get_headers(TERMINAL_ID), timeout=30)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert _get_error_code(resp) == "invalid_transaction_id", \
        f"Expected 'invalid_transaction_id', got {_get_error_code(resp)!r}"


@pytest.mark.tcid("TC-REST-411")
def test_get_transaction_not_found():
    """GET с числовым transaction_id, которого нет в базе. Ожидается 404, code='transaction_not_found'."""
    url = f"{BASE_URL}/9999999999"
    resp = requests.get(url, headers=make_get_headers(TERMINAL_ID), timeout=30)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert _get_error_code(resp) == "transaction_not_found", \
        f"Expected 'transaction_not_found', got {_get_error_code(resp)!r}"

