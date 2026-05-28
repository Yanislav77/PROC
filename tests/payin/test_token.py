"""
Тесты для payin method=token.
POST /api/v1/transactions — type:payin, method:token
"""

import time
import uuid

import pytest

from conftest import (
    post_transaction,
    get_request,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    BASE_URL,
    SETUP_DELAY,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}

_STUB_TOKEN = "b928586b-e6ec-4400-9039-e36f19c0094c"

_CARD_FOR_TOKEN = {
    "pan": "4111111111111111",
    "holder": "JOHN DOE",
    "expiry_month": "01",
    "expiry_year": "29",
    "cvv": "999",
}

_TOKEN_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "transaction_data": {
        "method": "token",
        "details": {"token": _STUB_TOKEN},
    },
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}


def _acquire_token(flow_data: dict) -> str:
    """Creates a card payin with given flow_data and returns recurrent/withdrawal token."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_acq")},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": _CARD_FOR_TOKEN},
        "flow_data": flow_data,
        "customer_data": CUSTOMER_DATA,
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Token acquisition failed: {resp.status_code}: {resp.text}"
    tr_id = resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    status = get_request(f"{BASE_URL}/{tr_id}")
    assert status.status_code == 200, f"Status poll failed: {status.text}"
    data = status.json()
    td = data.get("transaction_data") or {}
    token = td.get("recurrent_token") or td.get("withdrawal_token")
    assert token, f"No token in status response: {data}"
    return token


@pytest.fixture(scope="session")
def recurrent_token():
    return _acquire_token({"is_recurrent": True, "capture_mode": "auto"})


@pytest.fixture(scope="session")
def withdrawal_token_false():
    return _acquire_token({"is_recurrent": False, "capture_mode": "auto"})


@pytest.fixture(scope="session")
def withdrawal_token_empty_flow():
    try:
        return _acquire_token({})
    except AssertionError as e:
        pytest.skip(f"Setup with empty flow_data failed: {e}")


# ──────────────────────────────────────────────────────────────
# EXISTING TESTS
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PO-018")
def test_payin_token_nonexistent_uuid():
    """Payin token с несуществующим UUID (нулевой). Ожидается 400 или 404."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("token_nonexist")},
        "transaction_data": {
            "method": "token",
            "details": {"token": "00000000-0000-0000-0000-000000000000"},
            "parent_transaction_id": "000000000000",
        },
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-029")
def test_payin_token_missing_parent_transaction_id():
    """Payin token без parent_transaction_id. Ожидается 201 или 400."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_np")},
        "transaction_data": {
            "method": "token",
            "details": {"token": _STUB_TOKEN},
        },
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}"


# ──────────────────────────────────────────────────────────────
# 28. transaction_data.method
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-28-1")
def test_token_method_token(recurrent_token):
    """28.1 method=token с валидным recurrent_token → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_tok")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("PT-28-2")
def test_token_method_token1():
    """28.2 method=token1 → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_tok1")},
        "transaction_data": {"method": "token1", "details": {"token": _STUB_TOKEN}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-28-3")
def test_token_method_empty():
    """28.3 method="" → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_empty")},
        "transaction_data": {"method": "", "details": {"token": _STUB_TOKEN}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-28-4")
def test_token_method_null():
    """28.4 method=null → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_null")},
        "transaction_data": {"method": None, "details": {"token": _STUB_TOKEN}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 29. flow_data
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-29-1")
def test_token_no_flow_data(recurrent_token):
    """29.1 flow_data не передан."""
    body = {k: v for k, v in _TOKEN_BASE.items() if k != "flow_data"}
    body = {
        **body,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_none")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-29-2")
def test_token_flow_data_empty(recurrent_token):
    """29.2 flow_data={}."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_empty")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 30. flow_data.is_recurrent
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-30-1")
def test_token_is_recurrent_true(recurrent_token):
    """30.1 is_recurrent=true → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_true")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-30-2")
def test_token_is_recurrent_false(recurrent_token):
    """30.2 is_recurrent=false → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_false")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-30-3")
def test_token_is_recurrent_int_1(recurrent_token):
    """30.3 is_recurrent=1."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_1")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": 1, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-30-4")
def test_token_is_recurrent_int_0(recurrent_token):
    """30.4 is_recurrent=0."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_0")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": 0, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-30-5")
def test_token_is_recurrent_string():
    """30.5 is_recurrent="string" → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_str")},
        "flow_data": {"is_recurrent": "yes", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-30-6")
def test_token_is_recurrent_empty_string():
    """30.6 is_recurrent="" → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_es")},
        "flow_data": {"is_recurrent": "", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-30-7")
def test_token_is_recurrent_null():
    """30.7 is_recurrent=null → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_null")},
        "flow_data": {"is_recurrent": None, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-30-8")
def test_token_is_recurrent_missing(recurrent_token):
    """30.8 is_recurrent не передан → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_miss")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 31. flow_data.capture_mode
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-31-1")
def test_token_capture_mode_auto(recurrent_token):
    """31.1 capture_mode=auto → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_auto")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-31-2")
def test_token_capture_mode_manual(recurrent_token):
    """31.2 capture_mode=manual → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_man")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-31-3")
