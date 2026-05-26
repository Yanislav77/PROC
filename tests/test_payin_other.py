"""
Тесты для payin с методами p2p, qr, mobile и token.
POST /api/v1/transactions — type:payin, method: p2p | qr | mobile | token
"""
import uuid
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
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


def _assert_payin_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payin"
    return data


# ─────────────────────────────────────────────
# HAPPY PATH — p2p
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-001")
def test_payin_p2p():
    """Payin через P2P-перевод — method=p2p, детали карты не требуются."""
    _assert_payin_ok(post_transaction({**_BASE, "transaction_data": {"method": "p2p"}}))


# ─────────────────────────────────────────────
# HAPPY PATH — qr
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-002")
def test_payin_qr():
    """Payin через QR-код — method=qr."""
    _assert_payin_ok(post_transaction({**_BASE, "transaction_data": {"method": "qr"}}))


# ─────────────────────────────────────────────
# HAPPY PATH — mobile
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-003")
def test_payin_mobile():
    """Payin через мобильный платёж — phone обязателен."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# HAPPY PATH — token (rebill)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-004")
def test_payin_token_rebill(payin_transaction_id):
    """Ребилл по сохранённому токену карты (method=token), capture=auto."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("rebill")},
        "financial_data": {"amount": 1100, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            "parent_transaction_id": payin_transaction_id,
        },
    }
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-005")
def test_payin_token_rebill_manual_capture(payin_transaction_id):
    """Ребилл по токену с блокировкой средств (capture=manual)."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("rebill_manual")},
        "financial_data": {"amount": 1100, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "transaction_data": {
            "method": "token",
            "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            "parent_transaction_id": payin_transaction_id,
        },
    }
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — mobile
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-006")
def test_payin_mobile_missing_phone():
    """Payin mobile без поля phone (обязательное). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — p2p
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-007")
def test_payin_p2p_missing_transaction_data():
    """Payin p2p без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-008")
def test_payin_p2p_manual_capture():
    """Payin p2p с capture_mode=manual. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_manual")},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "transaction_data": {"method": "p2p"},
    }
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-009")
def test_payin_p2p_with_description():
    """Payin p2p с опциональным description. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_desc"), "description": "P2P test"},
        "transaction_data": {"method": "p2p"},
    }
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — qr
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-010")
def test_payin_qr_missing_transaction_data():
    """Payin qr без transaction_data. Ожидается 400."""
    body = {k: v for k, v in _BASE.items() if k != "transaction_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-011")
def test_payin_qr_is_recurrent():
    """Payin qr с is_recurrent=True. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_recurrent")},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "transaction_data": {"method": "qr"},
    }
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — mobile (дополнительные)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-012")
def test_payin_mobile_invalid_phone_format():
    """Payin mobile с телефоном не в формате E.164. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "89991234567"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-013")
def test_payin_mobile_phone_too_short():
    """Payin mobile с телефоном '+7' (слишком короткий). Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+7"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-014")
def test_payin_mobile_phone_with_spaces():
    """Payin mobile с пробелами в номере телефона. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+7 999 123 45 67"}}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-015")
def test_payin_mobile_with_provider():
    """Payin mobile с необязательным полем provider. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mobile_provider")},
        "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "provider": "MTS"}},
    }
    _assert_payin_ok(post_transaction(body))


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — token (дополнительные)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PO-016")
def test_payin_token_missing_token_field():
    """Payin token без поля token в details. Ожидается 400."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "token",
            "details": {},
            "parent_transaction_id": "000000000000",
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PO-017")
def test_payin_token_invalid_uuid_format():
    """Payin token с токеном в невалидном формате (не UUID). Ожидается 400."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "token",
            "details": {"token": "not-a-valid-uuid"},
            "parent_transaction_id": "000000000000",
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


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


@pytest.mark.tcid("PO-019")
def test_payin_token_empty_string():
    """Payin token с пустой строкой в качестве токена. Ожидается 400."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "token",
            "details": {"token": ""},
            "parent_transaction_id": "000000000000",
        },
    }
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ОБЩИЕ ГРАНИЧНЫЕ СЛУЧАИ
# ─────────────────────────────────────────────
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


@pytest.mark.tcid("PO-026")
def test_payin_mobile_response_fields():
    """Payin mobile — ответ содержит все обязательные поля."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_rf")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert_transaction_response(resp.json())


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


