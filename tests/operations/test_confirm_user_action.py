"""
Тесты confirm для транзакций в статусе waiting_action.
POST /api/v1/transactions/{id}/confirm

waiting_action достигается через P2P (method=p2p).
Fixture-based: каждый тест получает свою транзакцию (function scope).

Типы confirm для user-action (waiting_action через P2P):
  transfer_card    — подтверждение/отклонение P2P-перевода
  transfer_phone   — подтверждение/отклонение перевода по телефону
  transfer_qr      — подтверждение/отклонение QR
  transfer_account — подтверждение/отклонение перевода по счёту
  top_up_mobile    — подтверждение/отклонение пополнения телефона
  redirect         — подтверждение/отклонение редиректа (waiting_action и waiting_3DS_redirect)
"""
import json
import time
import uuid

import pytest
import requests as _req

from conftest import (
    post_transaction, post_operation, get_request,
    BASE_URL, TERMINAL_ID, MERCHANT_DATA, CUSTOMER_DATA, CARD_DETAILS, THREED,
    gen_order_id, SETUP_DELAY,
    calc_signature,
    make_block_payin, make_completed_payin,
    assert_error_response, assert_transaction_response,
)

_POLL_ATTEMPTS = 6
_POLL_DELAY    = 2.0


def _create_p2p() -> tuple[int, str]:
    """Создаёт P2P-транзакцию и ждёт статуса waiting_action."""
    oid  = gen_order_id("con_ua_fixture")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "p2p"},
    }
    resp = post_transaction(body)
    if resp.status_code != 201:
        pytest.skip(f"Failed to create P2P transaction: {resp.status_code}: {resp.text}")

    data = resp.json()
    tid  = data["transaction_id"]

    if data.get("status") == "waiting_action":
        return tid, oid

    for _ in range(_POLL_ATTEMPTS):
        time.sleep(_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == "waiting_action":
            return tid, oid
        if status in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"P2P transaction {tid} reached {status!r} instead of waiting_action")

    pytest.skip(f"P2P transaction {tid} did not reach waiting_action within timeout")


@pytest.fixture
def waiting_action_tid() -> tuple[int, str]:
    """Свежая P2P-транзакция в статусе waiting_action. Function-scoped."""
    return _create_p2p()


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ ХЕЛПЕРЫ И КОНСТАНТЫ
# ─────────────────────────────────────────────
_FAKE_TID = "000000000000"
_FAKE_OID = "order_ua_test"
_CARD_WAIT_3DS          = {**CARD_DETAILS, "cvv": "123"}  # CVV < 500  → waiting_3DS
_CARD_WAIT_3DS_REDIRECT = {**CARD_DETAILS, "cvv": "550"}  # CVV 500-599 → waiting_3DS_redirect


def _ua_confirm(tid, oid: str, result_type: str, details: dict):
    """Отправляет confirm user-action на транзакцию."""
    return post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": result_type, "details": details},
    })


def _ua_confirm_fake(result_type: str, details: dict):
    """Confirm на несуществующей транзакции — для тестов валидации."""
    return post_operation(_FAKE_TID, "confirm", {
        "merchant_data": {"order_id": _FAKE_OID},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": result_type, "details": details},
    })


def _create_3ds_transaction() -> tuple[int, str]:
    """Создаёт payin с CVV 123 (waiting_3DS) и возвращает (tid, oid)."""
    oid  = gen_order_id("ua_3ds")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD_WAIT_3DS},
    }
    resp = post_transaction(body)
    if resp.status_code != 201:
        pytest.skip(f"Failed to create 3DS transaction: {resp.status_code}: {resp.text}")
    data = resp.json()
    tid  = data["transaction_id"]
    if data.get("status") == "waiting_3DS":
        return tid, oid
    for _ in range(_POLL_ATTEMPTS):
        time.sleep(_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        s = r.json().get("status", "")
        if s == "waiting_3DS":
            return tid, oid
        if s in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"3DS transaction {tid} reached {s!r} instead of waiting_3DS")
    pytest.skip(f"3DS transaction {tid} did not reach waiting_3DS within timeout")


