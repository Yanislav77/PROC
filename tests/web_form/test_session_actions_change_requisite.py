"""
Тесты эндпоинта смены платёжного реквизита:
  POST /api/v1/payment-sessions/{payment_token}/actions/transfer/change-requisite
  (аналог /payments/{payment_token}/reselect)

Подпись (POST):
  HMAC-SHA256(customer_mac_key, "POST\n{path}\n{Api-Session-ID}\n{raw_body}")

Поведение:
  - State == "user_action": PAPI-вызов (WebpayV3ReselectAction), 200 OK, тело {}
    + state_data.userAction.waiting_result=False; PaymentStateSync push state="pending"
  - State ≠ "user_action": тихий 200, PAPI не вызывается, PaymentStateSync не вызывается
  - Битый JSON → 4xx (JSON не оборачивается в try/except, в отличие от /cancel)
  - payment_gateway_id учитывается только если spg.attempts_update_requisite НЕ установлен
"""
import hashlib
import hmac
import json
import uuid

import pytest
import requests

import _helpers.config as _cfg
from _helpers.validators import assert_error_response
from web_form.conftest import create_payment_token, options_preflight

_WEB3_HOST   = "https://web3preprod.testpaygate.com"
_BASE_PATH    = "/api/v1/payment-sessions"
_OLD_PATH     = "/payments"
_INVALID_JSON = "{not_a_json"

_RESELECT_BODY = {"payment_gateway_id": 42}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _reselect_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/actions/transfer/change-requisite"


def _old_reselect_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/reselect"


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


def _post_reselect(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = _reselect_path(token)
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_reselect_old(token: str, body: dict | str) -> requests.Response:
    path = _old_reselect_path(token)
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = _make_old_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА
# (требуют платёж в state "user_action" — настроить вручную)
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-001")
@pytest.mark.skip(reason="Требует платёж в state 'user_action', spg.attempts_update_requisite НЕ установлен — настроить вручную")
def test_change_requisite_user_action_without_attempts_flag(payment_token):
    """TC-01: Смена реквизита, state=user_action, attempts_update_requisite не задан.
    Ожидается 200 {}: PAPI-вызов с AddInfo.bank_info={payment_gateway_id:42};
    state_data.userAction.waiting_result=False; PaymentStateSync push state='pending'."""
    resp = _post_reselect(payment_token, _RESELECT_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}, f"Expected empty body, got: {resp.text}"


@pytest.mark.tcid("RC-002")
@pytest.mark.skip(reason="Требует платёж в state 'user_action', spg.attempts_update_requisite УСТАНОВЛЕН — настроить вручную")
def test_change_requisite_user_action_with_attempts_flag(payment_token):
    """TC-02: Смена реквизита, state=user_action, attempts_update_requisite установлен.
    Ожидается 200 {}: payment_gateway_id из body игнорируется, AddInfo.bank_info={}."""
    resp = _post_reselect(payment_token, _RESELECT_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}


@pytest.mark.tcid("RC-003")
@pytest.mark.skip(reason="Требует платёж в state 'user_action' — настроить вручную")
def test_change_requisite_without_payment_gateway_id(payment_token):
    """TC-03: Тело {} без payment_gateway_id, state=user_action, attempts_update_requisite не задан.
    Ожидается 200 {}: AddInfo.bank_info={payment_gateway_id: null}."""
    resp = _post_reselect(payment_token, {})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}


@pytest.mark.tcid("RC-013")
@pytest.mark.skip(reason="Требует платёж в state 'user_action' — настроить вручную")
def test_change_requisite_old_endpoint_regression_user_action(payment_token):
    """TC-13: Старый /payments/{token}/reselect с X-* заголовками, state=user_action.
    Ожидается 200 {}: PAPI-вызов с ReselectActionObject; state → pending."""
    resp = _post_reselect_old(payment_token, _RESELECT_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}


@pytest.mark.tcid("RC-015")
@pytest.mark.skip(reason="Требует платёж в state 'user_action' — настроить вручную")
def test_change_requisite_behavior_identical_to_old_endpoint():
    """TC-15: Одинаковое поведение старого и нового эндпоинта при state='user_action'.
    Оба возвращают 200 {}; ReselectActionObject идентичен."""
    token_new = create_payment_token()
    token_old = create_payment_token()
    resp_new  = _post_reselect(token_new, _RESELECT_BODY)
    resp_old  = _post_reselect_old(token_old, _RESELECT_BODY)
    assert resp_new.status_code == 200, f"New: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 200, f"Old: {resp_old.status_code}: {resp_old.text}"
    assert resp_new.json() == resp_old.json() == {}