@pytest.mark.tcid("PO-029")
def test_payin_token_missing_parent_transaction_id():
    """Payin token без parent_transaction_id. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_np")},
            "transaction_data": {
                "method": "token",
                "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
            }}
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}"


@pytest.mark.tcid("PO-030")
def test_payin_mobile_phone_null_returns_400():
    """Payin mobile с phone = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_pn")},
            "transaction_data": {"method": "mobile", "details": {"phone": None}}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _flow(**kw):
    d = {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED}
    d.update(kw)
    return d


def _flow_drop(*keys):
    d = {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED}
    for k in keys:
        d.pop(k, None)
    return d


# ═══════════════════════════════════════════════════════
# P2P — method (TC 1.x)
# ═══════════════════════════════════════════════════════
@pytest.mark.tcid("PO-031")
def test_payin_p2p_method_p22p():
    """TC 1.2 — method='p22p'. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "p22p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-032")
def test_payin_p2p_method_empty_string():
    """TC 1.3 — method=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": ""}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-033")
def test_payin_p2p_method_null():
    """TC 1.4 — method=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": None}})
    assert resp.status_code == 400
    assert_error_response(resp)


# P2P — flow_data (TC 2.x)
@pytest.mark.tcid("PO-034")
def test_payin_p2p_flow_data_absent():
    """TC 2.1 — flow_data не передаётся. Ожидается 400."""
    body = {k: v for k, v in {**_BASE, "transaction_data": {"method": "p2p"}}.items() if k != "flow_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-035")
def test_payin_p2p_flow_data_empty_obj():
    """TC 2.2 — flow_data={}. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {}, "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


# P2P — is_recurrent (TC 3.x)
@pytest.mark.tcid("PO-036")
def test_payin_p2p_is_recurrent_true():
    """TC 3.1 — is_recurrent=true. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_rect")},
            "flow_data": _flow(is_recurrent=True),
            "transaction_data": {"method": "p2p"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-037")
def test_payin_p2p_is_recurrent_false():
    """TC 3.2 — is_recurrent=false. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_recf")},
            "flow_data": _flow(is_recurrent=False),
            "transaction_data": {"method": "p2p"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-038")
def test_payin_p2p_is_recurrent_int_1():
    """TC 3.3 — is_recurrent=1 (integer). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=1),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-039")
def test_payin_p2p_is_recurrent_int_0():
    """TC 3.4 — is_recurrent=0 (integer). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=0),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-040")
def test_payin_p2p_is_recurrent_string():
    """TC 3.5 — is_recurrent='yes' (string). Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent="yes"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-041")
def test_payin_p2p_is_recurrent_empty_string():
    """TC 3.6 — is_recurrent=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=""),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-042")
def test_payin_p2p_is_recurrent_null():
    """TC 3.7 — is_recurrent=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=None),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-043")
def test_payin_p2p_is_recurrent_absent():
    """TC 3.8 — is_recurrent не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_rec_abs")},
                             "flow_data": _flow_drop("is_recurrent"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code in (201, 400)


# P2P — capture_mode (TC 4.x)
@pytest.mark.tcid("PO-044")
def test_payin_p2p_capture_mode_auto():
    """TC 4.1 — capture_mode='auto'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_cma")},
            "flow_data": _flow(capture_mode="auto"),
            "transaction_data": {"method": "p2p"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-045")
def test_payin_p2p_capture_mode_manual_v2():
    """TC 4.2 — capture_mode='manual'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_cmm2")},
            "flow_data": _flow(capture_mode="manual"),
            "transaction_data": {"method": "p2p"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-046")
def test_payin_p2p_capture_mode_123():
    """TC 4.3 — capture_mode='123'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="123"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-047")
def test_payin_p2p_capture_mode_empty():
    """TC 4.4 — capture_mode=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=""),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-048")
def test_payin_p2p_capture_mode_null():
    """TC 4.5 — capture_mode=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=None),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-049")
def test_payin_p2p_capture_mode_absent():
    """TC 4.6 — capture_mode не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_cm_abs")},
                             "flow_data": _flow_drop("capture_mode"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code in (201, 400)


# P2P — threed_secure (TC 5.x)
@pytest.mark.tcid("PO-050")
def test_payin_p2p_threed_secure_absent():
    """TC 5.1 — threed_secure не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_3ds_abs")},
                             "flow_data": _flow_drop("threed_secure"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PO-051")
def test_payin_p2p_threed_secure_empty_obj():
    """TC 5.2 — threed_secure={}."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_3ds_e")},
                             "flow_data": _flow(threed_secure={}),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code in (201, 400)


