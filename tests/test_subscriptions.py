"""
Тесты для управления подписками (рекуррентными токенами).
DELETE /api/v1/subscriptions/{token}

token — UUID, получается из поля recurrent_token в ответе на Payin с is_recurrent=True.
Happy path (отмена реальной подписки) требует сохранённого recurrent_token — см. conftest.py.
"""
import time

import pytest
import requests

from conftest import (
    delete_request,
    SUBSCRIPTIONS_URL,
    TERMINAL_ID,
    assert_error_response,
)

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
