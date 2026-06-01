"""
Тесты комбинаций block/rebill для POST /api/v1/transactions.

CVV 999 (≥ 600) → без 3DS.
recurrent_token: transaction_data.recurrent_token в GET /{id}.

КЕЙСЫ:
  RB-001: auto payin → auto rebill
  RB-002: auto payin → manual rebill + capture
  RB-003: manual payin + capture → auto rebill
  RB-004: manual payin + capture → manual rebill + capture
  RB-005: manual payin без capture → авто-отмена по таймауту (slow)
  RB-006: частичный capture (5000 из 10000)
  RB-007: повторный capture после полного → 409
  RB-008: capture несуществующей транзакции → 404
  RB-017: rebill с токеном другого терминала → 403/404
  RB-018: is_recurrent=false → withdrawal_token (не recurrent_token)
  RB-019: без is_recurrent (default false) → withdrawal_token
  RB-020: цепочка rebill (token1 → token2 → rebill)

ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ:
  RB-010: идемпотентность — повторный запрос с тем же ключом
  RB-011: recurrent_token является UUID v4
  RB-012: токен другого сервиса → 404/422
  RB-013: capture суммы больше авторизованной → 4xx
  RB-014: capture одностадийной транзакции → 409
  RB-015: rebill с несуществующим токеном → 404/422
  RB-016: is_recurrent=false → recurrent_token отсутствует
"""
import re
import time
import uuid

import pytest

import os

from conftest import (
    post_transaction,
    post_operation,
    get_request,
    BASE_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    SETUP_DELAY,
    TERMINAL_ID,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

# Второй терминал для кейса RB-017 (rebill чужого токена).
# Задать через TERMINAL_ID_2 в .env или terminals.json.
_TERMINAL_ID_2 = os.environ.get("TERMINAL_ID_2", "")

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


# ─────────────────────────────────────────────
# КЕЙС 5: manual payin без capture → авто-отмена
# ─────────────────────────────────────────────
_AUTO_CANCEL_TIMEOUT = 5 * 60  # 5 минут
_AUTO_CANCEL_POLL    = 30      # опрос каждые 30 сек


@pytest.mark.tcid("RB-005")
@pytest.mark.slow
def test_manual_payin_auto_cancel_on_timeout():
    """Manual payin без capture → статус cancelled по истечении таймаута (~5 мин)."""
    tid, oid, _ = _payin_card("manual", is_recurrent=False)
    _assert_status(tid, "authorized")

    elapsed = 0
    while elapsed < _AUTO_CANCEL_TIMEOUT:
        time.sleep(_AUTO_CANCEL_POLL)
        elapsed += _AUTO_CANCEL_POLL
        poll = get_request(f"{BASE_URL}/{tid}")
        status = poll.json().get("status")
        if status == "cancelled":
            return
        if status not in ("authorized", "processing"):
            pytest.fail(f"Unexpected status during wait: {status!r}")

    pytest.fail(f"Transaction {tid} did not auto-cancel within {_AUTO_CANCEL_TIMEOUT}s")


# ─────────────────────────────────────────────
# КЕЙС 6: частичный capture
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-006")
def test_partial_capture():
    """Partial capture 5000 из 10000 → completed, остаток разблокирован."""
    tid, oid, _ = _payin_card("manual", is_recurrent=False)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": 5000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Partial capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "completed")


# ─────────────────────────────────────────────
# КЕЙС 7: повторный capture после полного
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-007")
def test_repeated_capture_after_full_capture():
    """Повторный capture после полного → 409 (конфликт)."""
    tid, oid, _ = _payin_card("manual", is_recurrent=False)
    _assert_status(tid, "authorized")
    _capture(tid, oid)
    _assert_status(tid, "completed")

    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    })
    assert resp.status_code == 409, \
        f"Expected 409 for repeated capture, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КЕЙС 8: capture несуществующей транзакции
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-008")
def test_capture_nonexistent_transaction():
    """Capture для несуществующего transaction_id → 404."""
    resp = post_operation("9999999999", "capture", {
        "merchant_data":  {"order_id": "order_nonexistent"},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    })
    assert resp.status_code == 404, \
        f"Expected 404 for nonexistent transaction, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КЕЙС 11: rebill с токеном другого терминала
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-017")
def test_rebill_with_token_from_different_terminal():
    """Rebill токеном от первого терминала через второй → 403 или 404."""
    if not _TERMINAL_ID_2:
        pytest.skip("TERMINAL_ID_2 не задан — настроить в .env для этого кейса")

    # Шаг 1: получаем токен от первого терминала
    _, _, token = _payin_card("auto", is_recurrent=True)
    assert token, "recurrent_token must be present"

    # Шаг 2: пытаемся использовать этот токен от второго терминала
    oid  = gen_order_id("rb_other_terminal")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": token}},
    }
    resp = post_transaction(body, terminal_id=_TERMINAL_ID_2)
    assert resp.status_code in (400, 403, 404, 422), \
        f"Expected 4xx for cross-terminal token, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КЕЙС 12: is_recurrent=false → withdrawal_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-018")
def test_auto_payin_is_recurrent_false_gives_withdrawal_token():
    """Auto payin с is_recurrent=false → withdrawal_token присутствует, recurrent_token отсутствует."""
    tid, _, _ = _payin_card("auto", is_recurrent=False)
    _assert_status(tid, "completed")
    poll = get_request(f"{BASE_URL}/{tid}")
    td   = poll.json().get("transaction_data") or {}
    assert td.get("withdrawal_token"), \
        f"withdrawal_token должен присутствовать при is_recurrent=False: {td}"
    assert td.get("recurrent_token") is None, \
        f"recurrent_token не должен присутствовать при is_recurrent=False: {td}"


# ─────────────────────────────────────────────
# КЕЙС 13: без is_recurrent (default false) → withdrawal_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-019")
def test_auto_payin_without_is_recurrent_gives_withdrawal_token():
    """Auto payin без is_recurrent (default false) → withdrawal_token, нет recurrent_token."""
    oid  = gen_order_id("rb_no_recurrent")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Create failed: {resp.status_code}: {resp.text}"
    tid = resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "completed")
    poll = get_request(f"{BASE_URL}/{tid}")
    td   = poll.json().get("transaction_data") or {}
    assert td.get("withdrawal_token"), \
        f"withdrawal_token должен присутствовать без is_recurrent: {td}"
    assert td.get("recurrent_token") is None, \
        f"recurrent_token не должен присутствовать без is_recurrent: {td}"


# ─────────────────────────────────────────────
# КЕЙС 14: цепочка rebill (token1 → token2 → rebill)
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-020")
def test_rebill_chain():
    """Цепочка: родитель (is_recurrent=true) → token1; rebill1 (is_recurrent=true) → token2; rebill2 с token2."""
    # Шаг 1: родительская транзакция → token1
    _, _, token1 = _payin_card("auto", is_recurrent=True)
    assert token1, "token1 must be present"

    # Шаг 2: rebill с is_recurrent=true → token2
    oid2  = gen_order_id("rb_chain_2")
    body2 = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid2},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": token1}},
    }
    r2 = post_transaction(body2)
    assert r2.status_code == 201, f"rebill1 failed: {r2.status_code}: {r2.text}"
    tid2 = r2.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    _assert_status(tid2, "completed")

    poll2  = get_request(f"{BASE_URL}/{tid2}")
    token2 = (poll2.json().get("transaction_data") or {}).get("recurrent_token")
    assert token2, "token2 must be present after rebill with is_recurrent=True"

    # Шаг 3: rebill с token2
    tid3, _ = _rebill(token2, "auto")
    _assert_status(tid3, "completed")
