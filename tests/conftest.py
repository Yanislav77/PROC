import hashlib
import hmac
import html as _html
import json
import os
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

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
# REPORT FILE (HTML)
# ─────────────────────────────────────────────
_report_file = None
_http_captures: dict = {}  # nodeid -> list[(PreparedRequest, Response)]
_call_reports:  dict = {}  # nodeid -> report (stored until teardown phase)
_test_counter = 0

_REPORTS_DIR = Path(__file__).parent.parent / "reports"


def _make_report_suffix(config) -> str:
    args = [a for a in config.args if not a.startswith("-")]
    if not args:
        return "all"
    raw = args[0].replace("\\", "/")
    if "::" in raw:
        file_part, test_part = raw.split("::", 1)
        stem = Path(file_part).stem
        test_clean = test_part.replace("[", "_").replace("]", "")
        return f"{stem}__{test_clean}"
    stem = Path(raw).stem
    return "all" if stem in ("tests", "test", ".") or not stem else stem


def _esc(text) -> str:
    return _html.escape(str(text))


def _fmt_body_plain(raw) -> str:
    """Форматирует тело запроса/ответа как текст (без отступа) для HTML <pre>."""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except (ValueError, TypeError):
        return str(raw)


def _sc_class(code: int) -> str:
    if 200 <= code < 300:
        return "s2xx"
    if 400 <= code < 500:
        return "s4xx"
    return "s5xx"


def _write_report_entry(nodeid: str, status: str, error, captures: list) -> None:
    global _test_counter
    _test_counter += 1
    idx = _test_counter
    f = _report_file

    css = "passed" if status == "PASSED" else "failed"
    badge = "✓ PASSED" if status == "PASSED" else "✗ FAILED"
    open_attr = " open" if status != "PASSED" else ""
    icon = "▲" if open_attr else "▼"

    f.write(f'<div class="test {css}">\n')
    f.write(f'  <div class="test-header" onclick="toggle({idx})">\n')
    f.write(f'    <span class="badge">{badge}</span>\n')
    f.write(f'    <span class="test-name">{_esc(nodeid)}</span>\n')
    f.write(f'    <span class="icon" id="i{idx}">{icon}</span>\n')
    f.write(f'  </div>\n')
    f.write(f'  <div class="test-body{open_attr}" id="b{idx}">\n')

    if error:
        f.write('    <div class="section-label">Error</div>\n')
        f.write(f'    <div class="error-block"><pre>{_esc(error)}</pre></div>\n')

    for prep, resp in captures:
        phrase = _status_phrase(resp.status_code)
        sc = _sc_class(resp.status_code)

        f.write('    <div class="section-label">Request</div>\n')
        f.write(f'    <p class="http-line"><span class="method">{_esc(prep.method)}</span>'
                f' <span class="url">{_esc(prep.url)}</span></p>\n')
        body_text = _fmt_body_plain(prep.body)
        if body_text:
            f.write(f'    <pre class="body">{_esc(body_text)}</pre>\n')

        f.write('    <div class="section-label">Response</div>\n')
        f.write(f'    <p class="http-line"><span class="status-code {sc}">'
                f'{resp.status_code} {_esc(phrase)}</span></p>\n')
        resp_text = _fmt_body_plain(resp.text)
        if resp_text:
            f.write(f'    <pre class="body">{_esc(resp_text)}</pre>\n')

    f.write('  </div>\n</div>\n')
    f.flush()


def pytest_configure(config):
    global _report_file, _test_counter
    _test_counter = 0
    _REPORTS_DIR.mkdir(exist_ok=True)
    suffix = _make_report_suffix(config)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = _REPORTS_DIR / f"{ts}_{suffix}.html"
    _report_file = path.open("w", encoding="utf-8")
    _report_file.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Report — {_esc(suffix)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:24px;line-height:1.5}}
