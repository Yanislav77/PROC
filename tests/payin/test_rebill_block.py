"""
Тесты комбинаций block/rebill для POST /api/v1/transactions.

CVV 999 (≥ 600) → без 3DS.
recurrent_token: transaction_data.recurrent_token в GET /{id}.

КЕЙСЫ:
  RB-001: auto-capture payin  → auto rebill
  RB-002: auto-capture payin  → manual rebill + capture
  RB-003: manual payin + capture → auto rebill
  RB-004: manual payin + capture → manual rebill + capture

ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ:
  RB-010: идемпотентность — повторный запрос с тем же ключом
  RB-011: recurrent_token является UUID v4
  RB-012: токен другого сервиса → 404/422
  RB-013: capture суммы больше авторизованной → 422
  RB-014: capture одностадийной транзакции → 409
  RB-015: rebill с несуществующим токеном → 404/422
  RB-016: is_recurrent=false → recurrent_token отсутствует в ответе
"""
import re
import time
import uuid

import pytest

from conftest import (
    post_transaction,
    post_operation,
    get_request,
    BASE_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    SETUP_DELAY,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

_AMOUNT = 10000

_CARD = {
    "pan":          "4111111111111111",
    "holder":       "JOHN DOE",
    "expiry_month": "01",
    "expiry_year":  "29",
    "cvv":          "999",  # ≥ 600 → без 3DS
}

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _payin_card(capture_mode: str, is_recurrent: bool) -> tuple[int, str, str | None]:
    """Создаёт card-payin, поллит статус, возвращает (tid, order_id, recurrent_token|None)."""
    oid  = gen_order_id(f"rb_{capture_mode}")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": is_recurrent, "capture_mode": capture_mode, "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"card payin failed: {resp.status_code}: {resp.text}"
    tid = resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    poll = get_request(f"{BASE_URL}/{tid}")
    assert poll.status_code == 200
    token = (poll.json().get("transaction_data") or {}).get("recurrent_token")
    return tid, oid, token


def _rebill(token: str, capture_mode: str) -> tuple[int, str]:
    """Создаёт rebill по token, возвращает (tid, order_id)."""
    oid  = gen_order_id(f"rb_rebill_{capture_mode}")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": capture_mode, "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": token}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"rebill failed: {resp.status_code}: {resp.text}"
    tid = resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    return tid, oid


def _capture(tid: int, oid: str, amount: int = _AMOUNT):
    body = {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": amount, "currency": "RUB"},
    }
    resp = post_operation(tid, "capture", body)
    assert resp.status_code in (200, 201), f"capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    return resp


def _assert_status(tid: int, expected: str):
    poll = get_request(f"{BASE_URL}/{tid}")
    assert poll.status_code == 200
    status = poll.json().get("status")
    assert status == expected, f"Expected status={expected!r}, got {status!r}"


# ─────────────────────────────────────────────
# КЕЙС 1: auto → auto rebill
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-001")
def test_auto_payin_auto_rebill():
    """Auto-capture payin → auto rebill. Оба завершаются со статусом completed."""
    # Шаг 1: родительская транзакция
    tid_p, oid_p, token = _payin_card("auto", is_recurrent=True)
    assert token, "recurrent_token должен присутствовать при is_recurrent=True"
    _assert_status(tid_p, "completed")

    # Шаг 2: rebill
    tid_r, _ = _rebill(token, "auto")
    _assert_status(tid_r, "completed")


# ─────────────────────────────────────────────
# КЕЙС 2: auto → manual rebill + capture
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-002")
def test_auto_payin_manual_rebill_with_capture():
    """Auto-capture payin → manual rebill (authorized) → capture (completed)."""
    # Шаг 1
    _, _, token = _payin_card("auto", is_recurrent=True)
    assert token

    # Шаг 2: manual rebill → authorized
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    # Шаг 3: capture
    _capture(tid_r, oid_r)
    _assert_status(tid_r, "completed")


# ─────────────────────────────────────────────
# КЕЙС 3: manual + capture → auto rebill
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-003")
def test_manual_payin_capture_auto_rebill():
    """Manual payin (authorized) → capture (completed) → auto rebill (completed)."""
    # Шаг 1
    tid_p, oid_p, token = _payin_card("manual", is_recurrent=True)
    assert token
    _assert_status(tid_p, "authorized")

    # Шаг 2: capture родителя
    _capture(tid_p, oid_p)
    _assert_status(tid_p, "completed")

    # Шаг 3: auto rebill
    tid_r, _ = _rebill(token, "auto")
    _assert_status(tid_r, "completed")


# ─────────────────────────────────────────────
# КЕЙС 4: manual + capture → manual rebill + capture
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-004")
def test_manual_payin_capture_manual_rebill_with_capture():
    """Manual payin → capture → manual rebill (authorized) → capture (completed)."""
    # Шаг 1
    tid_p, oid_p, token = _payin_card("manual", is_recurrent=True)
    assert token
    _assert_status(tid_p, "authorized")

    # Шаг 2: capture родителя
    _capture(tid_p, oid_p)
    _assert_status(tid_p, "completed")

    # Шаг 3: manual rebill → authorized
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    # Шаг 4: capture rebill
    _capture(tid_r, oid_r)
    _assert_status(tid_r, "completed")


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-011")
def test_recurrent_token_is_uuid4():
    """recurrent_token должен быть UUID v4."""
    _, _, token = _payin_card("auto", is_recurrent=True)
    assert token, "recurrent_token отсутствует"
    assert _UUID4_RE.match(token), f"recurrent_token не является UUID v4: {token!r}"


@pytest.mark.tcid("RB-012")
def test_rebill_with_token_from_other_service():
    """Токен другого сервиса (валидный UUID4, но не из этого сервиса) → 404 или 422."""
    fake_token = str(uuid.uuid4())
    oid  = gen_order_id("rb_fake_token")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": fake_token}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404, 422), \
        f"Expected 400/404/422 for foreign token, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RB-013")
def test_capture_amount_exceeds_authorized():
    """Capture суммы больше авторизованной → 422."""
    tid_p, oid_p, _ = _payin_card("manual", is_recurrent=False)
    _assert_status(tid_p, "authorized")
    body = {
        "merchant_data":  {"order_id": oid_p},
        "financial_data": {"amount": _AMOUNT + 1, "currency": "RUB"},
    }
    resp = post_operation(tid_p, "capture", body)
    assert resp.status_code in (400, 409, 422), \
        f"Expected 4xx for over-capture, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RB-014")
