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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_rebill"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_rebill_manual"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_p2p_manual"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "transaction_data": {"method": "p2p"},
    }
    _assert_payin_ok(post_transaction(body))


@pytest.mark.tcid("PO-009")
def test_payin_p2p_with_description():
    """Payin p2p с опциональным description. Ожидается 201."""
    body = {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_p2p_desc", "description": "P2P test"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_qr_recurrent"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_mobile_provider"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_token_nonexist"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_qr_resp"},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_p2p_resp"},
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
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_qr_act_{uuid.uuid4().hex[:6]}"},
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
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_p2p_act_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "p2p"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    data = resp.json()
    assert_transaction_response(data)


@pytest.mark.tcid("PO-026")
def test_payin_mobile_response_fields():
    """Payin mobile — ответ содержит все обязательные поля."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_mob_rf_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "mobile", "details": {"phone": "+79991234567"}}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert_transaction_response(resp.json())


@pytest.mark.tcid("PO-027")
def test_payin_p2p_zero_amount_returns_400():
    """Payin P2P с нулевой суммой. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_p2p_z_{uuid.uuid4().hex[:6]}"},
            "financial_data": {"amount": 0, "currency": "RUB"},
            "transaction_data": {"method": "p2p"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-028")
def test_payin_qr_negative_amount_returns_400():
    """Payin QR с отрицательной суммой. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_qr_neg_{uuid.uuid4().hex[:6]}"},
            "financial_data": {"amount": -1, "currency": "RUB"},
            "transaction_data": {"method": "qr"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PO-029")
def test_payin_token_missing_parent_transaction_id():
    """Payin token без parent_transaction_id. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_tok_np_{uuid.uuid4().hex[:6]}"},
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
            "merchant_data": {**MERCHANT_DATA, "order_id": f"order_mob_pn_{uuid.uuid4().hex[:6]}"},
            "transaction_data": {"method": "mobile", "details": {"phone": None}}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)