# P2P — capture_mode дополнительные невалидные значения (TC 6.x)
@pytest.mark.tcid("PO-052")
def test_payin_p2p_capture_mode_01():
    """TC 6.1 — capture_mode='01'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="01"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-053")
def test_payin_p2p_capture_mode_02():
    """TC 6.2 — capture_mode='02'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="02"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-054")
def test_payin_p2p_capture_mode_03():
    """TC 6.3 — capture_mode='03'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="03"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-055")
def test_payin_p2p_capture_mode_04():
    """TC 6.4 — capture_mode='04'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="04"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-056")
def test_payin_p2p_capture_mode_05():
    """TC 6.5 — capture_mode='05'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="05"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-057")
def test_payin_p2p_capture_mode_06():
    """TC 6.6 — capture_mode='06'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="06"),
                             "transaction_data": {"method": "p2p"}})
    assert resp.status_code == 400
    assert_error_response(resp)


# P2P — details (TC 7, 8.x)
@pytest.mark.tcid("PO-058")
def test_payin_p2p_details_empty_obj():
    """TC 7 — details={}."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_det_e")},
                             "transaction_data": {"method": "p2p", "details": {}}})
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PO-059")
def test_payin_p2p_details_cvv():
    """TC 8.1 — details с cvv."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_cvv")},
            "transaction_data": {"method": "p2p", "details": {"cvv": CARD_DETAILS["cvv"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-060")
def test_payin_p2p_details_expiry_month():
    """TC 8.2 — details с expiry_month."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_em")},
            "transaction_data": {"method": "p2p", "details": {"expiry_month": CARD_DETAILS["expiry_month"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-061")
def test_payin_p2p_details_expiry_year():
    """TC 8.3 — details с expiry_year."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_ey")},
            "transaction_data": {"method": "p2p", "details": {"expiry_year": CARD_DETAILS["expiry_year"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-062")
def test_payin_p2p_details_holder():
    """TC 8.4 — details с holder."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_hol")},
            "transaction_data": {"method": "p2p", "details": {"holder": CARD_DETAILS["holder"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-063")
def test_payin_p2p_details_pan():
    """TC 8.5 — details с pan."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_pan")},
            "transaction_data": {"method": "p2p", "details": {"pan": CARD_DETAILS["pan"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-064")
def test_payin_p2p_details_pin():
    """TC 8.6 — details с pin."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_pin")},
            "transaction_data": {"method": "p2p", "details": {"pin": "1234"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-065")
def test_payin_p2p_details_phone():
    """TC 8.7 — details с phone."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_ph")},
            "transaction_data": {"method": "p2p", "details": {"phone": "+79991234567"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-066")
def test_payin_p2p_details_token():
    """TC 8.8 — details с token."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("p2p_tok")},
            "transaction_data": {"method": "p2p", "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"}}}
    assert post_transaction(body).status_code in (201, 400)


# ═══════════════════════════════════════════════════════
# QR — method (TC 9.x)
# ═══════════════════════════════════════════════════════
@pytest.mark.tcid("PO-067")
def test_payin_qr_method_qr1():
    """TC 9.2 — method='qr1'. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "qr1"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-068")
def test_payin_qr_method_empty_string():
    """TC 9.3 — method=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": ""}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-069")
def test_payin_qr_method_null():
    """TC 9.4 — method=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": None}})
    assert resp.status_code == 400
    assert_error_response(resp)


# QR — flow_data (TC 10.x)
@pytest.mark.tcid("PO-070")
def test_payin_qr_flow_data_absent():
    """TC 10.1 — flow_data не передаётся. Ожидается 400."""
    body = {k: v for k, v in {**_BASE, "transaction_data": {"method": "qr"}}.items() if k != "flow_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-071")
def test_payin_qr_flow_data_empty_obj():
    """TC 10.2 — flow_data={}. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {}, "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


# QR — is_recurrent (TC 11.x)
@pytest.mark.tcid("PO-072")
def test_payin_qr_is_recurrent_true():
    """TC 11.1 — is_recurrent=true. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_rect")},
            "flow_data": _flow(is_recurrent=True),
            "transaction_data": {"method": "qr"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-073")
def test_payin_qr_is_recurrent_false():
    """TC 11.2 — is_recurrent=false. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_recf")},
            "flow_data": _flow(is_recurrent=False),
            "transaction_data": {"method": "qr"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-074")
def test_payin_qr_is_recurrent_int_1():
    """TC 11.3 — is_recurrent=1. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=1), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-075")
def test_payin_qr_is_recurrent_int_0():
    """TC 11.4 — is_recurrent=0. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=0), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-076")
def test_payin_qr_is_recurrent_string():
    """TC 11.5 — is_recurrent='yes'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent="yes"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-077")
def test_payin_qr_is_recurrent_empty_string():
    """TC 11.6 — is_recurrent=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=""), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-078")
def test_payin_qr_is_recurrent_null():
    """TC 11.7 — is_recurrent=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=None), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-079")
def test_payin_qr_is_recurrent_absent():
    """TC 11.8 — is_recurrent не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_rec_abs")},
                             "flow_data": _flow_drop("is_recurrent"),
                             "transaction_data": {"method": "qr"}})
    assert resp.status_code in (201, 400)


# QR — capture_mode (TC 12.x)
@pytest.mark.tcid("PO-080")
def test_payin_qr_capture_mode_auto():
    """TC 12.1 — capture_mode='auto'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_cma")},
            "flow_data": _flow(capture_mode="auto"),
            "transaction_data": {"method": "qr"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-081")
def test_payin_qr_capture_mode_manual():
    """TC 12.2 — capture_mode='manual'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_cmm")},
            "flow_data": _flow(capture_mode="manual"),
            "transaction_data": {"method": "qr"}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-082")
def test_payin_qr_capture_mode_123():
    """TC 12.3 — capture_mode='123'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="123"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-083")
def test_payin_qr_capture_mode_empty():
    """TC 12.4 — capture_mode=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=""), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-084")
def test_payin_qr_capture_mode_null():
    """TC 12.5 — capture_mode=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=None), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-085")
def test_payin_qr_capture_mode_absent():
    """TC 12.6 — capture_mode не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_cm_abs")},
                             "flow_data": _flow_drop("capture_mode"),
                             "transaction_data": {"method": "qr"}})
    assert resp.status_code in (201, 400)


# QR — threed_secure (TC 13.x)
@pytest.mark.tcid("PO-086")
def test_payin_qr_threed_secure_absent():
    """TC 13.1 — threed_secure не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_3ds_abs")},
                             "flow_data": _flow_drop("threed_secure"),
                             "transaction_data": {"method": "qr"}})
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PO-087")
def test_payin_qr_threed_secure_empty_obj():
    """TC 13.2 — threed_secure={}."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_3ds_e")},
                             "flow_data": _flow(threed_secure={}),
                             "transaction_data": {"method": "qr"}})
    assert resp.status_code in (201, 400)


# QR — capture_mode дополнительные невалидные значения (TC 14.x)
@pytest.mark.tcid("PO-088")
def test_payin_qr_capture_mode_01():
    """TC 14.1 — capture_mode='01'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="01"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-089")
def test_payin_qr_capture_mode_02():
    """TC 14.2 — capture_mode='02'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="02"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-090")
def test_payin_qr_capture_mode_03():
    """TC 14.3 — capture_mode='03'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="03"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-091")
def test_payin_qr_capture_mode_04():
    """TC 14.4 — capture_mode='04'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="04"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-092")
def test_payin_qr_capture_mode_05():
    """TC 14.5 — capture_mode='05'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="05"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-093")
def test_payin_qr_capture_mode_06():
    """TC 14.6 — capture_mode='06'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="06"), "transaction_data": {"method": "qr"}})
    assert resp.status_code == 400
    assert_error_response(resp)


# QR — details (TC 15, 17.x)
@pytest.mark.tcid("PO-094")
def test_payin_qr_details_empty_obj():
    """TC 15 — details={}."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_det_e")},
                             "transaction_data": {"method": "qr", "details": {}}})
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PO-095")
def test_payin_qr_details_cvv():
    """TC 17.1 — details с cvv."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_cvv")},
            "transaction_data": {"method": "qr", "details": {"cvv": CARD_DETAILS["cvv"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-096")
def test_payin_qr_details_expiry_month():
    """TC 17.2 — details с expiry_month."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_em")},
            "transaction_data": {"method": "qr", "details": {"expiry_month": CARD_DETAILS["expiry_month"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-097")
def test_payin_qr_details_expiry_year():
    """TC 17.3 — details с expiry_year."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_ey")},
            "transaction_data": {"method": "qr", "details": {"expiry_year": CARD_DETAILS["expiry_year"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-098")
def test_payin_qr_details_holder():
    """TC 17.4 — details с holder."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_hol")},
            "transaction_data": {"method": "qr", "details": {"holder": CARD_DETAILS["holder"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-099")
def test_payin_qr_details_pan():
    """TC 17.5 — details с pan."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_pan")},
            "transaction_data": {"method": "qr", "details": {"pan": CARD_DETAILS["pan"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-100")
def test_payin_qr_details_pin():
    """TC 17.6 — details с pin."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_pin")},
            "transaction_data": {"method": "qr", "details": {"pin": "1234"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-101")
def test_payin_qr_details_phone():
    """TC 17.7 — details с phone."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_ph")},
            "transaction_data": {"method": "qr", "details": {"phone": "+79991234567"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-102")
def test_payin_qr_details_token():
    """TC 17.8 — details с token."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("qr_tok")},
            "transaction_data": {"method": "qr", "details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"}}}
    assert post_transaction(body).status_code in (201, 400)


# ═══════════════════════════════════════════════════════
# MOBILE — method (TC 18.x)
# ═══════════════════════════════════════════════════════
@pytest.mark.tcid("PO-103")
def test_payin_mobile_method_mobile1():
    """TC 18.2 — method='mobile1'. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "mobile1", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-104")
def test_payin_mobile_method_empty_string():
    """TC 18.3 — method=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-105")
def test_payin_mobile_method_null():
    """TC 18.4 — method=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": None, "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# MOBILE — flow_data (TC 19.x)
@pytest.mark.tcid("PO-106")
def test_payin_mobile_flow_data_absent():
    """TC 19.1 — flow_data не передаётся. Ожидается 400."""
    body = {k: v for k, v in {**_BASE, "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}.items() if k != "flow_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-107")
def test_payin_mobile_flow_data_empty_obj():
    """TC 19.2 — flow_data={}. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {},
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# MOBILE — is_recurrent (TC 20.x)
@pytest.mark.tcid("PO-108")
def test_payin_mobile_is_recurrent_true():
    """TC 20.1 — is_recurrent=true. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_rect")},
            "flow_data": _flow(is_recurrent=True),
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-109")
def test_payin_mobile_is_recurrent_false():
    """TC 20.2 — is_recurrent=false. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_recf")},
            "flow_data": _flow(is_recurrent=False),
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-110")
def test_payin_mobile_is_recurrent_int_1():
    """TC 20.3 — is_recurrent=1. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=1),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-111")
def test_payin_mobile_is_recurrent_int_0():
    """TC 20.4 — is_recurrent=0. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=0),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-112")
def test_payin_mobile_is_recurrent_string():
    """TC 20.5 — is_recurrent='yes'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent="yes"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-113")
def test_payin_mobile_is_recurrent_empty_string():
    """TC 20.6 — is_recurrent=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=""),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-114")
