"""
Тесты для payin method=qr.
POST /api/v1/transactions — type:payin, method:qr
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

_QR_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "transaction_data": {"method": "qr"},
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

@pytest.mark.tcid("PO-010")
def test_payin_qr_missing_transaction_data():
    """Payin qr без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-022")
def test_payin_qr_response_fields():
    """Payin qr — ответ содержит все обязательные поля согласно спецификации."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_resp")},
        "transaction_data": {"method": "qr"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    assert data["financial_data"]["currency"] == "RUB"


@pytest.mark.tcid("PO-024")
def test_payin_qr_response_has_action_data():
    """Payin QR — ответ для QR может содержать action с QR-кодом (если waiting_action)."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_act")},
            "transaction_data": {"method": "qr"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    data = resp.json()
    assert_transaction_response(data)
    if data.get("status") == "waiting_action":
        assert "action" in data, "action отсутствует при status=waiting_action"


@pytest.mark.tcid("PO-028")
def test_payin_qr_negative_amount_returns_400():
    """Payin QR с отрицательной суммой. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_neg")},
            "financial_data": {"amount": -1, "currency": "RUB"},
            "transaction_data": {"method": "qr"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 9. transaction_data.method
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-9-1")
def test_qr_method_qr():
    """9.1 method=qr → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_qr")},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("QR-9-2")
def test_qr_method_qr1():
    """9.2 method=qr1 → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_qr1")},
        "transaction_data": {"method": "qr1"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-9-3")
def test_qr_method_empty():
    """9.3 method="" → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_empty")},
        "transaction_data": {"method": ""},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-9-4")
def test_qr_method_null():
    """9.4 method=null → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("m_null")},
        "transaction_data": {"method": None},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ──────────────────────────────────────────────────────────────
# 10. flow_data
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-10-1")
def test_qr_no_flow_data():
    """10.1 flow_data не передан."""
    body = {k: v for k, v in _QR_BASE.items() if k != "flow_data"}
    body = {**body, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_none")}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-10-2")
def test_qr_flow_data_empty():
    """10.2 flow_data={}."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("fd_empty")},
        "flow_data": {},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 11. flow_data.is_recurrent
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-11-1")
def test_qr_is_recurrent_true():
    """11.1 is_recurrent=true → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_true")},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-11-2")
def test_qr_is_recurrent_false():
    """11.2 is_recurrent=false → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_false")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-11-3")
def test_qr_is_recurrent_int_1():
    """11.3 is_recurrent=1."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_1")},
        "flow_data": {"is_recurrent": 1, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-11-4")
def test_qr_is_recurrent_int_0():
    """11.4 is_recurrent=0."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_0")},
        "flow_data": {"is_recurrent": 0, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-11-5")
def test_qr_is_recurrent_string():
    """11.5 is_recurrent="string" → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_str")},
        "flow_data": {"is_recurrent": "yes", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-11-6")
def test_qr_is_recurrent_empty_string():
    """11.6 is_recurrent="" → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_es")},
        "flow_data": {"is_recurrent": "", "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-11-7")
def test_qr_is_recurrent_null():
    """11.7 is_recurrent=null → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_null")},
        "flow_data": {"is_recurrent": None, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-11-8")
def test_qr_is_recurrent_missing():
    """11.8 is_recurrent не передан → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("ir_miss")},
        "flow_data": {"capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 12. flow_data.capture_mode
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-12-1")
def test_qr_capture_mode_auto():
    """12.1 capture_mode=auto → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_auto")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-12-2")
def test_qr_capture_mode_manual():
    """12.2 capture_mode=manual → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_man")},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-12-3")
def test_qr_capture_mode_invalid():
    """12.3 capture_mode=123 → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_inv")},
        "flow_data": {"is_recurrent": False, "capture_mode": "123"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-12-4")
def test_qr_capture_mode_empty():
    """12.4 capture_mode="" → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": ""},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-12-5")
def test_qr_capture_mode_null():
    """12.5 capture_mode=null → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": None},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-12-6")
def test_qr_capture_mode_missing():
    """12.6 capture_mode не передан → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cm_miss")},
        "flow_data": {"is_recurrent": False},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 13. flow_data.threed_secure
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-13-1")
def test_qr_no_threed_secure():
    """13.1 threed_secure не передан → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_none")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-13-2")
def test_qr_threed_secure_empty():
    """13.2 threed_secure={} → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("3ds_empty")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 14. threed_secure.challenge_window_size
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-14-1")
def test_qr_challenge_window_size_01():
    """14.1 challenge_window_size=01 → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_01")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-14-2")
def test_qr_challenge_window_size_02():
    """14.2 challenge_window_size=02 → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_02")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "02"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-14-3")
def test_qr_challenge_window_size_03():
    """14.3 challenge_window_size=03 → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_03")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "03"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-14-4")
def test_qr_challenge_window_size_04():
    """14.4 challenge_window_size=04 → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_04")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "04"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-14-5")
def test_qr_challenge_window_size_05():
    """14.5 challenge_window_size=05 → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_05")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "05"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-14-6")
def test_qr_challenge_window_size_06():
    """14.6 challenge_window_size=06 → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_06")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": "06"}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-14-7")
def test_qr_challenge_window_size_empty():
    """14.7 challenge_window_size="" → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_es")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": ""}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-14-8")
def test_qr_challenge_window_size_null():
    """14.8 challenge_window_size=null → 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_null")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {"challenge_window_size": None}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("QR-14-9")
def test_qr_challenge_window_size_missing():
    """14.9 challenge_window_size не передан → 201."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cws_miss")},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 15. transaction_data.details
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-15")
def test_qr_details_empty():
    """15 details={} → 201 или 400."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_empty")},
        "transaction_data": {"method": "qr", "details": {}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────────────────────
# 17. transaction_data.details — дополнительные поля
# ──────────────────────────────────────────────────────────────

@pytest.mark.tcid("QR-17-1")
def test_qr_details_with_cvv():
    """17.1 details содержит cvv."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_cvv")},
        "transaction_data": {"method": "qr", "details": {"cvv": "999"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-2")
def test_qr_details_with_expiry_month():
    """17.2 details содержит expiry_month."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_em")},
        "transaction_data": {"method": "qr", "details": {"expiry_month": "01"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-3")
def test_qr_details_with_expiry_year():
    """17.3 details содержит expiry_year."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_ey")},
        "transaction_data": {"method": "qr", "details": {"expiry_year": "29"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-4")
def test_qr_details_with_holder():
    """17.4 details содержит holder."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_hld")},
        "transaction_data": {"method": "qr", "details": {"holder": "JOHN DOE"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-5")
def test_qr_details_with_pan():
    """17.5 details содержит pan."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pan")},
        "transaction_data": {"method": "qr", "details": {"pan": "4111111111111111"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-6")
def test_qr_details_with_pin():
    """17.6 details содержит pin."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_pin")},
        "transaction_data": {"method": "qr", "details": {"pin": "1234"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-7")
def test_qr_details_with_phone():
    """17.7 details содержит phone."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_phn")},
        "transaction_data": {"method": "qr", "details": {"phone": "+79001234567"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-8")
def test_qr_details_with_token():
    """17.8 details содержит token."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_tok")},
        "transaction_data": {"method": "qr", "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("QR-17-9")
def test_qr_details_with_provider():
    """17.9 details содержит provider."""
    body = {
        **_QR_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("det_prv")},
        "transaction_data": {"method": "qr", "details": {"provider": "visa"}},
    }
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Got {resp.status_code}: {resp.text}"
