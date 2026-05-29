try:
    import redis as _redis_lib
    _REDIS_LIB_AVAILABLE = True
except ImportError:
    _REDIS_LIB_AVAILABLE = False

import _helpers.config as _cfg


def query_transaction_from_redis(transaction_id: int) -> dict[str, str]:
    """Fetch Redis hash for *:*:{transaction_id} (tries tr_rest and tr prefixes). Returns {} if unavailable or not found."""
    if not _REDIS_LIB_AVAILABLE or not _cfg.REDIS_HOST:
        return {}
    try:
        r = _redis_lib.Redis(
            host=_cfg.REDIS_HOST, port=_cfg.REDIS_PORT,
            username=_cfg.REDIS_USER, password=_cfg.REDIS_PASSWORD,
            ssl=True, ssl_cert_reqs=None,
            decode_responses=True, socket_connect_timeout=_cfg.REDIS_CONNECT_TIMEOUT,
        )
        for pattern in (f"tr_rest:*:{transaction_id}", f"tr:*:{transaction_id}"):
            keys = r.keys(pattern)
            if keys:
                return r.hgetall(keys[0])
        return {}
    except Exception:
        return {}
