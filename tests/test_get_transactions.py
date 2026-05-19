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
)


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
def test_get_transaction_by_id(payin_transaction_id):
    """GET /{id} по реальному transaction_id. Ожидается 200 со всеми обязательными полями ответа."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data,  "Missing transaction_id"
    assert "status" in data,          "Missing status"
    assert "type" in data,            "Missing type"
    assert "merchant_data" in data,   "Missing merchant_data"
    assert "financial_data" in data,  "Missing financial_data"
    assert "created_at" in data,      "Missing created_at"
    assert data["transaction_id"] == payin_transaction_id, "transaction_id mismatch"


def test_get_transaction_fields(payin_transaction_id):
    """GET /{id} — проверка типов и формата обязательных полей ответа."""
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data["transaction_id"], str),   "transaction_id must be a string"
    assert isinstance(data["status"], str),           "status must be a string"
    assert isinstance(data["type"], str),             "type must be a string"
    assert data["type"] in ("payin", "payout"),       f"Unexpected type: {data['type']}"
    assert isinstance(data["financial_data"], dict),  "financial_data must be a dict"
    assert "amount" in data["financial_data"],        "Missing amount in financial_data"
    assert "currency" in data["financial_data"],      "Missing currency in financial_data"
    assert isinstance(data["financial_data"]["amount"], int), "amount must be an integer"
    assert len(data["financial_data"]["currency"]) == 3,     "currency must be 3-letter ISO code"


def test_get_transaction_status_is_valid(payin_transaction_id):
    """GET /{id} — статус транзакции входит в список допустимых значений по спецификации."""
    valid_statuses = {"completed", "authorized", "processing", "waiting_action", "cancelled", "rejected", "refunded"}
    url = f"{BASE_URL}/{payin_transaction_id}"
    resp = get_request(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in valid_statuses, f"Unexpected status: {data['status']}"


def test_get_transactions_by_order_id(payin_transaction_id):
    """GET ?order_id= по реальному order_id мерчанта. Ожидается 200 и массив транзакций."""
    resp = get_request(BASE_URL, params={"order_id": MERCHANT_DATA["order_id"]})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list), f"Expected a list, got {type(data)}"
    assert len(data) > 0, "Expected at least one transaction"
    item = data[0]
    assert "transaction_id" in item, "Missing transaction_id in list item"
    assert "status" in item,         "Missing status in list item"
    assert "type" in item,           "Missing type in list item"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ СЦЕНАРИИ
# ─────────────────────────────────────────────
def test_get_transaction_not_found():
    """GET по несуществующему числовому transaction_id. Ожидается 404."""
    url = f"{BASE_URL}/000000000000"
    resp = get_request(url)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_get_by_order_id_not_found():
    """GET ?order_id= с несуществующим order_id. Ожидается 404."""
    resp = get_request(BASE_URL, params={"order_id": "nonexistent_order_xyz_000"})
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_get_by_order_id_missing_param():
    """GET /transactions без параметра order_id. Ожидается 400 или 422."""
    resp = get_request(BASE_URL)
    assert resp.status_code in (400, 422), f"Expected 400/422, got {resp.status_code}: {resp.text}"


def test_get_transaction_no_auth():
    """GET /{id} без заголовков авторизации. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    resp = requests.get(url, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"


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


def test_get_transaction_missing_terminal_id():
    """GET /{id} без заголовка Api-Terminal-ID. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Signature": "0" * 64,
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"


def test_get_transaction_missing_timestamp():
    """GET /{id} без заголовка Api-Timestamp. Ожидается 400, 401 или 403."""
    url = f"{BASE_URL}/000000000000"
    headers = {
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature":   "0" * 64,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), f"Expected 4xx, got {resp.status_code}"
