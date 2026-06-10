"""
Тесты эндпоинта GET /api/v1/payment-sessions/{payment_token}
Аналог: GET /payments/{payment_token}

Подпись (GET, тело пустое):
  HMAC-SHA256(customer_mac_key, "GET\n{path}\n{Api-Session-ID}\n")
"""
import hashlib
import hmac
import uuid

import pytest
import requests

import _helpers.config as _cfg
from _helpers.validators import assert_error_response
from web_form.conftest import options_preflight

_WEB3_HOST = "https://web3preprod.testpaygate.com"
_BASE_PATH  = "/api/v1/payment-sessions"
_OLD_PATH   = "/payments"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _calc_get_sig(path: str, session_id: str) -> str:
    """HMAC-SHA256(customer_mac_key, GET\n{path}\n{session_id}\n)"""
    key = _cfg.CUSTOMER_MAC_KEY.encode()
    msg = f"GET\n{path}\n{session_id}\n".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _make_headers(path: str, session_id: str | None = None) -> dict[str, str]:
    sid = session_id or str(uuid.uuid4())
    return {
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_get_sig(path, sid),
    }


def _make_old_headers(old_path: str, session_id: str | None = None) -> dict[str, str]:
    sid = session_id or str(uuid.uuid4())
    return {
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_get_sig(old_path, sid),
    }


def _get(token: str, headers: dict | None = None) -> requests.Response:
    path = f"{_BASE_PATH}/{token}"
    h = headers if headers is not None else _make_headers(path)
    return requests.get(f"{_WEB3_HOST}{path}", headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _get_old(token: str, headers: dict | None = None) -> requests.Response:
    path = f"{_OLD_PATH}/{token}"
    h = headers if headers is not None else _make_old_headers(path)
    return requests.get(f"{_WEB3_HOST}{path}", headers=h, timeout=_cfg.HTTP_TIMEOUT)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("GP-001")
def test_get_payment_session(payment_token):
    """
    Получение данных платежа.

    Request:
      GET /api/v1/payment-sessions/{payment_token}
      Api-Session-ID: <uuid4>
      Api-Signature:  HMAC-SHA256(customer_mac_key, "GET\\n/api/v1/payment-sessions/{token}\\n{session_id}\\n")

    Response 200 OK:
      Content-Type: application/json
      {
        "service_id": "...",
        "state": "...",
        "payment_request": { ... },
        "theme": { ... }
      }
    """
    resp = _get(payment_token)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    for field in ("service_id", "state", "payment_request", "theme"):
        assert field in data, f"Missing field '{field}' in response: {list(data.keys())}"


@pytest.mark.tcid("GP-014")
def test_get_payment_session_options_preflight(payment_token):
    """
    OPTIONS preflight: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature.

    Request:
      OPTIONS /api/v1/payment-sessions/{payment_token}
      Origin: https://merchant.example.com
      Access-Control-Request-Method: GET
      Access-Control-Request-Headers: Api-Session-ID, Api-Signature, Content-Type

    Response 200/204:
      Access-Control-Allow-Headers: ..., Api-Session-ID, Api-Signature, ...
    """
    resp = options_preflight(f"{_BASE_PATH}/{payment_token}", request_method="GET")
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "")
    assert "Api-Session-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "Api-Signature"  in allow, f"Api-Signature not in Allow-Headers: {allow}"


@pytest.mark.tcid("GP-013")
def test_get_payment_session_response_identical_to_old(payment_token):
    """
    Ответы нового и старого эндпоинта идентичны для одного платежа.

    New request:
      GET /api/v1/payment-sessions/{token}
      Api-Session-ID: <uuid4>
      Api-Signature:  HMAC-SHA256(customer_mac_key, "GET\\n/api/v1/payment-sessions/{token}\\n{session_id}\\n")

    Old request:
      GET /payments/{token}
      X-CUSTOMER-SESSION-ID: <uuid4>
      X-REQUEST-SIGNATURE:   HMAC-SHA256(customer_mac_key, "GET\\n/payments/{token}\\n{session_id}\\n")

    Both → 200 OK, поля service_id / state / payment_request совпадают.
    """
    resp_new = _get(payment_token)
    resp_old = _get_old(payment_token)
    assert resp_new.status_code == 200, f"New endpoint: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 200, f"Old endpoint: {resp_old.status_code}: {resp_old.text}"
    data_new = resp_new.json()
    data_old = resp_old.json()
    # Сравниваем ключевые поля данных платежа
    for field in ("service_id", "state", "payment_request"):
        assert data_new.get(field) == data_old.get(field), \
            f"Field '{field}' differs: new={data_new.get(field)!r}, old={data_old.get(field)!r}"


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА
# ─────────────────────────────────────────────
@pytest.mark.tcid("GP-002")
@pytest.mark.skip(reason="Требует платёж в state=submitted с включённым bankList — настроить вручную")
def test_get_payment_session_submitted_with_banklist(payment_token):
    """Платёж в state=submitted, у сервиса включён bankList. В ответе присутствует bank_list."""
    resp = _get(payment_token)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "bank_list" in data, f"Missing bank_list in response: {list(data.keys())}"


@pytest.mark.tcid("GP-003")
@pytest.mark.skip(reason="Требует платёж в финальном состоянии с неистёкшим confirm_lifetime")
def test_get_payment_session_final_state_not_expired(payment_token):
    """Финальное состояние (success/fail), confirm_lifetime не истёк. Ожидается 200."""
    resp = _get(payment_token)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("GP-004")