def test_token_capture_mode_invalid():
    """31.3 capture_mode=123 → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_inv")},
        "flow_data": {"is_recurrent": False, "capture_mode": "123"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-31-4")
def test_token_capture_mode_empty():
    """31.4 capture_mode="" → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": ""},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-31-5")
def test_token_capture_mode_null():
    """31.5 capture_mode=null → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": None},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-31-6")
def test_token_capture_mode_missing(recurrent_token):
    """31.6 capture_mode не передан → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_miss")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 32. flow_data.threed_secure
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-32-1")
def test_token_no_threed_secure(recurrent_token):
    """32.1 threed_secure не передан → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_none")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-32-2")
def test_token_threed_secure_empty(recurrent_token):
    """32.2 threed_secure={} → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_empty")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 33. threed_secure.challenge_window_size
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-33-1")
def test_token_challenge_window_size_01(recurrent_token):
    """33.1 challenge_window_size=01 → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_01")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-33-2")
def test_token_challenge_window_size_02(recurrent_token):
    """33.2 challenge_window_size=02 → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_02")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "02"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-33-3")
def test_token_challenge_window_size_03(recurrent_token):
    """33.3 challenge_window_size=03 → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_03")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "03"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-33-4")
def test_token_challenge_window_size_04(recurrent_token):
    """33.4 challenge_window_size=04 → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_04")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "04"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-33-5")
def test_token_challenge_window_size_05(recurrent_token):
    """33.5 challenge_window_size=05 → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_05")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "05"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-33-6")
def test_token_challenge_window_size_06():
    """33.6 challenge_window_size=06 → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_06")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "06"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-33-7")
def test_token_challenge_window_size_empty():
    """33.7 challenge_window_size="" → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_es")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-33-8")
def test_token_challenge_window_size_null():
    """33.8 challenge_window_size=null → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-33-9")
def test_token_challenge_window_size_missing(recurrent_token):
    """33.9 challenge_window_size не передан → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_miss")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 34. transaction_data.details
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-34-1")
def test_token_no_details():
    """34.1 details не передан → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_none")},
        "transaction_data": {"method": "token"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-34-2")
def test_token_details_empty():
    """34.2 details={} → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_empty")},
        "transaction_data": {"method": "token", "details": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 35. transaction_data.details.token
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-35-1")
def test_token_valid_uuid(recurrent_token):
    """35.1 token — валидный UUID из recurrent payin → 201."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_valid")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("PT-35-2")
def test_token_non_uuid_format():
    """35.2 token — не UUID формат → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_nonuuid")},
        "transaction_data": {"method": "token", "details": {"token": "not-a-uuid-format"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-35-3")
def test_token_empty_string():
    """35.3 token="" → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_es")},
        "transaction_data": {"method": "token", "details": {"token": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-35-4")
def test_token_null():
    """35.4 token=null → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_null")},
        "transaction_data": {"method": "token", "details": {"token": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-35-5")
def test_token_missing():
    """35.5 token не передан → 400."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_miss")},
        "transaction_data": {"method": "token", "details": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-35-6")
def test_token_random_uuid():
    """35.6 token — случайный UUID, не существующий в системе → 400 или 404."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_rand")},
        "transaction_data": {"method": "token", "details": {"token": str(uuid.uuid4())}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 36. transaction_data.details — дополнительные поля
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-36-1")
def test_token_details_with_cvv(recurrent_token):
    """36.1 details содержит cvv вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_cvv")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "cvv": "999"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-2")
def test_token_details_with_expiry_month(recurrent_token):
    """36.2 details содержит expiry_month вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_em")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "expiry_month": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-3")
def test_token_details_with_expiry_year(recurrent_token):
    """36.3 details содержит expiry_year вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_ey")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "expiry_year": "29"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-4")
def test_token_details_with_holder(recurrent_token):
    """36.4 details содержит holder вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_hld")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-5")
def test_token_details_with_pan(recurrent_token):
    """36.5 details содержит pan вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pan")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "pan": "4111111111111111"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-6")
def test_token_details_with_pin(recurrent_token):
    """36.6 details содержит pin вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pin")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "pin": "1234"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-7")
def test_token_details_with_phone(recurrent_token):
    """36.7 details содержит phone вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_phn")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "phone": "+79001234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PT-36-8")
def test_token_details_with_provider(recurrent_token):
    """36.8 details содержит provider вместе с token."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_prv")},
        "transaction_data": {"method": "token", "details": {"token": recurrent_token, "provider": "visa"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 37. token из нерекуррентных транзакций
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("PT-37-1")
def test_token_from_non_recurrent_payin(withdrawal_token_false):
    """37.1 token из payin с is_recurrent=false → 400 или 404."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("wtok_false")},
        "transaction_data": {"method": "token", "details": {"token": withdrawal_token_false}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-37-2")
def test_token_from_empty_flow_payin(withdrawal_token_empty_flow):
    """37.2 token из payin с flow_data={} → 400 или 404."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("wtok_eflow")},
        "transaction_data": {"method": "token", "details": {"token": withdrawal_token_empty_flow}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PT-37-3")
def test_token_from_different_service():
    """37.3 token от другого сервиса → 400 или 404."""
    body = {
        **_TOKEN_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_other")},
        "transaction_data": {"method": "token", "details": {"token": "55b08de8-9e3e-42ed-9920-d0b20d9459d8"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