@pytest.mark.tcid("RC-016")
@pytest.mark.skip(reason="Требует WS-клиент + платёж в state 'user_action' — настроить вручную")
def test_change_requisite_ws_push_pending(payment_token):
    """TC-16: После смены реквизита WS-клиент получает фрейм state='pending',
    state_data.userAction.waiting_result=False."""
    resp = _post_reselect(payment_token, _RESELECT_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    # Проверка WS-фрейма выполняется вручную через /api/v1/payment-sessions/{token}/ws


# ─────────────────────────────────────────────
# ТИХИЙ 200 ПРИ state != "user_action"
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-004")
def test_change_requisite_silent_200_on_non_user_action_state():
    """TC-04: State платежа != 'user_action' (новый токен, state=new) → тихий 200, PAPI не вызывается."""
    token = create_payment_token()
    resp  = _post_reselect(token, _RESELECT_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}, f"Expected empty body, got: {resp.text}"


@pytest.mark.tcid("RC-017")
def test_change_requisite_idempotent_on_non_user_action_state():
    """TC-17: Два запроса подряд на платёж в state != 'user_action' — оба 200 {}.
    PAPI не вызывается, PaymentStateSync push не отправляется."""
    token = create_payment_token()
    path  = _reselect_path(token)
    raw   = json.dumps(_RESELECT_BODY, separators=(",", ":"))
    for i in range(2):
        resp = _post_reselect(token, _RESELECT_BODY, headers=_make_headers(path, raw))
        assert resp.status_code == 200, \
            f"Request {i + 1}: Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json() == {}, \
            f"Request {i + 1}: Expected empty body, got: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-005")
def test_change_requisite_invalid_json_body(payment_token):
    """TC-05: Битый JSON в body — в отличие от /cancel, JSON не оборачивается в try/except.
    Ожидается 4xx."""
    path = _reselect_path(payment_token)
    resp = _post_reselect(payment_token, _INVALID_JSON,
                          headers=_make_headers(path, _INVALID_JSON))
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for invalid JSON, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-006")
def test_change_requisite_missing_session_id(payment_token):
    """TC-06: Нет Api-Session-ID. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = _reselect_path(payment_token)
    raw  = json.dumps(_RESELECT_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":  "application/json",
        "Api-Signature": _calc_sig(path, str(uuid.uuid4()), raw),
    }
    resp = _post_reselect(payment_token, _RESELECT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RC-007")
def test_change_requisite_missing_signature(payment_token):
    """TC-07: Нет Api-Signature. Ожидается 4xx (MissingHTTPHeader: Api-Signature)."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_reselect(payment_token, _RESELECT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RC-008")
def test_change_requisite_invalid_signature(payment_token):
    """TC-08: Невалидная подпись (строка из нулей). Ожидается 4xx (InvalidSignature)."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_reselect(payment_token, _RESELECT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RC-009")
def test_change_requisite_signature_from_old_url(payment_token):
    """TC-09: Подпись посчитана от старого пути /payments/.../reselect. Ожидается 4xx (InvalidSignature)."""
    old_path = _old_reselect_path(payment_token)
    raw      = json.dumps(_RESELECT_BODY, separators=(",", ":"))
    sid      = str(uuid.uuid4())
    headers  = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(old_path, sid, raw),
    }
    resp = _post_reselect(payment_token, _RESELECT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RC-010")
def test_change_requisite_signature_body_mismatch(payment_token):
    """TC-10: Подпись от body_A, отправлен body_B. Ожидается 4xx (InvalidSignature)."""
    path   = _reselect_path(payment_token)
    body_a = json.dumps({"payment_gateway_id": 1}, separators=(",", ":"))
    body_b = json.dumps({"payment_gateway_id": 2}, separators=(",", ":"))
    sid    = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body_a),
    }
    resp = _post_reselect(payment_token, body_b, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-011")
def test_change_requisite_invalid_token_format():
    """TC-11: Невалидный payment_token (не UUID). Ожидается 4xx (validation_uuid_decorator)."""
    resp = _post_reselect("not-a-uuid", _RESELECT_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("RC-012")
def test_change_requisite_nonexistent_token():
    """TC-12: Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx (PaymentNotFound)."""
    resp = _post_reselect("00000000-0000-4000-8000-000000000000", _RESELECT_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# РЕГРЕСС (state=new → тихий 200)
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-013b")
def test_change_requisite_old_endpoint_regression_silent():
    """TC-13 (state=new): Старый /payments/{token}/reselect с X-* заголовками, state=new → тихий 200 {}."""
    token = create_payment_token()
    resp  = _post_reselect_old(token, _RESELECT_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == {}, f"Expected empty body, got: {resp.text}"


@pytest.mark.tcid("RC-014")
def test_change_requisite_old_headers_on_new_url(payment_token):
    """TC-14: Новый URL + старые заголовки X-CUSTOMER-SESSION-ID / X-REQUEST-SIGNATURE.
    Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    old_path = _old_reselect_path(payment_token)
    raw      = json.dumps(_RESELECT_BODY, separators=(",", ":"))
    sid      = str(uuid.uuid4())
    headers  = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(old_path, sid, raw),
    }
    resp = _post_reselect(payment_token, _RESELECT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("RC-018")
def test_change_requisite_options_preflight(payment_token):
    """OPTIONS preflight /actions/transfer/change-requisite: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(_reselect_path(payment_token))
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "")
    assert "Api-Session-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "Api-Signature"  in allow, f"Api-Signature not in Allow-Headers: {allow}"
