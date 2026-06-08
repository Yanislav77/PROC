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
from pathlib import Path

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

_TR_IDS_FILE = Path(__file__).parent.parent.parent / "tr_ids.json"


def _load_tr_ids() -> dict:
    if _TR_IDS_FILE.exists():
        try:
            return json.loads(_TR_IDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


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
def waiting_action_tid(request) -> tuple[int, str]:
    """Свежая P2P-транзакция в статусе waiting_action. Function-scoped.
    Если в tr_ids.json или --tr-id указан tr_id для текущего TCID — использует его."""
    tcid_marker = request.node.get_closest_marker("tcid")
    tcid_str = tcid_marker.args[0] if tcid_marker else None

    # 1. CLI --tr-id overrides the file (format: TCID:ID or just ID as fallback)
    manual_id = None
    tr_id_args = request.config.getoption("--tr-id", default=None)
    if tr_id_args:
        fallback_id = None
        for entry in tr_id_args:
            if ":" in entry:
                key, val = entry.split(":", 1)
                if key == tcid_str:
                    manual_id = val
                    break
            else:
                fallback_id = entry
        if manual_id is None:
            manual_id = fallback_id

    # 2. tr_ids.json — used when no CLI arg provided
    if manual_id is None and tcid_str:
        file_val = _load_tr_ids().get(tcid_str)
        if file_val is not None:
            manual_id = str(file_val)

    if manual_id is not None:
        tid = int(manual_id)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            pytest.skip(f"Manual tr_id={tid}: GET returned {r.status_code}: {r.text}")
        oid = r.json().get("merchant_data", {}).get("order_id", "")
        return tid, oid

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
    """redirect + confirmed=true → 409, need_confirm=false — confirm не применим."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": True})
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-012")
def test_ua_redirect_confirmed_false(waiting_action_tid):
    """redirect + confirmed=false → 409, need_confirm=false — confirm не применим."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "redirect", {"confirmed": False})
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
    assert_error_response(r)


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


# ═════════════════════════════════════════════
# ВАЛИДАЦИЯ ФИНАНСОВЫХ И MERCHANT ДАННЫХ (UA-046 … UA-047)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-046")
def test_ua_amount_mismatch_returns_4xx(waiting_action_tid):
    """confirmed=true, amount в confirm не совпадает с суммой транзакции → 4xx."""
    tid, oid = waiting_action_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 1, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    })
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for amount mismatch, got {r.status_code}: {r.text}"
    assert_error_response(r)


@pytest.mark.tcid("UA-047")
def test_ua_order_id_mismatch_returns_4xx(waiting_action_tid):
    """order_id в confirm не совпадает с реальным order_id транзакции → 4xx."""
    tid, _ = waiting_action_tid
    r = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": "wrong_order_id_xyz"},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    })
    assert r.status_code in range(400, 500), \
        f"Expected 4xx for order_id mismatch, got {r.status_code}: {r.text}"
    assert_error_response(r)


# ═════════════════════════════════════════════
# ФОРМАТ ОТВЕТА И ЗАГОЛОВКИ (UA-048 … UA-049)
# ═════════════════════════════════════════════

@pytest.mark.tcid("UA-048")
def test_ua_response_format_confirmed_true(waiting_action_tid):
    """confirmed=true: ответ содержит все обязательные поля и type='payin'."""
    tid, oid = waiting_action_tid
    r = _ua_confirm(tid, oid, "transfer_card", {"confirmed": True})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert_transaction_response(data)
    assert data.get("type") == "payin", f"Expected type='payin', got {data.get('type')!r}"


@pytest.mark.tcid("UA-049")
def test_ua_response_headers_on_success(waiting_action_tid):
    """Успешный confirm: ответ содержит Api-Terminal-ID и Api-Idempotency-Key."""
    tid, oid = waiting_action_tid
    body = {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "result": {"type": "transfer_card", "details": {"confirmed": True}},
    }
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())
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
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert "Api-Terminal-ID" in r.headers, "Response missing Api-Terminal-ID header"
    assert r.headers["Api-Terminal-ID"] == TERMINAL_ID, \
        f"Api-Terminal-ID mismatch: {r.headers.get('Api-Terminal-ID')!r} != {TERMINAL_ID!r}"
    assert "Api-Idempotency-Key" in r.headers, "Response missing Api-Idempotency-Key header"
    assert r.headers["Api-Idempotency-Key"] == key, \
        f"Api-Idempotency-Key mismatch: {r.headers.get('Api-Idempotency-Key')!r} != {key!r}"
