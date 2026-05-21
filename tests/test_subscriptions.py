"""
Тесты для управления подписками (рекуррентными токенами).
DELETE /api/v1/subscriptions/{token}

token — UUID, получается из поля recurrent_token в ответе на Payin с is_recurrent=True.
Happy path (отмена реальной подписки) требует сохранённого recurrent_token — см. conftest.py.
"""
import time
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
def test_cancel_nonexistent_subscription():
    """DELETE по несуществующему UUID-токену. Ожидается 404."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    resp = delete_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_cancel_subscription_invalid_token_format():
    """DELETE по токену, не соответствующему формату UUID. Ожидается 400 или 404."""
    url = f"{SUBSCRIPTIONS_URL}/{_INVALID_TOKEN}"
    resp = delete_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}"
    assert_error_response(resp)


def test_cancel_subscription_no_auth():
    """DELETE /subscriptions/{token} без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{SUBSCRIPTIONS_URL}/{_NONEXISTENT_TOKEN}"
    resp = requests.delete(url, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


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
