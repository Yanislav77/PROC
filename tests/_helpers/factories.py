import re
import time

import _helpers.config as _cfg
from _helpers.http_client import get_request, post_transaction
from _helpers.payloads import CARD_DETAILS, CUSTOMER_DATA, MERCHANT_DATA, THREED


_ORDER_ID_SLUG_MAX_LEN = 60
_FACTORY_POLL_ATTEMPTS = 10
_FACTORY_POLL_DELAY    = 2.0


def gen_order_id(name: str) -> str:
    """Unique order_id per test run, tied to a semantic name."""
    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:_ORDER_ID_SLUG_MAX_LEN]
    return f"{_cfg.RUN_ID}_{slug}"


def _wait_for_status(tid: int, expected: str) -> None:
    """Poll GET /{tid} until expected status or raise AssertionError on timeout/bad terminal state."""
    for _ in range(_FACTORY_POLL_ATTEMPTS):
        time.sleep(_FACTORY_POLL_DELAY)
        r = get_request(f"{_cfg.BASE_URL}/{tid}")
        if r.status_code != 200:
            continue
        status = r.json().get("status", "")
        if status == expected:
            return
        if status in ("rejected", "cancelled", "failed"):
            raise AssertionError(
                f"Setup transaction {tid} reached unexpected terminal status {status!r} "
                f"(expected {expected!r})"
            )
    raise AssertionError(
        f"Setup transaction {tid} did not reach {expected!r} within "
        f"{_FACTORY_POLL_ATTEMPTS * _FACTORY_POLL_DELAY:.0f}s"
    )


def make_block_payin(order_id: str | None = None, description: str | None = None) -> int:
    """Creates Payin with capture_mode=manual, polls until 'authorized', returns transaction_id."""
    md = {**MERCHANT_DATA, "order_id": order_id or gen_order_id("block")}
    if description is not None:
        md["description"] = description
    body = {
        "type": "payin",
        "merchant_data": md,
        "financial_data": {"amount": _cfg.BLOCK_PAYIN_AMOUNT, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "manual", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup Block Payin failed: {resp.text}"
    tid = resp.json()["transaction_id"]
    if resp.json().get("status") != "authorized":
        _wait_for_status(tid, "authorized")
    return tid


def make_completed_payin(order_id: str | None = None) -> int:
    """Creates auto-capture payin, polls until 'completed', returns transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id or gen_order_id("auto")},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": "RUB"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Setup auto payin failed: {resp.text}"
    tid = resp.json()["transaction_id"]
    if resp.json().get("status") != "completed":
        _wait_for_status(tid, "completed")
    return tid


def make_op_body(order_id: str, amount: int = _cfg.BLOCK_PAYIN_AMOUNT) -> dict:
    return {
        "merchant_data": {"order_id": order_id},
        "financial_data": {"amount": amount, "currency": "RUB"},
    }
