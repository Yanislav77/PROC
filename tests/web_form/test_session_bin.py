"""
Тесты эндпоинта BIN-lookup:
  POST /api/v1/payment-sessions/{payment_token}/bin  (аналог /payments/{payment_token}/get_bin_info)

Отличие от старого эндпоинта: новый требует Api-Session-ID + Api-Signature.
Старый /payments/{payment_token}/get_bin_info авторизации не имеет.

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

_BIN_6       = {"bin": "411111"}
_BIN_8       = {"bin": "41111111"}
_BIN_UNKNOWN = {"bin": "000000"}
_BIN_EMPTY   = {}
_BIN_INVALID_JSON = "{not_a_json"


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


def _post_bin(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = f"{_BASE_PATH}/{token}/bin"
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_bin_old(token: str, body: dict) -> requests.Response:
    """Старый эндпоинт — авторизация отсутствует, заголовки не нужны."""
    path = f"{_OLD_PATH}/{token}/get_bin_info"
    raw  = json.dumps(body, separators=(",", ":"))
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=raw,
        headers={"Content-Type": "application/json"},
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-001")
def test_bin_lookup_6digits(payment_token):
    """BIN-lookup для 6-значного BIN. Ожидается 200, ответ содержит bank_info и provider_country."""
    resp = _post_bin(payment_token, _BIN_6)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "bank_info"       in data, f"Missing bank_info: {data}"
    assert "is_4symbol_cvc"  in data, f"Missing is_4symbol_cvc: {data}"
    assert "provider_country" in data, f"Missing provider_country: {data}"


@pytest.mark.tcid("BI-006")
def test_bin_lookup_unknown_bin(payment_token):
    """Неизвестный BIN (000000). Ожидается 200, provider_country = null."""
    resp = _post_bin(payment_token, _BIN_UNKNOWN)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("provider_country") is None, \
        f"Expected provider_country=null for unknown BIN, got: {data.get('provider_country')}"


@pytest.mark.tcid("BI-012")
def test_bin_lookup_empty_body(payment_token):
    """Пустое тело {}. Ожидается 200 (bin_val='', provider_country=null)."""
    resp = _post_bin(payment_token, _BIN_EMPTY)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("provider_country") is None, \
        f"Expected provider_country=null for empty bin, got: {data.get('provider_country')}"


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА КОНФИГ СЕРВИСА
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-002")
@pytest.mark.skip(reason="Требует CONFIG.BinLookup.UseExtended8Bins=true — проверить конфиг препрода")
def test_bin_lookup_8digits_extended(payment_token):
    """8-значный BIN при UseExtended8Bins=true. Ожидается 200 с extended-данными."""
    resp = _post_bin(payment_token, _BIN_8)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "provider_country" in resp.json()


@pytest.mark.tcid("BI-003")
@pytest.mark.skip(reason="Требует BIN карты МИР — подобрать вручную")
def test_bin_lookup_mir_card(payment_token):
    """BIN карты МИР — bank_info.mir=True, convert_currency не вызывается."""
    mir_bin = {"bin": "220000"}  # заменить на реальный MIR BIN
    resp = _post_bin(payment_token, mir_bin)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["bank_info"]["mir"] is True, f"Expected mir=True: {data['bank_info']}"
    assert data.get("convert_data") is None, "convert_data should be null for MIR card"


@pytest.mark.tcid("BI-004")
@pytest.mark.skip(reason="Требует сервис с currency_code=RUB, spg.is_routing=1 и иностранный не-МИР BIN")
def test_bin_lookup_foreign_card_routing_enabled(payment_token):
    """Иностранная карта + is_routing=1 + RUB-сервис — convert_currency вызывается."""
    foreign_bin = {"bin": "400000", "client_amount": 1500}  # заменить на реальный иностранный BIN
    resp = _post_bin(payment_token, foreign_bin)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-005")
@pytest.mark.skip(reason="Требует сервис с is_routing != 1 и иностранный BIN")
def test_bin_lookup_foreign_card_routing_disabled(payment_token):
    """Иностранная карта + is_routing != 1 — convert_currency не вызывается."""
    foreign_bin = {"bin": "400000"}  # заменить на реальный иностранный BIN
    resp = _post_bin(payment_token, foreign_bin)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json().get("convert_data") is None


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-007")
def test_bin_lookup_missing_session_id(payment_token):
    """Нет Api-Session-ID. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Signature": _calc_sig(path, sid, raw),
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("BI-008")
def test_bin_lookup_missing_signature(payment_token):
    """Нет Api-Signature. Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("BI-009")
def test_bin_lookup_invalid_signature(payment_token):
    """Невалидная подпись (строка из нулей). Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-010")
def test_bin_lookup_invalid_token_format():
    """Невалидный payment_token (не UUID). Ожидается 4xx."""
    resp = _post_bin("not-a-uuid", _BIN_6)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("BI-011")
def test_bin_lookup_nonexistent_token():
    """Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx."""
    resp = _post_bin("00000000-0000-4000-8000-000000000000", _BIN_6)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-013")
def test_bin_lookup_invalid_json(payment_token):
    """Битый JSON в теле. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, _BIN_INVALID_JSON),
    }
    resp = _post_bin(payment_token, _BIN_INVALID_JSON, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-014")
def test_bin_lookup_old_endpoint_regression(payment_token):
    """Регресс: старый /payments/{token}/get_bin_info без авторизации продолжает работать."""
    resp = _post_bin_old(payment_token, _BIN_6)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "bank_info" in resp.json(), f"Missing bank_info in old endpoint response"


@pytest.mark.tcid("BI-015")
def test_bin_lookup_response_identical_to_old(payment_token):
    """Ответы нового и старого эндпоинта идентичны для одного BIN."""
    resp_new = _post_bin(payment_token, _BIN_6)
    resp_old = _post_bin_old(payment_token, _BIN_6)
    assert resp_new.status_code == 200, f"New: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 200, f"Old: {resp_old.status_code}: {resp_old.text}"
    data_new = resp_new.json()
    data_old = resp_old.json()
    for field in ("bank_info", "is_4symbol_cvc", "provider_country"):
        assert data_new.get(field) == data_old.get(field), \
            f"Field '{field}' differs: new={data_new.get(field)!r}, old={data_old.get(field)!r}"


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-016")
def test_bin_options_preflight(payment_token):
    """OPTIONS preflight /bin: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(f"{_BASE_PATH}/{payment_token}/bin")
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "")
    assert "Api-Session-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "Api-Signature"  in allow, f"Api-Signature not in Allow-Headers: {allow}"
