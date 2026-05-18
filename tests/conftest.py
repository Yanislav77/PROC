import hashlib
import hmac
import json
import os
import time

import pytest
import requests

BASE_URL = "https://papiv3preprod.testpaygate.com/api/v1/transactions"

TERMINAL_ID = os.environ.get("API_TERMINAL_ID", "your-terminal-id")
SECRET_KEY = os.environ.get("API_SECRET_KEY", "your-secret-key").encode()


def make_signature(method: str, timestamp: str, raw_body: str) -> str:
    """HMAC-SHA256: METHOD\nApi-Terminal-ID\nApi-Timestamp\nraw_body"""
    message = "\n".join([method, TERMINAL_ID, timestamp, raw_body]).encode()
    return hmac.new(SECRET_KEY, message, hashlib.sha256).hexdigest()


def auth_headers(method: str, body: dict | None = None) -> dict:
    timestamp = str(int(time.time()))
    raw_body = json.dumps(body, separators=(",", ":")) if body else ""
    signature = make_signature(method, timestamp, raw_body)
    return {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Timestamp": timestamp,
        "Api-Signature": signature,
    }


def post(path: str = "", body: dict | None = None) -> requests.Response:
    url = BASE_URL + (f"/{path}" if path else "")
    headers = auth_headers("POST", body)
    return requests.post(url, json=body, headers=headers)


def get(path: str = "", params: dict | None = None) -> requests.Response:
    url = BASE_URL + (f"/{path}" if path else "")
    headers = auth_headers("GET")
    return requests.get(url, params=params, headers=headers)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    yield s


@pytest.fixture
def card_payin_payload():
    return {
        "type": "payin",
        "method": "card",
        "amount": 100,
        "currency": "USD",
        "order_id": f"order-card-{int(time.time())}",
        "card": {
            "number": "4111111111111111",
            "exp_month": "12",
            "exp_year": "2030",
            "cvv": "123",
        },
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
        },
    }


@pytest.fixture
def p2p_payin_payload():
    return {
        "type": "payin",
        "method": "p2p",
        "amount": 200,
        "currency": "USD",
        "order_id": f"order-p2p-{int(time.time())}",
        "customer": {"name": "Test User", "email": "test@example.com"},
    }


@pytest.fixture
def mobile_payin_payload():
    return {
        "type": "payin",
        "method": "mobile",
        "amount": 50,
        "currency": "USD",
        "order_id": f"order-mobile-{int(time.time())}",
        "phone": "+79001234567",
        "customer": {"name": "Test User", "email": "test@example.com"},
    }


@pytest.fixture
def block_payin_payload():
    return {
        "type": "payin",
        "method": "block",
        "amount": 100,
        "currency": "USD",
        "order_id": f"order-block-{int(time.time())}",
        "card": {
            "number": "4111111111111111",
            "exp_month": "12",
            "exp_year": "2030",
            "cvv": "123",
        },
        "customer": {"name": "Test User", "email": "test@example.com"},
    }


@pytest.fixture
def recurrent_payload():
    return {
        "type": "recurrent",
        "amount": 100,
        "currency": "USD",
        "order_id": f"order-recurrent-{int(time.time())}",
        "recurrent_token": "valid-recurrent-token",
        "customer": {"name": "Test User", "email": "test@example.com"},
    }


@pytest.fixture
def payout_payload():
    return {
        "type": "payout",
        "amount": 100,
        "currency": "USD",
        "order_id": f"order-payout-{int(time.time())}",
        "card": {
            "number": "4111111111111111",
            "exp_month": "12",
            "exp_year": "2030",
        },
        "customer": {"name": "Test User", "email": "test@example.com"},
    }


@pytest.fixture
def rebill_payload():
    return {
        "type": "rebill",
        "amount": 100,
        "currency": "USD",
        "order_id": f"order-rebill-{int(time.time())}",
        "rebill_token": "valid-rebill-token",
    }


@pytest.fixture
def rebill_block_payload():
    return {
        "type": "rebill_block",
        "amount": 100,
        "currency": "USD",
        "order_id": f"order-rebill-block-{int(time.time())}",
        "rebill_token": "valid-rebill-token",
    }
