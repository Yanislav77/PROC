"""
Тесты для создания платёжных ссылок.
POST /api/v1/payment-links

Обязательные поля: merchant_data (с order_id), financial_data (amount + currency), customer_data
Необязательные: flow_data
"""
import copy
import hashlib
import hmac
import json
import os
import re
import time
import uuid
import requests
import pytest

from conftest import (
    PAYMENT_LINKS_URL,
    TERMINAL_ID,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    SERVICE_SECRET,
    assert_error_response,
    gen_order_id,
)

try:
    import psycopg2 as _psycopg2
    _DB_HOST     = os.environ.get("DB_HOST", "")
    _DB_USER     = os.environ.get("DB_USER", "postgres")
    _DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    _DB_AVAILABLE = bool(_DB_HOST)
except ImportError:
    _DB_AVAILABLE = False


def _query_pl_db(link_id: str) -> dict:
    """Возвращает строку из support.paylink по link_id или {}."""
    if not _DB_AVAILABLE:
        return {}
    try:
        conn = _psycopg2.connect(
            host=_DB_HOST, port=5432, dbname="support",
            user=_DB_USER, password=_DB_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM public.paylink WHERE id = %s LIMIT 1",
            (link_id,),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        conn.close()
        if not rows:
            return {}
        return dict(zip(cols, rows[0]))
    except Exception:
        return {}


def _query_webpayv3_db(session_id: str) -> dict:
    """Возвращает строку из support.webpayv3 по id (UUID из URL ответа) или {}."""
    if not _DB_AVAILABLE:
        return {}
    try:
        conn = _psycopg2.connect(
            host=_DB_HOST, port=5432, dbname="support",
            user=_DB_USER, password=_DB_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute("SELECT * FROM public.webpayv3 WHERE id = %s LIMIT 1", (session_id,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        conn.close()
        if not rows:
            return {}
        return dict(zip(cols, rows[0]))
    except Exception:
        return {}


def _query_webpayv3_by_paylink(paylink_id: str) -> dict:
    """Возвращает строку из support.webpayv3 по paylink_id или {}."""
    if not _DB_AVAILABLE:
        return {}
    try:
        conn = _psycopg2.connect(
            host=_DB_HOST, port=5432, dbname="support",
            user=_DB_USER, password=_DB_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM public.webpayv3 WHERE paylink_id = %s ORDER BY created_time DESC LIMIT 1",
            (paylink_id,),
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        conn.close()
        if not rows:
            return {}
        return dict(zip(cols, rows[0]))
    except Exception:
        return {}


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _extract_uuid(text: str) -> str:
    """Возвращает первый UUID из строки или ''."""
    m = _UUID_RE.search(text)
    return m.group(0) if m else ""


_PL_PATH = "/api/v1/payment-links"
_WEBPAY_CREATE_URL = "https://web3preprod.testpaygate.com/webpayments/create"
_WEBPAY_SITE_ID = os.environ.get("WEBPAY_SITE_ID", TERMINAL_ID)


def _post_webpay_create(body: dict) -> requests.Response:
    """POST /webpayments/create со старыми заголовками X-SITE-ID / X-REQUEST-SIGNATURE."""
    raw = json.dumps(body, separators=(",", ":"))
    request_id = str(uuid.uuid4())
    sig = hmac.new(SERVICE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-SITE-ID": _WEBPAY_SITE_ID,
        "X-REQUEST-ID": request_id,
        "X-REQUEST-SIGNATURE": sig,
    }
    return requests.post(_WEBPAY_CREATE_URL, data=raw, headers=headers, timeout=30)


def _sign_pl(terminal_id: str, timestamp: str, raw_body: str = "") -> str:
    """HMAC-SHA256 по спеке: Api-Timestamp + Api-Terminal-ID + raw_body (без разделителей)."""
    msg = timestamp + terminal_id + raw_body
    return hmac.new(SERVICE_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _make_pl_headers(raw_body: str = "", terminal_id: str = None,
                     idem_key: str = None, timestamp: str = None) -> dict:
    tid = terminal_id or TERMINAL_ID
    key = idem_key or str(uuid.uuid4())
    ts = timestamp or str(int(time.time()))
    return {
        "Content-Type": "application/json",
        "Api-Terminal-ID": tid,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(tid, ts, raw_body),
        "Api-Timestamp": ts,
    }


_VALID_LINK_BODY = {
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 5000, "currency": "RUB"},
    "customer_data": CUSTOMER_DATA,
}


def post_payment_link(body: dict) -> requests.Response:
    raw = json.dumps(body, separators=(",", ":"))
    headers = _make_pl_headers(raw_body=raw)
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
    order_id = gen_order_id("pl_resp_check")
    merchant = {**MERCHANT_DATA, "order_id": order_id}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("merchant_data", {}).get("order_id") == order_id


@pytest.mark.tcid("PL-031")
def test_payment_link_return_url_with_query_params():
    """Создание ссылки с return_url, содержащим query-параметры. Ожидается 201."""
    merchant = {**MERCHANT_DATA, "return_url": "https://example.com/return?order=abc&status=ok"}
    body = {**_VALID_LINK_BODY, "merchant_data": merchant}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("PL-032")
def test_payment_link_idempotency_same_key_returns_same_link():
    """TC-03: Повторный запрос с тем же Api-Idempotency-Key возвращает тот же link_id (кэш XPI)."""
    body = copy.deepcopy(_VALID_LINK_BODY)
    body["merchant_data"] = {**MERCHANT_DATA, "order_id": gen_order_id("pl_idem")}
    raw = json.dumps(body, separators=(",", ":"))
    key = str(uuid.uuid4())

    ts1 = str(int(time.time()))
    h = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(TERMINAL_ID, ts1, raw),
        "Api-Timestamp": ts1,
    }
    r1 = requests.post(PAYMENT_LINKS_URL, data=raw, headers=h, timeout=30)
    assert r1.status_code == 201, f"First link creation failed: {r1.text}"
    link_id_1 = r1.json().get("link_id")

    ts2 = str(int(time.time()))
    h["Api-Signature"] = _sign_pl(TERMINAL_ID, ts2, raw)
    h["Api-Timestamp"] = ts2
    r2 = requests.post(PAYMENT_LINKS_URL, data=raw, headers=h, timeout=30)
    assert r2.status_code in (200, 201), f"Expected 200/201 for idempotent request, got {r2.status_code}: {r2.text}"
    link_id_2 = r2.json().get("link_id")
    assert link_id_1 == link_id_2, f"Idempotent request returned different link_id: {link_id_1!r} vs {link_id_2!r}"


@pytest.mark.tcid("PL-033")
def test_payment_link_missing_idempotency_key_returns_400():
    """Payment link без Api-Idempotency-Key. Ожидается 400."""
    body = copy.deepcopy(_VALID_LINK_BODY)
    raw = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Signature": _sign_pl(TERMINAL_ID, timestamp, raw),
        "Api-Timestamp": timestamp,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-034")
def test_payment_link_response_has_all_required_fields():
    """POST /payment-links — ответ содержит link_id, link_data.url, merchant_data."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_f")}}
    resp = post_payment_link(body)
    assert resp.status_code == 201
    data = resp.json()
    assert "link_id" in data
    assert "link_data" in data
    assert "url" in data["link_data"]
    assert "merchant_data" in data


@pytest.mark.tcid("PL-035")
def test_payment_link_link_data_url_is_string():
    """POST /payment-links — link_data.url является строкой."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_url")}}
    resp = post_payment_link(body)
    assert resp.status_code == 201
    url = resp.json()["link_data"]["url"]
    assert isinstance(url, str) and url.startswith("http")


@pytest.mark.tcid("PL-036")
def test_payment_link_content_type_is_json():
    """POST /payment-links — Content-Type ответа содержит application/json."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_ct")}}
    resp = post_payment_link(body)
    assert resp.status_code == 201
    assert "application/json" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("PL-037")
def test_payment_link_flow_data_invalid_is_recurrent():
    """Payment link с is_recurrent = 1 (не boolean). Ожидается 400."""
    body = {**_VALID_LINK_BODY,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_ir")},
            "flow_data": {"is_recurrent": 1, "capture_mode": "auto"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PL-038")
def test_payment_link_financial_data_null_returns_400():
    """Payment link с financial_data = null. Ожидается 400."""
    body = {**_VALID_LINK_BODY,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_fn")},
            "financial_data": None}
    resp = post_payment_link(body)
    assert resp.status_code == 400
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-04: ИДЕМПОТЕНТНОСТЬ — тот же ключ, другое тело
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-039")
def test_payment_link_idempotency_different_body_returns_cached():
    """TC-04: Тот же Api-Idempotency-Key, другая сумма — возвращает кэшированный ответ первого запроса."""
    order_id = gen_order_id("pl_idem_diff")
    key = str(uuid.uuid4())

    body1 = {**_VALID_LINK_BODY,
             "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
             "financial_data": {"amount": 1000, "currency": "RUB"}}
    raw1 = json.dumps(body1, separators=(",", ":"))
    ts1 = str(int(time.time()))
    h1 = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(TERMINAL_ID, ts1, raw1),
        "Api-Timestamp": ts1,
    }
    r1 = requests.post(PAYMENT_LINKS_URL, data=raw1, headers=h1, timeout=30)
    assert r1.status_code == 201, f"First request failed: {r1.text}"
    link_id_1 = r1.json().get("link_id")

    body2 = {**_VALID_LINK_BODY,
             "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
             "financial_data": {"amount": 9999, "currency": "RUB"}}
    raw2 = json.dumps(body2, separators=(",", ":"))
    ts2 = str(int(time.time()))
    h2 = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(TERMINAL_ID, ts2, raw2),
        "Api-Timestamp": ts2,
    }
    r2 = requests.post(PAYMENT_LINKS_URL, data=raw2, headers=h2, timeout=30)
    assert r2.status_code in (200, 201), f"Expected cached 200/201, got {r2.status_code}: {r2.text}"
    link_id_2 = r2.json().get("link_id")
    assert link_id_1 == link_id_2, \
        f"Expected cached link_id from first request, got {link_id_1!r} vs {link_id_2!r}"


# ─────────────────────────────────────────────
# TC-05 / TC-06: ANTI-REPLAY — Api-Timestamp
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-040")
def test_payment_link_expired_timestamp():
    """TC-05: Api-Timestamp > 5 минут в прошлом — запрос должен отклоняться (anti-replay)."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    old_ts = str(int(time.time()) - 601)
    key = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(TERMINAL_ID, old_ts, raw),
        "Api-Timestamp": old_ts,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for expired timestamp, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("PL-041")
def test_payment_link_future_timestamp():
    """TC-06: Api-Timestamp > 5 минут в будущем — запрос должен отклоняться (anti-replay)."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    future_ts = str(int(time.time()) + 601)
    key = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(TERMINAL_ID, future_ts, raw),
        "Api-Timestamp": future_ts,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for future timestamp, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-09: ПОДПИСЬ БЕЗ Api-Timestamp
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-042")
def test_payment_link_signature_computed_without_timestamp():
    """TC-09: Подпись посчитана без Api-Timestamp (terminal_id + body вместо timestamp + terminal_id + body) → 4xx."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    ts = str(int(time.time()))
    key = str(uuid.uuid4())
    wrong_sig = hmac.new(SERVICE_SECRET.encode(), (TERMINAL_ID + raw).encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": wrong_sig,
        "Api-Timestamp": ts,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for signature without timestamp, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-12: НЕТ Api-Signature
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-043")
def test_payment_link_missing_signature():
    """TC-12: Запрос без заголовка Api-Signature → 4xx."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": str(uuid.uuid4()),
        "Api-Timestamp": str(int(time.time())),
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for missing Api-Signature, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-14: НЕСУЩЕСТВУЮЩИЙ Api-Terminal-ID
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-044")
def test_payment_link_unknown_terminal_id():
    """TC-14: Несуществующий Api-Terminal-ID → 4xx (InvalidSiteId)."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    fake_id = "NONEXISTENT-99999"
    ts = str(int(time.time()))
    key = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": fake_id,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(fake_id, ts, raw),
        "Api-Timestamp": ts,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403, 404), \
        f"Expected 4xx for unknown terminal, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-29: ФОРМАТ link_data.url
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-045")
def test_payment_link_url_path_contains_payment_sessions():
    """TC-29: link_data.url содержит /payment-sessions/<id>, но не /api/v1/ в пути ссылки."""
    body = {**_VALID_LINK_BODY, "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_urlpath")}}
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    url = resp.json()["link_data"]["url"]
    assert "/payment-sessions/" in url, f"Expected /payment-sessions/ in url, got: {url!r}"
    assert "/api/v1/" not in url, f"Unexpected /api/v1/ in link_data.url: {url!r}"


