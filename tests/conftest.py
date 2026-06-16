import time
from pathlib import Path

import pytest
import requests

import _helpers.config as _cfg
from _helpers.config import (
    BASE_URL,
    MERCHANT_BALANCE_URL,
    PAYMENT_LINKS_URL,
    SERVICE_SECRET,
    SETUP_DELAY,
    SUBSCRIPTIONS_URL,
    TERMINAL_ID,
)
from _helpers.db import (
    _query_paylink_from_db,
    _query_subscription_from_db,
    _query_transaction_from_db,
)
from _helpers.factories import (
    gen_order_id,
    make_block_payin,
    make_completed_payin,
    make_op_body,
)
from _helpers.http_client import (
    delete_request,
    get_request,
    post_operation,
    post_transaction,
)
from _helpers.payloads import (
    CARD_3DS, CARD_3DS_DECLINE, CARD_3DS_REDIRECT, CARD_3DS_REDIRECT_DECLINE,
    CARD_ASYNC, CARD_DECLINE, CARD_DETAILS, CARDS,
    CUSTOMER_DATA, MERCHANT_DATA, THREED,
)
from _helpers.redis_client import query_transaction_from_redis
from _helpers.signatures import calc_signature, make_get_headers, make_headers
from _helpers.validators import assert_error_response, assert_idempotency_echo, assert_transaction_response
from _helpers import report as _report


def pytest_addoption(parser):
    parser.addoption(
        "--tr-id",
        action="append",
        default=None,
        metavar="[TCID:]ID",
        help=(
            "Manually specify transaction ID for confirm tests. "
            "Use TCID:ID to target a specific test (e.g. --tr-id CON-045:111 --tr-id CON-052:222), "
            "or just ID as a fallback for all (e.g. --tr-id 111)."
        ),
    )
    parser.addoption(
        "--user-action-token",
        action="store",
        default=None,
        metavar="UUID",
        help=(
            "Payment token (UUID) in state 'user_action' for AC-001..003, AC-005, AC-015. "
            "Create a fresh P2P payment manually, wait for state=user_action, then pass the token here."
        ),
    )
    parser.addoption(
        "--bin-8digit",
        action="store",
        default=None,
        metavar="BIN",
        help="8-digit BIN for BI-002 (requires CONFIG.BinLookup.UseExtended8Bins=true on the stand).",
    )
    parser.addoption(
        "--bin-foreign-routing",
        action="store",
        default=None,
        metavar="BIN",
        help="Foreign non-MIR BIN for BI-004 (requires service with currency_code=RUB and spg.is_routing=1).",
    )
    parser.addoption(
        "--bin-foreign-no-routing",
        action="store",
        default=None,
        metavar="BIN",
        help="Foreign BIN for BI-005 (requires service with spg.is_routing != 1).",
    )


def pytest_configure(config):
    _report.pytest_configure(config)


def pytest_unconfigure(config):
    _report.pytest_unconfigure(config)


def pytest_runtest_logreport(report):
    _report.pytest_runtest_logreport(report)

_INTER_TEST_DELAY = _cfg.INTER_TEST_DELAY
_LOG_BAR_WIDTH    = 64


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────
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
        _report._tc_ids[request.node.nodeid] = marker.args[0]


@pytest.fixture(autouse=True)
def _apply_terminal_override(request):
    """Временно подменяет SERVICE_SECRET и TERMINAL_ID для тестов, у которых есть запись в terminals.json."""
    global SERVICE_SECRET, TERMINAL_ID
    try:
        rel = Path(request.fspath).relative_to(Path(__file__).parent).as_posix()
    except ValueError:
        rel = ""
    override = _cfg.TERMINAL_OVERRIDES.get(rel, {})
    new_secret   = override.get("SERVICE_SECRET") or _cfg.SERVICE_SECRET
    new_terminal = override.get("TERMINAL_ID")    or _cfg.TERMINAL_ID

    prev_cfg_secret, prev_cfg_terminal = _cfg.SERVICE_SECRET, _cfg.TERMINAL_ID
    prev_secret, prev_terminal = SERVICE_SECRET, TERMINAL_ID

    _cfg.SERVICE_SECRET = new_secret
    _cfg.TERMINAL_ID    = new_terminal
    SERVICE_SECRET      = new_secret
    TERMINAL_ID         = new_terminal

    # Патчим и сам тест-модуль — если он импортировал эти имена напрямую
    module = request.node.module
    mod_orig_secret   = getattr(module, "SERVICE_SECRET", None)
    mod_orig_terminal = getattr(module, "TERMINAL_ID",    None)
    if mod_orig_secret   is not None: module.SERVICE_SECRET = new_secret
    if mod_orig_terminal is not None: module.TERMINAL_ID    = new_terminal

    yield

    _cfg.SERVICE_SECRET = prev_cfg_secret
    _cfg.TERMINAL_ID    = prev_cfg_terminal
    SERVICE_SECRET      = prev_secret
    TERMINAL_ID         = prev_terminal
    if mod_orig_secret   is not None: module.SERVICE_SECRET = mod_orig_secret
    if mod_orig_terminal is not None: module.TERMINAL_ID    = mod_orig_terminal


