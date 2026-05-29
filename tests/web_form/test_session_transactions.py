"""
Тесты эндпоинтов транзакций:
  POST /api/v1/payment-sessions/{payment_token}/transactions/card      (аналог /payments/{payment_token}/submit)
  POST /api/v1/payment-sessions/{payment_token}/transactions/cardless  (аналог /payments/{payment_token}/submit_void)

Подпись (POST):
  HMAC-SHA256(customer_mac_key, "POST\n{path}\n{Api-Session-ID}\n{raw_body}")

Особенности /transactions/card:
  - Каждый успешный submit меняет состояние payment session → нужен свежий токен на тест
  - Структура тела: PaymentDetails + CustomerInfo (+ опционально bankInfo, ExtraData)
  - Ответ 201: {"name": "<state>", "details": {...}}
  - Дубль-submit (double_confirmation): 200 OK, тело {}

Особенности /transactions/cardless:
  - Требует платёж в state "submited" (после card submit)
  - bankInfo из тела молча игнорируется (get_bank_info → None)
  - save_payer_personal не вызывается
  - Структура тела: CustomerInfo (+ опционально customerBankInfo, ExtraData)
"""
import hashlib
import hmac
import json
import uuid

import pytest
import requests

import _helpers.config as _cfg
from _helpers.db import _query_addinfo_by_token
from _helpers.validators import assert_error_response
from web_form.conftest import create_payment_token, options_preflight

_WEB3_HOST = "https://web3preprod.testpaygate.com"
_BASE_PATH  = "/api/v1/payment-sessions"
_OLD_PATH   = "/payments"

_INVALID_JSON = "{not_a_json"

_SUBMIT_BODY = {
    "PaymentMethod": "Card",
    "PaymentDetails": {
        "CardNumber": "4111111111111111",
        "ExpYear":    2027,
        "ExpMonth":   5,
        "CVV":        "666",
        "CardHolder": "JOHN DOE",
    },
    "CustomerInfo": {
        "Email": "test@example.com",
        "Phone": "+79991234567",
    },
    "bankInfo": {
        "bank_name":        "Visa",
        "country":          "RU",
        "saveCustomerInfo": False,
    },
}


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


def _make_old_headers(path: str, raw_body: str = "", session_id: str | None = None) -> dict[str, str]:
    sid = session_id or str(uuid.uuid4())
    return {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw_body),
    }


