from contextlib import contextmanager

import requests

PARITY_BUG_PREFIX = "⚠ PARITY BUG"


@contextmanager
def parity_check(old_call: "callable[[], requests.Response]", msg: str = ""):
    """Automatically detects parity bugs between new and old endpoints.

    Wrap assertions about the new endpoint response. If they fail AND the old
    endpoint also returns an error, raises AssertionError with PARITY_BUG_PREFIX
    so the HTML report renders it as an orange parity-bug block.

    If the old endpoint succeeds, the original assertion error is re-raised as-is.

    Usage:
        resp_new = _post_phone(token, body)
        with parity_check(lambda: _post_phone_old(token, body)):
            assert resp_new.status_code == 200
            assert resp_new.json()["provider_country"]["code"] == "643"
    """
    try:
        yield
    except AssertionError as original_err:
        try:
            resp_old = old_call()
        except Exception:
            raise original_err
        if resp_old.status_code >= 400:
            old_url  = (resp_old.request.url if resp_old.request else "")
            old_body = resp_old.text[:500] if resp_old.text else "(no body)"
            detail   = f"\n{msg}" if msg else ""
            raise AssertionError(
                f"{PARITY_BUG_PREFIX}{detail}\n"
                f"Та же ошибка воспроизводится на старом эндпоинте.\n"
                f"Требуется отдельная задача разработки.\n\n"
                f"Старый: [{resp_old.status_code}]  {old_url}\n{old_body}\n\n"
                f"--- Оригинальная ошибка нового эндпоинта ---\n{original_err}"
            ) from None
        raise original_err

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


def assert_error_response(resp: requests.Response) -> None:
    """Validates that the error response body is a JSON object per ErrorResponse schema."""
    data = resp.json()
    assert isinstance(data, dict), \
        f"Error response must be a JSON object, got {type(data).__name__}: {resp.text[:200]}"


def assert_idempotency_echo(request_headers: dict, response: requests.Response) -> None:
    """If the response echoes Api-Idempotency-Key, it must match what was sent."""
    sent = request_headers.get("Api-Idempotency-Key")
    if sent and "Api-Idempotency-Key" in response.headers:
        assert response.headers["Api-Idempotency-Key"] == sent, (
            f"Api-Idempotency-Key mismatch: sent {sent!r}, "
            f"got {response.headers['Api-Idempotency-Key']!r}"
        )
