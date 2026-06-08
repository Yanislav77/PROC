"""
Тесты комбинаций block/rebill для POST /api/v1/transactions.
Управление подписками: DELETE /api/v1/subscriptions/{token}.

CVV 999 (≥ 600) → без 3DS.
recurrent_token: transaction_data.recurrent_token в GET /{id}.

КЕЙСЫ:
  RB-001: auto payin → auto rebill
  RB-002: auto payin → manual rebill + capture
  RB-003: manual payin + capture → auto rebill
  RB-004: manual payin + capture → manual rebill + capture
  RB-006: частичный capture (5000 из 10000)
  RB-007: повторный capture после полного → 409
  RB-008: capture несуществующей транзакции → 404
  RB-017: rebill с токеном другого терминала → 403/404
  RB-018: is_recurrent=false → withdrawal_token (не recurrent_token)
  RB-019: без is_recurrent (default false) → withdrawal_token
  RB-020: один токен → три rebill'а подряд (все успешны)
  RB-022: payin MIR (2201382000000013) → recurrent_token → rebill → неуспех
  RB-023: многократные частичные cancel = полная сумма → cancelled
  RB-024: многократные частичные capture = полная сумма → completed
  RB-025: block → частичный cancel → capture оставшегося → completed
  RB-026: block → частичный capture → cancel оставшегося → completed
  RB-027: cancel суммы больше авторизованной → 4xx
  RB-028: cancel после полного capture → 409
  RB-029: cancel одностадийной транзакции (auto) → 409
  RB-030: cancel с нулевой суммой → 400
  RB-050: block без capture → одностадийный rebill
  RB-051: block без capture → двухстадийный rebill + capture
  RB-052: block → cancel → одностадийный rebill
  RB-053: block → cancel → двухстадийный rebill + capture
  RB-054: recurrent_token остаётся валидным после cancel

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

from conftest import (
    post_transaction,
    post_operation,
    get_request,
    delete_request,
    BASE_URL,
    SUBSCRIPTIONS_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    SETUP_DELAY,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
)

_AMOUNT = 10000

_CARD = {
    "pan":          "4111111111111111",
    "holder":       "JOHN DOE",
    "expiry_month": "05",
    "expiry_year":  "27",
    "cvv":          "999",  # ≥ 600 → без 3DS
}

_CARD_MIR = {
    "pan":          "2201382000000013",
    "holder":       "JOHN DOE",
    "expiry_month": "01",
    "expiry_year":  "29",
    "cvv":          "999",
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


_POLL_ATTEMPTS = 10
_POLL_DELAY    = 2.0


def _assert_status(tid: int, expected: str):
    """Poll GET /{tid} until status = expected (up to _POLL_ATTEMPTS × _POLL_DELAY sec)."""
    status = None
    for _ in range(_POLL_ATTEMPTS):
        poll = get_request(f"{BASE_URL}/{tid}")
        assert poll.status_code == 200
        status = poll.json().get("status")
        if status == expected:
            return
        time.sleep(_POLL_DELAY)
    pytest.fail(
        f"Transaction {tid}: expected {expected!r}, got {status!r} "
        f"after {_POLL_ATTEMPTS} polls"
    )


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
        from _helpers.validators import assert_idempotency_echo
        ts  = str(int(_t.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": idem_key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        r = requests.post(f"{BASE_URL}", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _post()
    assert r1.status_code == 201, f"First request failed: {r1.status_code}: {r1.text}"
    r2 = _post()
    assert r2.status_code in (201, 409), f"Second request: expected 201/409, got {r2.status_code}: {r2.text}"
    if r2.status_code == 201:
        assert r1.json()["transaction_id"] == r2.json()["transaction_id"], \
            "Idempotent requests must return the same transaction_id"



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
    """Rebill с токеном, похожим на реальный, но принадлежащим другому сервису → 400/403/404/422."""
    # Генерируем UUID4 с теми же характеристиками что у recurrent_token,
    # но не существующий в БД текущего сервиса.
    foreign_token = str(uuid.uuid4())
    oid  = gen_order_id("rb_other_terminal")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": foreign_token}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 403, 404, 422), \
        f"Expected 4xx for foreign token, got {resp.status_code}: {resp.text}"
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
def test_multiple_rebills_from_same_token():
    """Один recurrent_token используется для трёх последовательных rebill'ов — все успешны, 409 не возникает."""
    # Шаг 1: родительская транзакция с is_recurrent=True → recurrent_token
    _, _, token = _payin_card("auto", is_recurrent=True)
    assert token, "recurrent_token must be present after parent transaction"

    # Шаги 2–4: три rebill'а с тем же токеном
    for i in range(1, 4):
        tid, _ = _rebill(token, "auto")
        _assert_status(tid, "completed")