def test_payin_mobile_is_recurrent_null():
    """TC 20.7 — is_recurrent=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=None),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-115")
def test_payin_mobile_is_recurrent_absent():
    """TC 20.8 — is_recurrent не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_rec_abs")},
                             "flow_data": _flow_drop("is_recurrent"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code in (201, 400)


# MOBILE — capture_mode (TC 21.x)
@pytest.mark.tcid("PO-116")
def test_payin_mobile_capture_mode_auto():
    """TC 21.1 — capture_mode='auto'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_cma")},
            "flow_data": _flow(capture_mode="auto"),
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-117")
def test_payin_mobile_capture_mode_manual():
    """TC 21.2 — capture_mode='manual'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_cmm")},
            "flow_data": _flow(capture_mode="manual"),
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-118")
def test_payin_mobile_capture_mode_123():
    """TC 21.3 — capture_mode='123'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="123"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-119")
def test_payin_mobile_capture_mode_empty():
    """TC 21.4 — capture_mode=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=""),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-120")
def test_payin_mobile_capture_mode_null():
    """TC 21.5 — capture_mode=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=None),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-121")
def test_payin_mobile_capture_mode_absent():
    """TC 21.6 — capture_mode не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_cm_abs")},
                             "flow_data": _flow_drop("capture_mode"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code in (201, 400)


# MOBILE — threed_secure (TC 22.x)
@pytest.mark.tcid("PO-122")
def test_payin_mobile_threed_secure_absent():
    """TC 22.1 — threed_secure не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_3ds_abs")},
                             "flow_data": _flow_drop("threed_secure"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PO-123")
def test_payin_mobile_threed_secure_empty_obj():
    """TC 22.2 — threed_secure={}."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_3ds_e")},
                             "flow_data": _flow(threed_secure={}),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code in (201, 400)


