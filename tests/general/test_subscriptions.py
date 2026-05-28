"""
Тесты для управления подписками (рекуррентными токенами).
DELETE /api/v1/subscriptions/{token}

token — UUID, получается из поля recurrent_token в ответе на Payin с is_recurrent=True.
"""
import hashlib
import hmac
import time
import uuid

import pytest
import requests

from conftest import (
    delete_request,
    post_transaction,
    get_request,
    make_get_headers,
    SUBSCRIPTIONS_URL,
    BASE_URL,
    TERMINAL_ID,
    SERVICE_SECRET,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    SETUP_DELAY,
    assert_error_response,
    gen_order_id,
)


def _sign(terminal_id: str, timestamp: str, raw_body: str = "") -> str:
    message = f"{timestamp}{terminal_id}{raw_body}"
    return hmac.new(SERVICE_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

_NONEXISTENT_TOKEN = "00000000-0000-0000-0000-000000000000"
_INVALID_TOKEN     = "not-a-valid-uuid-format"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# (happy path требует реальный recurrent_token из Payin с is_recurrent=True)
# ─────────────────────────────────────────────
@pytest.mark.tcid("SB-001")
def test_cancel_nonexistent_subscription():
    """DELETE по несуществующему UUID-токену. Ожидается 404."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    resp = delete_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-002")
def test_cancel_subscription_invalid_token_format():
    """DELETE по токену, не соответствующему формату UUID. Ожидается 400 или 404."""
    url = f"{SUBSCRIPTIONS_URL}/{_INVALID_TOKEN}"
    resp = delete_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-003")
def test_cancel_subscription_no_auth():
    """DELETE /subscriptions/{token} без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    resp = requests.delete(url, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-004")
def test_cancel_subscription_invalid_signature():
    """DELETE /subscriptions/{token} с подписью из нулей. Ожидается 401 или 403."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-005")
def test_cancel_subscription_missing_terminal_id():
    """DELETE /subscriptions/{token} без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    headers = {
        "Api-Signature": "0" * 64,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-006")
def test_cancel_subscription_missing_timestamp():
    """DELETE /subscriptions/{token} без Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ ГРАНИЧНЫЕ СЛУЧАИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("SB-007")
def test_cancel_subscription_missing_signature():
    """DELETE /subscriptions/{token} без заголовка Api-Signature. Ожидается 400, 401 или 403."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-008")
def test_cancel_subscription_all_zeros_token():
    """DELETE по токену из одних нулей-дефисов (UUID формат, но несуществующий). Ожидается 404."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000"
    resp = delete_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-009")
def test_cancel_subscription_short_token():
    """DELETE по токену длиной менее UUID (слишком короткий). Ожидается 400 или 404."""
    url = f"{SUBSCRIPTIONS_URL}/short"
    resp = delete_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-010")
def test_cancel_subscription_token_with_path_traversal():
    """DELETE по токену с попыткой path traversal '../admin'. Ожидается 400 или 404."""
    url = f"{SUBSCRIPTIONS_URL}/../admin"
    resp = delete_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"


@pytest.mark.tcid("SB-011")
def test_cancel_subscription_token_uppercase_uuid():
    """DELETE по UUID с заглавными буквами. Ожидается 400 или 404."""
    token = "00000000-0000-0000-0000-000000000001".upper()
    url = f"{SUBSCRIPTIONS_URL}/{token}"
    resp = delete_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("SB-012")
def test_cancel_subscription_numeric_token():
    """DELETE по числовому токену (не UUID). Ожидается 400 или 404."""
    url = f"{SUBSCRIPTIONS_URL}/123456789"
    resp = delete_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ (SB-013 … SB-018)
# ─────────────────────────────────────────────
@pytest.mark.tcid("SB-013")
def test_cancel_subscription_response_has_no_body_on_404():
    """DELETE по несуществующему токену — ответ 404 с JSON телом."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000"
    resp = delete_request(url)
    assert resp.status_code == 404
    assert_error_response(resp)


@pytest.mark.tcid("SB-014")
def test_cancel_subscription_post_instead_of_delete():
    """POST /subscriptions/{token} вместо DELETE. Ожидается 404 или 405."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000"
    headers = make_get_headers(TERMINAL_ID)
    resp = requests.post(url, headers=headers, timeout=30)
    assert resp.status_code in (404, 405), f"Expected 404/405, got {resp.status_code}"


@pytest.mark.tcid("SB-015")
def test_cancel_subscription_get_instead_of_delete():
    """GET /subscriptions/{token} вместо DELETE. Ожидается 404 или 405."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000"
    from conftest import get_request as _get
    resp = _get(url)
    assert resp.status_code in (404, 405), f"Expected 404/405, got {resp.status_code}"


@pytest.mark.tcid("SB-016")
def test_cancel_subscription_token_with_extra_segments():
    """DELETE /subscriptions/{token}/extra — лишний сегмент URL. Ожидается 404."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000/extra"
    resp = delete_request(url)
    assert resp.status_code in (400, 404, 405), f"Expected error, got {resp.status_code}"


@pytest.mark.tcid("SB-017")
def test_cancel_subscription_content_type_in_error_response():
    """DELETE несуществующего токена — Content-Type ответа application/json."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000"
    resp = delete_request(url)
    assert "application/json" in resp.headers.get("Content-Type", ""), \
        f"Content-Type не json: {resp.headers.get('Content-Type')}"


@pytest.mark.tcid("SB-018")
def test_cancel_subscription_idempotency_key_should_not_be_required():
    """DELETE /subscriptions — идемпотентный ключ не требуется (DELETE метод)."""
    url = f"{SUBSCRIPTIONS_URL}/00000000-0000-0000-0000-000000000000"
    timestamp = str(int(time.time()))
    sig = _sign(TERMINAL_ID, timestamp)
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": sig,
        "Api-Timestamp": timestamp,
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    assert resp.status_code in (404, 409), f"Expected 404/409, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# SETUP HELPERS ДЛЯ ПОЗИТИВНЫХ ТЕСТОВ
# ─────────────────────────────────────────────

def _create_recurrent_token(tag: str) -> str:
    """Создаёт card payin с is_recurrent=True и возвращает recurrent_token из ответа на опрос статуса."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id(tag)},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Payin setup failed: {resp.status_code}: {resp.text}"
    tr_id = resp.json()["transaction_id"]
    time.sleep(SETUP_DELAY)
    status = get_request(f"{BASE_URL}/{tr_id}")
    assert status.status_code == 200, f"Status poll failed: {status.text}"
    data = status.json()
    td = data.get("transaction_data") or {}
    token = td.get("recurrent_token")
    assert token, f"recurrent_token not found in transaction_data: {data}"
    return token


@pytest.fixture(scope="session")
def _sub_token_cancel():
    return _create_recurrent_token("sub_cancel")


@pytest.fixture(scope="session")
def _sub_token_recancel():
    return _create_recurrent_token("sub_recancel")


@pytest.fixture(scope="session")
def _sub_token_payin_after_cancel():
    return _create_recurrent_token("sub_payin_after")


# ─────────────────────────────────────────────
# ПОЗИТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────

@pytest.mark.tcid("SB-019")
def test_cancel_subscription_returns_204(_sub_token_cancel):
    """DELETE /subscriptions/{token} с действующим recurrent_token → 204, тело ответа пустое."""
    resp = delete_request(f"{SUBSCRIPTIONS_URL}/{_sub_token_cancel}")
    assert resp.status_code == 204, f"Expected 204, got {resp.status_code}: {resp.text}"
    assert resp.content == b"", f"Expected empty body on 204, got: {resp.content!r}"


@pytest.mark.tcid("SB-020")
def test_cancel_subscription_recancel_returns_conflict(_sub_token_recancel):
    """Повторная отмена уже отменённой подписки → 404 или 409 с JSON телом."""
    url = f"{SUBSCRIPTIONS_URL}/{_sub_token_recancel}"
    first = delete_request(url)
    assert first.status_code == 204, f"First cancel failed: {first.status_code}: {first.text}"
    second = delete_request(url)
    assert second.status_code in (404, 409), (
        f"Expected 404/409 on re-cancel, got {second.status_code}: {second.text}"
    )
    assert_error_response(second)


@pytest.mark.tcid("SB-021")
def test_cancelled_token_rejected_in_payin(_sub_token_payin_after_cancel):
    """После отмены подписки попытка оплаты отменённым токеном → 400/404/409."""
    token = _sub_token_payin_after_cancel
    cancel_resp = delete_request(f"{SUBSCRIPTIONS_URL}/{token}")
    assert cancel_resp.status_code == 204, (
        f"Cancel failed: {cancel_resp.status_code}: {cancel_resp.text}"
    )
    payin_body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("cancelled_sub_payin")},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "transaction_data": {"method": "token", "details": {"token": token}},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
    }
    payin_resp = post_transaction(payin_body)
    assert payin_resp.status_code in (400, 404, 409), (
        f"Expected error using cancelled token, got {payin_resp.status_code}: {payin_resp.text}"
    )
    assert_error_response(payin_resp)