def _post_card(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = f"{_BASE_PATH}/{token}/transactions/card"
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_card_old(token: str, body: dict) -> requests.Response:
    path = f"{_OLD_PATH}/{token}/submit"
    raw  = json.dumps(body, separators=(",", ":"))
    h    = _make_old_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-001")
def test_card_submit_success():
    """Успешный submit карточного платежа. Ожидается 201, ответ содержит name и details."""
    token = create_payment_token()
    resp  = _post_card(token, _SUBMIT_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "name"    in data, f"Missing 'name' in response: {data}"
    assert "details" in data, f"Missing 'details' in response: {data}"


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ / КОНФИГ
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-002")
@pytest.mark.skip(reason="Требует MetaData.PaymentType=Block в payment_request — настроить вручную")
def test_card_submit_payment_type_block():
    """Submit с PaymentType=Block — вызов через manual.WebpayV3Block."""
    token = create_payment_token()
    resp  = _post_card(token, _SUBMIT_BODY)
    assert resp.status_code == 201


@pytest.mark.tcid("TX-003")
@pytest.mark.skip(reason="Требует MetaData.PaymentType=Payout в payment_request — настроить вручную")
def test_card_submit_payment_type_payout():
    """Submit с PaymentType=Payout — вызов через manual.WebpayV3Payout."""
    token = create_payment_token()
    resp  = _post_card(token, _SUBMIT_BODY)
    assert resp.status_code == 201


@pytest.mark.tcid("TX-004")
@pytest.mark.skip(reason="Требует проверки customerBankInfo.customerBank в БД — настроить вручную")
def test_card_submit_with_customer_bank_info():
    """Submit с customerBankInfo.customerBank — проставляется в transaction.addinfo."""
    body  = {**_SUBMIT_BODY, "customerBankInfo": {"customerBank": "Sberbank"}}
    token = create_payment_token()
    resp  = _post_card(token, body)
    assert resp.status_code == 201


@pytest.mark.tcid("TX-005")
@pytest.mark.skip(reason="Требует платёж с валютой, не совпадающей с service.currency_code")
def test_card_submit_invalid_currency(payment_token):
    """Неверная валюта — PaymentRequest.Currency ≠ service.currency_code. Ожидается 4xx."""
    resp = _post_card(payment_token, _SUBMIT_BODY)
    assert resp.status_code in range(400, 500)
    assert_error_response(resp)


@pytest.mark.tcid("TX-006")
@pytest.mark.skip(reason="Требует несовпадения RebillFlag между customer_entity и PaymentRequest")
def test_card_submit_invalid_rebill_flag(payment_token):
    """Несовпадение RebillFlag. Ожидается 4xx."""
    resp = _post_card(payment_token, _SUBMIT_BODY)
    assert resp.status_code in range(400, 500)
    assert_error_response(resp)


@pytest.mark.tcid("TX-007")
@pytest.mark.skip(reason="Требует платёж в состоянии success/fail/user_action — настроить вручную")
def test_card_submit_invalid_payment_state(payment_token):
    """Платёж не в допустимом состоянии. Ожидается 4xx (InvalidPaymentState)."""
    resp = _post_card(payment_token, _SUBMIT_BODY)
    assert resp.status_code in range(400, 500)
    assert_error_response(resp)


@pytest.mark.tcid("TX-008")
@pytest.mark.skip(reason="Требует просроченный платёж (valid_to < now) — настроить вручную")
def test_card_submit_expired_payment(payment_token):
    """Просроченный платёж. Ожидается 4xx (PaymentIdIsExpired)."""
    resp = _post_card(payment_token, _SUBMIT_BODY)
    assert resp.status_code in range(400, 500)
    assert_error_response(resp)


@pytest.mark.tcid("TX-009")
@pytest.mark.skip(reason="Требует платёж с выставленным флагом double_confirmation (submit_void)")
def test_card_submit_double_confirmation(payment_token):
    """Двойной submit — ожидается 200 OK, тело {}."""
    resp = _post_card(payment_token, _SUBMIT_BODY)
    assert resp.status_code == 200
    assert resp.json() == {}


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-010")
def test_card_submit_missing_session_id(payment_token):
    """Нет Api-Session-ID. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/transactions/card"
    raw  = json.dumps(_SUBMIT_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Signature": _calc_sig(path, sid, raw),
    }
    resp = _post_card(payment_token, _SUBMIT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("TX-011")
def test_card_submit_missing_signature(payment_token):
    """Нет Api-Signature. Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_card(payment_token, _SUBMIT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("TX-012")
def test_card_submit_invalid_signature(payment_token):
    """Невалидная подпись (строка из нулей). Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_card(payment_token, _SUBMIT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("TX-013")
def test_card_submit_signature_from_old_url(payment_token):
    """Подпись от старого пути /payments/.../submit. Ожидается 4xx."""
    old_path = f"{_OLD_PATH}/{payment_token}/submit"
    raw  = json.dumps(_SUBMIT_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(old_path, sid, raw),
    }
    resp = _post_card(payment_token, _SUBMIT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("TX-014")
def test_card_submit_signature_body_mismatch(payment_token):
    """Подпись посчитана от body_A, отправлен body_B. Ожидается 4xx."""
    path    = f"{_BASE_PATH}/{payment_token}/transactions/card"
    body_a  = {**_SUBMIT_BODY, "PaymentMethod": "Card"}
    body_b  = {**_SUBMIT_BODY, "PaymentMethod": "AnotherMethod"}
    raw_a   = json.dumps(body_a, separators=(",", ":"))
    raw_b   = json.dumps(body_b, separators=(",", ":"))
    sid     = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw_a),
    }
    resp = _post_card(payment_token, body_b, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-015")
def test_card_submit_invalid_token_format():
    """Невалидный payment_token (не UUID). Ожидается 4xx (validation_uuid_decorator)."""
    resp = _post_card("not-a-uuid", _SUBMIT_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("TX-016")
def test_card_submit_nonexistent_token():
    """Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx."""
    resp = _post_card("00000000-0000-0000-0000-000000000000", _SUBMIT_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-017")
def test_card_submit_invalid_json(payment_token):
    """Битый JSON в теле. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/transactions/card"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, _INVALID_JSON),
    }
    resp = _post_card(payment_token, _INVALID_JSON, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-018")
def test_card_submit_old_endpoint_regression():
    """Регресс: старый /payments/{token}/submit с X-* заголовками продолжает работать."""
    token = create_payment_token()
    resp  = _post_card_old(token, _SUBMIT_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "name"    in data, f"Missing 'name' in old endpoint response"
    assert "details" in data, f"Missing 'details' in old endpoint response"


@pytest.mark.tcid("TX-019")
def test_card_submit_old_headers_on_new_url(payment_token):
    """Новый URL + старые заголовки X-*. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = f"{_OLD_PATH}/{payment_token}/submit"
    raw  = json.dumps(_SUBMIT_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw),
    }
    resp = _post_card(payment_token, _SUBMIT_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("TX-020")
def test_card_submit_response_structure_identical_to_old():
    """Структура ответа нового и старого эндпоинта идентична (свежий токен для каждого)."""
    token_new = create_payment_token()
    token_old = create_payment_token()
    resp_new  = _post_card(token_new, _SUBMIT_BODY)
    resp_old  = _post_card_old(token_old, _SUBMIT_BODY)
    assert resp_new.status_code == 201, f"New: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 201, f"Old: {resp_old.status_code}: {resp_old.text}"
    data_new = resp_new.json()
    data_old = resp_old.json()
    assert set(data_new.keys()) == set(data_old.keys()), \
        f"Response keys differ: new={set(data_new.keys())}, old={set(data_old.keys())}"


# ─────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНЫЕ — требуют DB/логов
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-021")
def test_card_submit_x_forwarded_for():
    """X-Forwarded-For проксируется в ip_address в secure.transactions.addinfo."""
    token = create_payment_token()
    path  = f"{_BASE_PATH}/{token}/transactions/card"
    raw   = json.dumps(_SUBMIT_BODY, separators=(",", ":"))
    sid   = str(uuid.uuid4())
    headers = {
        **_make_headers(path, raw, sid),
        "X-Forwarded-For": "5.6.7.8",
    }
    resp = _post_card(token, _SUBMIT_BODY, headers=headers)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    addinfo = _query_addinfo_by_token(token)
    if addinfo:
        assert addinfo.get("ip_address") == "5.6.7.8", \
            f"Expected ip_address=5.6.7.8, got: {addinfo.get('ip_address')!r}"


@pytest.mark.tcid("TX-022")
@pytest.mark.skip(reason="Требует ExtraData в PaymentRequest и проверки merge-логики в БД")
def test_card_submit_extra_data_merge():
    """ExtraData из тела сливается с ExtraData из PaymentRequest (без перезаписи)."""
    body  = {**_SUBMIT_BODY, "ExtraData": {"B": 3, "C": 4}}
    token = create_payment_token()
    resp  = _post_card(token, body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("TX-023")
def test_card_submit_options_preflight(payment_token):
    """OPTIONS preflight /transactions/card: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(f"{_BASE_PATH}/{payment_token}/transactions/card")
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "")
    assert "Api-Session-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "Api-Signature"  in allow, f"Api-Signature not in Allow-Headers: {allow}"


# ╔═══════════════════════════════════════════════════════════╗
# ║  /api/v1/payment-sessions/{token}/transactions/cardless  ║
# ╚═══════════════════════════════════════════════════════════╝

_CARDLESS_BODY = {
    "CustomerInfo": {
        "Email": "test@example.com",
        "Phone": "+79991234567",
    },
}

_CARDLESS_BODY_WITH_BANKINFO = {
    **_CARDLESS_BODY,
    "bankInfo": {
        "bank_name":        "TestBank",
        "country":          "RU",
        "saveCustomerInfo": True,
    },
}

_INVALID_CARDLESS_JSON = "{not_a_json"


def _post_cardless(token: str, body: dict | str, headers: dict | None = None) -> requests.Response:
    path = f"{_BASE_PATH}/{token}/transactions/cardless"
    raw  = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
    h    = headers if headers is not None else _make_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


def _post_cardless_old(token: str, body: dict) -> requests.Response:
    path = f"{_OLD_PATH}/{token}/submit_void"
    raw  = json.dumps(body, separators=(",", ":"))
    h    = _make_old_headers(path, raw)
    return requests.post(f"{_WEB3_HOST}{path}", data=raw, headers=h, timeout=_cfg.HTTP_TIMEOUT)


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА
# ─────────────────────────────────────────────
@pytest.mark.tcid("CL-001")
def test_cardless_submit_success():
    """Успешный submit без карты. Ожидается 201, ответ содержит name и details."""
    token     = create_payment_token()
    card_resp = _post_card(token, _SUBMIT_BODY)
    if card_resp.status_code != 201:
        pytest.skip(f"Card submit failed ({card_resp.status_code}) — can't reach submited state")
    resp = _post_cardless(token, _CARDLESS_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "name"    in data, f"Missing 'name': {data}"
    assert "details" in data, f"Missing 'details': {data}"


@pytest.mark.tcid("CL-002")
def test_cardless_submit_bankinfo_ignored():
    """bankInfo в теле игнорируется — в addinfo нет bank_info и bank_info_base."""
    token     = create_payment_token()
    card_resp = _post_card(token, _SUBMIT_BODY)
    if card_resp.status_code != 201:
        pytest.skip(f"Card submit failed ({card_resp.status_code}) — can't reach submited state")
    resp = _post_cardless(token, _CARDLESS_BODY_WITH_BANKINFO)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    addinfo = _query_addinfo_by_token(token)
    if addinfo:
        assert addinfo.get("bank_info")      is None, f"bank_info should be absent, got: {addinfo.get('bank_info')!r}"
        assert addinfo.get("bank_info_base") is None, f"bank_info_base should be absent, got: {addinfo.get('bank_info_base')!r}"


@pytest.mark.tcid("CL-003")
def test_cardless_submit_customer_bank_info():
    """customerBankInfo.customerBank сохраняется в addinfo.customer_bank."""
    token     = create_payment_token()
    card_resp = _post_card(token, _SUBMIT_BODY)
    if card_resp.status_code != 201:
        pytest.skip(f"Card submit failed ({card_resp.status_code}) — can't reach submited state")
    body = {**_CARDLESS_BODY, "customerBankInfo": {"customerBank": "Sberbank"}}
    resp = _post_cardless(token, body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    addinfo = _query_addinfo_by_token(token)
    if addinfo:
        assert addinfo.get("customer_bank") == "Sberbank", \
            f"Expected customer_bank=Sberbank, got: {addinfo.get('customer_bank')!r}"


@pytest.mark.tcid("CL-004")
@pytest.mark.skip(reason="Требует платёж с выставленным флагом double_confirmation (submit_void)")
def test_cardless_submit_double_confirmation(payment_token):
    """Двойной submit_void — ожидается 200 OK, тело {}."""
    resp = _post_cardless(payment_token, _CARDLESS_BODY)
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.tcid("CL-005")
@pytest.mark.skip(reason="Требует платёж в недопустимом состоянии (не submited) — настроить вручную")
def test_cardless_submit_invalid_state(payment_token):
    """Платёж не в state=submited. Ожидается 4xx (InvalidPaymentState)."""
    resp = _post_cardless(payment_token, _CARDLESS_BODY)
    assert resp.status_code in range(400, 500)
    assert_error_response(resp)


@pytest.mark.tcid("CL-006")
@pytest.mark.skip(reason="Требует просроченный платёж (valid_to < now) — настроить вручную")
def test_cardless_submit_expired_payment(payment_token):
    """Просроченный платёж. Ожидается 4xx (PaymentIdIsExpired)."""
    resp = _post_cardless(payment_token, _CARDLESS_BODY)
    assert resp.status_code in range(400, 500)
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("CL-007")
def test_cardless_submit_missing_session_id(payment_token):
    """Нет Api-Session-ID. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/transactions/cardless"
    raw  = json.dumps(_CARDLESS_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Signature": _calc_sig(path, sid, raw),
    }
    resp = _post_cardless(payment_token, _CARDLESS_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CL-008")
def test_cardless_submit_missing_signature(payment_token):
    """Нет Api-Signature. Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
    }
    resp = _post_cardless(payment_token, _CARDLESS_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CL-009")
def test_cardless_submit_invalid_signature(payment_token):
    """Невалидная подпись (строка из нулей). Ожидается 4xx."""
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": str(uuid.uuid4()),
        "Api-Signature":  "0" * 64,
    }
    resp = _post_cardless(payment_token, _CARDLESS_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CL-010")
def test_cardless_submit_signature_from_old_url(payment_token):
    """Подпись от старого пути /payments/.../submit_void. Ожидается 4xx."""
    old_path = f"{_OLD_PATH}/{payment_token}/submit_void"
    raw  = json.dumps(_CARDLESS_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(old_path, sid, raw),
    }
    resp = _post_cardless(payment_token, _CARDLESS_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CL-011")
def test_cardless_submit_signature_body_mismatch(payment_token):
    """Подпись посчитана от body_A, отправлен body_B. Ожидается 4xx."""
    path   = f"{_BASE_PATH}/{payment_token}/transactions/cardless"
    body_a = _CARDLESS_BODY
    body_b = _CARDLESS_BODY_WITH_BANKINFO
    raw_a  = json.dumps(body_a, separators=(",", ":"))
    raw_b  = json.dumps(body_b, separators=(",", ":"))
    sid    = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, raw_a),
    }
    resp = _post_cardless(payment_token, body_b, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token
# ─────────────────────────────────────────────
@pytest.mark.tcid("CL-012")
def test_cardless_submit_invalid_token_format():
    """Невалидный payment_token (не UUID). Ожидается 4xx."""
    resp = _post_cardless("not-a-uuid", _CARDLESS_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CL-013")
def test_cardless_submit_nonexistent_token():
    """Несуществующий payment_token (валидный UUID, не в БД). Ожидается 4xx."""
    resp = _post_cardless("00000000-0000-0000-0000-000000000000", _CARDLESS_BODY)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("CL-014")
def test_cardless_submit_invalid_json(payment_token):
    """Битый JSON в теле. Ожидается 4xx."""
    path = f"{_BASE_PATH}/{payment_token}/transactions/cardless"
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":   "application/json",
        "Api-Session-ID": sid,
        "Api-Signature":  _calc_sig(path, sid, _INVALID_CARDLESS_JSON),
    }
    resp = _post_cardless(payment_token, _INVALID_CARDLESS_JSON, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("CL-015")
@pytest.mark.skip(reason="Требует проверки bankInfo-обработки в БД (bank_info, payer_personal_data)")
def test_cardless_old_endpoint_bankinfo_processed():
    """Регресс: старый /submit_void по-прежнему обрабатывает bankInfo (bank_info и payer_personal_data)."""
    token = create_payment_token()
    _post_card(token, _SUBMIT_BODY)
    body = {
        **_CARDLESS_BODY,
        "bankInfo": {"bank_name": "X", "saveCustomerInfo": True},
        "ExtraData": {"PersonalId": "123"},
    }
    resp = _post_cardless_old(token, body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    # Проверить через БД: transaction.addinfo.bank_info заполнен, запись в payer_personal_data создана


@pytest.mark.tcid("CL-016")
def test_cardless_old_headers_on_new_url(payment_token):
    """Новый URL + старые заголовки X-*. Ожидается 4xx (MissingHTTPHeader: Api-Session-ID)."""
    path = f"{_OLD_PATH}/{payment_token}/submit_void"
    raw  = json.dumps(_CARDLESS_BODY, separators=(",", ":"))
    sid  = str(uuid.uuid4())
    headers = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   _calc_sig(path, sid, raw),
    }
    resp = _post_cardless(payment_token, _CARDLESS_BODY, headers=headers)
    assert resp.status_code in range(400, 500), f"Expected 4xx, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CL-017")
@pytest.mark.skip(reason="Требует платёж в state=submited и сравнения addinfo в БД")
def test_cardless_response_identical_to_old_without_bankinfo():
    """Ответы нового и старого эндпоинта идентичны для body без bankInfo."""
    token_new = create_payment_token()
    token_old = create_payment_token()
    _post_card(token_new, _SUBMIT_BODY)
    _post_card(token_old, _SUBMIT_BODY)
    resp_new = _post_cardless(token_new, _CARDLESS_BODY)
    resp_old = _post_cardless_old(token_old, _CARDLESS_BODY)
    assert resp_new.status_code == 201, f"New: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 201, f"Old: {resp_old.status_code}: {resp_old.text}"
    assert set(resp_new.json().keys()) == set(resp_old.json().keys()), \
        f"Response keys differ: new={set(resp_new.json().keys())}, old={set(resp_old.json().keys())}"


@pytest.mark.tcid("CL-018")
@pytest.mark.skip(reason="Требует state=submited + проверки bank_info/payer_personal_data в БД")
def test_cardless_bankinfo_behaviour_differs_from_old():
    """Сознательное отличие: с bankInfo старый пишет bank_info в addinfo, новый — нет."""
    token_new = create_payment_token()
    token_old = create_payment_token()
    _post_card(token_new, _SUBMIT_BODY)
    _post_card(token_old, _SUBMIT_BODY)
    resp_new = _post_cardless(token_new, _CARDLESS_BODY_WITH_BANKINFO)
    resp_old = _post_cardless_old(token_old, _CARDLESS_BODY_WITH_BANKINFO)
    assert resp_new.status_code == 201, f"New: {resp_new.status_code}: {resp_new.text}"
    assert resp_old.status_code == 201, f"Old: {resp_old.status_code}: {resp_old.text}"
    # Проверить через БД: у нового bank_info=None, у старого bank_info заполнен


@pytest.mark.tcid("CL-019")
def test_cardless_x_forwarded_for():
    """X-Forwarded-For проксируется в ip_address в secure.transactions.addinfo."""
    token     = create_payment_token()
    card_resp = _post_card(token, _SUBMIT_BODY)
    if card_resp.status_code != 201:
        pytest.skip(f"Card submit failed ({card_resp.status_code}) — can't reach submited state")
    path  = f"{_BASE_PATH}/{token}/transactions/cardless"
    raw   = json.dumps(_CARDLESS_BODY, separators=(",", ":"))
    sid   = str(uuid.uuid4())
    headers = {
        **_make_headers(path, raw, sid),
        "X-Forwarded-For": "5.6.7.8",
    }
    resp = _post_cardless(token, _CARDLESS_BODY, headers=headers)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    addinfo = _query_addinfo_by_token(token)
    if addinfo:
        assert addinfo.get("ip_address") == "5.6.7.8", \
            f"Expected ip_address=5.6.7.8, got: {addinfo.get('ip_address')!r}"


@pytest.mark.tcid("CL-020")
@pytest.mark.skip(reason="Требует ExtraData в PaymentRequest и state=submited — проверить через БД")
def test_cardless_extra_data_merge():
    """ExtraData из тела сливается с ExtraData из PaymentRequest (без перезаписи существующих)."""
    body  = {**_CARDLESS_BODY, "ExtraData": {"B": 3, "C": 4}}
    token = create_payment_token()
    _post_card(token, _SUBMIT_BODY)
    resp  = _post_cardless(token, body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT
# ─────────────────────────────────────────────
@pytest.mark.tcid("CL-021")
def test_cardless_options_preflight(payment_token):
    """OPTIONS preflight /transactions/cardless: Access-Control-Allow-Headers содержит Api-Session-ID и Api-Signature."""
    resp = options_preflight(f"{_BASE_PATH}/{payment_token}/transactions/cardless")
    assert resp.status_code in (200, 204), f"Expected 200/204, got {resp.status_code}: {resp.text}"
    allow = resp.headers.get("Access-Control-Allow-Headers", "")
    assert "Api-Session-ID" in allow, f"Api-Session-ID not in Allow-Headers: {allow}"
    assert "Api-Signature"  in allow, f"Api-Signature not in Allow-Headers: {allow}"