# MOBILE — capture_mode дополнительные невалидные значения (TC 23.x)
@pytest.mark.tcid("PO-124")
def test_payin_mobile_capture_mode_01():
    """TC 23.1 — capture_mode='01'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="01"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-125")
def test_payin_mobile_capture_mode_02():
    """TC 23.2 — capture_mode='02'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="02"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-126")
def test_payin_mobile_capture_mode_03():
    """TC 23.3 — capture_mode='03'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="03"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-127")
def test_payin_mobile_capture_mode_04():
    """TC 23.4 — capture_mode='04'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="04"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-128")
def test_payin_mobile_capture_mode_05():
    """TC 23.5 — capture_mode='05'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="05"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-129")
def test_payin_mobile_capture_mode_06():
    """TC 23.6 — capture_mode='06'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="06"),
                             "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# MOBILE — details (TC 24.x)
@pytest.mark.tcid("PO-130")
def test_payin_mobile_details_absent():
    """TC 24.1 — details не передаётся. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "mobile"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-131")
def test_payin_mobile_details_empty_obj():
    """TC 24.2 — details={}. Ожидается 400 (phone обязателен)."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "mobile", "details": {}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# MOBILE — phone (TC 25.x)
@pytest.mark.tcid("PO-132")
def test_payin_mobile_phone_valid_with_plus():
    """TC 25.1 — phone с '+'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_ph_p")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-133")
def test_payin_mobile_phone_without_plus():
    """TC 25.2 — phone без '+'. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": "79991234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-134")
