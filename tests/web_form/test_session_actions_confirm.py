"""
Тесты эндпоинта подтверждения пользовательского действия (PROC-73):
  POST /api/v1/payment-sessions/{payment_token}/actions/transfer/confirm
  (аналог /payments/{payment_token}/user_action)

Подпись (POST):
  HMAC-SHA256(customer_mac_key, "POST\n{path}\n{Api-Session-ID}\n{raw_body}")

Поведение:
  - resultObject обязателен; иначе InvalidStateData → 4xx
  - State == "user_action": manual.WebpayV3UserAction → PAPI; state → "pending"/"skip_pending"
  - BadStatusForUserAction: 201 с response_entity, state не меняется
  - Старый /payments/{token}/user_action не требует заголовков авторизации (регресс)
  - Новый эндпоинт требует Api-Session-ID + Api-Signature с валидной HMAC-подписью
"""
import hashlib
import hmac
import json
import uuid

import pytest
import requests

import _helpers.config as _cfg
from _helpers.validators import assert_error_response, parity_check
from web_form.conftest import create_payment_token, options_preflight

_WEB3_HOST    = "https://web3preprod.testpaygate.com"
_BASE_PATH    = "/api/v1/payment-sessions"
_OLD_PATH     = "/payments"
_INVALID_JSON = "{not_a_json"

_RESULT_BODY       = {"resultObject": {"some": "data"}}
_RESULT_BODY_SKIP  = {"resultObject": {"some": "data"}, "skip_pending": True}
_RESULT_BODY_SKIP_INNER = {"resultObject": {"skip_pending": True, "some": "data"}}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _confirm_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/actions/transfer/confirm"


def _old_confirm_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/user_action"


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


