"""
Тесты эндпоинта lookup'а страны по номеру телефона:
  POST /api/v1/payment-sessions/{payment_token}/phone  (аналог /payments/{payment_token}/get_phone_info)

Отличия от старого эндпоинта:
  - Обязательна авторизация: Api-Session-ID + Api-Signature
  - Валидируется UUID-формат payment_token
  - payment_token НЕ используется в бизнес-логике (load_payment не вызывается)
  - Несуществующий UUID → 200 OK (не 4xx)

Подпись (POST):
  HMAC-SHA256(customer_mac_key, "POST\n{path}\n{Api-Session-ID}\n{raw_body}")
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
_OLD_PATH   = "/payments"

_PHONE_RU    = {"phone": "+79991234567"}
_PHONE_US    = {"phone": "+14155551234"}
_PHONE_EMPTY = {"phone": ""}
_PHONE_NONE  = {}
_PHONE_BAD   = {"phone": "abc123"}
_INVALID_JSON = "{not_a_json"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
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


def _post_phone(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = f"{_BASE_PATH}/{token}/phone"
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_phone_old(token: str, body: dict) -> requests.Response:
    """Старый эндпоинт — без авторизации и UUID-валидации."""
    raw = json.dumps(body, separators=(",", ":"))
    return requests.post(
        f"{_WEB3_HOST}{_OLD_PATH}/{token}/get_phone_info",
        data=raw,
        headers={"Content-Type": "application/json"},
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _assert_null_country(resp: requests.Response) -> None:
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json().get("provider_country") is None, \
        f"Expected provider_country=null, got: {resp.json()}"


# ─────────────────────────────────────────────
# HAPPY PATH — lookup
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-001")
def test_phone_lookup_russian_number(payment_token):
    """Lookup российского номера. Ожидается 200, provider_country с code=RU."""
    resp = _post_phone(payment_token, _PHONE_RU)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    country = data.get("provider_country")
    assert country is not None, f"Expected provider_country to be filled: {data}"
    assert country.get("code") == "RU", f"Expected code=RU, got: {country}"
    assert "name_ru" in country and "name_en" in country, f"Missing name fields: {country}"


@pytest.mark.tcid("PH-002")
def test_phone_lookup_foreign_number(payment_token):
    """Lookup американского номера. Ожидается 200, provider_country с code=US."""
    resp = _post_phone(payment_token, _PHONE_US)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    country = resp.json().get("provider_country")
    assert country is not None, f"Expected provider_country to be filled"
    assert country.get("code") == "US", f"Expected code=US, got: {country}"


# ─────────────────────────────────────────────
# HAPPY PATH — граничные случаи возвращают null
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-003")
def test_phone_lookup_empty_string(payment_token):
    """Пустой phone. Ожидается 200, provider_country=null."""
    _assert_null_country(_post_phone(payment_token, _PHONE_EMPTY))


@pytest.mark.tcid("PH-004")
def test_phone_lookup_missing_field(payment_token):
    """Поле phone отсутствует в теле. Ожидается 200, provider_country=null."""
    _assert_null_country(_post_phone(payment_token, _PHONE_NONE))


@pytest.mark.tcid("PH-005")
def test_phone_lookup_invalid_format(payment_token):
    """Нераспознаваемый номер (не телефон). Ожидается 200, provider_country=null."""
    _assert_null_country(_post_phone(payment_token, _PHONE_BAD))


@pytest.mark.tcid("PH-017")
def test_phone_lookup_nonexistent_token():
    """Валидный UUID, которого нет в БД → 200 (load_payment не вызывается)."""
    _assert_null_country(
        _post_phone("00000000-0000-4000-8000-000000000000", _PHONE_NONE)
    )


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-006")
def test_phone_lookup_missing_session_id(payment_token):
    """Нет Api-Session-ID. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/phone"
    raw  = json.dumps(_PHONE_RU, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Signature": _calc_sig(path, sid, raw),
    }
    resp = _post_phone(payment_token, _PHONE_RU, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PH-007")
def test_phone_lookup_missing_signature(payment_token):
    """Нет Api-Signature. Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_phone(payment_token, _PHONE_RU, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PH-008")
def test_phone_lookup_invalid_signature(payment_token):
    """Невалидная подпись (строка из нулей). Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_phone(payment_token, _PHONE_RU, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PH-009")
def test_phone_lookup_signature_from_old_url(payment_token):
    """Подпись посчитана от старого пути /payments/.../get_phone_info. Ожидается 4xx."""
    old_path = f"{_OLD_PATH}/{payment_token}/get_phone_info"
    raw  = json.dumps(_PHONE_RU, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(old_path, sid, raw),
    }
    resp = _post_phone(payment_token, _PHONE_RU, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PH-010")
def test_phone_lookup_signature_body_mismatch(payment_token):
    """Подпись посчитана от body_A, отправлен body_B. Ожидается 4xx."""
    path   = f"{_BASE_PATH}/{payment_token}/phone"
    raw_a  = json.dumps(_PHONE_RU, separators=(",", ":"))
    raw_b  = json.dumps(_PHONE_US, separators=(",", ":"))
    sid    = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw_a),  # подпись от RU-номера
    }
    resp = _post_phone(payment_token, _PHONE_US, headers=headers)  # тело US-номера
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-011")
def test_phone_lookup_invalid_token_format():
    """Невалидный payment_token (не UUID). Ожидается 4xx (validation_uuid_decorator)."""
    resp = _post_phone("not-a-uuid", _PHONE_RU)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-012")
def test_phone_lookup_invalid_json(payment_token):
    """Битый JSON в теле. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/phone"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, _INVALID_JSON),
    }
    resp = _post_phone(payment_token, _INVALID_JSON, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PH-015")
def test_phone_lookup_old_headers_on_new_url(payment_token):
    """Новый URL + старые заголовки X-*. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = f"{_OLD_PATH}/{payment_token}/get_phone_info"
    raw  = json.dumps(_PHONE_RU, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw),
    }
    resp = _post_phone(payment_token, _PHONE_RU, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-013")
def test_phone_lookup_old_endpoint_no_auth(payment_token):
    """Регресс: старый /payments/{token}/get_phone_info без авторизации продолжает работать."""
    resp = _post_phone_old(payment_token, _PHONE_RU)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "provider_country" in resp.json(), f"Missing provider_country in old response"


@pytest.mark.tcid("PH-014")
def test_phone_lookup_old_endpoint_accepts_non_uuid_token():
    """Регресс: старый эндпоинт принимает не-UUID в токене (UUID не валидируется)."""
    resp = _post_phone_old("anything-not-uuid", _PHONE_RU)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PH-016")
def test_phone_lookup_response_identical_to_old(payment_token):
    """Ответы нового и старого эндпоинта идентичны для одного номера."""
    resp_new = _post_phone(payment_token, _PHONE_RU)
    resp_old = _post_phone_old(payment_token, _PHONE_RU)
    assert resp_new.status_code == 200, f"New: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 200, f"Old: {resp_old.status_code}: {resp_old.text}"
    assert resp_new.json() == resp_old.json(), \
        f"Responses differ:\n  new: {resp_new.json()}\n  old: {resp_old.json()}"


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("PH-018")
def test_phone_options_preflight(payment_token):
    """OPTIONS preflight /phone: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(f"{_BASE_PATH}/{payment_token}/phone")
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "")
    assert "Api-Session-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "Api-Signature"  in allow, f"Api-Signature not in Allow-Headers: {allow}"