def test_payin_mobile_phone_4_chars():
    """TC 25.3 — phone из 4 символов включая '+' ('+123'). Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": "+123"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-135")
def test_payin_mobile_phone_7_chars():
    """TC 25.4 — phone из 7 символов включая '+' ('+123456'). Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": "+123456"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-136")
def test_payin_mobile_phone_16_chars():
    """TC 25.5 — phone из 16 символов включая '+'."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_ph_16")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+799912345678901"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-137")
def test_payin_mobile_phone_17_chars():
    """TC 25.6 — phone из 17 символов включая '+'. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": "+7999123456789012"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-138")
def test_payin_mobile_phone_with_letters():
    """TC 25.7 — phone содержит буквы. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": "+7abc1234567"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-139")
def test_payin_mobile_phone_with_special_chars():
    """TC 25.8 — phone содержит спецсимволы. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": "+7(999)123-45-67"}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-140")
def test_payin_mobile_phone_empty_string():
    """TC 25.9 — phone=''. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {"phone": ""}}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-141")
def test_payin_mobile_phone_not_sent():
    """TC 25.11 — phone не передаётся в details. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "mobile", "details": {}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# MOBILE — extra card details (TC 26.x)
@pytest.mark.tcid("PO-142")
def test_payin_mobile_details_with_cvv():
    """TC 26.1 — phone + cvv."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_cvv")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "cvv": CARD_DETAILS["cvv"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-143")
def test_payin_mobile_details_with_expiry_month():
    """TC 26.2 — phone + expiry_month."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_em")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "expiry_month": CARD_DETAILS["expiry_month"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-144")
def test_payin_mobile_details_with_expiry_year():
    """TC 26.3 — phone + expiry_year."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_ey")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "expiry_year": CARD_DETAILS["expiry_year"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-145")
def test_payin_mobile_details_with_holder():
    """TC 26.4 — phone + holder."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_hol")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "holder": CARD_DETAILS["holder"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-146")
def test_payin_mobile_details_with_pan():
    """TC 26.5 — phone + pan."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_pan")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "pan": CARD_DETAILS["pan"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-147")
def test_payin_mobile_details_with_pin():
    """TC 26.6 — phone + pin."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_pin")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "pin": "1234"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-148")