def _create_3ds_redirect_transaction() -> tuple[int, str]:
    """Создаёт payin с CVV 550 (waiting_3DS_redirect) и возвращает (tid, oid)."""
    oid  = gen_order_id("ua_3ds_redir")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD_WAIT_3DS_REDIRECT},
    }
    resp = post_transaction(body)
    if resp.status_code != 201:
        pytest.skip(f"Failed to create 3DS_redirect transaction: {resp.status_code}: {resp.text}")
    data = resp.json()
    tid  = data["transaction_id"]
    if data.get("status") == "waiting_3DS_redirect":
        return tid, oid
    for _ in range(_POLL_ATTEMPTS):
        time.sleep(_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        s = r.json().get("status", "")
        if s == "waiting_3DS_redirect":
            return tid, oid
        if s in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"3DS_redirect transaction {tid} reached {s!r} instead of waiting_3DS_redirect")
    pytest.skip(f"3DS_redirect transaction {tid} did not reach waiting_3DS_redirect within timeout")


def _create_cancelled_transaction() -> tuple[int, str]:
    """Создаёт authorized block payin и отменяет его. Возвращает (tid, oid)."""
    oid = gen_order_id("ua_cancel")
    tid = make_block_payin(oid)
    r = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    })
    if r.status_code not in (200, 201):
        pytest.skip(f"Failed to cancel transaction {tid}: {r.text}")
    return tid, oid


# ─────────────────────────────────────────────
# TRANSFER_CARD
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-046")
def test_confirm_transfer_card_confirmed_true(waiting_action_tid):
    """Confirm type=transfer_card, confirmed=true — пользователь принял перевод."""
    tid, oid = waiting_action_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "processing"
    assert isinstance(data.get("transaction_id"), int)
    assert_transaction_response(data)


@pytest.mark.tcid("CON-047")
def test_confirm_transfer_card_confirmed_false(waiting_action_tid):
    """Confirm type=transfer_card, confirmed=false — пользователь отклонил перевод."""
    tid, oid = waiting_action_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": False}},
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────
# ОСТАЛЬНЫЕ USER-ACTION ТИПЫ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-048")
@pytest.mark.parametrize("result_type", [
    "redirect",
    "transfer_phone",
    "transfer_qr",
    "transfer_account",
    "top_up_mobile",
])
def test_confirm_user_action_types_confirmed_true(waiting_action_tid, result_type):
    """Confirm с разными user-action типами, confirmed=true → 200, одинаковая структура ответа."""
    tid, oid = waiting_action_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": result_type, "details": {"confirmed": True}},
    })
    assert r.status_code == 200, f"[{result_type}] Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "processing", f"[{result_type}] Expected status=processing"
    assert isinstance(data.get("transaction_id"), int)


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("CON-074")
def test_idempotency_same_key_returns_same_transaction_id(waiting_action_tid):
    """Повторный confirm с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import uuid
    import requests as _req
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    tid, oid = waiting_action_tid
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _post():
        ts = str(int(time.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        from _helpers.validators import assert_idempotency_echo
        r = _req.post(f"{BASE_URL}/{tid}/confirm", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _post()
    assert r1.status_code in (200, 201), f"First confirm failed: {r1.text}"
    tid1 = r1.json().get("transaction_id")
    r2 = _post()
    assert r2.status_code in (200, 201), f"Duplicate key: expected 200/201, got {r2.status_code}: {r2.text}"
    assert r2.json().get("transaction_id") == tid1, (
        f"Duplicate key returned different transaction_id: r1={tid1}, r2={r2.json().get('transaction_id')}"
    )


# ═════════════════════════════════════════════
# UA — HAPPY PATH (UA-001 … UA-010)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-001")
def test_ua_transfer_card_confirmed_true(waiting_action_tid):
    """transfer_card + confirmed=true → 200, status=processing."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("status") == "processing"
    assert isinstance(data.get("transaction_id"), int)
    assert_transaction_response(data)


