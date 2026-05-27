import hashlib
import hmac
import html as _html
import json
import os
import re
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()  # читает .env из корня проекта

try:
    import psycopg2 as _psycopg2
    _DB_HOST     = os.environ.get("DB_HOST", "")
    _DB_USER     = os.environ.get("DB_USER", "postgres")
    _DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

try:
    import redis as _redis_lib
    _REDIS_HOST     = os.environ.get("REDIS_HOST", "")
    _REDIS_PORT     = int(os.environ.get("REDIS_PORT", "6379"))
    _REDIS_USER     = os.environ.get("REDIS_USER", "")
    _REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
    _REDIS_AVAILABLE = bool(_REDIS_HOST)
except ImportError:
    _REDIS_AVAILABLE = False

_RUN_ID = uuid.uuid4().hex[:6]

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
_API_BASE            = "https://papiv3preprod.testpaygate.com/api/v1"
BASE_URL             = f"{_API_BASE}/transactions"
SUBSCRIPTIONS_URL    = f"{_API_BASE}/subscriptions"
PAYMENT_LINKS_URL    = "https://web3preprod.testpaygate.com/api/v1/payment-links"
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
CARD_3DS = {**CARD_DETAILS, "cvv": "550"}

CARDS = {
    "default": CARD_DETAILS,
    "3ds": CARD_3DS,
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
_http_captures: dict = {}  # nodeid -> (ungrouped[(prep,resp,label,css)], groups[{title,tr_id,css_class,http_blocks,db_data,redis}])
_call_reports:  dict = {}  # nodeid -> report (stored until teardown phase)
_tc_ids:        dict = {}  # nodeid -> tcid string (from @pytest.mark.tcid)
_test_counter = 0

_REPORTS_DIR = Path(__file__).parent.parent / "reports"


def _query_paylink_from_db(link_id: str) -> list:
    """Query support DB for payment link data. Returns list of {db, table, columns, rows}."""
    if not _DB_AVAILABLE or not _DB_HOST or not link_id:
        return []
    results = []
    try:
        conn = _psycopg2.connect(
            host=_DB_HOST, port=5432, dbname="support",
            user=_DB_USER, password=_DB_PASSWORD,
        )
        for table, col in [("webpayv3", "id")]:
            try:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT * FROM public.{table} WHERE {col} = %s LIMIT 1",
                    (link_id,),
                )
                rows = cur.fetchall()
                if rows:
                    cols = [d[0] for d in cur.description]
                    results.append({"db": "support", "table": table, "columns": cols, "rows": rows})
                cur.close()
            except Exception:
                conn.rollback()
        conn.close()
    except Exception:
        pass
    return results


def query_transaction_from_redis(transaction_id) -> dict:
    """Fetch Redis hash for *:*:{transaction_id} (tries tr_rest and tr prefixes). Returns {} if unavailable or not found."""
    if not _REDIS_AVAILABLE:
        return {}
    try:
        r = _redis_lib.Redis(
            host=_REDIS_HOST, port=_REDIS_PORT,
            username=_REDIS_USER, password=_REDIS_PASSWORD,
            ssl=True, ssl_cert_reqs=None,
            decode_responses=True, socket_connect_timeout=5,
        )
        for pattern in (f"tr_rest:*:{transaction_id}", f"tr:*:{transaction_id}"):
            keys = r.keys(pattern)
            if keys:
                return r.hgetall(keys[0])
        return {}
    except Exception:
        return {}