def test_payin_mobile_details_with_token():
    """TC 26.7 — phone + token."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("mob_tok")},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567", "token": "b928586b-e6ec-4400-9039-e36f19c0094c"}}}
    assert post_transaction(body).status_code in (201, 400)


# ═══════════════════════════════════════════════════════
# TOKEN — method (TC 28.x)
# ═══════════════════════════════════════════════════════
_TOK = {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"}


@pytest.mark.tcid("PO-149")
def test_payin_token_method_token1():
    """TC 28.2 — method='token1'. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "token1", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-150")
def test_payin_token_method_empty_string():
    """TC 28.3 — method=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-151")
def test_payin_token_method_null():
    """TC 28.4 — method=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": None, "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


# TOKEN — flow_data (TC 29.x)
@pytest.mark.tcid("PO-152")
def test_payin_token_flow_data_absent():
    """TC 29.1 — flow_data не передаётся. Ожидается 400."""
    body = {k: v for k, v in {**_BASE, "transaction_data": {"method": "token", "details": _TOK}}.items() if k != "flow_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-153")
def test_payin_token_flow_data_empty_obj():
    """TC 29.2 — flow_data={}. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": {}, "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


# TOKEN — is_recurrent (TC 30.x)
@pytest.mark.tcid("PO-154")
def test_payin_token_is_recurrent_true():
    """TC 30.1 — is_recurrent=true. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_rect")},
            "flow_data": _flow(is_recurrent=True),
            "transaction_data": {"method": "token", "details": _TOK}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-155")
def test_payin_token_is_recurrent_false():
    """TC 30.2 — is_recurrent=false. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_recf")},
            "flow_data": _flow(is_recurrent=False),
            "transaction_data": {"method": "token", "details": _TOK}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-156")
def test_payin_token_is_recurrent_int_1():
    """TC 30.3 — is_recurrent=1. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=1),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-157")
def test_payin_token_is_recurrent_int_0():
    """TC 30.4 — is_recurrent=0. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=0),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-158")
def test_payin_token_is_recurrent_string():
    """TC 30.5 — is_recurrent='yes'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent="yes"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-159")
def test_payin_token_is_recurrent_empty_string():
    """TC 30.6 — is_recurrent=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=""),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-160")
def test_payin_token_is_recurrent_null():
    """TC 30.7 — is_recurrent=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(is_recurrent=None),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-161")
def test_payin_token_is_recurrent_absent():
    """TC 30.8 — is_recurrent не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_rec_abs")},
                             "flow_data": _flow_drop("is_recurrent"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code in (201, 400)


# TOKEN — capture_mode (TC 31.x)
@pytest.mark.tcid("PO-162")
def test_payin_token_capture_mode_auto():
    """TC 31.1 — capture_mode='auto'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_cma")},
            "flow_data": _flow(capture_mode="auto"),
            "transaction_data": {"method": "token", "details": _TOK}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-163")
def test_payin_token_capture_mode_manual():
    """TC 31.2 — capture_mode='manual'. Ожидается 201."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_cmm")},
            "flow_data": _flow(capture_mode="manual"),
            "transaction_data": {"method": "token", "details": _TOK}}
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-164")
def test_payin_token_capture_mode_123():
    """TC 31.3 — capture_mode='123'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="123"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-165")
def test_payin_token_capture_mode_empty():
    """TC 31.4 — capture_mode=''. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=""),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-166")
def test_payin_token_capture_mode_null():
    """TC 31.5 — capture_mode=null. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode=None),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-167")