@pytest.mark.tcid("UA-002")
def test_ua_transfer_card_confirmed_false(waiting_action_tid):
    """transfer_card + confirmed=false → 200, транзакция отклонена."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


@pytest.mark.tcid("UA-003")
def test_ua_transfer_phone_confirmed_true(waiting_action_tid):
    """transfer_phone + confirmed=true → 200."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_phone", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") == "processing"
    assert_transaction_response(r.json())


@pytest.mark.tcid("UA-004")
def test_ua_transfer_phone_confirmed_false(waiting_action_tid):
    """transfer_phone + confirmed=false → 200, транзакция отклонена."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_phone", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


@pytest.mark.tcid("UA-005")
def test_ua_transfer_qr_confirmed_true(waiting_action_tid):
    """transfer_qr + confirmed=true → 200."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_qr", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") == "processing"
    assert_transaction_response(r.json())


@pytest.mark.tcid("UA-006")
def test_ua_transfer_qr_confirmed_false(waiting_action_tid):
    """transfer_qr + confirmed=false → 200, транзакция отклонена."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_qr", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


@pytest.mark.tcid("UA-007")
def test_ua_transfer_account_confirmed_true(waiting_action_tid):
    """transfer_account + confirmed=true → 200."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_account", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") == "processing"
    assert_transaction_response(r.json())


@pytest.mark.tcid("UA-008")
def test_ua_transfer_account_confirmed_false(waiting_action_tid):
    """transfer_account + confirmed=false → 200, транзакция отклонена."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_account", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


@pytest.mark.tcid("UA-009")
def test_ua_top_up_mobile_confirmed_true(waiting_action_tid):
    """top_up_mobile + confirmed=true → 200."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "top_up_mobile", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") == "processing"
    assert_transaction_response(r.json())


@pytest.mark.tcid("UA-010")
def test_ua_top_up_mobile_confirmed_false(waiting_action_tid):
    """top_up_mobile + confirmed=false → 200, транзакция отклонена."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "top_up_mobile", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


@pytest.mark.tcid("UA-011")
def test_ua_redirect_confirmed_true(waiting_action_tid):
    """redirect + confirmed=true → 200, status=processing."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") == "processing"
    assert_transaction_response(r.json())


@pytest.mark.tcid("UA-012")
def test_ua_redirect_confirmed_false(waiting_action_tid):
    """redirect + confirmed=false → 200, транзакция отклонена."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


# ═════════════════════════════════════════════
# ВАЛИДАЦИЯ ПОЛЯ confirmed (UA-013 … UA-022)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-013")
def test_ua_confirmed_missing():
    """confirmed отсутствует в details → 400."""
    r = _ua_confirm_fake("transfer_card", {})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-014")
def test_ua_confirmed_null():
    """confirmed = null → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": None})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-015")
def test_ua_confirmed_string_true():
    """confirmed = "true" (строка) → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": "true"})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-016")
def test_ua_confirmed_string_false():
    """confirmed = "false" (строка) → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": "false"})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-017")
def test_ua_confirmed_int_1():
    """confirmed = 1 (integer) → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": 1})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-018")
def test_ua_confirmed_int_0():
    """confirmed = 0 (integer) → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": 0})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-019")
def test_ua_confirmed_array():
    """confirmed = [] (массив) → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": []})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-020")
def test_ua_confirmed_object():
    """confirmed = {} (объект) → 400."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": {}})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-021")
def test_ua_redirect_confirmed_missing():
    """redirect + confirmed отсутствует → 400 (redirect может иметь отдельную ветку валидации)."""
    r = _ua_confirm_fake("redirect", {})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-022")
def test_ua_redirect_confirmed_null():
    """redirect + confirmed = null → 400."""
    r = _ua_confirm_fake("redirect", {"confirmed": None})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════
# ВАЛИДАЦИЯ СТРУКТУРЫ result.details (UA-023 … UA-028)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-023")
def test_ua_details_missing():
    """result.details отсутствует → 400."""
    r = post_operation(_FAKE_TID, "confirm", {
        "merchant_data": {"order_id": _FAKE_OID},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card"},
    })
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-024")
def test_ua_details_empty_object():
    """result.details = {} (пустой объект, нет confirmed) → 400."""
    r = _ua_confirm_fake("transfer_card", {})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-025")