def _query_transaction_from_db(tr_id: int) -> list:
    """Query both DBs for transaction data. Returns list of {db, table, columns, rows}."""
    if not _DB_AVAILABLE:
        return []
    results = []
    try:
        sc = _psycopg2.connect(host=_DB_HOST, port=5432, dbname="secure", user=_DB_USER, password=_DB_PASSWORD)
        sp = _psycopg2.connect(host=_DB_HOST, port=5432, dbname="support", user=_DB_USER, password=_DB_PASSWORD)
        sc_cur = sc.cursor()
        sp_cur = sp.cursor()

        card_id = None

        queries = [
            (sc_cur, "secure",  "transactions",            "id",           tr_id),
            (sc_cur, "secure",  "transactions_history",    "trans_id",     tr_id),
            (sp_cur, "support", "bapi_tr_fields",          "tr_id",        tr_id),
            (sp_cur, "support", "limits_transaction_info", "tran_id",      tr_id),
            (sp_cur, "support", "receipt",                 "tran_id",      tr_id),
            (sp_cur, "support", "meta_transaction",        "transaction_id", tr_id),
            (sp_cur, "support", "af_data",                 "tr_id",        tr_id),
            (sp_cur, "support", "ui_interactions",         "transaction_id", tr_id),
        ]

        for cur, db, table, col, val in queries:
            try:
                cur.execute(f'SELECT * FROM public."{table}" WHERE "{col}" = %s LIMIT 5', (val,))
                rows = cur.fetchall()
                if rows:
                    cols = [d[0] for d in cur.description]
                    results.append({"db": db, "table": table, "columns": cols, "rows": rows})
                    if table == "transactions":
                        idx = cols.index("card_id") if "card_id" in cols else -1
                        if idx >= 0:
                            card_id = rows[0][idx]
            except Exception:
                pass

        if card_id:
            try:
                sc_cur.execute(
                    "SELECT id, key_id, cardholder, expiration_date FROM public.card_storage WHERE id = %s",
                    (str(card_id),)
                )
                rows = sc_cur.fetchall()
                if rows:
                    cols = [d[0] for d in sc_cur.description]
                    results.append({"db": "secure", "table": "card_storage", "columns": cols, "rows": rows})
            except Exception:
                pass

        sc.close()
        sp.close()
    except Exception:
        pass
    return results


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


def _render_http_block(f, prep, resp, title, css_class, indent="    ") -> None:
    phrase = _status_phrase(resp.status_code)
    sc = _sc_class(resp.status_code)
    i = indent
    f.write(f'{i}<div class="http-block">\n')
    f.write(f'{i}  <div class="http-block-title {css_class}">{title}</div>\n')
    f.write(f'{i}  <div class="http-block-body">\n')
    f.write(f'{i}    <div class="section-label">Request</div>\n')
    f.write(f'{i}    <p class="http-line"><span class="method">{_esc(prep.method)}</span>'
            f' <span class="url">{_esc(prep.url)}</span></p>\n')
    if prep.headers:
        headers_text = "\n".join(f"{k}: {v}" for k, v in prep.headers.items())
        f.write(f'{i}    <pre class="headers">{_esc(headers_text)}</pre>\n')
    body_text = _fmt_body_plain(prep.body)
    if body_text:
        f.write(f'{i}    <pre class="body">{_esc(body_text)}</pre>\n')
    f.write(f'{i}    <div class="section-label">Response</div>\n')
    f.write(f'{i}    <p class="http-line"><span class="status-code {sc}">'
            f'{resp.status_code} {_esc(phrase)}</span></p>\n')
    resp_text = _fmt_body_plain(resp.text)
    if resp_text:
        f.write(f'{i}    <pre class="body">{_esc(resp_text)}</pre>\n')
    f.write(f'{i}  </div>\n{i}</div>\n')


