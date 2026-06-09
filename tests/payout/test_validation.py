"""
Тесты валидации полей запроса для выплат (type=payout).
Используют method=sbp как транспорт, т.к. SbpDetails не имеет обязательных полей.
"""
from datetime import datetime

import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

_BASE = {
    "type": "payout",
    "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}

_VALID = {**_BASE, "transaction_data": {"method": "sbp"}}


def _assert_payout_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payout"
    return data


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ — общие
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-021")
def test_payout_unknown_method():
    """Неизвестный метод выплаты. Ожидается 400."""
    body = {**_BASE, "transaction_data": {"method": "unknown_method"}}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TYPE — граничные случаи (2.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-025")
def test_payout_type_payin():
    """type = 'payin' вместо 'payout'. Ожидается 400."""
    resp = post_transaction({**_VALID, "type": "payin"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-026")
def test_payout_type_null():
    """type = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "type": None})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-027")
def test_payout_type_empty():
    """type = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "type": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-028")
def test_payout_type_uppercase():
    """type = 'PAYOUT' (верхний регистр). Ожидается 400."""
    resp = post_transaction({**_VALID, "type": "PAYOUT"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# MERCHANT_DATA.ORDER_ID — граничные случаи (3.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-029")
def test_payout_missing_order_id():
    """merchant_data без order_id. Ожидается 400."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    resp = post_transaction({**_VALID, "merchant_data": merchant})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-030")
def test_payout_order_id_null():
    """merchant_data.order_id = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-031")
def test_payout_order_id_empty():
    """merchant_data.order_id = '' (пустая строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": ""}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-032")
def test_payout_order_id_spaces():
    """merchant_data.order_id = '   ' (только пробелы). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "   "}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-033")
def test_payout_order_id_special_chars():
    """merchant_data.order_id = спецсимволы ORDER#@$%^&*(). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "ORDER#@$%^&*()"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-034")
def test_payout_order_id_256_chars():
    """merchant_data.order_id = 256 символов (граничное). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 256}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-035")
def test_payout_order_id_257_chars():
    """merchant_data.order_id = 257 символов (превышение лимита). Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 257}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-036")
def test_payout_order_id_cyrillic():
    """merchant_data.order_id = кириллица 'ЗАКАЗ-12345'. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": "ЗАКАЗ-12345"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-037")
def test_payout_order_id_duplicate():
    """merchant_data.order_id = дубликат уже созданного заказа. Ожидается 201 или 409."""
    body = {**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("payout_card_dup")}}
    resp = post_transaction(body)
    assert resp.status_code in (201, 409), f"Expected 201 or 409, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FINANCIAL_DATA.AMOUNT — граничные случаи (4.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-038")
def test_payout_amount_missing():
    """financial_data без поля amount. Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-039")
def test_payout_amount_min():
    """financial_data.amount = 1 (минимально допустимое). Ожидается 201."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1, "currency": "RUB"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-040")
def test_payout_amount_as_string():
    """financial_data.amount = '10000' (строка). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": "10000", "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-041")
def test_payout_amount_float():
    """financial_data.amount = 100.50 (дробное число). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 100.50, "currency": "RUB"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-042")
def test_payout_amount_large():
    """financial_data.amount = 99999999999 (очень большое). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 99999999999, "currency": "RUB"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-043")
def test_payout_amount_exceeds_balance():
    """financial_data.amount = 999999999999999 (заведомо превышает баланс). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 999999999999999, "currency": "RUB"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FINANCIAL_DATA.CURRENCY — граничные случаи (5.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-044")
def test_payout_currency_usd():
    """financial_data.currency = 'USD'. Ожидается 201 или 400 (зависит от настроек терминала)."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "USD"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-045")
def test_payout_currency_eur():
    """financial_data.currency = 'EUR'. Ожидается 201 или 400 (зависит от настроек терминала)."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "EUR"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-046")
def test_payout_currency_missing():
    """financial_data без поля currency. Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-047")
def test_payout_currency_null():
    """financial_data.currency = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-048")
def test_payout_currency_lowercase():
    """financial_data.currency = 'rub' (нижний регистр). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "rub"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-049")
def test_payout_currency_rur():
    """financial_data.currency = 'RUR' (старый код рубля). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "RUR"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-050")
