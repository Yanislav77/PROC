import json

import requests

import _helpers.config as _cfg
from _helpers.signatures import make_headers, make_get_headers


def post_transaction(body: dict, terminal_id: str = None) -> requests.Response:
    """POST /transactions — создание транзакции."""
    tid = terminal_id or _cfg.TERMINAL_ID
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(tid, raw)
    return requests.post(_cfg.BASE_URL, data=raw, headers=headers, timeout=_cfg.HTTP_TIMEOUT)


def get_request(url: str, params: dict = None, terminal_id: str = None) -> requests.Response:
    """GET-запрос с корректной HMAC-подписью (без тела)."""
    tid = terminal_id or _cfg.TERMINAL_ID
    headers = make_get_headers(tid)
    return requests.get(url, params=params, headers=headers, timeout=_cfg.HTTP_TIMEOUT)


def delete_request(url: str, terminal_id: str = None) -> requests.Response:
    """DELETE-запрос с корректной HMAC-подписью (без тела)."""
    tid = terminal_id or _cfg.TERMINAL_ID
    headers = make_get_headers(tid)
    return requests.delete(url, headers=headers, timeout=_cfg.HTTP_TIMEOUT)


def post_operation(transaction_id: str, operation: str, body: dict, terminal_id: str = None) -> requests.Response:
    """POST /{transaction_id}/{operation} — capture, cancel, refund, confirm."""
    tid = terminal_id or _cfg.TERMINAL_ID
    url = f"{_cfg.BASE_URL}/{transaction_id}/{operation}"
    raw = json.dumps(body, separators=(",", ":"))
    headers = make_headers(tid, raw)
    return requests.post(url, data=raw, headers=headers, timeout=_cfg.HTTP_TIMEOUT)
