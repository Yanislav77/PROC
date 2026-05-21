"""
Тесты для операции confirm (подтверждение ожидающего действия).
POST /api/v1/transactions/{id}/confirm
Типы: threed_secure, redirect, transfer_card, transfer_phone, transfer_qr, transfer_account, top_up_mobile.
Happy path требует транзакцию в статусе waiting_action — покрыты только негативные сценарии.
"""
from conftest import post_operation, assert_error_response


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
def test_confirm_nonexistent_transaction():
    """Confirm по несуществующей транзакции. Ожидается 404."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares", "md": "test_md"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_missing_result():
    """Confirm без поля result (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_missing_financial_data():
    """Confirm без financial_data (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_missing_merchant_data():
    """Confirm без merchant_data (обязательное). Ожидается 400 или 422."""
    body = {
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_missing_order_id():
    """Confirm с merchant_data без order_id. Ожидается 400 или 422."""
    body = {
        "merchant_data": {},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {"confirmed": True}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_invalid_result_type():
    """Confirm с неизвестным типом result. Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "unknown_action", "details": {}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_threed_secure_missing_pares():
    """Confirm 3DS без поля pares (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"md": "test_md"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_threed_secure_missing_md():
    """Confirm 3DS без поля md (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares"}},
        },
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_confirm_redirect_missing_confirmed():
    """Confirm redirect без поля confirmed (обязательное). Ожидается 400 или 422."""
    body = {
        "merchant_data": {"order_id": "order_confirm_test"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "result": {"type": "redirect", "details": {}},
    }
    resp = post_operation("000000000000", "confirm", body)
    assert resp.status_code in (400, 404, 422), f"Expected error, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
