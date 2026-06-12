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
from _helpers.validators import assert_error_response, parity_check
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
@pytest.fixture
def bin_8digit(request):
    """8-значный BIN для BI-002. Передать через: pytest --bin-8digit <BIN>"""
    b = request.config.getoption("--bin-8digit")
    if not b:
        pytest.skip(
            "Требует CONFIG.BinLookup.UseExtended8Bins=true — "
            "передайте BIN: pytest --bin-8digit <8digits>"
        )
    return b


@pytest.fixture
def bin_foreign_routing(request):
    """Иностранный BIN для BI-004. Передать через: pytest --bin-foreign-routing <BIN>"""
    b = request.config.getoption("--bin-foreign-routing")
    if not b:
        pytest.skip(
            "Требует сервис с currency_code=RUB, spg.is_routing=1 и иностранный не-МИР BIN — "
            "передайте BIN: pytest --bin-foreign-routing <BIN>"
        )
    return b


@pytest.fixture
def bin_foreign_no_routing(request):
    """Иностранный BIN для BI-005. Передать через: pytest --bin-foreign-no-routing <BIN>"""
    b = request.config.getoption("--bin-foreign-no-routing")
    if not b:
        pytest.skip(
            "Требует сервис с is_routing != 1 и иностранный BIN — "
            "передайте BIN: pytest --bin-foreign-no-routing <BIN>"
        )
    return b


@pytest.mark.tcid("BI-002")
def test_bin_lookup_8digits_extended(payment_token, bin_8digit):
    """8-значный BIN при UseExtended8Bins=true. Ожидается 200 с extended-данными."""
    resp = _post_bin(payment_token, {"bin": bin_8digit})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "provider_country" in resp.json()


@pytest.mark.tcid("BI-003")
def test_bin_lookup_mir_card(payment_token):
    """BIN карты МИР — bank_info.mir=True, convert_currency не вызывается."""
    mir_bin = {"bin": "123666"}
    resp = _post_bin(payment_token, mir_bin)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["bank_info"]["mir"] is True, f"Expected mir=True: {data['bank_info']}"
    assert data.get("convert_data") is None, "convert_data should be null for MIR card"


@pytest.mark.tcid("BI-004")
def test_bin_lookup_foreign_card_routing_enabled(payment_token, bin_foreign_routing):
    """Иностранная карта + is_routing=1 + RUB-сервис — convert_currency вызывается."""
    resp = _post_bin(payment_token, {"bin": bin_foreign_routing, "client_amount": 1500})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-005")
def test_bin_lookup_foreign_card_routing_disabled(payment_token, bin_foreign_no_routing):
    """Иностранная карта + is_routing != 1 — convert_currency не вызывается."""
    resp = _post_bin(payment_token, {"bin": bin_foreign_no_routing})
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
    with parity_check(lambda: resp_old):
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
    allow = resp.headers.get("Access-Control-Allow-Headers", "").upper()
    assert "API-SESSION-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "API-SIGNATURE"  in allow, f"Api-Signature not in Allow-Headers: {allow}"


# ─────────────────────────────────────────────
# ФОРМАТ BIN
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-017")
def test_bin_whitespace_only(payment_token):
    """BIN только из пробелов. Ожидается не 500, provider_country=null."""
    resp = _post_bin(payment_token, {"bin": "      "})
    assert resp.status_code != 500, f"Got 500: {resp.text}"
    if resp.status_code == 200:
        assert resp.json().get("provider_country") is None, \
            f"Expected provider_country=null for whitespace BIN: {resp.json()}"


@pytest.mark.tcid("BI-018")
def test_bin_negative_string(payment_token):
    """BIN — отрицательное число в строке. Ожидается не 500."""
    resp = _post_bin(payment_token, {"bin": "-41111"})
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-019")
def test_bin_as_integer(payment_token):
    """BIN передан как integer, а не строка. Фиксируем поведение сервера."""
    body = '{"bin":411111}'
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body),
    }
    resp = _post_bin(payment_token, body, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-020")
def test_bin_very_long_string(payment_token):
    """BIN — строка из 100 символов. Ожидается не 500."""
    resp = _post_bin(payment_token, {"bin": "4" * 100})
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-021")
def test_bin_null_value(payment_token):
    """BIN = null. Ожидается не 500."""
    body = '{"bin":null}'
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body),
    }
    resp = _post_bin(payment_token, body, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


# ─────────────────────────────────────────────
# ЗАГОЛОВКИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-022")
def test_bin_empty_session_id(payment_token):
    """Api-Session-ID — пустая строка. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": "",
        "Api-Signature":  _calc_sig(path, "", raw),
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-023")
def test_bin_empty_signature(payment_token):
    """Api-Signature — пустая строка. Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "",
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-024")
def test_bin_duplicate_session_id_header(payment_token):
    """Дубликат Api-Session-ID (два с разными значениями). Ожидается не 500."""
    import http.client
    import ssl
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    sid1 = str(uuid.uuid4())
    sid2 = str(uuid.uuid4())
    sig  = _calc_sig(path, sid1, raw)
    ctx  = ssl.create_default_context()
    conn = http.client.HTTPSConnection("web3preprod.testpaygate.com", context=ctx,
                                       timeout=_cfg.HTTP_TIMEOUT)
    conn.putrequest("POST", path)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Api-Session-ID", sid1)
    conn.putheader("Api-Session-ID", sid2)
    conn.putheader("Api-Signature", sig)
    conn.endheaders(raw.encode())
    r = conn.getresponse()
    assert r.status != 500, f"Got 500 for duplicate Api-Session-ID header"


# ─────────────────────────────────────────────
# HTTP-МЕТОД
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-025")
def test_bin_get_method_not_allowed(payment_token):
    """GET на /bin. Ожидается 405 Method Not Allowed."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    key  = _cfg.CUSTOMER_MAC_KEY.encode()
    sid  = str(uuid.uuid4())
    sig  = hmac.new(key, f"GET\n{path}\n{sid}\n".encode(), hashlib.sha256).hexdigest()
    headers = {"Api-Session-ID": sid, "Api-Signature": sig}
    resp = requests.get(f"{_WEB3_HOST}{path}", headers=headers, timeout=_cfg.HTTP_TIMEOUT)
    assert resp.status_code == 405, f"Expected 405, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-026")
def test_bin_put_method_not_allowed(payment_token):
    """PUT на /bin. Ожидается 405 Method Not Allowed."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    key  = _cfg.CUSTOMER_MAC_KEY.encode()
    sid  = str(uuid.uuid4())
    sig  = hmac.new(key, f"PUT\n{path}\n{sid}\n{raw}".encode(), hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "Api-Session-ID": sid, "Api-Signature": sig}
    resp = requests.put(f"{_WEB3_HOST}{path}", data=raw, headers=headers, timeout=_cfg.HTTP_TIMEOUT)
    assert resp.status_code == 405, f"Expected 405, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-027")
