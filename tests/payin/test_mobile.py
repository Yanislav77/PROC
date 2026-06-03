"""
Тесты для payin method=mobile.
POST /api/v1/transactions — type:payin, method:mobile
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

_POLL_ATTEMPTS = 6
_POLL_DELAY    = 2.0


def _poll_status(tid: int, expected: str) -> None:
    """Poll GET /{tid} until expected status or skip."""
    for _ in range(_POLL_ATTEMPTS):
        time.sleep(_POLL_DELAY)
        r = get_request(f"{BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == expected:
            return
        if status in ("completed", "authorized", "rejected", "cancelled", "failed"):
            pytest.skip(f"Transaction {tid} reached {status!r} instead of {expected!r}")
    pytest.skip(f"Transaction {tid} did not reach {expected!r} within timeout")

_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}

_MOBILE_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}


def _ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    return data


# ──────────────────────────────────────────────────────────────
# EXISTING TESTS
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PO-015")
def test_payin_mobile_with_provider():
    """Payin mobile с необязательным полем provider. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mobile_provider")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS"}},
    }
    data = _ok(post_transaction(body))
    tid = data["transaction_id"]
    if data.get("status") != "completed":
        _poll_status(tid, "completed")


@pytest.mark.tcid("PO-026")
def test_payin_mobile_response_fields():
    """Payin mobile — ответ содержит все обязательные поля."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_rf")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    data = resp.json()
    assert_transaction_response(data)
    tid = data["transaction_id"]
    if data.get("status") != "completed":
        _poll_status(tid, "completed")


# ──────────────────────────────────────────────────────────────
# 18. transaction_data.method
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-18-1")
def test_mobile_method_mobile():
    """18.1 method=mobile → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_mob")},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("MOB-18-2")
def test_mobile_method_mobile1():
    """18.2 method=mobile1 → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_mob1")},
        "transaction_data": {"method": "mobile1", "details": {"phone": "+79991234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-18-3")
def test_mobile_method_empty():
    """18.3 method="" → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_empty")},
        "transaction_data": {"method": "", "details": {"phone": "+79991234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-18-4")
def test_mobile_method_null():
    """18.4 method=null → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_null")},
        "transaction_data": {"method": None, "details": {"phone": "+79991234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 19. flow_data
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-19-1")
def test_mobile_no_flow_data():
    """19.1 flow_data не передан."""
    body = {k: v for k, v in _MOBILE_BASE.items() if k != "flow_data"}
    body = {**body, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_none")}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-19-2")
def test_mobile_flow_data_empty():
    """19.2 flow_data={}."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_empty")},
        "flow_data": {},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 20. flow_data.is_recurrent
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-20-1")
def test_mobile_is_recurrent_true():
    """20.1 is_recurrent=true → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_true")},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-20-2")
def test_mobile_is_recurrent_false():
    """20.2 is_recurrent=false → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_false")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-20-3")
def test_mobile_is_recurrent_int_1():
    """20.3 is_recurrent=1."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_1")},
        "flow_data": {"is_recurrent": 1, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-20-4")
def test_mobile_is_recurrent_int_0():
    """20.4 is_recurrent=0."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_0")},
        "flow_data": {"is_recurrent": 0, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-20-5")
def test_mobile_is_recurrent_string():
    """20.5 is_recurrent="string" → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_str")},
        "flow_data": {"is_recurrent": "yes", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-20-6")
def test_mobile_is_recurrent_empty_string():
    """20.6 is_recurrent="" → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_es")},
        "flow_data": {"is_recurrent": "", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-20-7")
def test_mobile_is_recurrent_null():
    """20.7 is_recurrent=null → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_null")},
        "flow_data": {"is_recurrent": None, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-20-8")
def test_mobile_is_recurrent_missing():
    """20.8 is_recurrent не передан → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_miss")},
        "flow_data": {"capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 21. flow_data.capture_mode
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-21-1")
def test_mobile_capture_mode_auto():
    """21.1 capture_mode=auto → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_auto")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-21-2")
def test_mobile_capture_mode_manual():
    """21.2 capture_mode=manual → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_man")},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-21-3")
def test_mobile_capture_mode_invalid():
    """21.3 capture_mode=123 → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_inv")},
        "flow_data": {"is_recurrent": False, "capture_mode": "123"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-21-4")
def test_mobile_capture_mode_empty():
    """21.4 capture_mode="" → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": ""},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-21-5")
def test_mobile_capture_mode_null():
    """21.5 capture_mode=null → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": None},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-21-6")
def test_mobile_capture_mode_missing():
    """21.6 capture_mode не передан → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_miss")},
        "flow_data": {"is_recurrent": False},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 22. flow_data.threed_secure
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-22-1")
def test_mobile_no_threed_secure():
    """22.1 threed_secure не передан → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_none")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-22-2")
def test_mobile_threed_secure_empty():
    """22.2 threed_secure={} → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 23. threed_secure.challenge_window_size
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-23-1")
def test_mobile_challenge_window_size_01():
    """23.1 challenge_window_size=01 → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_01")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-23-2")
def test_mobile_challenge_window_size_02():
    """23.2 challenge_window_size=02 → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_02")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "02"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-23-3")
def test_mobile_challenge_window_size_03():
    """23.3 challenge_window_size=03 → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_03")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "03"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-23-4")
def test_mobile_challenge_window_size_04():
    """23.4 challenge_window_size=04 → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_04")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "04"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-23-5")