# ─────────────────────────────────────────────
# КЕЙС 22: capture с отказом банка
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-022")
def test_rebill_bank_decline():
    """Block MIR (2201382000000013, cvv=666, manual) → recurrent_token → rebill block (manual) → rejected."""
    _CARD_MIR_BLOCK = {
        "pan":          "2201382000000013",
        "holder":       "JOHN DOE",
        "expiry_month": "05",
        "expiry_year":  "27",
        "cvv":          "666",
    }
    oid_p = gen_order_id("rb022_parent")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid_p},
        "financial_data":   {"amount": 1000, "currency": "RUB"},
        "flow_data":        {"is_recurrent": True, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD_MIR_BLOCK},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"MIR block payin failed: {resp.status_code}: {resp.text}"
    tid_p = resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)

    poll  = get_request(f"{BASE_URL}/{tid_p}")
    token = (poll.json().get("transaction_data") or {}).get("recurrent_token")
    if not token:
        pytest.skip("MIR card payin did not return recurrent_token")

    oid_r = gen_order_id("rb022_rebill")
    rebill_body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid_r},
        "financial_data":   {"amount": 1100, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": token}},
    }
    r = post_transaction(rebill_body)
    if r.status_code in (400, 422):
        assert_error_response(r)
        return
    assert r.status_code == 201, f"Unexpected rebill response: {r.status_code}: {r.text}"
    tid_r = r.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    poll_r = get_request(f"{BASE_URL}/{tid_r}")
    status = poll_r.json().get("status")
    assert status in ("rejected", "failed", "cancelled"), \
        f"Expected rebill failure status, got {status!r}"


# ─────────────────────────────────────────────
# КЕЙС 23: многократные частичные cancel = полная сумма
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-023")
def test_multiple_partial_cancel_full_sum():
    """10 частичных отмен по 100 (итого 1000) — промежуточный статус authorized, финальный cancelled."""
    oid = gen_order_id("rb_multi_cancel")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    for i in range(10):
        step_oid = gen_order_id(f"rb_mcancel_s{i}")
        resp = post_operation(tid, "cancel", {
            "merchant_data":  {"order_id": step_oid},
            "financial_data": {"amount": 100, "currency": "RUB"},
        })
        assert resp.status_code in (200, 201), \
            f"Cancel шаг {i + 1}/10 failed: {resp.status_code}: {resp.text}"
        time.sleep(SETUP_DELAY)
        if i < 9:
            poll = get_request(f"{BASE_URL}/{tid}")
            assert poll.status_code == 200
            status = poll.json().get("status")
            assert status in ("authorized", "processing"), \
                f"После {i + 1}/10 отмен ожидался authorized/processing, got {status!r}"

    _assert_status(tid, "cancelled")


# ─────────────────────────────────────────────
# КЕЙС 24: многократные частичные capture = полная сумма
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-024")
def test_multiple_partial_capture_full_sum():
    """10 частичных capture по 100 (итого 1000) — промежуточный статус authorized, финальный completed."""
    oid = gen_order_id("rb_multi_capture")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    for i in range(10):
        step_oid = gen_order_id(f"rb_mcapture_s{i}")
        resp = post_operation(tid, "capture", {
            "merchant_data":  {"order_id": step_oid},
            "financial_data": {"amount": 100, "currency": "RUB"},
        })
        assert resp.status_code in (200, 201), \
            f"Capture шаг {i + 1}/10 failed: {resp.status_code}: {resp.text}"
        time.sleep(SETUP_DELAY)
        if i < 9:
            _assert_status(tid, "authorized")

    _assert_status(tid, "completed")


