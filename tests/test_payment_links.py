"""
Тесты для создания платёжных ссылок.
POST /api/v1/payment-links

Обязательные поля: merchant_data (с order_id), financial_data (amount + currency), customer_data
Необязательные: flow_data
"""
import json
import time
import uuid
import requests
import pytest

from conftest import (
    make_headers,
    PAYMENT_LINKS_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_error_response,
)

_VALID_LINK_BODY = {
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 5000, "currency": "RUB"},
    "customer_data": CUSTOMER_DATA,
}


def post_payment_link(body: dict) -> requests.Response:
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(TERMINAL_ID, raw)
    return requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-001")
def test_create_payment_link():
    """Создание платёжной ссылки со всеми обязательными полями. Ожидается 201."""
    resp = post_payment_link(_VALID_LINK_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "link_id" in data,                    "Missing link_id"
    assert "merchant_data" in data,              "Missing merchant_data"
    assert "link_data" in data,                  "Missing link_data"
    assert "url" in data["link_data"],           "Missing url in link_data"


@pytest.mark.tcid("PL-002")
def test_create_payment_link_response_fields():
    """Проверка типов обязательных полей в ответе на создание ссылки."""
    resp = post_payment_link(_VALID_LINK_BODY)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data["link_id"], str),         "link_id must be a string"
    assert isinstance(data["link_data"]["url"], str), "url must be a string"
    assert data["link_data"]["url"].startswith("http"), "url must be a valid URL"


@pytest.mark.tcid("PL-003")
def test_create_payment_link_with_flow_data():
    """Создание ссылки с необязательным flow_data. Ожидается 201."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-004")
def test_create_payment_link_with_recurrent_flow():
    """Создание ссылки с is_recurrent=True. Ожидается 201."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-005")
def test_create_payment_link_with_manual_capture():
    """Создание ссылки с capture_mode=manual. Ожидается 201."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {"capture_mode": "manual"},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-006")
def test_create_payment_link_without_webhook_url():
    """Создание ссылки без необязательного webhook_url в merchant_data. Ожидается 201."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "webhook_url"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-007")
def test_create_payment_link_without_return_url():
    """Создание ссылки без необязательного return_url в merchant_data. Ожидается 201."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "return_url"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-008")
def test_create_payment_link_minimal_customer_data():
    """Создание ссылки с пустым customer_data — все поля CustomerData необязательны."""
    body = {**_VALID_LINK_BODY, "customer_data": {}}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-009")
def test_create_payment_link_rub():
    """Создание платёжной ссылки с суммой 1000 RUB. Ожидается 201."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 1000, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — обязательные поля верхнего уровня
# ─────────────────────────────────────────────
@pytest.mark.parametrize("missing_field", ["merchant_data", "financial_data", "customer_data"])
@pytest.mark.tcid("PL-010")
def test_payment_link_missing_required_field(missing_field):
    """Отсутствие одного из трёх обязательных полей верхнего уровня. Ожидается 400."""
    body = {k: v for k, v in _VALID_LINK_BODY.items() if k != missing_field}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400 for missing {missing_field}, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-011")
def test_payment_link_missing_order_id():
    """Создание ссылки без order_id в merchant_data (обязательное). Ожидается 400."""
    merchant = {k: v for k, v in MERCHANT_DATA.items() if k != "order_id"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — финансовые данные
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-012")
def test_payment_link_negative_amount():
    """Создание ссылки с отрицательной суммой. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": -100, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-013")
def test_payment_link_zero_amount():
    """Создание ссылки с нулевой суммой. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 0, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-014")
def test_payment_link_invalid_currency():
    """Создание ссылки с невалидным кодом валюты. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 5000, "currency": "INVALID"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-015")
def test_payment_link_missing_currency():
    """Создание ссылки без поля currency в financial_data. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 5000}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-016")
def test_payment_link_missing_amount():
    """Создание ссылки без поля amount в financial_data. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-017")
def test_payment_link_invalid_capture_mode():
    """Создание ссылки с невалидным capture_mode в flow_data. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "flow_data": {"capture_mode": "instant"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ — авторизация
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-018")
def test_payment_link_no_auth():
    """Создание ссылки без заголовков авторизации. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    resp = requests.post(PAYMENT_LINKS_URL, data=raw,
                         headers={"Content-Type": "application/json"}, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-019")
def test_payment_link_invalid_signature():
    """Создание ссылки с невалидной подписью. Ожидается 401 или 403."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-020")
def test_payment_link_missing_terminal_id():
    """Создание ссылки без Api-Terminal-ID. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
        "Api-Timestamp":       str(int(time.time())),
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-021")
def test_payment_link_missing_timestamp():
    """Создание ссылки без Api-Timestamp. Ожидается 400, 401 или 403."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    headers = {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       "0" * 64,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — ФИНАНСОВЫЕ ДАННЫЕ
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-022")
def test_payment_link_amount_as_string():
    """Создание ссылки с суммой как строкой. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": "5000", "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-023")
def test_payment_link_amount_as_float():
    """Создание ссылки с суммой как вещественным числом. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 99.99, "currency": "RUB"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-024")
def test_payment_link_currency_usd():
    """Создание ссылки с валютой USD. Ожидается 201 или 400 (зависит от настроек терминала)."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 5000, "currency": "USD"}}
    resp = post_payment_link(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — MERCHANT_DATA
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-025")
def test_payment_link_order_id_null():
    """Создание ссылки с order_id = null. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": None}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-026")
def test_payment_link_order_id_empty():
    """Создание ссылки с пустым order_id. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": ""}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-027")
def test_payment_link_order_id_257_chars():
    """Создание ссылки с order_id длиной 257 символов (превышение лимита). Ожидается 400."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": "x" * 257}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-028")
def test_payment_link_webhook_url_invalid():
    """Создание ссылки с невалидным webhook_url. Ожидается 400."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "webhook_url": "not_a_url"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — FLOW_DATA
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-029")
def test_payment_link_invalid_threed_window_size():
    """Создание ссылки с невалидным challenge_window_size в threed_secure. Ожидается 400."""
    body = {
        **_VALID_LINK_BODY,
        "flow_data": {
            "capture_mode": "auto",
            "threed_secure": {"challenge_window_size": "99"},
        },
    }
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ПРОВЕРКА ПОЛЕЙ ОТВЕТА
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-030")
def test_payment_link_response_order_id_matches():
    """В ответе merchant_data.order_id совпадает с отправленным значением."""
    merchant = {**MERCHANT_DATA, "order_id": "order_link_resp_check"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("merchant_data", {}).get("order_id") == "order_link_resp_check"


@pytest.mark.tcid("PL-031")
def test_payment_link_return_url_with_query_params():
    """Создание ссылки с return_url, содержащим query-параметры. Ожидается 201."""
    merchant = {**MERCHANT_DATA, "return_url": "https://example.com/return?order=abc&status=ok"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