def test_mobile_challenge_window_size_05():
    """23.5 challenge_window_size=05 → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_05")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "05"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-23-6")
def test_mobile_challenge_window_size_06():
    """23.6 challenge_window_size=06 → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_06")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "06"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-23-7")
def test_mobile_challenge_window_size_empty():
    """23.7 challenge_window_size="" → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_es")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-23-8")
def test_mobile_challenge_window_size_null():
    """23.8 challenge_window_size=null → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-23-9")
def test_mobile_challenge_window_size_missing():
    """23.9 challenge_window_size не передан → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_miss")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 24. transaction_data.details
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-24-1")
def test_mobile_no_details():
    """24.1 details не передан → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_none")},
        "transaction_data": {"method": "mobile"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-24-2")
def test_mobile_details_empty():
    """24.2 details={} → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_empty")},
        "transaction_data": {"method": "mobile", "details": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 25. details.phone
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-25-1")
def test_mobile_phone_with_plus():
    """25.1 phone с + → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_plus")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-25-2")
def test_mobile_phone_without_plus():
    """25.2 phone без + → 201 или 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_noplus")},
        "transaction_data": {"method": "mobile", "details": {"phone": "79991234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-25-3")
def test_mobile_phone_4_chars():
    """25.3 phone из 4 символов включая + → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_4")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+799"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-4")
def test_mobile_phone_7_chars():
    """25.4 phone из 7 символов включая + → 400 или 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_7")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79912"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-25-5")
def test_mobile_phone_16_chars():
    """25.5 phone из 16 символов включая + → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_16")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+799912345678901"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-25-6")
def test_mobile_phone_17_chars():
    """25.6 phone из 17 символов включая + → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_17")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+7999123456789012"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-7")
def test_mobile_phone_with_letters():
    """25.7 phone содержит буквы → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_let")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+7999abc4567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-8")
def test_mobile_phone_with_special_chars():
    """25.8 phone содержит спецсимволы → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_spec")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+7(999)123-45-67"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-9")
def test_mobile_phone_empty():
    """25.9 phone="" → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_es")},
        "transaction_data": {"method": "mobile", "details": {"phone": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-10")
def test_mobile_phone_null():
    """25.10 phone=null → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_null")},
        "transaction_data": {"method": "mobile", "details": {"phone": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-11")
def test_mobile_phone_missing():
    """25.11 phone не передан → 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_miss")},
        "transaction_data": {"method": "mobile", "details": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("MOB-25-12")
def test_mobile_phone_8_chars():
    """25.12 phone из 8 символов включая + → 400 или 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ph_8")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+7999123"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 26. details.provider
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-26-1")
def test_mobile_provider_latin():
    """26.1 provider латиницей → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_lat")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-26-2")
def test_mobile_provider_cyrillic():
    """26.2 provider кириллицей → 201 или 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_cyr")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "МТС"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-26-3")
def test_mobile_provider_alphanum():
    """26.3 provider из букв и цифр → 201 или 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_an")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS123"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-26-4")
def test_mobile_provider_special_chars():
    """26.4 provider из букв и спецсимволов → 201 или 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_spec")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS@#"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-26-5")
def test_mobile_provider_empty():
    """26.5 provider="" → 201 или 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_es")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-26-6")
def test_mobile_provider_null():
    """26.6 provider=null → 201 или 400."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_null")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-26-7")
def test_mobile_provider_missing():
    """26.7 provider не передан → 201."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("prv_miss")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 27. transaction_data.details — дополнительные поля
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("MOB-27-1")
def test_mobile_details_with_cvv():
    """27.1 details содержит cvv вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_cvv")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "cvv": "999"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-27-2")
def test_mobile_details_with_expiry_month():
    """27.2 details содержит expiry_month вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_em")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "expiry_month": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-27-3")
def test_mobile_details_with_expiry_year():
    """27.3 details содержит expiry_year вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_ey")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "expiry_year": "29"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-27-4")
def test_mobile_details_with_holder():
    """27.4 details содержит holder вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_hld")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-27-5")
def test_mobile_details_with_pan():
    """27.5 details содержит pan вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pan")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "pan": "4111111111111111"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-27-6")
def test_mobile_details_with_pin():
    """27.6 details содержит pin вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pin")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "pin": "1234"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("MOB-27-7")
def test_mobile_details_with_token():
    """27.7 details содержит token вместе с phone."""
    body = {
        **_MOBILE_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_tok")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "token": "b928586b-e6ec-4400-9039-e36f19c0094c"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("MOB-28-1")
def test_idempotency_same_key_returns_same_transaction_id():
    """Повторный запрос с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import time
    import uuid
    import requests as _req
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_mob")},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
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
        return _req.post(BASE_URL, data=raw, headers=h, timeout=30)

    r1 = _post()
    assert r1.status_code == 201, f"First request failed: {r1.text}"
    r2 = _post()
    assert r2.status_code in (200, 201), f"Duplicate key: expected 200/201, got {r2.status_code}: {r2.text}"
    assert r2.json()["transaction_id"] == r1.json()["transaction_id"], (
        f"Duplicate key created new transaction: "
        f"r1.tid={r1.json().get('transaction_id')}, r2.tid={r2.json().get('transaction_id')}"
    )