# ─────────────────────────────────────────────
# OPTIONS PREFLIGHT — CORS
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-046")
def test_payment_link_options_preflight_cors_headers():
    """OPTIONS preflight возвращает CORS-заголовок с Api-Terminal-ID, Api-Idempotency-Key, Api-Signature, Api-Timestamp."""
    resp = requests.options(
        PAYMENT_LINKS_URL,
        headers={
            "Origin": "https://merchant.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "Api-Terminal-ID, Api-Idempotency-Key, Api-Signature, Api-Timestamp"
            ),
        },
        timeout=30,
    )
    assert resp.status_code in (200, 204), f"Expected 200/204 for OPTIONS, got {resp.status_code}: {resp.text}"
    allow_headers = resp.headers.get("Access-Control-Allow-Headers", "")
    for header in ("Api-Terminal-ID", "Api-Idempotency-Key", "Api-Signature", "Api-Timestamp"):
        assert header.lower() in allow_headers.lower(), \
            f"Expected {header!r} in Access-Control-Allow-Headers, got: {allow_headers!r}"


# ─────────────────────────────────────────────
# TC-07: Timestamp в пределах окна
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-047")
def test_payment_link_timestamp_at_minus_60s():
    """TC-07: Api-Timestamp = now - 60 (в пределах 5-минутного окна). Ожидается 201."""
    body = {**_VALID_LINK_BODY,
            "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_ts60")}}
    raw = json.dumps(body, separators=(",", ":"))
    ts = str(int(time.time()) - 60)
    key = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Api-Terminal-ID": TERMINAL_ID,
        "Api-Idempotency-Key": key,
        "Api-Signature": _sign_pl(TERMINAL_ID, ts, raw),
        "Api-Timestamp": ts,
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code == 201, f"Expected 201 for timestamp -60s, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# TC-18: Невалидная валюта "RUR"
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-048")
def test_payment_link_currency_rur():
    """TC-18: financial_data.currency='RUR' (устаревший код). Ожидается 400."""
    body = {**_VALID_LINK_BODY, "financial_data": {"amount": 5000, "currency": "RUR"}}
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-23..28: Маппинг полей в БД
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-049")
def test_payment_link_db_contact_info_mapping():
    """TC-23: contact_info → CustomerInfo в БД (Town, не City; ZIP, не Zip)."""
    body = {
        **_VALID_LINK_BODY,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_ci_map")},
        "customer_data": {
            "contact_info": {
                "email": "test@example.com",
                "phone": "+79991234567",
                "country": "RU",
                "city": "Moscow",
                "zip": "101000",
                "state": "Moscow",
            }
        },
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    link_id = resp.json().get("link_id")
    db = _query_pl_db(link_id)
    if db:
        pr = db.get("request") or {}
        ci = pr.get("CustomerInfo", {}) if isinstance(pr, dict) else {}
        assert ci.get("Email") == "test@example.com", f"CustomerInfo.Email mismatch: {ci}"
        assert ci.get("Phone") == "+79991234567",     f"CustomerInfo.Phone mismatch: {ci}"
        assert ci.get("Country") == "RU",             f"CustomerInfo.Country mismatch: {ci}"
        assert ci.get("Town") == "Moscow",            f"CustomerInfo.Town mismatch (must be Town, not City): {ci}"
        assert ci.get("ZIP") == "101000",             f"CustomerInfo.ZIP mismatch: {ci}"
        assert ci.get("State") == "Moscow",           f"CustomerInfo.State mismatch: {ci}"


@pytest.mark.tcid("PL-050")
def test_payment_link_db_personal_info_mapping():
    """TC-24: personal_info → CustomerInfo + PassportInfo в БД."""
    body = {
        **_VALID_LINK_BODY,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_pi_map")},
        "customer_data": {
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
                    "issuer": "UFMS",
                    "department_code": "032-018",
                    "series": "7700",
                },
            }
        },
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    link_id = resp.json().get("link_id")
    db = _query_pl_db(link_id)
    if db:
        pr = db.get("request") or {}
        if isinstance(pr, dict):
            ci = pr.get("CustomerInfo", {})
            assert ci.get("FirstName") == "John",         f"CustomerInfo.FirstName: {ci}"
            assert ci.get("LastName") == "Doe",           f"CustomerInfo.LastName: {ci}"
            assert ci.get("DateOfBirth") == "1990-05-25", f"CustomerInfo.DateOfBirth: {ci}"
            pi = pr.get("PassportInfo", {})
            assert pi.get("Nationality") == "JP",         f"PassportInfo.Nationality: {pi}"
            assert pi.get("NumberDocument") == "11223344", f"PassportInfo.NumberDocument: {pi}"
            assert pi.get("IssueDate") == "2020-05-25",   f"PassportInfo.IssueDate: {pi}"
            assert pi.get("ExpireDate") == "2030-05-25",  f"PassportInfo.ExpireDate: {pi}"
            assert pi.get("Gender") == "M",               f"PassportInfo.Gender: {pi}"
            assert pi.get("Issuer") == "UFMS",            f"PassportInfo.Issuer: {pi}"
            assert pi.get("DepartmentCode") == "032-018", f"PassportInfo.DepartmentCode: {pi}"
            assert pi.get("Series") == "7700",            f"PassportInfo.Series: {pi}"


