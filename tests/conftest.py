import hashlib
import hmac
import json
import os
import time
import uuid
from http import HTTPStatus

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()  # читает .env из корня проекта

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
_API_BASE            = "https://papiv3preprod.testpaygate.com/api/v1"
BASE_URL             = f"{_API_BASE}/transactions"
SUBSCRIPTIONS_URL    = f"{_API_BASE}/subscriptions"
PAYMENT_LINKS_URL    = f"{_API_BASE}/payment-links"
MERCHANT_BALANCE_URL = f"{_API_BASE}/merchant/balance"

SERVICE_SECRET = os.environ["SERVICE_SECRET"]   # обязательно: задать в .env
TERMINAL_ID    = os.environ.get("TERMINAL_ID", "374")

# ─────────────────────────────────────────────
# SIGNATURE HELPERS
# ─────────────────────────────────────────────
def calc_signature(terminal_id: str, timestamp: str, raw_body: str = "") -> str:
    """HMAC-SHA256: Api-Timestamp + Api-Terminal-ID + raw_body (POST) или Api-Timestamp + Api-Terminal-ID (GET/DELETE)"""
    message = f"{timestamp}{terminal_id}{raw_body}"
    return hmac.new(
        SERVICE_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()


# ─────────────────────────────────────────────
# REQUEST BUILDERS
# ─────────────────────────────────────────────
def make_headers(terminal_id: str, raw_body: str = "", method: str = "POST") -> dict:
    """Заголовки для POST-запросов с телом и idempotency key."""
    timestamp = str(int(time.time()))
    body_for_sig = raw_body if method == "POST" else ""
    signature = calc_signature(terminal_id, timestamp, body_for_sig)
    return {
        "Content-Type":        "application/json",
        "Api-Terminal-ID":     terminal_id,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Signature":       signature,
        "Api-Timestamp":       timestamp,
    }


def make_get_headers(terminal_id: str) -> dict:
    """Заголовки для GET и DELETE запросов (без тела, без Idempotency-Key)."""
    timestamp = str(int(time.time()))
    signature = calc_signature(terminal_id, timestamp, "")
    return {
        "Api-Terminal-ID": terminal_id,
        "Api-Signature":   signature,
        "Api-Timestamp":   timestamp,
    }


def post_transaction(body: dict, terminal_id: str = None) -> requests.Response:
    """POST /transactions — создание транзакции."""
    tid = terminal_id or TERMINAL_ID
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(tid, raw)
    return requests.post(BASE_URL, data=raw, headers=headers, timeout=30)


def get_request(url: str, params: dict = None, terminal_id: str = None) -> requests.Response:
    """GET-запрос с корректной HMAC-подписью (без тела)."""
    tid = terminal_id or TERMINAL_ID
    headers = make_get_headers(tid)
    return requests.get(url, params=params, headers=headers, timeout=30)


def delete_request(url: str, terminal_id: str = None) -> requests.Response:
    """DELETE-запрос с корректной HMAC-подписью (без тела)."""
    tid = terminal_id or TERMINAL_ID
    headers = make_get_headers(tid)
    return requests.delete(url, headers=headers, timeout=30)


def post_operation(transaction_id: str, operation: str, body: dict, terminal_id: str = None) -> requests.Response:
    """POST /{transaction_id}/{operation} — capture, cancel, refunds, confirm."""
    tid = terminal_id or TERMINAL_ID
    url = f"{BASE_URL}/{transaction_id}/{operation}"
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(tid, raw)
    return requests.post(url, data=raw, headers=headers, timeout=30)


# ─────────────────────────────────────────────
# SHARED PAYLOADS
# ─────────────────────────────────────────────
CUSTOMER_DATA = {
    "contact_info": {
        "email": "user@example.com",
        "phone": "+19991231212",
        "country": "US",
        "city": "New York",
        "zip": "10001",
        "state": "NY",
    },
    "personal_info": {
        "first_name": "John",
        "last_name": "Doe",
        "date_of_birth": "1990-05-25",
        "nationality": "JP",
        "document_type": "passport",
        "document_details": {
            "number": "11223344",
            "issue_date": "2020-05-25",
            "expiry_date": "2030-05-25",
            "gender": "M",
            "issuer": "string",
            "department_code": "032-018",
            "series": "string",
        },
    },
    "browser_info": {
        "screen_height": 1080,
        "screen_width": 1920,
        "time_zone": -120,
        "color_depth": 24,
        "user_agent": "Mozilla/5.0",
        "accept_header": "application/json",
        "java_enabled": False,
        "java_script_enabled": True,
        "ip": "192.168.1.1",
        "language": "ru",
    },
    "payer_info": {"payer_id": "payer_abc123"},
}

MERCHANT_DATA = {
    "order_id": "order_1111",
    "description": "Order payment",
    "webhook_url": "https://merchant.com/webhook",
    "return_url": "https://merchant.com/return",
}

CARD_DETAILS = {
    "pan": "4111111111111111",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# Заглушка для нескольких карт. Сейчас используется только "default" (= CARD_DETAILS).
# Когда понадобится — добавьте новую карту по образцу и используйте CARDS["visa"] и т.д.
CARDS = {
    "default": CARD_DETAILS,
    # "visa": {
    #     "pan": "...",
    #     "holder": "...",
    #     "expiry_month": "...",
    #     "expiry_year": "...",
    #     "cvv": "...",
    # },
    # "mastercard": {
    #     "pan": "...",
    #     "holder": "...",
    #     "expiry_month": "...",
    #     "expiry_year": "...",
    #     "cvv": "...",
    # },
}

THREED = {"challenge_window_size": "05"}


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# HTTP LOGGING
# ─────────────────────────────────────────────
def _fmt_body(raw) -> str:
    if not raw:
        return "    (no body)"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        lines = json.dumps(json.loads(raw), ensure_ascii=False, indent=2).splitlines()
        return "\n".join("    " + line for line in lines)
    except (ValueError, TypeError):
        return "    " + str(raw)


def _status_phrase(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return ""


@pytest.fixture(autouse=True)
def log_http_calls():
    """Перехватывает HTTP-вызовы теста и печатает запрос/ответ после его завершения."""
    captures = []
    orig = requests.Session.send

    def _patched(self, prepared, **kw):
        resp = orig(self, prepared, **kw)
        captures.append((prepared, resp))
        return resp

    requests.Session.send = _patched
    yield
    requests.Session.send = orig

    bar = "━" * 64
    for prep, resp in captures:
        phrase = _status_phrase(resp.status_code)
        print(f"\n{bar}")
        print(f"  {prep.method} {prep.url}")
        print(f"  ── Request body {'─' * 46}")
        print(_fmt_body(prep.body))
        print(f"  ── Response: {resp.status_code} {phrase} {'─' * max(0, 44 - len(phrase))}")
        print(_fmt_body(resp.text))
        print(bar)


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def payin_transaction_id():
    """Делает реальный Payin и возвращает transaction_id для Rebill/Recurrent/Refund."""
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Payin failed: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data, f"No transaction_id in response: {data}"
    return data["transaction_id"]


@pytest.fixture(scope="session")
def payin_block_transaction_id():
    """Создаёт Payin с capture_mode=manual (холд средств). Используется в тестах /capture и /cancel."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": "order_block_fixture"},
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Block Payin failed: {resp.text}"
    data = resp.json()
    assert "transaction_id" in data, f"No transaction_id in response: {data}"
    return data["transaction_id"]