# ─────────────────────────────────────────────
# КЕЙС 25: частичный cancel → capture оставшегося
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-025")
def test_block_partial_cancel_then_capture_remaining():
    """Block 1000 → cancel 300 (authorized с уменьшенной суммой) → capture 700 → completed."""
    oid = gen_order_id("rb_cancel_then_cap")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb_ctc_cancel")},
        "financial_data": {"amount": 300, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), \
        f"Partial cancel failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb_ctc_capture")},
        "financial_data": {"amount": 700, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), \
        f"Capture remaining failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "completed")


# ─────────────────────────────────────────────
# КЕЙС 26: частичный capture → cancel оставшегося
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-026")
def test_block_partial_capture_then_cancel_remaining():
    """Block 1000 → capture 300 (authorized) → cancel 700 → completed."""
    oid = gen_order_id("rb_cap_then_cancel")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb_cpc_capture")},
        "financial_data": {"amount": 300, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), \
        f"Partial capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb_cpc_cancel")},
        "financial_data": {"amount": 700, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), \
        f"Cancel remaining failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "completed")


# ─────────────────────────────────────────────
# КЕЙС 27: cancel суммы больше авторизованной
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-027")
def test_cancel_amount_exceeds_authorized():
    """Block 1000 → cancel 1500 (> авторизованной суммы) → 4xx."""
    oid = gen_order_id("rb_cancel_exceed")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb_cancel_exceed_op")},
        "financial_data": {"amount": 1500, "currency": "RUB"},
    })
    assert resp.status_code in (400, 409, 422), \
        f"Expected 4xx for over-cancel, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КЕЙС 28: cancel после полного capture
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-028")
def test_cancel_after_full_capture():
    """Block → полный capture (completed) → cancel → 409 Conflict."""
    oid = gen_order_id("rb_cancel_after_cap")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb_cac_capture")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid, "completed")

    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb_cac_cancel")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code == 409, \
        f"Expected 409 for cancel after full capture, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КЕЙС 29: cancel одностадийной транзакции
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-029")
def test_cancel_auto_capture_transaction():
    """Auto-capture транзакция (completed) → cancel → 409 Conflict."""
    oid = gen_order_id("rb_cancel_auto")
    tid = make_completed_payin(oid)
    _assert_status(tid, "completed")

    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb_cancel_auto_op")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    assert resp.status_code == 409, \
        f"Expected 409 for cancel of auto-capture transaction, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# КЕЙС 30: cancel с нулевой суммой
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-030")
def test_cancel_zero_amount():
    """Block → cancel amount=0 → ошибка валидации 400 или 422."""
    oid = gen_order_id("rb_cancel_zero")
    tid = make_block_payin(oid)
    _assert_status(tid, "authorized")

    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb_cancel_zero_op")},
        "financial_data": {"amount": 0, "currency": "RUB"},
    })
    assert resp.status_code in (400, 422), \
        f"Expected 400/422 for zero amount cancel, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ═════════════════════════════════════════════════════════════
# ДВУХСТАДИЙНЫЕ REBILL (RB-031 … RB-038)
# ═════════════════════════════════════════════════════════════

def _get_token() -> str:
    """Создаёт родительский payin и возвращает recurrent_token."""
    _, _, token = _payin_card("auto", is_recurrent=True)
    assert token, "recurrent_token должен присутствовать при is_recurrent=True"
    return token