def _render_db_section(f, db_data: list, indent="    ") -> None:
    if not db_data:
        return
    i = indent
    f.write(f'{i}<div class="section-label">Database</div>\n')
    f.write(f'{i}<div class="db-section">\n')
    grouped: dict = {}
    for record in db_data:
        grouped.setdefault(record["db"], []).append(record)
    order = [db for db in ("secure", "support") if db in grouped]
    order += [db for db in grouped if db not in order]
    for db_name in order:
        safe = _esc(db_name)
        f.write(f'{i}  <div class="db-group">\n')
        f.write(f'{i}    <div class="db-group-header {safe}">{safe}</div>\n')
        f.write(f'{i}    <div class="db-group-body">\n')
        for record in grouped[db_name]:
            f.write(f'{i}      <div class="db-table-block">\n')
            f.write(f'{i}        <div class="db-table-name">{_esc(record["table"])}</div>\n')
            f.write(f'{i}        <div class="db-block">\n')
            f.write(f'{i}          <table class="db-table"><thead><tr>\n')
            for col in record["columns"]:
                f.write(f'{i}            <th>{_esc(col)}</th>\n')
            f.write(f'{i}          </tr></thead><tbody>\n')
            for row in record["rows"]:
                f.write(f'{i}          <tr>\n')
                for val in row:
                    if val is None:
                        cell = "<span style='color:#555'>NULL</span>"
                    else:
                        s = str(val)
                        cell = _esc(s[:200] + "…" if len(s) > 200 else s)
                    f.write(f'{i}            <td>{cell}</td>\n')
                f.write(f'{i}          </tr>\n')
            f.write(f'{i}          </tbody></table>\n')
            f.write(f'{i}        </div>\n{i}      </div>\n')
        f.write(f'{i}    </div>\n{i}  </div>\n')
    f.write(f'{i}</div>\n')


def _render_redis_section(f, redis_entry: dict, indent="    ") -> None:
    if not redis_entry:
        return
    i = indent
    api_status = redis_entry.get("api_status") or ""
    rdata      = redis_entry.get("data", {})
    r_status   = rdata.get("status", "")
    match      = (api_status == r_status) if (api_status and r_status) else None
    rbadge     = ('<span class="redis-match">✓ match</span>' if match is True else
                  '<span class="redis-mismatch">✗ mismatch</span>' if match is False else "")
    f.write(f'{i}<div class="section-label">Redis</div>\n')
    f.write(f'{i}<div class="db-section">\n')
    f.write(f'{i}  <div class="db-group">\n')
    f.write(f'{i}    <div class="db-group-header Redis">'
            f'{"API: <b>" + _esc(api_status) + "</b>&nbsp;&nbsp;" if api_status else ""}'
            f'{"Redis: <b>" + _esc(r_status) + "</b>" if r_status else ""}'
            f'{"&nbsp;&nbsp;" + rbadge if rbadge else ""}'
            f'</div>\n')
    f.write(f'{i}    <div class="db-group-body">\n')
    f.write(f'{i}      <div class="db-table-block"><div class="db-block">\n')
    f.write(f'{i}        <table class="db-table"><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>\n')
    for k, v in rdata.items():
        s = str(v)
        cell = _esc(s[:300] + "…" if len(s) > 300 else s)
        f.write(f'{i}          <tr><td>{_esc(k)}</td><td>{cell}</td></tr>\n')
    f.write(f'{i}        </tbody></table>\n')
    f.write(f'{i}      </div></div>\n')
    f.write(f'{i}    </div>\n{i}  </div>\n')
    f.write(f'{i}</div>\n')


