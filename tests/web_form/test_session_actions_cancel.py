"""
Тесты эндпоинта отмены платежа пользователем (PROC-71):
  POST /api/v1/payment-sessions/{payment_token}/actions/transfer/cancel
  (аналог /payments/{payment_token}/cancellation-by-user)

Подпись (POST):
  HMAC-SHA256(customer_mac_key, "POST\n{path}\n{Api-Session-ID}\n{raw_body}")

Поведение:
  - State == "user_action": PAPI-вызов (WebpayV3CancellationByUserAction), 200 OK, тело {}
  - State ≠ "user_action": тихий 200, PAPI не вызывается
  - Битый/пустой JSON → data={}, ошибка поглощается try/except, 200 OK
  - Все поля тела (CancellationReason, CancellationReasonDescription, CancellationScreenshots) опциональны
"""
import hashlib
import hmac
import json
import uuid

import pytest
import requests
import websocket

import _helpers.config as _cfg
from _helpers.validators import assert_error_response, parity_check
from web_form.conftest import create_payment_token, options_preflight

_WEB3_HOST  = "https://web3preprod.testpaygate.com"
_BASE_PATH   = "/api/v1/payment-sessions"
_OLD_PATH    = "/payments"
_INVALID_JSON = "{not_a_json"

_USER_ACTION_TOKEN = "bf7cfa91-bd4b-4797-b874-2c06eb745b58"


@pytest.fixture
def user_action_token():
    """Токен платежа в state 'user_action'. Проверяет состояние через WS и пропускает тест если оно изменилось."""
    try:
        ws = websocket.create_connection(
            f"wss://web3preprod.testpaygate.com/api/v1/payment-sessions/{_USER_ACTION_TOKEN}/ws",
            timeout=5,
        )
        msg = json.loads(ws.recv())
        ws.close()
    except Exception as e:
        pytest.skip(f"user_action_token: не удалось подключиться — {e}")
    state = msg.get("state")
    if state != "user_action":
        pytest.skip(
            f"user_action_token: ожидается state='user_action', получен '{state}' — "
            f"обновите _USER_ACTION_TOKEN вручную"
        )
    return _USER_ACTION_TOKEN

_CANCEL_BODY = {
    "CancellationReason":            "too_long",
    "CancellationReasonDescription": "Очень долго ждал перевод",
    "CancellationScreenshots":       [],
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _cancel_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/actions/transfer/cancel"


def _old_cancel_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/cancellation-by-user"


def _calc_sig(path: str, session_id: str, raw_body: str) -> str:
    """HMAC-SHA256(customer_mac_key, POST\n{path}\n{session_id}\n{raw_body})"""
    key = _cfg.CUSTOMER_MAC_KEY.encode()
    msg = f"POST\n{path}\n{session_id}\n{raw_body}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _make_headers(path: str, raw_body: str = "", session_id: str | None = None) -> dict[str, str]:
    sid = session_id or str(uuid.uuid4())
    return {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw_body),
    }


def _make_old_headers(path: str, raw_body: str = "", session_id: str | None = None) -> dict[str, str]:
    sid = session_id or str(uuid.uuid4())
    return {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw_body),
    }


def _post_cancel(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = _cancel_path(token)
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_cancel_old(token: str, body: dict | str) -> requests.Response:
    path = _old_cancel_path(token)
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = _make_old_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА
# (требуют платёж в state "user_action" — настроить вручную)
# ─────────────────────────────────────────────
@pytest.mark.tcid("AC-001")
def test_transfer_cancel_user_action_state(user_action_token):
    """TC-01: Отмена платежа на стадии user_action. Ожидается 200 OK, тело {}."""
    resp = _post_cancel(user_action_token, _CANCEL_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}, f"Expected empty body, got: {resp.text}"


@pytest.mark.tcid("AC-002")
def test_transfer_cancel_empty_body(user_action_token):
    """TC-02: Отмена с пустым body {}. Ожидается 200 OK, тело {}."""
    resp = _post_cancel(user_action_token, {})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}


@pytest.mark.tcid("AC-003")
def test_transfer_cancel_invalid_json_body(user_action_token):
    """TC-03: Битый JSON в body — ошибка поглощается try/except. Ожидается 200 OK, тело {}."""
    path = _cancel_path(user_action_token)
    resp = _post_cancel(user_action_token, _INVALID_JSON,
                        headers=_make_headers(path, _INVALID_JSON))
    assert resp.status_code == 200, f"Expected 200 (bad JSON swallowed), got {resp.status_code}: {resp.text}"
    assert resp.json() == {}


@pytest.mark.tcid("AC-005")
def test_transfer_cancel_without_screenshots(user_action_token):
    """TC-05: Отмена без опционального CancellationScreenshots. Ожидается 200 OK, тело {}."""
    body = {
        "CancellationReason":            "too_long",
        "CancellationReasonDescription": "Очень долго ждал перевод",
    }
    resp = _post_cancel(user_action_token, body)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}