@pytest.fixture(autouse=True)
def log_http_calls(request, _apply_terminal_override):
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
    op_count: dict = {}  # counts occurrences of (tr_id, label) for POST ops
    tr_id_type_violations: list = []
    redis_status_violations: list = []

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

                # List response (e.g. GET ?order_id=): check each item
                if isinstance(body, list):
                    for item in body:
                        if isinstance(item, dict):
                            item_tr_id = item.get("transaction_id")
                            if item_tr_id is not None and not isinstance(item_tr_id, int):
                                tr_id_type_violations.append(
                                    f"{prep.method} {prep.url} → item transaction_id={item_tr_id!r}"
                                    f" ({type(item_tr_id).__name__})"
                                )
                    ungrouped.append((prep, resp, label, css_class))
                    continue

                tr_id   = body.get("transaction_id")
                link_id = body.get("link_id")

                if isinstance(tr_id, int):
                    poll_title = "Статус после создания"
                    for suffix, pt in _POLL_TITLES.items():
                        if suffix in url:
                            poll_title = pt
                            break
                    # GET status polls deduplicate per tr_id to avoid noise from
                    # polling loops (_assert_status etc.). POST operations use a
                    # per-occurrence counter so every action — including repeated
                    # partial captures/cancels — gets its own group and Redis check.
                    if prep.method == "GET":
                        key = (tr_id, "poll")
                    else:
                        op_key = (tr_id, label)
                        op_count[op_key] = op_count.get(op_key, 0) + 1
                        key = (tr_id, label, op_count[op_key])
                    if key not in seen:
                        seen.add(key)
                        time.sleep(_cfg.STATUS_POLL_DELAY)
                        poll_headers = make_headers(_cfg.TERMINAL_ID, method="GET")
                        poll_resp = requests.get(f"{BASE_URL}/{tr_id}", headers=poll_headers, timeout=_cfg.HTTP_TIMEOUT)
                        db_data = _query_transaction_from_db(tr_id)
                        rdata = query_transaction_from_redis(tr_id)
                        redis_entry = None
                        if rdata:
                            try:
                                api_status = poll_resp.json().get("status")
                            except Exception:
                                api_status = None
                            redis_entry = {"tr_id": tr_id, "api_status": api_status, "data": rdata}
                            redis_status = rdata.get("status")
                            if redis_status and api_status and redis_status != api_status:
                                redis_status_violations.append(
                                    f"tr_id={tr_id}: API={api_status!r}, Redis={redis_status!r}"
                                )
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

                elif tr_id is not None:
                    # transaction_id present but wrong type — API type bug
                    tr_id_type_violations.append(
                        f"{prep.method} {prep.url} → transaction_id={tr_id!r}"
                        f" ({type(tr_id).__name__})"
                    )
                    ungrouped.append((prep, resp, label, css_class))

                elif isinstance(link_id, str) and link_id:
                    key = ("link", link_id)
                    if key not in seen:
                        seen.add(key)
                        time.sleep(_cfg.STATUS_POLL_DELAY)
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
        elif prep.method == "DELETE" and resp.status_code == 204 and SUBSCRIPTIONS_URL in url:
            token_part = url.rstrip("/").split("/")[-1].split("?")[0]
            db_data = _query_subscription_from_db(token_part)
            groups.append({
                "title": "Отмена подписки",
                "css_class": "operation",
                "tr_id": None,
                "http_blocks": [(prep, resp, "Отмена подписки", "operation")],
                "db_data": db_data,
                "redis": None,
            })
        else:
            ungrouped.append((prep, resp, label, css_class))

    _report._http_captures[request.node.nodeid] = (ungrouped, groups)

    if tr_id_type_violations:
        pytest.fail(
            "transaction_id type violation — expected int, got:\n"
            + "\n".join(f"  {v}" for v in tr_id_type_violations)
        )

    if redis_status_violations:
        pytest.fail(
            "Redis status mismatch:\n"
            + "\n".join(f"  {v}" for v in redis_status_violations)
        )

    bar = "-" * _LOG_BAR_WIDTH
    for prep, resp in captures:
        phrase = _report._status_phrase(resp.status_code)
        print(f"\n{bar}")
        print(f"  {prep.method} {prep.url}")
        if prep.headers:
            print(f"  -- Request headers {'-' * 44}")
            for k, v in prep.headers.items():
                print(f"  {k}: {v}")
        print(f"  -- Request body {'-' * 46}")
        print(_report._fmt_body(prep.body))
        print(f"  -- Response: {resp.status_code} {phrase} {'-' * max(0, 44 - len(phrase))}")
        if resp.headers:
            for k, v in resp.headers.items():
                print(f"  {k}: {v}")
        print(_report._fmt_body(resp.text))
        print(bar)


# ─────────────────────────────────────────────
# SESSION-SCOPED SETUP FIXTURES
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def payin_transaction_id():
    """Делает реальный Payin и возвращает transaction_id для Rebill/Recurrent/Refund."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("payin_fixture")},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": "RUB"},
        "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    try:
        resp = post_transaction(body)
    except Exception as e:
        pytest.skip(f"Setup Payin: request failed — {e}")
    if resp.status_code != 201:
        pytest.skip(f"Setup Payin: expected 201, got {resp.status_code} — {resp.text}")
    data = resp.json()
    if "transaction_id" not in data:
        pytest.skip(f"Setup Payin: no transaction_id in response — {data}")
    return data["transaction_id"]


@pytest.fixture(scope="session")
def payin_block_transaction_id():
    """Создаёт Payin с capture_mode=manual (холд средств). Используется в тестах /capture и /cancel."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": gen_order_id("block_payin_fixture")},
        "financial_data": {"amount": _cfg.BLOCK_PAYIN_AMOUNT, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    try:
        resp = post_transaction(body)
    except Exception as e:
        pytest.skip(f"Setup Block Payin: request failed — {e}")
    if resp.status_code != 201:
        pytest.skip(f"Setup Block Payin: expected 201, got {resp.status_code} — {resp.text}")
    data = resp.json()
    if "transaction_id" not in data:
        pytest.skip(f"Setup Block Payin: no transaction_id in response — {data}")
    return data["transaction_id"]
