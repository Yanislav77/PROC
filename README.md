# PROC — CORE REST API Test Suite

Automated integration tests for the CORE REST API (payment gateway).

## Structure

```
PROC/
├── pytest.ini               # pytest configuration
├── requirements.txt         # dependencies
└── tests/
    ├── conftest.py          # base URL, HMAC-SHA256 signing helpers, fixtures
    ├── test_happy_path.py   # positive scenarios
    └── test_negative.py     # negative / edge-case scenarios
```

## Configuration

| Environment variable | Description                     |
|----------------------|---------------------------------|
| `API_TERMINAL_ID`    | Terminal ID issued by the gateway |
| `API_SECRET_KEY`     | HMAC secret for request signing |

Export them before running tests:

```bash
export API_TERMINAL_ID=your-terminal-id
export API_SECRET_KEY=your-secret-key
```

### Request signing

Every request is signed with HMAC-SHA256. The signature message is:

```
METHOD\nApi-Terminal-ID\nApi-Timestamp\nraw_body
```

where `raw_body` is the JSON-serialised request body (compact, no spaces) and
`Api-Timestamp` is a Unix timestamp (seconds). The resulting hex digest is sent
in the `Api-Signature` header.

## Installation

```bash
pip install -r requirements.txt
```

## Running tests

```bash
# all tests
pytest

# only happy-path tests
pytest tests/test_happy_path.py

# only negative tests
pytest tests/test_negative.py

# stop on first failure
pytest -x

# show full diff on assertion errors
pytest --tb=long
```

## Test coverage

### Happy path (`test_happy_path.py`)

| Class | Scenario |
|---|---|
| `TestPayinCard` | Card payin — success, transaction ID returned |
| `TestPayinP2P` | P2P payin — success, payment URL or transaction ID |
| `TestPayinMobile` | Mobile payin — success, transaction ID |
| `TestPayinBlock` | Block (auth-only) payin — hold confirmed |
| `TestRecurrent` | Recurrent charge via token |
| `TestPayout` | Payout to card |
| `TestRebill` | Rebill via rebill token |
| `TestRebillBlock` | Rebill block (auth-only) |
| `TestRefund` | Full and partial refund |

### Negative / edge cases (`test_negative.py`)

| Class | Scenario |
|---|---|
| `TestMissingRequiredFields` | Missing `type`, `amount`, `currency`, `order_id`, card number, empty body |
| `TestInvalidValues` | Invalid card, negative/zero amount, invalid currency, expired card, bad CVV, unknown type |
| `TestInvalidSignature` | Wrong signature, empty signature, missing terminal ID, missing timestamp, tampered body |
| `TestIdempotency` | Duplicate `order_id` deduplicated, conflicting amount rejected, distinct IDs both accepted |