def _write_report_entry(nodeid: str, status: str, error, ungrouped: list, tc_id: str = "", groups: list = None) -> None:
    global _test_counter
    _test_counter += 1
    idx = _test_counter
    f = _report_file

    css = "passed" if status == "PASSED" else "failed"
    badge = "✓ PASSED" if status == "PASSED" else "✗ FAILED"

    f.write(f'<div class="panel {css}" id="p{idx}" data-name="{_esc(nodeid)}" data-status="{css}" data-tcid="{_esc(tc_id)}">\n')
    f.write(f'  <div class="panel-header">\n')
    f.write(f'    <span class="badge">{badge}</span>\n')
    if tc_id:
        f.write(f'    <span class="tc-id">{_esc(tc_id)}</span>\n')
    f.write(f'    <span class="panel-name">{_esc(nodeid)}</span>\n')
    f.write(f'  </div>\n')
    f.write(f'  <div class="panel-body">\n')

    if error:
        f.write('    <div class="section-label">Error</div>\n')
        f.write(f'    <div class="error-block"><pre>{_esc(error)}</pre></div>\n')

    for prep, resp, title, css_class in (ungrouped or []):
        _render_http_block(f, prep, resp, title, css_class)

    for grp in (groups or []):
        title      = grp.get("title", "")
        tr_id      = grp.get("tr_id")
        css_class  = grp.get("css_class", "create")
        http_blocks = grp.get("http_blocks", [])
        db_data    = grp.get("db_data") or []
        redis_entry = grp.get("redis")

        final_status = ""
        for _, resp, lbl, _ in reversed(http_blocks):
            if lbl.startswith("Статус"):
                try:
                    final_status = resp.json().get("status", "")
                except Exception:
                    pass
                break

        meta = f"tr_id: {tr_id}" if tr_id is not None else ""
        status_span = (f'<span class="tx-status s2xx">{_esc(final_status)}</span>'
                       if final_status else "")

        f.write(f'  <details class="tx-group">\n')
        f.write(f'    <summary>'
                f'<span class="tx-title {css_class}">{_esc(title)}</span>'
                f'{" · <span class=\"tx-meta\">" + _esc(meta) + "</span>" if meta else ""}'
                f'{" · " + status_span if status_span else ""}'
                f'</summary>\n')
        f.write(f'    <div class="tx-body">\n')
        for prep, resp, lbl, cc in http_blocks:
            _render_http_block(f, prep, resp, lbl, cc, indent="      ")
        _render_db_section(f, db_data, indent="      ")
        _render_redis_section(f, redis_entry, indent="      ")
        f.write(f'    </div>\n  </details>\n')

    f.write('  </div>\n</div>\n')
    f.flush()