@pytest.mark.tcid("AC-015")
def test_transfer_cancel_behavior_identical_to_old_endpoint(user_action_token):
    """TC-15: Одинаковое поведение старого и нового эндпоинта при state='user_action'.
    Оба возвращают 200 OK, тело {}."""
    resp_new = _post_cancel(user_action_token, _CANCEL_BODY)
    resp_old = _post_cancel_old(user_action_token, _CANCEL_BODY)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == 200, f"New: {resp_new.status_code}: {resp_new.text}"
        assert resp_old.status_code == 200, f"Old: {resp_old.status_code}: {resp_old.text}"
        assert resp_new.json() == resp_old.json() == {}


# ─────────────────────────────────────────────
# ТИХИЙ 200 ПРИ state != "user_action"
# ─────────────────────────────────────────────
@pytest.mark.tcid("AC-004")
def test_transfer_cancel_silent_200_on_non_user_action_state():
    """TC-04: State платежа != 'user_action' (новый токен, state=new) → тихий 200, PAPI не вызывается."""
    token = create_payment_token()
    resp  = _post_cancel(token, _CANCEL_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}, f"Expected empty body, got: {resp.text}"


@pytest.mark.tcid("AC-016")
def test_transfer_cancel_idempotent_on_non_user_action_state():
    """TC-16: Два запроса подряд на платёж в state != 'user_action' — оба 200 {}. PAPI не вызывается."""
    token = create_payment_token()
    path  = _cancel_path(token)
    raw   = json.dumps(_CANCEL_BODY, separators=(",", ":"))
    for i in range(2):
        resp = _post_cancel(token, _CANCEL_BODY, headers=_make_headers(path, raw))
        assert resp.status_code == 200, \
            f"Request {i + 1}: Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json() == {}, \
            f"Request {i + 1}: Expected empty body, got: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("AC-006")
def test_transfer_cancel_missing_session_id(payment_token):
    """TC-06: Нет Api-Session-ID. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = _cancel_path(payment_token)
    raw  = json.dumps(_CANCEL_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":  "application/json",
        "Api-Signature": _calc_sig(path, str(uuid.uuid4()), raw),
    }
    resp = _post_cancel(payment_token, _CANCEL_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("AC-007")
def test_transfer_cancel_missing_signature(payment_token):
    """TC-07: Нет Api-Signature. Ожидается 4xx (MissingHTTPHeader: Api-Signature)."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_cancel(payment_token, _CANCEL_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("AC-008")
def test_transfer_cancel_invalid_signature(payment_token):
    """TC-08: Невалидная подпись (строка из нулей). Ожидается 4xx (InvalidSignature)."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_cancel(payment_token, _CANCEL_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("AC-009")
def test_transfer_cancel_signature_from_old_url(payment_token):
    """TC-09: Подпись посчитана от старого пути /payments/.../cancellation-by-user. Ожидается 4xx (InvalidSignature)."""
    old_path = _old_cancel_path(payment_token)
    raw      = json.dumps(_CANCEL_BODY, separators=(",", ":"))
    sid      = str(uuid.uuid4())
    headers  = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(old_path, sid, raw),
    }
    resp = _post_cancel(payment_token, _CANCEL_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("AC-010")
def test_transfer_cancel_signature_body_mismatch(payment_token):
    """TC-10: Подпись от body_A, отправлен body_B. Ожидается 4xx (InvalidSignature)."""
    path   = _cancel_path(payment_token)
    body_a = json.dumps(_CANCEL_BODY, separators=(",", ":"))
    body_b = json.dumps({"CancellationReason": "other_reason"}, separators=(",", ":"))
    sid    = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body_a),
    }
    resp = _post_cancel(payment_token, body_b, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("AC-011")
def test_transfer_cancel_invalid_token_format():
    """TC-11: Невалидный payment_token (не UUID). Ожидается 4xx (validation_uuid_decorator)."""
    resp = _post_cancel("not-a-uuid", _CANCEL_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("AC-012")
def test_transfer_cancel_nonexistent_token():
    """TC-12: Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx (PaymentNotFound)."""
    resp = _post_cancel("00000000-0000-4000-8000-000000000000", _CANCEL_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("AC-013")
def test_transfer_cancel_old_endpoint_regression():
    """TC-13: Старый /payments/{token}/cancellation-by-user с X-* заголовками продолжает работать.
    Свежий токен (state=new) → тихий 200 {}."""
    token = create_payment_token()
    resp  = _post_cancel_old(token, _CANCEL_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}, f"Expected empty body, got: {resp.text}"


@pytest.mark.tcid("AC-014")
def test_transfer_cancel_old_headers_on_new_url(payment_token):
    """TC-14: Новый URL + старые заголовки X-CUSTOMER-SESSION-ID / X-REQUEST-SIGNATURE.
    Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    old_path = _old_cancel_path(payment_token)
    raw      = json.dumps(_CANCEL_BODY, separators=(",", ":"))
    sid      = str(uuid.uuid4())
    headers  = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(old_path, sid, raw),
    }
    resp = _post_cancel(payment_token, _CANCEL_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("AC-017")
def test_transfer_cancel_options_preflight(payment_token):
    """OPTIONS preflight /actions/transfer/cancel: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(_cancel_path(payment_token))
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "").upper()
    assert "API-SESSION-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "API-SIGNATURE"  in allow, f"Api-Signature not in Allow-Headers: {allow}"
