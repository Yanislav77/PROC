import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg2 as _psycopg2  # noqa: F401
    DB_HOST     = os.environ.get("DB_HOST", "")
    DB_USER     = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_AVAILABLE = True
except ImportError:
    DB_HOST = DB_USER = DB_PASSWORD = ""
    DB_AVAILABLE = False

try:
    import redis as _redis_lib  # noqa: F401
    REDIS_HOST     = os.environ.get("REDIS_HOST", "")
    REDIS_PORT     = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_USER     = os.environ.get("REDIS_USER", "")
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
    REDIS_AVAILABLE = bool(REDIS_HOST)
except ImportError:
    REDIS_HOST = REDIS_USER = REDIS_PASSWORD = ""
    REDIS_PORT = 6379
    REDIS_AVAILABLE = False

# ── Tuneable constants ────────────────────────────────────────
DB_PORT               = 5432   # PostgreSQL default port
HTTP_TIMEOUT          = 30     # seconds, HTTP request timeout
STATUS_POLL_DELAY     = 1      # seconds, wait before polling transaction status
REDIS_CONNECT_TIMEOUT = 5      # seconds, Redis connection timeout
PAYIN_AMOUNT          = 10000  # RUB, auto-capture setup fixture amount
BLOCK_PAYIN_AMOUNT    = 1000   # RUB, manual-capture setup fixture amount

_RUN_ID_HEX_LEN = 6
RUN_ID = uuid.uuid4().hex[:_RUN_ID_HEX_LEN]

_API_BASE            = "https://papiv3preprod.testpaygate.com/api/v1"
BASE_URL             = f"{_API_BASE}/transactions"
SUBSCRIPTIONS_URL    = f"{_API_BASE}/subscriptions"
PAYMENT_LINKS_URL    = "https://web3preprod.testpaygate.com/api/v1/payment-links"
MERCHANT_BALANCE_URL = f"{_API_BASE}/merchant/balance"

SERVICE_SECRET   = os.environ["SERVICE_SECRET"]
TERMINAL_ID      = os.environ.get("TERMINAL_ID", "374")
CUSTOMER_MAC_KEY = os.environ.get("CUSTOMER_MAC_KEY", "")

INTER_TEST_DELAY = float(os.environ.get("TEST_DELAY", "3.0"))
SETUP_DELAY      = float(os.environ.get("SETUP_DELAY", "1.0"))

# terminals.json лежит в корне проекта (на два уровня выше _helpers/)
_terminals_path = Path(__file__).parent.parent.parent / "terminals.json"
TERMINAL_OVERRIDES: dict = {}
if _terminals_path.exists():
    try:
        TERMINAL_OVERRIDES = json.loads(_terminals_path.read_text(encoding="utf-8"))
    except Exception:
        pass