def pytest_configure(config):
    global _report_file, _test_counter
    _test_counter = 0
    config.addinivalue_line("markers", "tcid(id): test case identifier shown in HTML report")
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
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;flex-direction:column;height:100vh;overflow:hidden}}
.top-bar{{background:#12122a;border-bottom:1px solid #2a2a4a;padding:10px 20px;flex-shrink:0;display:flex;align-items:center;gap:16px}}
.top-bar h1{{color:#fff;font-size:1.1em;white-space:nowrap}}
.top-bar .meta{{color:#666;font-size:.8em}}
#summary{{display:flex;gap:14px;font-size:.88em;margin-left:auto;align-items:center;white-space:nowrap}}
.sum-p{{color:#4caf50;font-weight:bold}}
.sum-f{{color:#f44336;font-weight:bold}}
.sum-t{{color:#777}}
.layout{{display:flex;flex:1;overflow:hidden}}
.sidebar{{width:290px;background:#12122a;border-right:1px solid #2a2a4a;overflow-y:auto;flex-shrink:0;padding:6px 0}}
.nav-item{{padding:7px 12px 7px 14px;cursor:pointer;border-left:3px solid transparent;font-family:'Consolas',monospace;font-size:.76em;color:#999;line-height:1.4;word-break:break-all;user-select:none;display:flex;align-items:flex-start;gap:6px}}
.nav-item:hover{{background:#1a1a38;color:#ddd}}
.nav-item.active{{background:#1e1e3a;color:#fff;border-left-color:#5c7aaa}}
.nav-badge{{flex-shrink:0;margin-top:1px}}
.nav-item.passed .nav-badge{{color:#4caf50}}
.nav-item.failed .nav-badge{{color:#f44336}}
.main{{flex:1;overflow-y:auto;padding:20px}}
.panel{{display:none}}
.panel.active{{display:block}}
.panel-header{{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:6px 6px 0 0}}
.panel.passed .panel-header{{background:#1b3a1b;border:1px solid #2d4a2d;border-bottom:none}}
.panel.failed .panel-header{{background:#3a1b1b;border:1px solid #4a2020;border-bottom:none}}
.badge{{font-size:.75em;font-weight:bold;padding:2px 8px;border-radius:10px;flex-shrink:0}}
.panel.passed .badge{{background:#2e7d32;color:#a5d6a7}}
.panel.failed .badge{{background:#b71c1c;color:#ffcdd2}}
.panel-name{{font-family:'Consolas',monospace;font-size:.88em;color:#ddd;word-break:break-all}}
.panel-body{{padding:14px 16px;background:#16213e;border-radius:0 0 6px 6px}}
.panel.passed .panel-body{{border:1px solid #2d4a2d;border-top:none}}
.panel.failed .panel-body{{border:1px solid #4a2020;border-top:none}}
.section-label{{font-size:.72em;font-weight:bold;letter-spacing:.08em;color:#5c7aaa;text-transform:uppercase;margin:12px 0 6px}}
.section-label:first-child{{margin-top:0}}
.http-line{{font-family:monospace;font-size:.85em;margin-bottom:6px}}
.method{{color:#82aaff;font-weight:bold}}
.url{{color:#c3e88d}}
.status-code{{font-family:monospace;font-weight:bold;font-size:.85em}}
.s2xx{{color:#4caf50}}.s4xx{{color:#ff9800}}.s5xx{{color:#f44336}}
.tc-id{{font-family:'Consolas',monospace;font-size:.72em;font-weight:bold;color:#e0b060;background:#2a1f00;border:1px solid #4a3800;padding:1px 7px;border-radius:4px;flex-shrink:0}}
.nav-tcid{{font-family:'Consolas',monospace;font-size:.72em;color:#c9963a;flex-shrink:0;white-space:nowrap}}
pre.body{{background:#0d1117;border:1px solid #2a2a4a;border-radius:4px;padding:10px 12px;
  font-family:'Consolas',monospace;font-size:.82em;color:#cdd9e5;
  white-space:pre-wrap;word-break:break-all;max-height:340px;overflow-y:auto;margin:0}}
pre.headers{{background:#0a0f1a;border:1px solid #1e2a3a;border-radius:4px;padding:8px 12px;
  font-family:'Consolas',monospace;font-size:.78em;color:#7a9abf;
  white-space:pre-wrap;word-break:break-all;max-height:160px;overflow-y:auto;margin:0 0 6px}}
.error-block{{background:#1a0a0a;border-left:3px solid #f44336;border-radius:0 4px 4px 0;padding:12px;margin-top:8px}}
.error-block pre{{color:#ff8a80;font-size:.82em;white-space:pre-wrap;word-break:break-all;
  max-height:400px;overflow-y:auto;margin:0}}
.http-block{{border:1px solid #2a2a4a;border-radius:6px;margin-top:12px;overflow:hidden}}
.http-block-title{{background:#1a1a38;padding:6px 12px;font-size:.75em;font-weight:bold;letter-spacing:.07em;text-transform:uppercase;border-bottom:1px solid #2a2a4a}}
.http-block-title.create{{color:#82aaff}}.http-block-title.operation{{color:#ffb74d}}.http-block-title.poll{{color:#c3e88d}}
.http-block-body{{padding:10px 14px}}
details.tx-group{{border:1px solid #2a2a4a;border-radius:6px;margin-top:12px;overflow:hidden}}
details.tx-group>summary{{background:#1a1a38;padding:9px 14px;cursor:pointer;list-style:none;display:flex;align-items:center;gap:10px;user-select:none;border-bottom:1px solid transparent}}
details.tx-group>summary::-webkit-details-marker{{display:none}}
details.tx-group>summary::before{{content:'▶';font-size:.6em;color:#5c7aaa;flex-shrink:0;transition:transform .15s}}
details[open].tx-group>summary{{border-bottom-color:#2a2a4a}}
details[open].tx-group>summary::before{{transform:rotate(90deg)}}
.tx-title{{font-weight:bold;text-transform:uppercase;letter-spacing:.06em;font-size:.75em}}
.tx-title.create{{color:#82aaff}}.tx-title.operation{{color:#ffb74d}}.tx-title.poll{{color:#c3e88d}}
.tx-meta{{color:#666;font-size:.78em;font-family:'Consolas',monospace}}
.tx-status{{font-family:'Consolas',monospace;font-size:.78em;font-weight:bold;color:#cdd9e5}}
.tx-body{{padding:10px 14px;background:#13192e}}
.db-section{{margin-top:12px}}
.db-group{{border-radius:6px;margin-top:10px;overflow:hidden;border:1px solid #2a2a4a}}
.db-group-header{{padding:7px 14px;font-size:.76em;font-weight:bold;letter-spacing:.08em;text-transform:uppercase}}
.db-group-header.secure{{background:#1a1333;color:#c9a8ff;border-bottom:1px solid #3a2a5a}}
.db-group-header.support{{background:#0f1f2a;color:#82aaff;border-bottom:1px solid #1e3a4a}}
.db-group-header.Redis{{background:#1a1a0a;color:#e8cc60;border-bottom:1px solid #3a3a10;font-weight:normal;font-size:.8em;letter-spacing:.03em}}
.redis-match{{color:#4caf50;font-weight:bold;margin-left:8px}}
.redis-mismatch{{color:#f44336;font-weight:bold;margin-left:8px}}
.db-group-body{{padding:10px 12px;display:flex;flex-direction:column;gap:10px}}
.db-table-block{{border:1px solid #222240;border-radius:4px;overflow:hidden}}
.db-table-name{{background:#16163a;padding:4px 10px;font-family:'Consolas',monospace;font-size:.74em;color:#aaa;border-bottom:1px solid #222240}}
.db-block{{max-height:220px;overflow:auto}}
.db-table{{border-collapse:collapse;font-family:'Consolas',monospace;font-size:.78em;width:100%}}
.db-table th{{background:#1e1433;color:#c9a8ff;padding:4px 10px;text-align:left;border:1px solid #3a2a5a;white-space:nowrap;position:sticky;top:0}}
.db-table td{{padding:4px 10px;border:1px solid #2a1e40;color:#cdd9e5;vertical-align:top;word-break:break-all;max-width:360px}}
.db-table tr:nth-child(even) td{{background:#130f1e}}
</style>
</head>
<body>
<div class="top-bar">
  <h1>Test Report</h1>
  <span class="meta">Suite: <b>{_esc(suffix)}</b> &nbsp;|&nbsp; {started}</span>
  <div id="summary"></div>
</div>
<div class="layout">
  <div class="sidebar" id="sidebar"></div>
  <div class="main" id="main">
""")
    _report_file.flush()


def pytest_unconfigure(config):
    global _report_file
    if _report_file:
        finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _report_file.write(f"""
  </div>
</div>
<script>
(function(){{
  function parseTcid(t){{
    if(!t)return['ZZZZ',99999];
    var m=t.match(/^([A-Z0-9]+)-(\\d+)$/);
    return m?[m[1],parseInt(m[2])]:[t,0];
  }}
  var main=document.getElementById('main');
  var sidebar=document.getElementById('sidebar');
  var panels=Array.from(document.querySelectorAll('.panel'));
  panels.sort(function(a,b){{
    var ta=parseTcid(a.dataset.tcid),tb=parseTcid(b.dataset.tcid);
    if(ta[0]!==tb[0])return ta[0]<tb[0]?-1:1;
    return ta[1]-tb[1];
  }});
  panels.forEach(function(p){{main.appendChild(p);}});
  var passed=0,failed=0,firstFailed=null,navItems=[];
  panels.forEach(function(p){{
    var st=p.dataset.status,nm=p.dataset.name;
    if(st==='passed')passed++;else{{failed++;if(!firstFailed)firstFailed=p;}}
    var tcid=p.dataset.tcid;
    var item=document.createElement('div');
    item.className='nav-item '+st;
    item.innerHTML='<span class="nav-badge">'+(st==='passed'?'✓':'✗')+'</span>'+(tcid?'<span class="nav-tcid">['+tcid+']</span> ':'')+nm;
    (function(panel,navItem){{
      navItem.onclick=function(){{
        panels.forEach(function(x){{x.classList.remove('active');}});
        navItems.forEach(function(x){{x.classList.remove('active');}});
        panel.classList.add('active');
        navItem.classList.add('active');
      }};
    }})(p,item);
    sidebar.appendChild(item);
    navItems.push(item);
  }});
  var toShow=firstFailed||panels[0];
  if(toShow){{
    toShow.classList.add('active');
    navItems[panels.indexOf(toShow)].classList.add('active');
  }}
  var total=passed+failed;
  document.getElementById('summary').innerHTML=
    '<span class="sum-p">✓ '+passed+' passed</span>'+
    (failed?'<span class="sum-f">&nbsp;&nbsp;✗ '+failed+' failed</span>':'')+
    '<span class="sum-t">&nbsp;&nbsp;/ '+total+' total</span>';
  document.querySelector('.meta').innerHTML+=
    '&nbsp;|&nbsp; Finished: {finished}';
}})();
</script>
</body>
</html>
""")
        _report_file.close()
        _report_file = None


def pytest_runtest_logreport(report):
    if _report_file is None:
        return
    if report.when == "setup" and report.failed:
        tc_id = _tc_ids.get(report.nodeid, "")
        _write_report_entry(report.nodeid, "ERROR (setup failed)", str(report.longrepr), [], tc_id)
    elif report.when == "call":
        _call_reports[report.nodeid] = report
    elif report.when == "teardown":
        call = _call_reports.pop(report.nodeid, None)
        if call is None:
            return
        ungrouped, groups = _http_captures.pop(report.nodeid, ([], []))
        status = "PASSED" if call.passed else "FAILED"
        error = str(call.longrepr) if call.failed else None
        tc_id = _tc_ids.get(report.nodeid, "")
        _write_report_entry(report.nodeid, status, error, ungrouped, tc_id, groups)


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


_INTER_TEST_DELAY = float(os.environ.get("TEST_DELAY", "3.0"))
SETUP_DELAY       = float(os.environ.get("SETUP_DELAY", "1.0"))


def gen_order_id(name: str) -> str:
    """Unique order_id per test run, tied to a semantic name."""
    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:60]
    return f"{_RUN_ID}_{slug}"


def make_block_payin(order_id: str = None, description: str = None) -> str:
    """Creates Payin with capture_mode=manual (hold) and returns transaction_id."""
    md = {**MERCHANT_DATA, "order_id": order_id or gen_order_id("block")}
    if description is not None:
        md["description"] = description
    body = {
        "type": "payin",
        "merchant_data": md,
        "financial_data": {"amount": 1000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Block Payin failed: {resp.text}"
    time.sleep(SETUP_DELAY)
    return resp.json()["transaction_id"]


def make_completed_payin(order_id: str = None) -> str:
    """Creates auto-capture payin and returns transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id or gen_order_id("auto")},
        "financial_data": {"amount": 10000, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup auto payin failed: {resp.text}"
    time.sleep(SETUP_DELAY)
    return resp.json()["transaction_id"]


def make_op_body(order_id: str, amount: int = 1000) -> dict:
    return {
        "merchant_data": {"order_id": order_id},
        "financial_data": {"amount": amount, "currency": "RUB"},
    }


@pytest.fixture(autouse=True)
def _inter_test_delay():
    yield
    time.sleep(_INTER_TEST_DELAY)


@pytest.fixture(autouse=True)
def _inject_unique_order_id(request):
    """Replace order_id in all module-level body dicts before each test and restore after."""
    module = request.node.module
    patched = []
    for obj in vars(module).values():
        if isinstance(obj, dict) and isinstance(obj.get('merchant_data'), dict):
            orig_md = obj['merchant_data']
            obj['merchant_data'] = {**orig_md, 'order_id': gen_order_id(request.node.name)}
            patched.append((obj, orig_md))
    yield
    for obj, orig_md in patched:
        obj['merchant_data'] = orig_md


@pytest.fixture(autouse=True)
def _capture_tcid(request):
    marker = request.node.get_closest_marker("tcid")
    if marker:
        _tc_ids[request.node.nodeid] = marker.args[0]


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

    _OP_LABELS = {
        "/cancel":  "Cancel",
        "/capture": "Capture",
        "/refund":  "Refund",
        "/confirm": "Confirm",
    }
    _POLL_TITLES = {
        "/cancel":  "Статус после отмены",
        "/capture": "Статус после захвата",
        "/refund":  "Статус после возврата",
        "/confirm": "Статус после подтверждения",
    }

    ungrouped: list = []
    groups: list = []
    seen: set = set()

    for prep, resp in captures:
        url = prep.url or ""

        if prep.method == "GET":
            label = "Опрос статуса"
            css_class = "poll"
        elif prep.method == "DELETE":
            label = "Удаление"
            css_class = "operation"
        else:
            label = "Создание транзакции"
            css_class = "create"
        for suffix, op_label in _OP_LABELS.items():
            if suffix in url:
                label = op_label
                css_class = "operation"
                break

        if resp.status_code in (200, 201):
            try:
                body = resp.json()
                tr_id   = body.get("transaction_id")
                link_id = body.get("link_id")

                if isinstance(tr_id, int):
                    poll_title = "Статус после создания"
                    for suffix, pt in _POLL_TITLES.items():
                        if suffix in url:
                            poll_title = pt
                            break
                    key = (tr_id, label)
                    if key not in seen:
                        seen.add(key)
                        time.sleep(1)
                        poll_headers = make_headers(TERMINAL_ID, method="GET")
                        poll_resp = requests.get(f"{BASE_URL}/{tr_id}", headers=poll_headers, timeout=30)
                        db_data = _query_transaction_from_db(tr_id)
                        rdata = query_transaction_from_redis(tr_id)
                        redis_entry = None
                        if rdata:
                            try:
                                api_status = poll_resp.json().get("status")
                            except Exception:
                                api_status = None
                            redis_entry = {"tr_id": tr_id, "api_status": api_status, "data": rdata}
                        groups.append({
                            "title": label,
                            "css_class": css_class,
                            "tr_id": tr_id,
                            "http_blocks": [
                                (prep, resp, label, css_class),
                                (poll_resp.request, poll_resp, poll_title, "poll"),
                            ],
                            "db_data": db_data,
                            "redis": redis_entry,
                        })
                    else:
                        ungrouped.append((prep, resp, label, css_class))

                elif isinstance(link_id, str) and link_id:
                    key = ("link", link_id)
                    if key not in seen:
                        seen.add(key)
                        time.sleep(1)
                        link_db = _query_paylink_from_db(link_id)
                        groups.append({
                            "title": label,
                            "css_class": css_class,
                            "tr_id": None,
                            "http_blocks": [(prep, resp, label, css_class)],
                            "db_data": link_db,
                            "redis": None,
                        })
                    else:
                        ungrouped.append((prep, resp, label, css_class))
                else:
                    ungrouped.append((prep, resp, label, css_class))
            except Exception:
                ungrouped.append((prep, resp, label, css_class))
        else:
            ungrouped.append((prep, resp, label, css_class))

    _http_captures[request.node.nodeid] = (ungrouped, groups)

    bar = "-" * 64
    for prep, resp in captures:
        phrase = _status_phrase(resp.status_code)
        print(f"\n{bar}")
        print(f"  {prep.method} {prep.url}")
        print(f"  -- Request body {'-' * 46}")
        print(_fmt_body(prep.body))
        print(f"  -- Response: {resp.status_code} {phrase} {'-' * max(0, 44 - len(phrase))}")
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
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("payin_fixture")},
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
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("block_payin_fixture")},
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
