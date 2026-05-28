"""
Тесты для payin method=p2p.
POST /api/v1/transactions — type:payin, method:p2p
"""

import pytest
from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
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

_P2P_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "transaction_data": {"method": "p2p"},
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

@pytest.mark.tcid("PO-007")
def test_payin_p2p_missing_transaction_data():
    """Payin p2p без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-009")
def test_payin_p2p_with_description():
    """Payin p2p с опциональным description. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_desc"), "description": "P2P test"},
        "transaction_data": {"method": "p2p"},
    }
    _ok(post_transaction(body))


@pytest.mark.tcid("PO-020")
def test_payin_unknown_method():
    """Payin с неизвестным методом. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "unknown_method"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-021")
def test_payin_missing_transaction_data():
    """Payin без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-023")
def test_payin_p2p_response_fields():
    """Payin p2p — ответ содержит transaction_id, status, type, created_at."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_resp")},
        "transaction_data": {"method": "p2p"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"


@pytest.mark.tcid("PO-025")
def test_payin_p2p_response_has_action_data():
    """Payin P2P — ответ может содержать action с реквизитами перевода."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_act")},
            "transaction_data": {"method": "p2p"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    data = resp.json()
    assert_transaction_response(data)


@pytest.mark.tcid("PO-027")
def test_payin_p2p_zero_amount_returns_400():
    """Payin P2P с нулевой суммой. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_z")},
            "financial_data": {"amount": 0, "currency": "RUB"},
            "transaction_data": {"method": "p2p"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 1. transaction_data.method
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-1-1")
def test_p2p_method_p2p():
    """1.1 method=p2p → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_p2p")},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("P2P-1-2")
def test_p2p_method_p22p():
    """1.2 method=p22p → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_p22p")},
        "transaction_data": {"method": "p22p"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-1-3")
def test_p2p_method_empty():
    """1.3 method="" → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_empty")},
        "transaction_data": {"method": ""},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-1-4")
def test_p2p_method_null():
    """1.4 method=null → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_null")},
        "transaction_data": {"method": None},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 2. flow_data
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-2-1")
def test_p2p_no_flow_data():
    """2.1 flow_data не передан."""
    body = {k: v for k, v in _P2P_BASE.items() if k != "flow_data"}
    body = {**body, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_none")}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-2-2")
def test_p2p_flow_data_empty():
    """2.2 flow_data={}."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_empty")},
        "flow_data": {},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 3. flow_data.is_recurrent
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-3-1")
def test_p2p_is_recurrent_true():
    """3.1 is_recurrent=true → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_true")},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-3-2")
def test_p2p_is_recurrent_false():
    """3.2 is_recurrent=false → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_false")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-3-3")
def test_p2p_is_recurrent_int_1():
    """3.3 is_recurrent=1."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_1")},
        "flow_data": {"is_recurrent": 1, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-3-4")
def test_p2p_is_recurrent_int_0():
    """3.4 is_recurrent=0."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_0")},
        "flow_data": {"is_recurrent": 0, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-3-5")
def test_p2p_is_recurrent_string():
    """3.5 is_recurrent="string" → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_str")},
        "flow_data": {"is_recurrent": "yes", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-3-6")
def test_p2p_is_recurrent_empty_string():
    """3.6 is_recurrent="" → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_es")},
        "flow_data": {"is_recurrent": "", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-3-7")
def test_p2p_is_recurrent_null():
    """3.7 is_recurrent=null → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_null")},
        "flow_data": {"is_recurrent": None, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-3-8")
def test_p2p_is_recurrent_missing():
    """3.8 is_recurrent не передан → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_miss")},
        "flow_data": {"capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 4. flow_data.capture_mode
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-4-1")
def test_p2p_capture_mode_auto():
    """4.1 capture_mode=auto → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_auto")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-4-2")
def test_p2p_capture_mode_manual():
    """4.2 capture_mode=manual → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_man")},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-4-3")
def test_p2p_capture_mode_invalid():
    """4.3 capture_mode=123 → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_inv")},
        "flow_data": {"is_recurrent": False, "capture_mode": "123"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-4-4")
def test_p2p_capture_mode_empty():
    """4.4 capture_mode="" → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": ""},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-4-5")
def test_p2p_capture_mode_null():
    """4.5 capture_mode=null → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": None},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-4-6")
def test_p2p_capture_mode_missing():
    """4.6 capture_mode не передан → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_miss")},
        "flow_data": {"is_recurrent": False},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 5. flow_data.threed_secure
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-5-1")
def test_p2p_no_threed_secure():
    """5.1 threed_secure не передан → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_none")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-5-2")
def test_p2p_threed_secure_empty():
    """5.2 threed_secure={} → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 6. threed_secure.challenge_window_size
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-6-1")
def test_p2p_challenge_window_size_01():
    """6.1 challenge_window_size=01 → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_01")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-6-2")
def test_p2p_challenge_window_size_02():
    """6.2 challenge_window_size=02 → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_02")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "02"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-6-3")
def test_p2p_challenge_window_size_03():
    """6.3 challenge_window_size=03 → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_03")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "03"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-6-4")
def test_p2p_challenge_window_size_04():
    """6.4 challenge_window_size=04 → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_04")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "04"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-6-5")
def test_p2p_challenge_window_size_05():
    """6.5 challenge_window_size=05 → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_05")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "05"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-6-6")
def test_p2p_challenge_window_size_06():
    """6.6 challenge_window_size=06 → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_06")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "06"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-6-7")
def test_p2p_challenge_window_size_empty():
    """6.7 challenge_window_size="" → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_es")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-6-8")
def test_p2p_challenge_window_size_null():
    """6.8 challenge_window_size=null → 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("P2P-6-9")
def test_p2p_challenge_window_size_missing():
    """6.9 challenge_window_size не передан → 201."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_miss")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 7. transaction_data.details
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-7")
def test_p2p_details_empty():
    """7 details={} → 201 или 400."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_empty")},
        "transaction_data": {"method": "p2p", "details": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 8. transaction_data.details — дополнительные поля
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("P2P-8-1")
def test_p2p_details_with_cvv():
    """8.1 details содержит cvv."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_cvv")},
        "transaction_data": {"method": "p2p", "details": {"cvv": "999"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-2")
def test_p2p_details_with_expiry_month():
    """8.2 details содержит expiry_month."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_em")},
        "transaction_data": {"method": "p2p", "details": {"expiry_month": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-3")
def test_p2p_details_with_expiry_year():
    """8.3 details содержит expiry_year."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_ey")},
        "transaction_data": {"method": "p2p", "details": {"expiry_year": "29"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-4")
def test_p2p_details_with_holder():
    """8.4 details содержит holder."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_hld")},
        "transaction_data": {"method": "p2p", "details": {"holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-5")
def test_p2p_details_with_pan():
    """8.5 details содержит pan."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pan")},
        "transaction_data": {"method": "p2p", "details": {"pan": "4111111111111111"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-6")
def test_p2p_details_with_pin():
    """8.6 details содержит pin."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pin")},
        "transaction_data": {"method": "p2p", "details": {"pin": "1234"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-7")
def test_p2p_details_with_phone():
    """8.7 details содержит phone."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_phn")},
        "transaction_data": {"method": "p2p", "details": {"phone": "+79001234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-8")
def test_p2p_details_with_token():
    """8.8 details содержит token."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_tok")},
        "transaction_data": {"method": "p2p", "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("P2P-8-9")
def test_p2p_details_with_provider():
    """8.9 details содержит provider."""
    body = {
        **_P2P_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_prv")},
        "transaction_data": {"method": "p2p", "details": {"provider": "visa"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"