def test_bin_patch_method_not_allowed(payment_token):
    """PATCH на /bin. Ожидается 405 Method Not Allowed."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    key  = _cfg.CUSTOMER_MAC_KEY.encode()
    sid  = str(uuid.uuid4())
    sig  = hmac.new(key, f"PATCH\n{path}\n{sid}\n{raw}".encode(), hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "Api-Session-ID": sid, "Api-Signature": sig}
    resp = requests.patch(f"{_WEB3_HOST}{path}", data=raw, headers=headers, timeout=_cfg.HTTP_TIMEOUT)
    assert resp.status_code == 405, f"Expected 405, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CONTENT-TYPE
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-028")
def test_bin_no_content_type(payment_token):
    """Запрос без Content-Type. Фиксируем поведение сервера."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw),
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-029")
def test_bin_text_plain_content_type(payment_token):
    """Content-Type: text/plain с валидным JSON-телом. Фиксируем поведение."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "text/plain",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw),
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-030")
def test_bin_form_encoded_content_type(payment_token):
    """Content-Type: application/x-www-form-urlencoded. Фиксируем поведение."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    raw  = json.dumps(_BIN_6, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/x-www-form-urlencoded",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw),
    }
    resp = _post_bin(payment_token, _BIN_6, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


# ─────────────────────────────────────────────
# ПОЛЕ client_amount
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-031")
def test_bin_client_amount_as_string(payment_token):
    """client_amount передан как строка "1500". Фиксируем поведение сервера."""
    body = '{"bin":"411111","client_amount":"1500"}'
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body),
    }
    resp = _post_bin(payment_token, body, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-032")
def test_bin_client_amount_zero(payment_token):
    """client_amount = 0. Ожидается 200, конвертация не ломается."""
    resp = _post_bin(payment_token, {"bin": "411111", "client_amount": 0})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("BI-033")
def test_bin_client_amount_negative(payment_token):
    """client_amount отрицательный. Ожидается не 500."""
    resp = _post_bin(payment_token, {"bin": "411111", "client_amount": -100})
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-034")
def test_bin_client_amount_very_large(payment_token):
    """client_amount очень большое число. Ожидается не 500."""
    resp = _post_bin(payment_token, {"bin": "411111", "client_amount": 10 ** 15})
    assert resp.status_code != 500, f"Got 500: {resp.text}"


# ─────────────────────────────────────────────
# ТЕЛО ЗАПРОСА
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-035")
def test_bin_no_body(payment_token):
    """Тело полностью отсутствует (не {}, а no body). Фиксируем поведение."""
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, ""),
    }
    resp = requests.post(f"{_WEB3_HOST}{path}", headers=headers, timeout=_cfg.HTTP_TIMEOUT)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-036")
def test_bin_body_is_array(payment_token):
    """Тело — массив [1,2,3]. Ожидается 4xx или graceful 200 (не 500)."""
    body = "[1,2,3]"
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body),
    }
    resp = _post_bin(payment_token, body, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-037")
def test_bin_body_is_null(payment_token):
    """Тело — строка null. Фиксируем поведение."""
    body = "null"
    path = f"{_BASE_PATH}/{payment_token}/bin"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, body),
    }
    resp = _post_bin(payment_token, body, headers=headers)
    assert resp.status_code != 500, f"Got 500: {resp.text}"


@pytest.mark.tcid("BI-038")
def test_bin_extra_unknown_fields(payment_token):
    """Лишние неизвестные поля в теле. Ожидается 200, поля игнорируются."""
    resp = _post_bin(payment_token, {"bin": "411111", "foo": "bar", "extra": 42})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "bank_info" in resp.json(), f"Missing bank_info: {resp.json()}"


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("BI-039")
def test_bin_two_identical_requests(payment_token):
    """Два одинаковых запроса подряд с одним payment_token → оба 200, ответы идентичны."""
    resp1 = _post_bin(payment_token, _BIN_6)
    resp2 = _post_bin(payment_token, _BIN_6)
    assert resp1.status_code == 200, f"First request: {resp1.status_code}: {resp1.text}"
    assert resp2.status_code == 200, f"Second request: {resp2.status_code}: {resp2.text}"
    for field in ("bank_info", "provider_country", "is_4symbol_cvc"):
        assert resp1.json().get(field) == resp2.json().get(field), \
            f"Field '{field}' differs: {resp1.json().get(field)!r} vs {resp2.json().get(field)!r}"
