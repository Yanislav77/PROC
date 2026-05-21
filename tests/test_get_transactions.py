"""
Тесты для GET-эндпоинтов транзакций.
GET /api/v1/transactions?order_id=  — поиск по order_id мерчанта
GET /api/v1/transactions/{id}       — получение транзакции по числовому ID
"""
import time
import requests
import pytest

from conftest import (
    get_request,
    make_get_headers,
    BASE_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    assert_transaction_response,
    assert_error_response,
)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-001")
def test_get_transaction_by_id(payin_transaction_id):
    """GET /{id} по реальному transaction_id. Ожидается 200 со всеми обязательными полями ответа."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["transaction_id"] == payin_transaction_id, "transaction_id mismatch"


@pytest.mark.tcid("GT-002")
def test_get_transaction_fields(payin_transaction_id):
    """GET /{id} — проверка типов и формата всех полей ответа по спецификации."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert_transaction_response(resp.json())


@pytest.mark.tcid("GT-003")
def test_get_transactions_by_order_id(payin_transaction_id):
    """GET ?order_id= по реальному order_id мерчанта. Ожидается 200 и массив транзакций."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list), f"Expected a list, got {type(data)}"
    assert len(data) > 0, "Expected at least one transaction"
    item = data[0]
    assert_transaction_response(item)


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-004")
def test_get_transaction_not_found():
    """GET по несуществующему числовому transaction_id. Ожидается 404."""
    url = f"{BASE_URL}/000000000000"
    resp = get_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-005")
def test_get_by_order_id_not_found():
    """GET ?order_id= с несуществующим order_id. Ожидается 404."""
    resp = get_request(BASE_URL, params={"order_id": "nonexistent_order_xyz_000"})
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-006")
def test_get_by_order_id_missing_param():
    """GET /transactions без параметра order_id. Ожидается 400."""
    resp = get_request(BASE_URL)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-007")
def test_get_transaction_no_auth():
    """GET /{id} без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    resp = requests.get(url, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-008")
def test_get_transaction_invalid_signature():
    """GET /{id} с подписью из нулей. Ожидается 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
        "Api-Timestamp":   str(int(time.time())),
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-009")
def test_get_transaction_missing_terminal_id():
    """GET /{id} без заголовка Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Signature": "0" * 64,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-010")
def test_get_transaction_missing_timestamp():
    """GET /{id} без заголовка Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ПРОВЕРКА ПОЛЕЙ ОТВЕТА
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-011")
def test_get_transaction_type_is_payin(payin_transaction_id):
    """GET /{id} — поле type в ответе должно быть 'payin'."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("type") == "payin", f"Expected type='payin', got {data.get('type')!r}"


@pytest.mark.tcid("GT-012")
def test_get_transaction_financial_data_fields(payin_transaction_id):
    """GET /{id} — financial_data содержит amount (int) и currency (3 буквы)."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    fd = resp.json().get("financial_data", {})
    assert isinstance(fd.get("amount"), int), f"amount must be int, got {fd.get('amount')!r}"
    currency = fd.get("currency", "")
    assert isinstance(currency, str) and len(currency) == 3, f"currency must be 3-char, got {currency!r}"


@pytest.mark.tcid("GT-013")
def test_get_transaction_merchant_data_order_id(payin_transaction_id):
    """GET /{id} — merchant_data.order_id присутствует и совпадает с созданным заказом."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    md = resp.json().get("merchant_data", {})
    assert isinstance(md.get("order_id"), str) and md["order_id"], "order_id must be non-empty string"
    assert md["order_id"] == MERCHANT_DATA["order_id"], "order_id mismatch"


@pytest.mark.tcid("GT-014")
def test_get_transaction_created_at_iso8601(payin_transaction_id):
    """GET /{id} — поле created_at валидно как ISO 8601."""
    from datetime import datetime
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    created_at = resp.json().get("created_at", "")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pytest.fail(f"created_at не является ISO 8601: {created_at!r}")


@pytest.mark.tcid("GT-015")
def test_get_transaction_status_is_valid(payin_transaction_id):
    """GET /{id} — поле status принадлежит допустимому набору значений."""
    _valid_statuses = {"completed", "authorized", "processing", "waiting_action",
                       "cancelled", "rejected", "refunded"}
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    status = resp.json().get("status")
    assert status in _valid_statuses, f"Неожиданный status: {status!r}"


# ─────────────────────────────────────────────
# ГРАНИЧНЫЕ СЛУЧАИ — ПАРАМЕТРЫ ЗАПРОСА
# ─────────────────────────────────────────────
@pytest.mark.tcid("GT-016")
def test_get_by_order_id_empty_value():
    """GET ?order_id= (пустая строка). Ожидается 400."""
    resp = get_request(BASE_URL, params={"order_id": ""})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-017")
def test_get_transaction_non_numeric_id():
    """GET /transactions/not-a-number — не числовой ID. Ожидается 400 или 404."""
    url = f"{BASE_URL}/not-a-valid-id"
    resp = get_request(url)
    assert resp.status_code in (400, 404), f"Expected 400/404, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("GT-018")
def test_get_by_order_id_list_structure(payin_transaction_id):
    """GET ?order_id= — каждый элемент массива содержит transaction_id и status."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list) and len(data) > 0, "Expected non-empty list"
    for item in data:
        assert "transaction_id" in item, f"Missing transaction_id in item: {item}"
        assert "status" in item, f"Missing status in item: {item}"
