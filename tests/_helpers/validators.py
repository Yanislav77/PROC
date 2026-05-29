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