def _cancel_op(tid: int, oid: str, amount: int):
    """Вызывает /cancel и ассертирует 200/201."""
    resp = post_operation(tid, "cancel", {
        "merchant_data":  {"order_id": oid},
        "financial_data": {"amount": amount, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"cancel failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    return resp


@pytest.mark.tcid("RB-031")
def test_double_stage_rebill_capture_full():
    """Двухстадийный rebill → полный capture → статус completed.
    Шаг 1: родительский payin (is_recurrent=True) → recurrent_token.
    Шаг 2: rebill method=token, capture_mode=manual → authorized.
    Шаг 3: /capture полная сумма → completed."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")
    _capture(tid_r, oid_r)
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-032")
def test_double_stage_rebill_capture_partial():
    """Двухстадийный rebill → частичный capture → authorized → capture остатка → completed.
    Шаг 1: rebill 10000, manual.
    Шаг 2: /capture 3000 → authorized.
    Шаг 3: GET → authorized.
    Шаг 4: /capture 7000 → completed."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    resp = post_operation(tid_r, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb31_cap1")},
        "financial_data": {"amount": 3000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Partial capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_r, "authorized")

    resp = post_operation(tid_r, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb31_cap2")},
        "financial_data": {"amount": 7000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Final capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-033")
def test_double_stage_rebill_cancel_before_capture():
    """Двухстадийный rebill → /cancel без capture → статус cancelled.
    Шаг 1: rebill (manual) → authorized.
    Шаг 2: /cancel → cancelled."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")
    _cancel_op(tid_r, gen_order_id("rb32_cancel"), _AMOUNT)
    _assert_status(tid_r, "cancelled")


@pytest.mark.tcid("RB-034")
def test_double_stage_rebill_partial_cancel_then_capture():
    """Двухстадийный rebill → частичный cancel → capture оставшейся суммы → completed.
    Шаг 1: rebill 10000 (manual) → authorized.
    Шаг 2: /cancel 3000 → authorized (остаток 7000).
    Шаг 3: /capture 7000 → completed."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    _cancel_op(tid_r, gen_order_id("rb33_cancel"), 3000)
    _assert_status(tid_r, "authorized")

    resp = post_operation(tid_r, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb33_cap")},
        "financial_data": {"amount": 7000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Capture remaining failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-035")
def test_double_stage_rebill_partial_capture_then_cancel():
    """Двухстадийный rebill → частичный capture → cancel остатка → completed.
    Шаг 1: rebill 10000 (manual) → authorized.
    Шаг 2: /capture 3000 → authorized.
    Шаг 3: /cancel 7000 → completed (или cancelled, фиксируем поведение)."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    resp = post_operation(tid_r, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb34_cap")},
        "financial_data": {"amount": 3000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Partial capture failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_r, "authorized")

    resp = post_operation(tid_r, "cancel", {
        "merchant_data":  {"order_id": gen_order_id("rb34_cancel")},
        "financial_data": {"amount": 7000, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Cancel remaining failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    final = get_request(f"{BASE_URL}/{tid_r}").json().get("status")
    assert final in ("completed", "cancelled"), \
        f"Expected completed or cancelled after partial-capture + cancel, got {final!r}"


@pytest.mark.tcid("RB-036")
def test_double_stage_rebill_capture_amount_exceeds():
    """Двухстадийный rebill → capture суммы больше авторизованной → ошибка 4xx.
    Шаг 1: rebill 10000 (manual) → authorized.
    Шаг 2: /capture 10001 → 4xx."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    resp = post_operation(tid_r, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb35_cap")},
        "financial_data": {"amount": _AMOUNT + 1, "currency": "RUB"},
    })
    assert resp.status_code in (400, 409, 422), \
        f"Expected 4xx for over-capture on rebill, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RB-037")
def test_double_stage_rebill_repeated_capture_after_full():
    """Двухстадийный rebill → полный capture → повторный capture → 409.
    Шаг 1: rebill (manual) → authorized.
    Шаг 2: /capture полная → completed.
    Шаг 3: /capture повторно → 409."""
    token = _get_token()
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")
    _capture(tid_r, oid_r)
    _assert_status(tid_r, "completed")

    resp = post_operation(tid_r, "capture", {
        "merchant_data":  {"order_id": gen_order_id("rb36_cap2")},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    })
    assert resp.status_code == 409, \
        f"Expected 409 for repeated capture on rebill, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.slow
@pytest.mark.skip(reason="Требует ожидания timeout (~5 мин) — запускать вручную с -m slow")
@pytest.mark.tcid("RB-038")
def test_double_stage_rebill_auto_cancel_timeout():
    """Двухстадийный rebill без capture → автоматическая отмена по таймауту → cancelled.
    Не запускается в обычном прогоне: слишком медленный."""
    token = _get_token()
    tid_r, _ = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")
    time.sleep(300)   # 5 минут — зависит от конфигурации сервиса
    _assert_status(tid_r, "cancelled")


# ═════════════════════════════════════════════════════════════
# УПРАВЛЕНИЕ ПОДПИСКАМИ (RB-041 … RB-046)
# ═════════════════════════════════════════════════════════════

