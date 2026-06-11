"""
Тесты эндпоинта UI-логирования:
  POST /api/v1/payment-sessions/{payment_token}/ui/logs    (аналог /payments/{payment_token}/ui_logger)
  POST /api/v1/payment-sessions/ui/logs                    (аналог /payments/ui_logger)

Изменения по сравнению со старым эндпоинтом /payments/<token>/ui_logger:
  Параметр              Старый                            Новый
  Путь (с токеном)      /payments/<token>/ui_logger       /api/v1/payment-sessions/<token>/ui/logs
  Путь (без токена)     /payments/ui_logger               /api/v1/payment-sessions/ui/logs
  Заголовок сессии      X-CUSTOMER-SESSION-ID             Api-Session-ID
  Заголовок подписи     X-REQUEST-SIGNATURE               Api-Signature
  Идемпотентность       —                                 Api-Idempotency-Key (новый обязательный заголовок)
  Тело запроса          {message, params}                 без изменений
  Тело ответа           {"message": "Log with id ..."}    без изменений
  HTTP-метод            POST                              POST
  Алгоритм подписи      signature_v3                      без изменений

Обратная совместимость: старый эндпоинт с X-* заголовками продолжает работать (UL-012).
"""
import hashlib
import hmac
import json
import uuid

import pytest
import requests

import _helpers.config as _cfg
from _helpers.validators import assert_error_response
from web_form.conftest import options_preflight

_WEB3_HOST = "https://web3preprod.testpaygate.com"
_BASE_PATH  = "/api/v1/payment-sessions"

_LOG_BODY = {
    "message": "card_form_opened",
    "params": {
        "device": {"platform": "web"},
        "step": "card",
    },
}
_END_BODY = {
    "message": "payment_flow_end",
    "params": {
        "device": {"platform": "web"},
        "step": "card",
    },
}
_EMPTY_BODY = {}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _calc_sig(path_qs: str, session_id: str, raw_body: str) -> str:
    """HMAC-SHA256(CUSTOMER_MAC_KEY, POST\n{path}\n{session_id}\n{body})"""
    key = _cfg.CUSTOMER_MAC_KEY.encode()
    msg = f"POST\n{path_qs}\n{session_id}\n{raw_body}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _make_headers(path_qs: str, raw_body: str = "", session_id: str | None = None) -> dict[str, str]:
    sid = session_id or str(uuid.uuid4())
    return {
        "Content-Type":        "application/json",
        "Api-Session-ID":      sid,
        "Api-Signature":       _calc_sig(path_qs, sid, raw_body),
        "Api-Idempotency-Key": str(uuid.uuid4()),
    }


def _post(token: str, body: dict, headers: dict | None = None) -> requests.Response:
    from _helpers.validators import assert_idempotency_echo
    path = f"{_BASE_PATH}/{token}/ui/logs"
    raw  = json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    r    = requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)
    assert_idempotency_echo(h, r)
    return r


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-001")
def test_ui_log_with_token(payment_token):
    """Лог с payment_token, обычное событие. Ожидается 200."""
    resp = _post(payment_token, _LOG_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "message" in resp.json(), f"Missing 'message' in response: {resp.text}"


@pytest.mark.tcid("UL-002")
def test_ui_log_with_token_end_event(payment_token):
    """Лог с payment_token, событие payment_flow_end. Ожидается 200."""
    resp = _post(payment_token, _END_BODY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: отсутствующие заголовки
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-004")
def test_ui_log_missing_session_id(payment_token):
    """Нет Api-Session-ID. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/ui/logs"
    raw  = json.dumps(_LOG_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":        "application/json",
        "Api-Signature":       _calc_sig(path, sid, raw),
        "Api-Idempotency-Key": str(uuid.uuid4()),
    }
    resp = _post(payment_token, _LOG_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("UL-005")
def test_ui_log_missing_signature(payment_token):
    """Нет Api-Signature. Ожидается 4xx."""
    headers = {
        "Content-Type":        "application/json",
        "Api-Session-ID":      str(uuid.uuid4()),
        "Api-Idempotency-Key": str(uuid.uuid4()),
    }
    resp = _post(payment_token, _LOG_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("UL-006")
def test_ui_log_missing_idempotency_key(payment_token):
    """Нет Api-Idempotency-Key (обязательный). Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/ui/logs"
    raw  = json.dumps(_LOG_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw),
    }
    resp = _post(payment_token, _LOG_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: подпись
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-007")
def test_ui_log_invalid_signature(payment_token):
    """Невалидная подпись (строка из нулей). Ожидается 4xx."""
    headers = {
        "Content-Type":        "application/json",
        "Api-Session-ID":      str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Idempotency-Key": str(uuid.uuid4()),
    }
    resp = _post(payment_token, _LOG_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("UL-008")
def test_ui_log_signature_from_old_url(payment_token):
    """Подпись посчитана от старого пути /payments/.../ui_logger. Ожидается 4xx."""
    old_path = f"/payments/{payment_token}/ui_logger"
    raw  = json.dumps(_LOG_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":        "application/json",
        "Api-Session-ID":      sid,
        "Api-Signature":       _calc_sig(old_path, sid, raw),
        "Api-Idempotency-Key": str(uuid.uuid4()),
    }
    resp = _post(payment_token, _LOG_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-009")
def test_ui_log_invalid_token_format():
    """Невалидный payment_token (не UUID). Ожидается 4xx."""
    resp = _post("not-a-uuid", _LOG_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("UL-010")
def test_ui_log_nonexistent_token():
    """Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx."""
    resp = _post("00000000-0000-4000-8000-000000000000", _LOG_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-011")
def test_ui_log_empty_body(payment_token):
    """Пустое тело {}. Ожидается 4xx (MessageOrParamsNotFound)."""
    resp = _post(payment_token, _EMPTY_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-012")
def test_ui_log_old_endpoint_regression(payment_token):
    """Регресс: старый /payments/{token}/ui_logger с X-* заголовками продолжает работать."""
    path = f"/payments/{payment_token}/ui_logger"
    raw  = json.dumps(_LOG_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw),
    }
    resp = requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=headers, timeout=_cfg.HTTP_TIMEOUT)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("UL-013")
def test_ui_log_old_headers_on_new_url(payment_token):
    """Новый URL + старые заголовки X-*. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = f"{_BASE_PATH}/{payment_token}/ui/logs"
    raw  = json.dumps(_LOG_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw),
        "Api-Idempotency-Key":   str(uuid.uuid4()),
    }
    resp = _post(payment_token, _LOG_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("UL-014")
def test_ui_logs_options_preflight(payment_token):
    """OPTIONS preflight /ui/logs: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(f"{_BASE_PATH}/{payment_token}/ui/logs")
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "").upper()
    assert "API-SESSION-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "API-SIGNATURE"  in allow, f"Api-Signature not in Allow-Headers: {allow}"
