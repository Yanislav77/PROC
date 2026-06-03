"""
Тесты confirm для транзакций в статусе waiting_action.
POST /api/v1/transactions/{id}/confirm

waiting_action достигается через P2P (method=p2p).
Fixture-based: каждый тест получает свою транзакцию (function scope).

Типы confirm для user-action:
  transfer_card    — подтверждение/отклонение P2P-перевода
  redirect         — подтверждение/отклонение редиректа
  transfer_phone   — подтверждение/отклонение перевода по телефону
  transfer_qr      — подтверждение/отклонение QR
  transfer_account — подтверждение/отклонение перевода по счёту
  top_up_mobile    — подтверждение/отклонение пополнения телефона
"""
import time

import pytest

from conftest import (
    post_transaction, post_operation, get_request,
    BASE_URL, MERCHANT_DATA, CUSTOMER_DATA, THREED,
    gen_order_id, SETUP_DELAY,
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
        return _req.post(f"{BASE_URL}/{tid}/confirm", data=raw, headers=h, timeout=30)

    r1 = _post()
    assert r1.status_code in (200, 201), f"First confirm failed: {r1.text}"
    tid1 = r1.json().get("transaction_id")
    r2 = _post()
    assert r2.status_code in (200, 201), f"Duplicate key: expected 200/201, got {r2.status_code}: {r2.text}"
    assert r2.json().get("transaction_id") == tid1, (
        f"Duplicate key returned different transaction_id: r1={tid1}, r2={r2.json().get('transaction_id')}"
    )