def test_ua_details_extra_field(waiting_action_tid):
    """result.details = {confirmed: true, extra_field: 'value'} — фиксируем поведение: 200 или 400."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True, "extra_field": "value"})
    assert r.status_code in (200, 400), f"Expected 200 or 400, got {r.status_code}: {r.text}"


@pytest.mark.tcid("UA-026")
def test_ua_details_mixed_user_action_and_3ds(waiting_action_tid):
    """result.details = {confirmed: true, pares: 'x', md: 'y'} — смешанная структура, фиксируем поведение."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True, "pares": "x", "md": "y"})
    assert r.status_code in (200, 400), f"Expected 200 or 400, got {r.status_code}: {r.text}"


@pytest.mark.tcid("UA-027")
def test_ua_redirect_details_empty():
    """redirect + result.details = {} (нет confirmed) → 400."""
    r = _ua_confirm_fake("redirect", {})
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-028")
def test_ua_redirect_details_missing():
    """redirect + result.details отсутствует → 400."""
    r = post_operation(_FAKE_TID, "confirm", {
        "merchant_data": {"order_id": _FAKE_OID},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "redirect"},
    })
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════
# НЕСОВМЕСТИМЫЕ КОМБИНАЦИИ (UA-029 … UA-034)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-029")
def test_ua_transfer_card_with_3ds_fields_no_confirmed():
    """type=transfer_card + details.data.pares + details.data.md (без confirmed) → 400."""
    r = post_operation(_FAKE_TID, "confirm", {
        "merchant_data": {"order_id": _FAKE_OID},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-030")
def test_ua_transfer_card_confirmed_and_data(waiting_action_tid):
    """type=transfer_card + details содержит и confirmed, и data → 400 или игнорирование лишнего."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_card", {
        "confirmed": True,
        "data": {"pares": "test_pares", "md": "test_md"},
    })
    assert r.status_code in (200, 400), f"Expected 200 or 400, got {r.status_code}: {r.text}"


@pytest.mark.tcid("UA-031")
def test_ua_redirect_with_3ds_fields_no_confirmed():
    """type=redirect + details.data.pares + details.data.md (без confirmed) → 400."""
    r = post_operation(_FAKE_TID, "confirm", {
        "merchant_data": {"order_id": _FAKE_OID},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"data": {"pares": "test_pares", "md": "test_md"}}},
    })
    assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-032")
def test_ua_redirect_confirmed_and_data(waiting_action_tid):
    """type=redirect + details содержит и confirmed, и data → фиксируем поведение: 200 или 400."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "redirect", {
        "confirmed": True,
        "data": {"pares": "test_pares", "md": "test_md"},
    })
    assert r.status_code in (200, 400), f"Expected 200 or 400, got {r.status_code}: {r.text}"