def _post_confirm(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = _confirm_path(token)
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_confirm_old(token: str, body: dict | str) -> requests.Response:
    """Вызов старого эндпоинта — без Api-* заголовков (auth не валидируется)."""
    path = _old_confirm_path(token)
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=raw,
        headers={"Content-Type": "application/json"},
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ─────────────────────────────────────────────
# КЕЙСЫ: state == "user_action" (требуют ручной настройки)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CA-001")
@pytest.mark.skip(reason="Требует платёж в state 'user_action', skip_pending=false — настроить вручную")
def test_confirm_user_action_skip_pending_false(payment_token):
    """TC-01: resultObject + skip_pending=false, state=user_action.
    Ожидается 201; state → 'pending'; PaymentStateSync push отправлен."""
    resp = _post_confirm(payment_token, _RESULT_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CA-002")
@pytest.mark.skip(reason="Требует платёж в state 'user_action', skip_pending=true в body — настроить вручную")
def test_confirm_user_action_skip_pending_true_body(payment_token):
    """TC-02: resultObject + skip_pending=true в теле, state=user_action.
    Ожидается 201; ветка skip_pending → set_pending_payment_state + send_skip_pending_state."""
    resp = _post_confirm(payment_token, _RESULT_BODY_SKIP)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CA-003")
@pytest.mark.skip(reason="Требует платёж в state 'user_action', skip_pending=true внутри resultObject — настроить вручную")
def test_confirm_user_action_skip_pending_true_in_result_object(payment_token):
    """TC-03: skip_pending=true внутри resultObject (читается из result_object.skip_pending если dict).
    Ожидается 201; та же ветка skip_pending."""
    resp = _post_confirm(payment_token, _RESULT_BODY_SKIP_INNER)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CA-004")
@pytest.mark.skip(reason="Требует смоделированный BadStatusForUserAction на стороне PAPI — настроить вручную")
def test_confirm_bad_status_for_user_action(payment_token):
    """TC-04: PAPI вернул BadStatusForUserAction.
    Ожидается 201 с response_entity; state платежа НЕ меняется; PaymentStateSync push не отправлен."""
    resp = _post_confirm(payment_token, _RESULT_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CA-017")
@pytest.mark.skip(reason="Требует state 'user_action' на двух платежах одновременно — настроить вручную")
def test_confirm_behavior_identical_to_old_endpoint():
    """TC-17: Одинаковое поведение старого и нового эндпоинта при state='user_action'.
    Оба возвращают 201; PaymentUserActionResultObject (TransactionId, OrderId, SiteId) идентичен."""
    token_new = create_payment_token()
    token_old = create_payment_token()
    resp_new  = _post_confirm(token_new, _RESULT_BODY)
    resp_old  = _post_confirm_old(token_old, _RESULT_BODY)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == 201, f"New: {resp_new.status_code}: {resp_new.text}"
        assert resp_old.status_code == 201, f"Old: {resp_old.status_code}: {resp_old.text}"


@pytest.mark.tcid("CA-018")
@pytest.mark.skip(reason="Требует WS-клиент + платёж в state 'user_action' — настроить вручную")
def test_confirm_ws_push_pending(payment_token):
    """TC-18: После /actions/transfer/confirm WS-клиент /api/v1/payment-sessions/{token}/ws
    получает фрейм с payment_state, state='pending' (или 'skip_pending')."""
    resp = _post_confirm(payment_token, _RESULT_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    # Проверка WS-фрейма выполняется вручную


@pytest.mark.tcid("CA-019")
@pytest.mark.skip(reason="Требует платёж в state 'user_action' + доступ к PAPI-запросу — настроить вручную")
def test_confirm_user_click_time_present(payment_token):
    """TC-19: В PAPI-запросе UserActionResultObject содержит user_click_time как timestamp."""
    resp = _post_confirm(payment_token, _RESULT_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    # Проверяется в логах Kibana / мониторинге PAPI


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("CA-005")
def test_confirm_missing_result_object(payment_token):
    """TC-05: resultObject отсутствует в теле → 4xx (InvalidStateData)."""
    resp = _post_confirm(payment_token, {"skip_pending": False})
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for missing resultObject, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-006")
def test_confirm_empty_body(payment_token):
    """TC-06: Пустое тело {} → 4xx (InvalidStateData)."""
    resp = _post_confirm(payment_token, {})
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for empty body, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-007")
def test_confirm_invalid_json_body(payment_token):
    """TC-07: Битый JSON в body → 4xx (ошибка парсинга JSON)."""
    path = _confirm_path(payment_token)
    resp = _post_confirm(payment_token, _INVALID_JSON,
                         headers=_make_headers(path, _INVALID_JSON))
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for invalid JSON, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("CA-008")
def test_confirm_missing_session_id(payment_token):
    """TC-08: Нет Api-Session-ID → 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = _confirm_path(payment_token)
    raw  = json.dumps(_RESULT_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":  "application/json",
        "Api-Signature": _calc_sig(path, str(uuid.uuid4()), raw),
    }
    resp = _post_confirm(payment_token, _RESULT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for missing Api-Session-ID, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-009")
def test_confirm_missing_signature(payment_token):
    """TC-09: Нет Api-Signature → 4xx (MissingHTTPHeader: Api-Signature)."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_confirm(payment_token, _RESULT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for missing Api-Signature, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-010")
def test_confirm_invalid_signature(payment_token):
    """TC-10: Невалидная подпись (строка из нулей) → 4xx (InvalidSignature)."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_confirm(payment_token, _RESULT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for invalid signature, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-011")
def test_confirm_signature_from_old_url(payment_token):
    """TC-11: Подпись посчитана от старого пути /payments/.../user_action → 4xx (InvalidSignature)."""
    old_path = _old_confirm_path(payment_token)
    raw      = json.dumps(_RESULT_BODY, separators=(",", ":"))
    sid      = str(uuid.uuid4())
    headers  = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(old_path, sid, raw),
    }
    resp = _post_confirm(payment_token, _RESULT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for signature from old URL, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-012")
def test_confirm_signature_body_mismatch(payment_token):
    """TC-12: Подпись от body_A, отправлен body_B → 4xx (InvalidSignature)."""
    path   = _confirm_path(payment_token)
    body_a = json.dumps({"resultObject": {"x": 1}}, separators=(",", ":"))
    body_b = json.dumps({"resultObject": {"x": 2}}, separators=(",", ":"))
    sid    = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body_a),
    }
    resp = _post_confirm(payment_token, body_b, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for body mismatch, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("CA-013")
def test_confirm_invalid_token_format():
    """TC-13: Невалидный payment_token (не UUID) → 4xx (validation_uuid_decorator)."""
    resp = _post_confirm("not-a-uuid", _RESULT_BODY)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for non-UUID token, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CA-014")
def test_confirm_nonexistent_token():
    """TC-14: Несуществующий payment_token (валидный UUID, не в БД) → 4xx (PaymentNotFound)."""
    resp = _post_confirm("00000000-0000-4000-8000-000000000000", _RESULT_BODY)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for nonexistent token, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# РЕГРЕСС СТАРОГО ЭНДПОИНТА
# ─────────────────────────────────────────────
@pytest.mark.tcid("CA-015")
def test_confirm_old_endpoint_regression_no_auth():
    """TC-15: Старый /payments/{token}/user_action без Api-* заголовков и без подписи.
    Ожидается 201 — авторизация на старом эндпоинте не появилась (signature_validate=pass)."""
    token = create_payment_token()
    resp  = _post_confirm_old(token, _RESULT_BODY)
    assert resp.status_code == 201, \
        f"Expected 201 (no auth on old endpoint), got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CA-016")
def test_confirm_old_headers_on_new_url(payment_token):
    """TC-16: Новый URL + старые заголовки X-CUSTOMER-SESSION-ID / X-REQUEST-SIGNATURE.
    Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    old_path = _old_confirm_path(payment_token)
    raw      = json.dumps(_RESULT_BODY, separators=(",", ":"))
    sid      = str(uuid.uuid4())
    headers  = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(old_path, sid, raw),
    }
    resp = _post_confirm(payment_token, _RESULT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for old headers on new URL, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT (CORS)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CA-020")
def test_confirm_options_preflight(payment_token):
    """OPTIONS preflight: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(_confirm_path(payment_token))
    assert resp.status_code in (200, 204), \
        f"Expected 200/204 for OPTIONS, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "").upper()
    assert "API-SESSION-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow!r}"
    assert "API-SIGNATURE"  in allow, f"Api-Signature not in Allow-Headers: {allow!r}"
