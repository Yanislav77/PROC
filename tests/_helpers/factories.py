import re
import time

import _helpers.config as _cfg
from _helpers.http_client import post_transaction
from _helpers.payloads import CARD_DETAILS, CUSTOMER_DATA, MERCHANT_DATA, THREED


_ORDER_ID_SLUG_MAX_LEN = 60

def gen_order_id(name: str) -> str:
    """Unique order_id per test run, tied to a semantic name."""
    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:_ORDER_ID_SLUG_MAX_LEN]
    return f"{_cfg.RUN_ID}_{slug}"


def make_block_payin(order_id: str = None, description: str = None) -> int:
    """Creates Payin with capture_mode=manual (hold) and returns transaction_id."""
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
    time.sleep(_cfg.SETUP_DELAY)
    return resp.json()["transaction_id"]


def make_completed_payin(order_id: str = None) -> int:
    """Creates auto-capture payin and returns transaction_id."""
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
    time.sleep(_cfg.SETUP_DELAY)
    return resp.json()["transaction_id"]


def make_op_body(order_id: str, amount: int = 1000) -> dict:
    return {
        "merchant_data": {"order_id": order_id},
        "financial_data": {"amount": amount, "currency": "RUB"},
    }