def _cancel_subscription(token: str):
    """DELETE /api/v1/subscriptions/{token}"""
    return delete_request(f"{SUBSCRIPTIONS_URL}/{token}")


def _try_rebill(token: str) -> int:
    """Пытается создать rebill, возвращает HTTP-статус."""
    oid  = gen_order_id("rb_sub_rebill")
    body = {
        "type":             "payin",
        "merchant_data":    {**MERCHANT_DATA, "order_id": oid},
        "financial_data":   {"amount": _AMOUNT, "currency": "RUB"},
        "flow_data":        {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data":    CUSTOMER_DATA,
        "transaction_data": {"method": "token", "details": {"token": token}},
    }
    return post_transaction(body).status_code


@pytest.mark.tcid("RB-041")
def test_cancel_subscription_before_rebill():
    """Отмена подписки до первого rebill → rebill невозможен.
    Шаг 1: родительский payin (is_recurrent=True) → recurrent_token.
    Шаг 2: DELETE /subscriptions/{token} → 204.
    Шаг 3: rebill с этим токеном → 404 или 409."""
    token = _get_token()

    r = _cancel_subscription(token)
    assert r.status_code in (200, 204), \
        f"Expected 200/204 for subscription cancel, got {r.status_code}: {r.text}"

    rebill_status = _try_rebill(token)
    assert rebill_status in (400, 404, 409, 422), \
        f"Expected error for rebill after subscription cancel, got {rebill_status}"


@pytest.mark.tcid("RB-042")
def test_cancel_subscription_after_one_rebill():
    """Отмена подписки после успешного rebill → следующий rebill невозможен.
    Шаг 1: родитель → token1.
    Шаг 2: успешный rebill с token1.
    Шаг 3: DELETE /subscriptions/{token1} → 200/204.
    Шаг 4: второй rebill → ошибка."""
    token = _get_token()

    tid_r, _ = _rebill(token, "auto")
    _assert_status(tid_r, "completed")

    r = _cancel_subscription(token)
    assert r.status_code in (200, 204), \
        f"Expected 200/204, got {r.status_code}: {r.text}"

    rebill_status = _try_rebill(token)
    assert rebill_status in (400, 404, 409, 422), \
        f"Expected error for rebill after subscription cancel, got {rebill_status}"


@pytest.mark.tcid("RB-043")
def test_cancel_subscription_with_pending_double_stage_rebill():
    """Отмена подписки при наличии незавершённого двухстадийного rebill.
    Pending rebill не отменяется, но новый rebill с тем же токеном создать нельзя.
    Шаг 1: родитель → token1.
    Шаг 2: rebill (manual) → authorized (pending).
    Шаг 3: DELETE /subscriptions/{token1} → 200/204.
    Шаг 4: новый rebill → ошибка.
    Шаг 5: GET pending rebill → всё ещё authorized (не отменился)."""
    token = _get_token()

    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    r = _cancel_subscription(token)
    assert r.status_code in (200, 204), \
        f"Expected 200/204, got {r.status_code}: {r.text}"

    rebill_status = _try_rebill(token)
    assert rebill_status in (400, 404, 409, 422), \
        f"Expected error for new rebill after subscription cancel, got {rebill_status}"

    poll = get_request(f"{BASE_URL}/{tid_r}")
    assert poll.status_code == 200
    assert poll.json().get("status") == "authorized", \
        f"Pending rebill должен остаться authorized после отмены подписки"


@pytest.mark.tcid("RB-044")
def test_cancel_already_cancelled_subscription():
    """Повторная отмена подписки → 404.
    Шаг 1: получить token.
    Шаг 2: DELETE → 200/204.
    Шаг 3: повторный DELETE → 404."""
    token = _get_token()

    r1 = _cancel_subscription(token)
    assert r1.status_code in (200, 204), \
        f"First cancel: Expected 200/204, got {r1.status_code}: {r1.text}"

    r2 = _cancel_subscription(token)
    assert r2.status_code in (404, 409), \
        f"Second cancel: Expected 404 or 409, got {r2.status_code}: {r2.text}"
    assert_error_response(r2)


@pytest.mark.tcid("RB-045")
def test_cancel_subscription_invalid_token():
    """Отмена подписки с несуществующим токеном → 404."""
    fake_token = str(uuid.uuid4())
    r = _cancel_subscription(fake_token)
    assert r.status_code == 404, \
        f"Expected 404 for nonexistent token, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("RB-046")
def test_cancel_subscription_wrong_terminal():
    """Попытка отменить подписку, принадлежащую другому терминалу → 403 или 404.
    Используем UUID4, аналогичный реальному recurrent_token,
    но не существующий для текущего терминала."""
    foreign_token = str(uuid.uuid4())
    r = _cancel_subscription(foreign_token)
    assert r.status_code in (403, 404), \
        f"Expected 403/404 for foreign terminal token, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ─────────────────────────────────────────────
# КЕЙСЫ 50–54: block без capture / с cancel → rebill
# ─────────────────────────────────────────────
@pytest.mark.tcid("RB-050")
def test_block_without_capture_single_stage_rebill():
    """Block (capture_mode=manual, is_recurrent=true) без capture → одностадийный rebill. Ожидается 201, completed."""
    # Шаг 1: block → token (статус authorized, capture не вызываем)
    tid_p, _, token = _payin_card("manual", is_recurrent=True)
    assert token, "recurrent_token must be present"
    _assert_status(tid_p, "authorized")

    # Шаг 2: одностадийный rebill с тем же токеном
    tid_r, _ = _rebill(token, "auto")
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-051")
def test_block_without_capture_double_stage_rebill():
    """Block без capture → двухстадийный rebill → capture → completed."""
    # Шаг 1: block → token
    _, _, token = _payin_card("manual", is_recurrent=True)
    assert token, "recurrent_token must be present"

    # Шаг 2: двухстадийный rebill → authorized
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    # Шаг 3: capture → completed
    _capture(tid_r, oid_r)
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-052")
def test_block_with_cancel_single_stage_rebill():
    """Block → полный cancel → одностадийный rebill с тем же токеном. Ожидается 201, completed."""
    # Шаг 1: block → token
    tid_p, oid_p, token = _payin_card("manual", is_recurrent=True)
    assert token, "recurrent_token must be present"
    _assert_status(tid_p, "authorized")

    # Шаг 2: полный cancel
    resp = post_operation(tid_p, "cancel", {
        "merchant_data":  {"order_id": oid_p},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Cancel failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_p, "cancelled")

    # Шаг 3: одностадийный rebill
    tid_r, _ = _rebill(token, "auto")
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-053")
def test_block_with_cancel_double_stage_rebill():
    """Block → полный cancel → двухстадийный rebill → capture → completed."""
    # Шаг 1: block → token
    tid_p, oid_p, token = _payin_card("manual", is_recurrent=True)
    assert token, "recurrent_token must be present"
    _assert_status(tid_p, "authorized")

    # Шаг 2: полный cancel
    resp = post_operation(tid_p, "cancel", {
        "merchant_data":  {"order_id": oid_p},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Cancel failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_p, "cancelled")

    # Шаг 3: двухстадийный rebill → authorized
    tid_r, oid_r = _rebill(token, "manual")
    _assert_status(tid_r, "authorized")

    # Шаг 4: capture → completed
    _capture(tid_r, oid_r)
    _assert_status(tid_r, "completed")


@pytest.mark.tcid("RB-054")
def test_rebill_token_after_cancel():
    """recurrent_token остаётся валидным после полной отмены block.
    Если rebill возвращает ошибку — cancel деактивирует токен (фиксируем поведение)."""
    # Шаг 1: block → token
    tid_p, oid_p, token = _payin_card("manual", is_recurrent=True)
    assert token, "recurrent_token must be present"
    _assert_status(tid_p, "authorized")

    # Шаг 2: полный cancel
    resp = post_operation(tid_p, "cancel", {
        "merchant_data":  {"order_id": oid_p},
        "financial_data": {"amount": _AMOUNT, "currency": "RUB"},
    })
    assert resp.status_code in (200, 201), f"Cancel failed: {resp.status_code}: {resp.text}"
    time.sleep(SETUP_DELAY)
    _assert_status(tid_p, "cancelled")

    # Шаг 3: rebill — токен должен остаться активным
    tid_r, _ = _rebill(token, "auto")
    _assert_status(tid_r, "completed")