def test_capture_auto_capture_transaction():
    """Capture для auto-capture транзакции → 409."""
    tid_p, oid_p, _ = _payin_card("auto", is_recurrent=False)
    _assert_status(tid_p, "completed")
    body = {
        "merchant_data":  {"order_id": oid_p},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    }
    resp = post_operation(tid_p, "capture", body)
    assert resp.status_code == 409, \
        f"Expected 409 for capture of auto-capture transaction, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RB-015")
def test_rebill_nonexistent_token():
    """Rebill с несуществующим токеном → 400, 404 или 422."""
    oid  = gen_order_id("rb_notoken")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": "00000000-0000-4000-8000-000000000000"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404, 422), \
        f"Expected 400/404/422 for nonexistent token, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RB-016")
def test_no_recurrent_token_when_is_recurrent_false():
    """При is_recurrent=false recurrent_token не должен присутствовать в ответе."""
    tid, _, _ = _payin_card("auto", is_recurrent=False)
    _assert_status(tid, "completed")
    poll = get_request(f"{BASE_URL}/{tid}")
    td   = poll.json().get("transaction_data") or {}
    assert td.get("recurrent_token") is None, \
        f"recurrent_token не должен присутствовать при is_recurrent=False, got {td.get('recurrent_token')!r}"


@pytest.mark.tcid("RB-010")
def test_idempotency_same_key_returns_same_result():
    """Повторный запрос с тем же Api-Idempotency-Key → тот же результат (409 дедупликация)."""
    import json
    import requests
    from conftest import calc_signature, TERMINAL_ID

    oid  = gen_order_id("rb_idem")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD},
    }
    raw = json.dumps(body, separators=(",", ":"))
    idem_key = str(uuid.uuid4())

    def _post():
        import time as _t
        ts  = str(int(_t.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        return requests.post(
            f"{BASE_URL}",
            data=raw,
            headers={
                "Content-Type":        "application/json",
                "Api-Terminal-ID":     TERMINAL_ID,
                "Api-Idempotency-Key": idem_key,
                "Api-Signature":       sig,
                "Api-Timestamp":       ts,
            },
            timeout=30,
        )

    r1 = _post()
    assert r1.status_code == 201, f"First request failed: {r1.status_code}: {r1.text}"
    r2 = _post()
    assert r2.status_code in (201, 409), f"Second request: expected 201/409, got {r2.status_code}: {r2.text}"
    if r2.status_code == 201:
        assert r1.json()["transaction_id"] == r2.json()["transaction_id"], \
            "Idempotent requests must return the same transaction_id"