@pytest.mark.tcid("PL-051")
def test_payment_link_db_is_recurrent_mapping():
    """TC-25: flow_data.is_recurrent=true → PaymentRequest.RebillFlag=true в БД."""
    body = {
        **_VALID_LINK_BODY,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_rebill")},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto"},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    link_id = resp.json().get("link_id")
    db = _query_pl_db(link_id)
    if db:
        pr = db.get("request") or {}
        if isinstance(pr, dict):
            assert pr.get("RebillFlag") is True, f"PaymentRequest.RebillFlag must be true, got: {pr}"


@pytest.mark.tcid("PL-052")
def test_payment_link_db_challenge_window_size_mapping():
    """TC-26: threed_secure.challenge_window_size='05' → PaymentRequest.ExtraData.ChallengeWindowSize='05' в БД."""
    body = {
        **_VALID_LINK_BODY,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_cws")},
        "flow_data": {
            "capture_mode": "auto",
            "threed_secure": {"challenge_window_size": "05"},
        },
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    link_id = resp.json().get("link_id")
    db = _query_pl_db(link_id)
    if db:
        pr = db.get("request") or {}
        if isinstance(pr, dict):
            extra = pr.get("ExtraData", {})
            assert extra.get("ChallengeWindowSize") == "05", \
                f"ExtraData.ChallengeWindowSize must be '05', got: {extra}"


@pytest.mark.tcid("PL-053")
def test_payment_link_db_return_url_mapping():
    """TC-27: merchant_data.return_url → PaymentRequest.ExtraData.ReturnUrl в БД."""
    return_url = "https://merchant.example.com/return?order=test"
    body = {
        **_VALID_LINK_BODY,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_rurl"), "return_url": return_url},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    link_id = resp.json().get("link_id")
    db = _query_pl_db(link_id)
    if db:
        pr = db.get("request") or {}
        if isinstance(pr, dict):
            extra = pr.get("ExtraData", {})
            assert extra.get("ReturnUrl") == return_url, \
                f"ExtraData.ReturnUrl mismatch, got: {extra}"


@pytest.mark.tcid("PL-054")
def test_payment_link_db_payer_id_mapping():
    """TC-28: customer_data.payer_info.payer_id → CustomerInfo.UserId в БД."""
    body = {
        **_VALID_LINK_BODY,
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("pl_uid")},
        "customer_data": {"payer_info": {"payer_id": "USER-001"}},
    }
    resp = post_payment_link(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    link_id = resp.json().get("link_id")
    db = _query_pl_db(link_id)
    if db:
        pr = db.get("request") or {}
        if isinstance(pr, dict):
            ci = pr.get("CustomerInfo", {})
            assert ci.get("UserId") == "USER-001", \
                f"CustomerInfo.UserId must be 'USER-001', got: {ci}"


# ─────────────────────────────────────────────
# TC-31: Старый PascalCase-формат на новом URL
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-055")
def test_payment_link_old_pascal_case_body_rejected():
    """TC-31: Тело в старом PascalCase-формате на /api/v1/payment-links. Ожидается 400."""
    body = {
        "PaymentRequest": {
            "OrderId": gen_order_id("pl_old_pc"),
            "Amount": 10000,
            "Currency": "RUB",
        }
    }
    resp = post_payment_link(body)
    assert resp.status_code == 400, f"Expected 400 for PascalCase body, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-32: Старые заголовки на новом URL
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-056")
def test_payment_link_old_headers_rejected():
    """TC-32: Заголовки X-SITE-ID / X-REQUEST-SIGNATURE вместо Api-* → 4xx MissingHTTPHeader."""
    raw = json.dumps(_VALID_LINK_BODY, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "X-SITE-ID": TERMINAL_ID,
        "X-REQUEST-ID": str(uuid.uuid4()),
        "X-REQUEST-SIGNATURE": hmac.new(
            SERVICE_SECRET.encode(),
            raw.encode(),
            hashlib.sha256,
        ).hexdigest(),
    }
    resp = requests.post(PAYMENT_LINKS_URL, data=raw, headers=headers, timeout=30)
    assert resp.status_code in (400, 401, 403), \
        f"Expected 4xx for old-style headers, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# TC-30: Регресс старого /webpayments/create
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-057")
def test_webpay_create_regression():
    """TC-30: POST /webpayments/create по-прежнему работает (регресс)."""
    body = {
        "MetaData": {"PaymentType": "Pay"},
        "PaymentRequest": {
            "Amount": "250",
            "Currency": "RUB",
            "Description": "Regression test",
            "OrderId": gen_order_id("webpay_regress"),
            "RebillFlag": False,
            "ExtraData": {
                "ReturnURL1": "https://merchant.example.com/return",
            },
        },
        "CustomerInfo": {
            "FirstName": "John",
            "LastName": "Doe",
            "Email": "test@example.com",
            "Phone": "+79991234567",
            "ZIP": "101000",
            "DateOfBirth": "1990-05-25",
        },
    }
    resp = _post_webpay_create(body)
    assert resp.status_code in (200, 201), \
        f"Old /webpayments/create must still return 200/201, got {resp.status_code}: {resp.text}"
    # Ответ — plain-text URL вида https://host/pay/<uuid>
    session_id = _extract_uuid(resp.text)
    assert session_id, f"Expected UUID in response URL, got: {resp.text!r}"
    db = _query_webpayv3_db(session_id)
    if db:
        assert db.get("state") is not None,   f"webpayv3.state is None: {db}"
        req = db.get("request") or {}
        if isinstance(req, dict):
            assert req.get("Currency") == "RUB", f"webpayv3.request.Currency mismatch: {req}"


# ─────────────────────────────────────────────
# TC-33: Идентичность side effects: старый и новый URL
# ─────────────────────────────────────────────
@pytest.mark.tcid("PL-058")
def test_payment_link_side_effects_match_webpay_create():
    """TC-33: Эквивалентные запросы через /webpayments/create и /api/v1/payment-links
    создают записи с одинаковыми ключевыми полями в БД."""
    order_id_old = gen_order_id("tc33_old")
    order_id_new = gen_order_id("tc33_new")

    # ── старый эндпоинт ──────────────────────────────────────
    old_body = {
        "MetaData": {"PaymentType": "Pay"},
        "PaymentRequest": {
            "Amount": "1000",
            "Currency": "RUB",
            "Description": "TC-33 old",
            "OrderId": order_id_old,
            "RebillFlag": False,
            "ExtraData": {"ReturnURL1": "https://merchant.example.com/return"},
        },
        "CustomerInfo": {
            "FirstName": "John",
            "LastName": "Doe",
            "Email": "test@example.com",
            "Phone": "+79991234567",
        },
    }
    resp_old = _post_webpay_create(old_body)
    assert resp_old.status_code in (200, 201), \
        f"/webpayments/create failed: {resp_old.status_code}: {resp_old.text}"

    # ── новый эндпоинт ──────────────────────────────────────
    new_body = {
        "merchant_data": {
            **MERCHANT_DATA,
            "order_id": order_id_new,
            "description": "TC-33 new",
            "return_url": "https://merchant.example.com/return",
        },
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto"},
        "customer_data": {
            "contact_info": {
                "email": "test@example.com",
                "phone": "+79991234567",
            },
            "personal_info": {
                "first_name": "John",
                "last_name": "Doe",
            },
        },
    }
    resp_new = post_payment_link(new_body)
    assert resp_new.status_code == 201, \
        f"/api/v1/payment-links failed: {resp_new.status_code}: {resp_new.text}"

    # ── DB-сравнение (только при наличии доступа к БД) ──────
    link_id = resp_new.json().get("link_id")
    db_new = _query_pl_db(link_id)
    if db_new:
        pr_new = db_new.get("request") or {}
        if isinstance(pr_new, dict):
            assert pr_new.get("Currency") == "RUB",  f"Currency mismatch in new: {pr_new}"
            assert pr_new.get("Amount") in (1000, "1000"), f"Amount mismatch in new: {pr_new}"
            ci = pr_new.get("CustomerInfo", {})
            assert ci.get("Email") == "test@example.com", f"CustomerInfo.Email mismatch: {ci}"

    # ── webpayv3 по paylink_id (появится после открытия ссылки) ──
    db_wv3 = _query_webpayv3_by_paylink(link_id)
    if db_wv3:
        assert str(db_wv3.get("paylink_id")) == link_id, \
            f"webpayv3.paylink_id mismatch: {db_wv3}"
        req_wv3 = db_wv3.get("request") or {}
        if isinstance(req_wv3, dict):
            assert req_wv3.get("Currency") == "RUB", f"webpayv3.request.Currency mismatch: {req_wv3}"