def test_payout_currency_numeric_code():
    """financial_data.currency = '643' (цифровой код). Ожидается 400."""
    resp = post_transaction({**_VALID, "financial_data": {"amount": 1000, "currency": "643"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# CUSTOMER_DATA — граничные случаи (6.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-051")
def test_payout_missing_customer_data():
    """customer_data отсутствует. Ожидается 400."""
    body = {k: v for k, v in _VALID.items() if k != "customer_data"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-052")
def test_payout_invalid_email():
    """customer_data.contact_info.email = невалидный email. Ожидается 400."""
    customer = {**CUSTOMER_DATA, "contact_info": {"email": "not_an_email", "phone": "+79991234567"}}
    resp = post_transaction({**_VALID, "customer_data": customer})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-053")
def test_payout_invalid_phone_format():
    """customer_data.contact_info.phone не в формате E.164. Ожидается 400."""
    customer = {**CUSTOMER_DATA, "contact_info": {"email": "test@test.com", "phone": "89991234567"}}
    resp = post_transaction({**_VALID, "customer_data": customer})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TRANSACTION_DATA.METHOD — граничные случаи (7.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-054")
def test_payout_method_missing():
    """transaction_data без поля method. Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-055")
def test_payout_method_null():
    """transaction_data.method = null. Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": None}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-056")
def test_payout_method_uppercase():
    """transaction_data.method = 'CARD' (верхний регистр). Ожидается 400."""
    resp = post_transaction({**_VALID, "transaction_data": {"method": "CARD"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ОПЦИОНАЛЬНЫЕ ПОЛЯ MERCHANT_DATA (8.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-057")
def test_payout_description_long():
    """merchant_data.description = 1000 символов. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "description": "x" * 1000}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-058")
def test_payout_description_special_chars():
    """merchant_data.description = спецсимволы. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "description": "Test!@#$%^&*()_+[]{}|;':\",.<>?"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-059")
def test_payout_webhook_url_valid_https():
    """merchant_data.webhook_url = валидный HTTPS URL. Ожидается 201."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "https://example.com/webhook"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-060")
def test_payout_webhook_url_invalid():
    """merchant_data.webhook_url = невалидный URL. Ожидается 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "not_a_url"}})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-061")
def test_payout_webhook_url_http():
    """merchant_data.webhook_url = HTTP URL (небезопасный). Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "http://example.com/webhook"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-062")
def test_payout_return_url_valid_https():
    """merchant_data.return_url = валидный HTTPS URL. Ожидается 201."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "return_url": "https://example.com/return"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-063")
def test_payout_return_url_with_query_params():
    """merchant_data.return_url = URL с query-параметрами. Ожидается 201."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "return_url": "https://example.com/return?order=123&status=ok"}})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ПОЛЯ ОТВЕТА (16.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-101")
def test_payout_response_merchant_order_id():
    """В ответе merchant_data.order_id совпадает с отправленным значением."""
    order_id = gen_order_id("payout_resp_check")
    body = {**_VALID, "merchant_data": {**MERCHANT_DATA, "order_id": order_id}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("merchant_data", {}).get("order_id") == order_id


@pytest.mark.tcid("PY-102")
def test_payout_response_financial_data():
    """В ответе financial_data.amount и currency соответствуют запросу."""
    resp = post_transaction(_VALID)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    fd = data.get("financial_data", {})
    assert fd.get("amount") == 1000
    assert fd.get("currency") == "RUB"


@pytest.mark.tcid("PY-103")
def test_payout_response_created_at():
    """В ответе присутствует created_at в формате ISO 8601."""
    resp = post_transaction(_VALID)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    created_at = data.get("created_at")
    assert created_at is not None, "created_at отсутствует в ответе"
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"created_at не является валидным ISO 8601: {created_at}")



@pytest.mark.tcid("PY-106")
def test_payout_type_missing():
    """type полностью отсутствует в теле запроса. Ожидается 400."""
    body = {k: v for k, v in _VALID.items() if k != "type"}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PY-107")
def test_payout_description_emoji():
    """merchant_data.description = эмодзи. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "description": "Выплата 🎉💳✅"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-108")
def test_payout_webhook_url_localhost():
    """merchant_data.webhook_url = localhost URL. Ожидается 201 или 400."""
    resp = post_transaction({**_VALID, "merchant_data": {**MERCHANT_DATA, "webhook_url": "http://localhost:8080/webhook"}})
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PY-111")
def test_payout_response_type_is_payout():
    """Payout — type в ответе равен 'payout'."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_type")},
            "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert resp.json().get("type") == "payout"


@pytest.mark.tcid("PY-112")
def test_payout_response_content_type_is_json():
    """Payout — Content-Type ответа содержит application/json."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_ct")},
            "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 201
    assert "application/json" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("PY-116")
def test_payout_financial_data_null_returns_400():
    """Payout с financial_data = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_fd_null")},
            "financial_data": None, "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-117")
def test_payout_customer_data_null_returns_400():
    """Payout с customer_data = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_cd_null")},
            "customer_data": None, "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-118")
def test_payout_merchant_data_null_returns_400():
    """Payout с merchant_data = null. Ожидается 400."""
    body = {**_BASE, "merchant_data": None, "transaction_data": {"method": "sbp"}}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-119")
def test_payout_transaction_data_null_returns_400():
    """Payout с transaction_data = null. Ожидается 400."""
    body = {**_BASE,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("py_td_null")},
            "transaction_data": None}
    resp = post_transaction(body)
    assert resp.status_code == 400
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ИДЕМПОТЕНТНОСТЬ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-148")
def test_idempotency_same_key_returns_same_transaction_id():
    """Повторный запрос с тем же Api-Idempotency-Key возвращает transaction_id первого запроса без создания дубля."""
    import json
    import time
    import uuid
    import requests as _req
    from _helpers.config import BASE_URL, TERMINAL_ID
    from _helpers.signatures import calc_signature

    body = {
        "type": "payout",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("idem_py_val")},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "sbp"},
    }
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    def _post():
        ts = str(int(time.time()))
        sig = calc_signature(TERMINAL_ID, ts, raw)
        h = {
            "Content-Type":        "application/json",
            "Api-Terminal-ID":     TERMINAL_ID,
            "Api-Idempotency-Key": key,
            "Api-Signature":       sig,
            "Api-Timestamp":       ts,
        }
        from _helpers.validators import assert_idempotency_echo
        r = _req.post(BASE_URL, data=raw, headers=h, timeout=30)
        assert_idempotency_echo(h, r)
        return r

    r1 = _post()
    assert r1.status_code == 201, f"First request failed: {r1.text}"
    r2 = _post()
    assert r2.status_code in (200, 201), f"Duplicate key: expected 200/201, got {r2.status_code}: {r2.text}"
    assert r2.json()["transaction_id"] == r1.json()["transaction_id"], (
        f"Duplicate key created new transaction: "
        f"r1.tid={r1.json().get('transaction_id')}, r2.tid={r2.json().get('transaction_id')}"
    )