@pytest.mark.skip(reason="Требует платёж в success/fail с истёкшим confirm_lifetime и need_expire_confirm=true")
def test_get_payment_session_final_state_expired(payment_token):
    """Финальное состояние, confirm_lifetime истёк. Ожидается 410 Gone."""
    resp = _get(payment_token)
    assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("status_code") == 410, f"Unexpected body: {data}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: отсутствующие заголовки
# ─────────────────────────────────────────────
@pytest.mark.tcid("GP-005")
def test_get_payment_session_missing_session_id(payment_token):
    """
    Нет Api-Session-ID. Ожидается 4xx.

    Request:
      GET /api/v1/payment-sessions/{payment_token}
      Api-Signature: HMAC-SHA256(customer_mac_key, ...)   # Api-Session-ID отсутствует

    Response 4xx:
      Content-Type: application/json
      { ... }   (ErrorResponse)
    """
    path = f"{_BASE_PATH}/{payment_token}"
    sid  = str(uuid.uuid4())
    headers = {"Api-Signature": _calc_get_sig(path, sid)}
    resp = _get(payment_token, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GP-006")
def test_get_payment_session_missing_signature(payment_token):
    """
    Нет Api-Signature. Ожидается 4xx.

    Request:
      GET /api/v1/payment-sessions/{payment_token}
      Api-Session-ID: <uuid4>   # Api-Signature отсутствует

    Response 4xx:
      { ... }   (ErrorResponse)
    """
    headers = {"Api-Session-ID": str(uuid.uuid4())}
    resp = _get(payment_token, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: подпись
# ─────────────────────────────────────────────
@pytest.mark.tcid("GP-007")
def test_get_payment_session_invalid_signature(payment_token):
    """
    Невалидная подпись (строка из нулей). Ожидается 4xx.

    Request:
      GET /api/v1/payment-sessions/{payment_token}
      Api-Session-ID: <uuid4>
      Api-Signature:  "0000000000000000000000000000000000000000000000000000000000000000"   (64 нуля)

    Response 4xx:
      { ... }   (ErrorResponse: signature mismatch)
    """
    headers = {
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _get(payment_token, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GP-008")
def test_get_payment_session_signature_from_old_url(payment_token):
    """
    Подпись посчитана от старого пути /payments/{token}. Ожидается 4xx.

    Request:
      GET /api/v1/payment-sessions/{payment_token}
      Api-Session-ID: <uuid4>
      Api-Signature:  HMAC-SHA256(customer_mac_key, "GET\\n/payments/{token}\\n{session_id}\\n")   # ← неверный path в сообщении

    Response 4xx:
      { ... }   (ErrorResponse: signature mismatch)
    """
    old_path = f"{_OLD_PATH}/{payment_token}"
    sid = str(uuid.uuid4())
    headers = {
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_get_sig(old_path, sid),
    }
    resp = _get(payment_token, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("GP-009")
def test_get_payment_session_invalid_token_format():
    """
    Невалидный payment_token (не UUID). Ожидается 4xx.

    Request:
      GET /api/v1/payment-sessions/not-a-uuid
      Api-Session-ID: <uuid4>
      Api-Signature:  HMAC-SHA256(customer_mac_key, "GET\\n/api/v1/payment-sessions/not-a-uuid\\n{session_id}\\n")

    Response 4xx:
      { ... }   (ErrorResponse: validation_uuid_decorator)
    """
    resp = _get("not-a-uuid")
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GP-010")
def test_get_payment_session_nonexistent_token():
    """
    Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx.

    Request:
      GET /api/v1/payment-sessions/00000000-0000-4000-8000-000000000000
      Api-Session-ID: <uuid4>
      Api-Signature:  HMAC-SHA256(customer_mac_key, "GET\\n/api/v1/payment-sessions/00000000-...\\n{session_id}\\n")

    Response 4xx:
      { ... }   (ErrorResponse: PaymentNotFound)
    """
    resp = _get("00000000-0000-4000-8000-000000000000")
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("GP-011")
def test_get_payment_session_old_endpoint_regression(payment_token):
    """
    Регресс: старый /payments/{token} с X-* заголовками продолжает работать.

    Request:
      GET /payments/{payment_token}
      X-CUSTOMER-SESSION-ID: <uuid4>
      X-REQUEST-SIGNATURE:   HMAC-SHA256(customer_mac_key, "GET\\n/payments/{token}\\n{session_id}\\n")

    Response 200 OK:
      Content-Type: application/json
      { "state": "...", ... }
    """
    resp = _get_old(payment_token)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "state" in resp.json(), f"Missing 'state' in old endpoint response"


@pytest.mark.tcid("GP-012")
def test_get_payment_session_old_headers_on_new_url(payment_token):
    """
    Новый URL + старые заголовки X-*. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID).

    Request:
      GET /api/v1/payment-sessions/{payment_token}
      X-CUSTOMER-SESSION-ID: <uuid4>
      X-REQUEST-SIGNATURE:   HMAC-SHA256(customer_mac_key, "GET\\n/payments/{token}\\n{session_id}\\n")   # старые заголовки

    Response 4xx:
      { ... }   (ErrorResponse: MissingHTTPHeader Api-Session-ID)
    """
    old_path = f"{_OLD_PATH}/{payment_token}"
    sid = str(uuid.uuid4())
    headers = {
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_get_sig(old_path, sid),
    }
    resp = _get(payment_token, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
