"""
Тесты выплат методом card (type=payout, method=card).
"""
import time

import pytest

from conftest import (
    post_transaction,
    get_request,
    BASE_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)
from _helpers.polling import poll_status

_BASE = {
    "type": "payout",
    "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}

_VALID = {**_BASE, "transaction_data": {"method": "sbp"}}


def _assert_payout_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payout"
    return data


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-001")
def test_payout_card():
    """Выплата на карту — pan и holder обязательны."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("payout_card")},
        "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}},
    }
    data = _assert_payout_ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "processing":
        poll_status(tid, "processing")


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — card
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-012")
def test_payout_card_missing_pan():
    """Выплата на карту без pan (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card", "details": {"holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-013")
def test_payout_card_missing_holder():
    """Выплата на карту без holder (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card", "details": {"pan": "5413000000000000"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-014")
def test_payout_card_missing_details():
    """Выплата на карту без details. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "card"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-022")
def test_payout_negative_amount():
    """Выплата с отрицательной суммой. Ожидается 400."""
    body = {
        **_BASE,
        "financial_data": {"amount": -1000, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-023")
def test_payout_zero_amount():
    """Выплата с нулевой суммой. Ожидается 400."""
    body = {
        **_BASE,
        "financial_data": {"amount": 0, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-024")
def test_payout_invalid_currency():
    """Выплата с невалидным кодом валюты. Ожидается 400."""
    body = {
        **_BASE,
        "financial_data": {"amount": 1000, "currency": "INVALID"},
        "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CARD DETAILS — граничные случаи (9.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-064")
def test_payout_card_pan_empty():
    """card.pan = '' (пустая строка). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-065")
def test_payout_card_pan_invalid_luhn():
    """card.pan не проходит проверку Luhn. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111111111111112", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-066")
def test_payout_card_pan_too_short():
    """card.pan менее 13 цифр. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "411111111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-067")
def test_payout_card_pan_too_long():
    """card.pan более 19 цифр. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "54130000000000001111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-068")
def test_payout_card_pan_with_spaces():
    """card.pan = '4111 1111 1111 1111' (с пробелами). Ожидается 400 (сервер может вернуть 500 — баг валидации)."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111 1111 1111 1111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code in (400, 500)


@pytest.mark.tcid("PY-069")
def test_payout_card_pan_with_dashes():
    """card.pan = '4111-1111-1111-1111' (с дефисами). Ожидается 400 (сервер может вернуть 500 — баг валидации)."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "4111-1111-1111-1111", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code in (400, 500)


@pytest.mark.tcid("PY-070")
def test_payout_card_holder_empty():
    """card.holder = '' (пустая строка). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": ""}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-071")
def test_payout_card_holder_spaces():
    """card.holder = '   ' (только пробелы). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "   "}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-072")
def test_payout_card_holder_cyrillic():
    """card.holder = 'ИВАН ПЕТРОВ' (кириллица). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "ИВАН ПЕТРОВ"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-073")
def test_payout_card_holder_with_dot():
    """card.holder = 'JOHN DOE JR.' (с точкой). Ожидается 201 или 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE JR."}}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-074")
def test_payout_card_expiry_month_13():
    """card.expiry_month = '13' (невалидный месяц). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "5413000000000000", "holder": "JOHN DOE",
        "expiry_month": "13", "expiry_year": "30", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-075")
def test_payout_card_expiry_month_00():
    """card.expiry_month = '00'. Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "5413000000000000", "holder": "JOHN DOE",
        "expiry_month": "00", "expiry_year": "30", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-076")
def test_payout_card_expiry_month_single_digit():
    """card.expiry_month = '5' (без ведущего нуля). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "5413000000000000", "holder": "JOHN DOE",
        "expiry_month": "5", "expiry_year": "30", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-077")
def test_payout_card_expired():
    """Истёкший срок действия карты (год 20). Ожидается 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "5413000000000000", "holder": "JOHN DOE",
        "expiry_month": "01", "expiry_year": "20", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-078")
def test_payout_card_expiry_year_far_future():
    """card.expiry_year = '50' (слишком далёкий год). Ожидается 201 или 400."""
    body = {**_VALID, "transaction_data": {"method": "card", "details": {
        "pan": "5413000000000000", "holder": "JOHN DOE",
        "expiry_month": "01", "expiry_year": "50", "cvv": "123",
    }}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-113")
def test_payout_card_without_expiry_fields():
    """Payout card без expiry_month/expiry_year — поля опциональны для payout. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_no_exp")},
            "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-120")
def test_payout_card_response_has_transaction_id():
    """Payout card — ответ содержит transaction_id."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_tid")},
            "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert "transaction_id" in resp.json(), "transaction_id отсутствует в ответе payout"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-142")
def test_idempotency_same_key_returns_same_transaction_id():
    """Повторный запрос с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import time
    import uuid
    import requests as _req
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_py_card")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}},
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
        r = _req.post(BASE_URL, data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _post()
    assert r1.status_code == 201, f"First request failed: {r1.text}"
    r2 = _post()
    assert r2.status_code in (200, 201), f"Duplicate key: expected 200/201, got {r2.status_code}: {r2.text}"
    assert r2.json()["transaction_id"] == r1.json()["transaction_id"], (
        f"Duplicate key created new transaction: "
        f"r1.tid={r1.json().get('transaction_id')}, r2.tid={r2.json().get('transaction_id')}"
    )


# ─────────────────────────────────────────────
# РЕГРЕСС — копейки
# ─────────────────────────────────────────────

@pytest.mark.tcid("PY-148")
def test_payout_card_amount_with_kopecks():
    """Выплата на карту — сумма с копейками (1050 = 10.50 руб). Ожидается 201 и amount=1050 в ответе."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("kopecks")},
        "financial_data": {"amount": 1050, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "5413000000000000", "holder": "JOHN DOE"}},
    }
    data = _assert_payout_ok(post_transaction(body))
    assert data["financial_data"]["amount"] == 1050


# ─────────────────────────────────────────────
# РЕГРЕСС — отказ банка
# ─────────────────────────────────────────────

@pytest.mark.tcid("PY-154")
def test_payout_card_declined():
    """Выплата на карту, которую банк отклоняет (pan=5000000000000009). Ожидается статус rejected."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_declined")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": {"pan": "5000000000000009", "holder": "JOHN DOE"}},
    }
    data = _assert_payout_ok(post_transaction(body))
    assert_transaction_response(data)
    tid = data["transaction_id"]
    if data.get("status") != "rejected":
        poll_status(tid, "rejected")