h1{{color:#fff;font-size:1.4em;margin-bottom:6px}}
.meta{{color:#888;font-size:.85em;margin-bottom:20px}}
#summary{{display:flex;gap:20px;margin-bottom:24px;font-size:1em;align-items:center}}
.sum-p{{color:#4caf50;font-weight:bold}}
.sum-f{{color:#f44336;font-weight:bold}}
.sum-t{{color:#aaa}}
.test{{border-radius:6px;margin-bottom:8px;overflow:hidden;border:1px solid transparent}}
.test.passed{{border-color:#2d4a2d}}
.test.failed{{border-color:#4a2020}}
.test-header{{display:flex;align-items:center;gap:12px;padding:10px 14px;cursor:pointer;user-select:none}}
.test.passed .test-header{{background:#1b3a1b}}
.test.failed .test-header{{background:#3a1b1b}}
.test-header:hover{{filter:brightness(1.2)}}
.badge{{font-size:.75em;font-weight:bold;padding:2px 8px;border-radius:10px;flex-shrink:0}}
.test.passed .badge{{background:#2e7d32;color:#a5d6a7}}
.test.failed .badge{{background:#b71c1c;color:#ffcdd2}}
.test-name{{font-family:'Consolas',monospace;font-size:.88em;color:#ddd;word-break:break-all}}
.icon{{margin-left:auto;color:#666;font-size:.8em;flex-shrink:0}}
.test-body{{display:none;padding:14px 16px;background:#16213e;border-top:1px solid #2a2a4a}}
.test-body.open{{display:block}}
.section-label{{font-size:.72em;font-weight:bold;letter-spacing:.08em;color:#5c7aaa;text-transform:uppercase;margin:12px 0 6px}}
.section-label:first-child{{margin-top:0}}
.http-line{{font-family:monospace;font-size:.85em;margin-bottom:6px}}
.method{{color:#82aaff;font-weight:bold}}
.url{{color:#c3e88d}}
.status-code{{font-family:monospace;font-weight:bold;font-size:.85em}}
.s2xx{{color:#4caf50}}.s4xx{{color:#ff9800}}.s5xx{{color:#f44336}}
pre.body{{background:#0d1117;border:1px solid #2a2a4a;border-radius:4px;padding:10px 12px;
  font-family:'Consolas',monospace;font-size:.82em;color:#cdd9e5;
  white-space:pre-wrap;word-break:break-all;max-height:320px;overflow-y:auto;margin:0}}
.error-block{{background:#1a0a0a;border-left:3px solid #f44336;border-radius:0 4px 4px 0;padding:12px;margin-top:8px}}
.error-block pre{{color:#ff8a80;font-size:.82em;white-space:pre-wrap;word-break:break-all;
  max-height:400px;overflow-y:auto;margin:0}}
</style>
<script>
function toggle(id){{
  var b=document.getElementById('b'+id),i=document.getElementById('i'+id);
  b.classList.toggle('open');
  i.textContent=b.classList.contains('open')?'▲':'▼';
}}
window.onload=function(){{
  var p=document.querySelectorAll('.test.passed').length;
  var f=document.querySelectorAll('.test.failed').length;
  document.getElementById('summary').innerHTML=
    '<span class="sum-p">✓ '+p+' passed</span>'+
    (f?'<span class="sum-f">&nbsp;&nbsp;✗ '+f+' failed</span>':'')+
    '<span class="sum-t">&nbsp;&nbsp;/ '+(p+f)+' total</span>';
}};
</script>
</head>
<body>
<h1>Test Report</h1>
<div class="meta">Suite: <b>{_esc(suffix)}</b> &nbsp;|&nbsp; Started: {started}</div>
<div id="summary"></div>
""")
    _report_file.flush()


def pytest_unconfigure(config):
    global _report_file
    if _report_file:
        finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _report_file.write(
            f'<div class="meta" style="margin-top:24px;border-top:1px solid #333;padding-top:12px;">'
            f'Finished: {finished}</div>\n'
        )
        _report_file.write("</body>\n</html>\n")
        _report_file.close()
        _report_file = None


def pytest_runtest_logreport(report):
    if _report_file is None:
        return
    if report.when == "setup" and report.failed:
        _write_report_entry(report.nodeid, "ERROR (setup failed)", str(report.longrepr), [])
    elif report.when == "call":
        _call_reports[report.nodeid] = report
    elif report.when == "teardown":
        call = _call_reports.pop(report.nodeid, None)
        if call is None:
            return
        captures = _http_captures.pop(report.nodeid, [])
        status = "PASSED" if call.passed else "FAILED"
        error = str(call.longrepr) if call.failed else None
        _write_report_entry(report.nodeid, status, error, captures)


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
def log_http_calls(request):
    """Перехватывает HTTP-вызовы теста, печатает в stdout и сохраняет для файлового репорта."""
    captures = []
    orig = requests.Session.send

    def _patched(self, prepared, **kw):
        resp = orig(self, prepared, **kw)
        captures.append((prepared, resp))
        return resp

    requests.Session.send = _patched
    yield
    requests.Session.send = orig

    _http_captures[request.node.nodeid] = captures

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


# ─────────────────────────────────────────────
# RESPONSE SCHEMA HELPERS (per PROCESSING_API.yml)
# ─────────────────────────────────────────────
_VALID_STATUSES = frozenset({
    "completed", "authorized", "processing",
    "waiting_action", "cancelled", "rejected", "refunded",
})


def assert_transaction_response(data: dict) -> None:
    """Validates ResponseBase schema per PROCESSING_API.yml spec."""
    assert isinstance(data.get("transaction_id"), int), \
        f"transaction_id must be a int, got {data.get('transaction_id')!r}"
    assert data.get("status") in _VALID_STATUSES, \
        f"status must be one of {sorted(_VALID_STATUSES)}, got {data.get('status')!r}"
    assert data.get("type") in ("payin", "payout"), \
        f"type must be 'payin' or 'payout', got {data.get('type')!r}"
    md = data.get("merchant_data")
    assert isinstance(md, dict), f"merchant_data must be a dict, got {type(md).__name__}"
    assert isinstance(md.get("order_id"), str), \
        f"merchant_data.order_id must be a string, got {md.get('order_id')!r}"
    fd = data.get("financial_data")
    assert isinstance(fd, dict), f"financial_data must be a dict, got {type(fd).__name__}"
    assert isinstance(fd.get("amount"), int), \
        f"financial_data.amount must be an integer, got {fd.get('amount')!r}"
    currency = fd.get("currency", "")
    assert isinstance(currency, str) and len(currency) == 3, \
        f"financial_data.currency must be 3-char ISO 4217 code, got {currency!r}"
    assert isinstance(data.get("created_at"), str) and data.get("created_at"), \
        f"created_at must be a non-empty string, got {data.get('created_at')!r}"


def assert_error_response(resp) -> None:
    """Validates that the error response body is a JSON object per ErrorResponse schema."""
    data = resp.json()
    assert isinstance(data, dict), \
        f"Error response must be a JSON object, got {type(data).__name__}: {resp.text[:200]}"