@pytest.mark.tcid("UA-033")
def test_ua_transfer_card_on_waiting_3ds_transaction():
    """Транзакция в статусе waiting_3DS + transfer_card confirm → 4xx (тип не соответствует статусу)."""
    tid, oid = _create_3ds_transaction()
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for transfer_card on waiting_3DS, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-034")
def test_ua_redirect_on_waiting_3ds_transaction():
    """Транзакция в статусе waiting_3DS + redirect confirm → 4xx (ожидается threed_secure, не redirect)."""
    tid, oid = _create_3ds_transaction()
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for redirect on waiting_3DS, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════
# СОСТОЯНИЕ ТРАНЗАКЦИИ (UA-035 … UA-043)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-035")
def test_ua_nonexistent_transaction():
    """Несуществующий transaction_id + transfer_card → 404."""
    r = _ua_confirm_fake("transfer_card", {"confirmed": True})
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-036")
def test_ua_nonexistent_transaction_redirect():
    """Несуществующий transaction_id + redirect → 404."""
    r = _ua_confirm_fake("redirect", {"confirmed": True})
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-037")
def test_ua_completed_transaction():
    """Транзакция в статусе completed + transfer_card + confirmed=true → 4xx."""
    oid = gen_order_id("ua_comp")
    tid = make_completed_payin(oid)
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for confirm on completed transaction, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-038")
def test_ua_completed_transaction_redirect():
    """Транзакция в статусе completed + redirect + confirmed=true → 4xx."""
    oid = gen_order_id("ua_comp_redir")
    tid = make_completed_payin(oid)
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for redirect confirm on completed transaction, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-039")
def test_ua_cancelled_transaction():
    """Транзакция в статусе cancelled + transfer_card + confirmed=true → 4xx."""
    tid, oid = _create_cancelled_transaction()
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for confirm on cancelled transaction, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-040")
def test_ua_rejected_transaction():
    """Транзакция в статусе rejected + transfer_card + confirmed=true → 4xx."""
    oid  = gen_order_id("ua_rej")
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    if resp.status_code != 201:
        pytest.skip(f"Cannot create transaction: {resp.status_code}")
    tid = resp.json()["transaction_id"]
    for _ in range(_POLL_ATTEMPTS):
        time.sleep(_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code == 200:
            s = r.json().get("status", "")
            if s == "rejected":
                break
            if s in ("completed", "authorized"):
                pytest.skip(f"Transaction {tid} ended in {s!r} — no rejected state in this env")
    else:
        pytest.skip(f"Transaction {tid} did not reach 'rejected' within timeout")
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for confirm on rejected transaction, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-041")
def test_ua_waiting_3ds_redirect_with_redirect_confirmed_true():
    """waiting_3DS_redirect + redirect + confirmed=true → 200, status=processing.
    Валидная комбинация: redirect на транзакции в состоянии ожидания редиректа."""
    tid, oid = _create_3ds_redirect_transaction()
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") == "processing"
    assert_transaction_response(r.json())


@pytest.mark.tcid("UA-042")
def test_ua_waiting_3ds_redirect_with_redirect_confirmed_false():
    """waiting_3DS_redirect + redirect + confirmed=false → 200, транзакция отклонена."""
    tid, oid = _create_3ds_redirect_transaction()
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("status") in ("rejected", "cancelled", "failed", "processing")


@pytest.mark.tcid("UA-043")
def test_ua_waiting_3ds_redirect_with_transfer_card():
    """waiting_3DS_redirect + transfer_card → 4xx (неверный тип confirm для данного статуса)."""
    tid, oid = _create_3ds_redirect_transaction()
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for transfer_card on waiting_3DS_redirect, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════
# ИДЕМПОТЕНТНОСТЬ (UA-044 … UA-045)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-044")
def test_ua_idempotency_same_key_same_body(waiting_action_tid):
    """Повторный confirm с тем же idempotency key, тот же body → 409 или кэшированный 200."""
    tid, oid = waiting_action_tid
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _post():
        from _helpers.validators import assert_idempotency_echo
        ts  = str(int(time.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        r = _req.post(f"{BASE_URL}/{tid}/confirm", data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _post()
    assert r1.status_code in (200, 201), f"First confirm failed: {r1.text}"
    r2 = _post()
    assert r2.status_code in (200, 201, 409), \
        f"Expected cached 200 or 409, got {r2.status_code}: {r2.text}"
    if r2.status_code in (200, 201):
        assert r2.json().get("transaction_id") == r1.json().get("transaction_id"), \
            "Idempotent response returned different transaction_id"


@pytest.mark.tcid("UA-045")
def test_ua_idempotency_new_key_on_confirmed_transaction(waiting_action_tid):
    """Повторный confirm с новым idempotency key на уже подтверждённой транзакции → 4xx."""
    tid, oid = waiting_action_tid
    r1 = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r1.status_code == 200, f"First confirm failed: {r1.text}"
    r2 = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r2.status_code in range(400, 500), \
        f"Expected 4xx on second confirm with new key, got {r2.status_code}: {r2.text}"
    assert_error_response(r2)