def test_payin_token_capture_mode_absent():
    """TC 31.6 — capture_mode не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_cm_abs")},
                             "flow_data": _flow_drop("capture_mode"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code in (201, 400)


# TOKEN — threed_secure (TC 32.x)
@pytest.mark.tcid("PO-168")
def test_payin_token_threed_secure_absent():
    """TC 32.1 — threed_secure не передаётся."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_3ds_abs")},
                             "flow_data": _flow_drop("threed_secure"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PO-169")
def test_payin_token_threed_secure_empty_obj():
    """TC 32.2 — threed_secure={}."""
    resp = post_transaction({**_BASE,
                             "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_3ds_e")},
                             "flow_data": _flow(threed_secure={}),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code in (201, 400)


# TOKEN — capture_mode дополнительные невалидные значения (TC 33.x)
@pytest.mark.tcid("PO-170")
def test_payin_token_capture_mode_01():
    """TC 33.1 — capture_mode='01'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="01"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-171")
def test_payin_token_capture_mode_02():
    """TC 33.2 — capture_mode='02'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="02"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-172")
def test_payin_token_capture_mode_03():
    """TC 33.3 — capture_mode='03'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="03"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-173")
def test_payin_token_capture_mode_04():
    """TC 33.4 — capture_mode='04'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="04"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-174")
def test_payin_token_capture_mode_05():
    """TC 33.5 — capture_mode='05'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="05"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-175")
def test_payin_token_capture_mode_06():
    """TC 33.6 — capture_mode='06'. Ожидается 400."""
    resp = post_transaction({**_BASE, "flow_data": _flow(capture_mode="06"),
                             "transaction_data": {"method": "token", "details": _TOK}})
    assert resp.status_code == 400
    assert_error_response(resp)


# TOKEN — details (TC 34.x)
@pytest.mark.tcid("PO-176")
def test_payin_token_details_absent():
    """TC 34.1 — details не передаётся. Ожидается 400."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "token"}})
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-177")
def test_payin_token_details_empty_obj():
    """TC 34.2 — details={}. Ожидается 400 (token обязателен)."""
    resp = post_transaction({**_BASE, "transaction_data": {"method": "token", "details": {}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# TOKEN — token field (TC 35.x)
@pytest.mark.tcid("PO-178")
def test_payin_token_field_null():
    """TC 35.4 — token=null. Ожидается 400."""
    resp = post_transaction({**_BASE,
                             "transaction_data": {"method": "token", "details": {"token": None}}})
    assert resp.status_code == 400
    assert_error_response(resp)


# TOKEN — extra card details alongside token (TC 36.x)
@pytest.mark.tcid("PO-179")
def test_payin_token_details_with_cvv():
    """TC 36.1 — token + cvv."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_cvv")},
            "transaction_data": {"method": "token", "details": {**_TOK, "cvv": CARD_DETAILS["cvv"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-180")
def test_payin_token_details_with_expiry_month():
    """TC 36.2 — token + expiry_month."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_em")},
            "transaction_data": {"method": "token", "details": {**_TOK, "expiry_month": CARD_DETAILS["expiry_month"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-181")
def test_payin_token_details_with_expiry_year():
    """TC 36.3 — token + expiry_year."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_ey")},
            "transaction_data": {"method": "token", "details": {**_TOK, "expiry_year": CARD_DETAILS["expiry_year"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-182")
def test_payin_token_details_with_holder():
    """TC 36.4 — token + holder."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_hol")},
            "transaction_data": {"method": "token", "details": {**_TOK, "holder": CARD_DETAILS["holder"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-183")
def test_payin_token_details_with_pan():
    """TC 36.5 — token + pan."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_pan")},
            "transaction_data": {"method": "token", "details": {**_TOK, "pan": CARD_DETAILS["pan"]}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-184")
def test_payin_token_details_with_pin():
    """TC 36.6 — token + pin."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_pin")},
            "transaction_data": {"method": "token", "details": {**_TOK, "pin": "1234"}}}
    assert post_transaction(body).status_code in (201, 400)


@pytest.mark.tcid("PO-185")
def test_payin_token_details_with_phone():
    """TC 36.7 — token + phone."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("tok_ph")},
            "transaction_data": {"method": "token", "details": {**_TOK, "phone": "+79991234567"}}}
    assert post_transaction(body).status_code in (201, 400)
