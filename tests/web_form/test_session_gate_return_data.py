"""
Тесты gate-эндпоинта /gate/return/data (PROC-75):
  POST /api/v1/payment-sessions/{payment_token}/gate/return/data  (аналог /payments/{payment_token}/confirm)
  GET  /api/v1/payment-sessions/{payment_token}/gate/return/data

  GD-001..017   GET/POST /gate/return/data   (PROC-75)
"""
import hashlib
import hmac as _hmac
import json
import uuid
from pathlib import Path

import pytest
import requests

import _helpers.config as _cfg
from _helpers.validators import assert_error_response, parity_check
from web_form.conftest import create_payment_token

_WEB3_HOST = "https://web3preprod.testpaygate.com"
_BASE_PATH  = "/api/v1/payment-sessions"
_OLD_PATH   = "/payments"

_TR_IDS_FILE = Path(__file__).parent.parent.parent / "tr_ids.json"


def _load_tr_ids() -> dict:
    if _TR_IDS_FILE.exists():
        try:
            return json.loads(_TR_IDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _token_from_tr_ids(key: str) -> str:
    """Возвращает payment token UUID из tr_ids.json по ключу; pytest.skip если ключ отсутствует."""
    val = _load_tr_ids().get(key)
    if val is None:
        pytest.skip(f'Add "{key}": "<token-uuid>" to tr_ids.json to run this test')
    return str(val)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
_SPG_ORIGIN   = "https://merchant.example.com"
_FORM_DATA    = "PaRes=eJxVUstuwjAQ%2B%2B%2Bh&MD=12345"
_FORM_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-SPG-Origin": _SPG_ORIGIN,
}


def _return_data_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/gate/return/data"


def _old_return_data_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/confirm"


def _post_return_data(token: str, body: str = _FORM_DATA,
                      headers: dict | None = None) -> requests.Response:
    path = _return_data_path(token)
    h    = headers if headers is not None else _FORM_HEADERS
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=body,
        headers=h,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _get_return_data(token: str, params: str = _FORM_DATA,
                     headers: dict | None = None) -> requests.Response:
    path = _return_data_path(token)
    h    = headers if headers is not None else {"X-SPG-Origin": _SPG_ORIGIN}
    return requests.get(
        f"{_WEB3_HOST}{path}",
        params=params,
        headers=h,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _post_return_data_old(token: str, body: str = _FORM_DATA) -> requests.Response:
    path = _old_return_data_path(token)
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=body,
        headers=_FORM_HEADERS,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


_SUBMIT_BODY = {
    "CustomerInfo": {"Phone": "+79991234567", "Email": "test@example.com"},
    "PaymentMethod": "Card",
    "PaymentDetails": {
        "CardholderName": "TEST TEST",
        "CVC": "111",
        "CardNumber": "4111111111111111",
        "ExpMonth": "01",
        "ExpYear": "29",
    },
    "RebillFlag": False,
    "ExtraData": {
        "ScreenHeight": 1080, "ScreenWidth": 1920, "JavaEnabled": False,
        "TimeZoneOffset": -180, "Region": "ru-RU", "UserLang": "ru",
        "DeviceType": "desktop", "OsType": "windows", "ColorDepth": 32,
        "UserAgent": "Mozilla/5.0", "acceptHeader": "text/html",
        "javaScriptEnabled": True,
    },
    "ReceiptData": {},
}


def _submit_payment(token: str, x_forwarded_for: str | None = None) -> requests.Response:
    """POST /payments/{token}/submit — кладёт платёж в состояние 3DS (CVC=111 < 600)."""
    path = f"{_OLD_PATH}/{token}/submit"
    raw  = json.dumps(_SUBMIT_BODY, separators=(",", ":"))
    sid  = uuid.uuid4().hex[:8]
    sig  = _hmac.new(
        _cfg.CUSTOMER_MAC_KEY.encode(),
        f"POST\n{path}\n{sid}\n{raw}".encode(),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "Content-Type":          "application/json",
        "X-CUSTOMER-SESSION-ID": sid,
        "X-REQUEST-SIGNATURE":   sig,
        "Origin":                _WEB3_HOST,
        "Referer":               f"{_WEB3_HOST}/pay/{token}",
    }
    if x_forwarded_for:
        headers["X-Forwarded-For"] = x_forwarded_for
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=raw,
        headers=headers,
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ══════════════════════════════════════════════════════════════
# GD — GET/POST /gate/return/data
# (аналог /payments/{payment_token}/confirm)
# ══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА (ручная настройка)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GD-001")
def test_gate_return_data_post_success():
    """TC-01: POST с PaRes/MD, X-SPG-Origin — успешный возврат с банка.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS).
    Ожидается 302 Found, Location: <origin>/payment-sessions/<token>."""
    token = create_payment_token()
    _submit_payment(token)
    resp = _post_return_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _SPG_ORIGIN in location, f"Expected origin in Location, got: {location!r}"
    assert token in location, f"Expected token in Location, got: {location!r}"


@pytest.mark.tcid("GD-002")
def test_gate_return_data_get_success():
    """TC-02: GET с ?MD=...&PaRes=..., X-SPG-Origin — Base3DSHelper использует extract_data_get.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS).
    Ожидается 302 Found с тем же result_url."""
    token = create_payment_token()
    _submit_payment(token)
    resp = _get_return_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _SPG_ORIGIN in location, f"Expected origin in Location, got: {location!r}"


@pytest.mark.tcid("GD-003")
def test_gate_return_data_skip_pending_ws_push():
    """TC-03: После confirm state → skip_pending; WS-клиент получает push state='skip_pending'.
    Ожидается 302 Found; PaymentStateSync push виден в /ws-канале."""
    token = _token_from_tr_ids("GD-003")
    resp = _post_return_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    # Проверка WS-фрейма выполняется вручную


@pytest.mark.tcid("GD-004")
def test_gate_return_data_repeat_increments_request_count():
    """TC-04: Повторный POST — state_data.safe_object.request_count инкрементируется.
    Ожидается 302 Found; request_count = 2."""
    token = _token_from_tr_ids("GD-004")
    resp = _post_return_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    # Проверить request_count в БД вручную


@pytest.mark.tcid("GD-005")
def test_gate_return_data_ip_mismatch():
    """TC-05: spg.check_ip='1', X-Forwarded-For не совпадает с сохранённым IP.
    Предусловие: submit с X-Forwarded-For=1.1.1.1; gate/return/data — с 2.2.2.2.
    Ожидается 4xx (check_ip_address_matching — точный тип уточнить у разработчика)."""
    token = create_payment_token()
    _submit_payment(token, x_forwarded_for="1.1.1.1")
    headers = {**_FORM_HEADERS, "X-Forwarded-For": "2.2.2.2"}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for IP mismatch, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("GD-006")
def test_gate_return_data_ip_match():
    """TC-06: spg.check_ip='1', X-Forwarded-For совпадает с сохранённым IP.
    Предусловие: submit с X-Forwarded-For=1.1.1.1; gate/return/data — с тем же IP.
    Ожидается 302 Found."""
    token = create_payment_token()
    _submit_payment(token, x_forwarded_for="1.1.1.1")
    headers = {**_FORM_HEADERS, "X-Forwarded-For": "1.1.1.1"}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-007")
def test_gate_return_data_no_ip_check():
    """TC-07: spg.check_ip не установлен (check_ip=0) — IP не проверяется.
    Предусловие: submit с X-Forwarded-For=1.1.1.1; gate/return/data — с другим IP.
    ВАЖНО: запускать после установки check_ip=0 в SPG-параметрах сервиса.
    Ожидается 302 Found."""
    token = create_payment_token()
    _submit_payment(token, x_forwarded_for="1.1.1.1")
    headers = {**_FORM_HEADERS, "X-Forwarded-For": "99.99.99.99"}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-013")
def test_gate_return_data_empty_post_body():
    """TC-13: POST с пустым телом (Content-Length: 0) — сервер не падает, возвращает 302.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS)."""
    token = create_payment_token()
    _submit_payment(token)
    headers = {**_FORM_HEADERS, "Content-Length": "0"}
    resp = _post_return_data(token, body="", headers=headers)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-015")
def test_gate_return_data_identical_to_old_endpoint():
    """TC-15: POST новый, GET новый и POST старый — все возвращают 302; статус-коды совпадают.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS)."""
    token        = create_payment_token()
    _submit_payment(token)
    resp_post_new = _post_return_data(token)
    resp_get_new  = _get_return_data(token)
    resp_post_old = _post_return_data_old(token)
    with parity_check(lambda: resp_post_old):
        assert resp_post_new.status_code == 302, \
            f"POST new: Expected 302, got {resp_post_new.status_code}: {resp_post_new.text[:200]}"
        assert resp_get_new.status_code == 302, \
            f"GET new: Expected 302, got {resp_get_new.status_code}: {resp_get_new.text[:200]}"
        assert resp_post_old.status_code == 302, \
            f"POST old: Expected 302, got {resp_post_old.status_code}: {resp_post_old.text[:200]}"
        assert token in resp_post_new.headers.get("Location", ""), \
            f"POST new: token not in Location: {resp_post_new.headers.get('Location')!r}"
        assert token in resp_get_new.headers.get("Location", ""), \
            f"GET new: token not in Location: {resp_get_new.headers.get('Location')!r}"
        assert token in resp_post_old.headers.get("Location", ""), \
            f"POST old: token not in Location: {resp_post_old.headers.get('Location')!r}"


@pytest.mark.tcid("GD-016")
def test_gate_return_data_get_without_query_params():
    """TC-16: GET без query-параметров (?PaRes/MD отсутствуют) — сервер не падает, возвращает 302.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS)."""
    token = create_payment_token()
    _submit_payment(token)
    resp = _get_return_data(token, params=None)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert "PaRes" not in location, f"PaRes leaked into Location: {location!r}"
    assert "MD" not in location,    f"MD leaked into Location: {location!r}"
    assert "?" not in location,     f"Unexpected query in Location: {location!r}"


@pytest.mark.tcid("GD-017")
def test_gate_return_data_get_and_post_same_response():
    """TC-17: POST и GET с одинаковым PaRes/MD — оба возвращают 302, статус-коды совпадают.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS)."""
    token    = create_payment_token()
    _submit_payment(token)
    resp_post = _post_return_data(token)
    resp_get  = _get_return_data(token)
    assert resp_post.status_code == 302, \
        f"POST: Expected 302, got {resp_post.status_code}: {resp_post.text[:200]}"
    assert resp_get.status_code == 302, \
        f"GET: Expected 302, got {resp_get.status_code}: {resp_get.text[:200]}"
    assert resp_post.status_code == resp_get.status_code, \
        f"Status mismatch: POST={resp_post.status_code}, GET={resp_get.status_code}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GD-008")
def test_gate_return_data_invalid_token_format():
    """TC-08: Невалидный payment_token (не UUID) → 4xx (validation_uuid_decorator)."""
    resp = _post_return_data("not-a-uuid")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for non-UUID token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("GD-009")
def test_gate_return_data_nonexistent_token():
    """TC-09: Несуществующий payment_token (валидный UUID, не в БД) → 4xx (PaymentNotFound)."""
    resp = _post_return_data("00000000-0000-4000-8000-000000000000")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for nonexistent token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ НЕ ТРЕБУЕТСЯ (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GD-010a")
def test_gate_return_data_post_no_api_session_id():
    """TC-10a: POST — заголовок Api-Session-ID отсутствует → 302 Found (авторизация не требуется)."""
    token = create_payment_token()
    headers = {**_FORM_HEADERS, "Api-Signature": "0" * 64}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010b")
def test_gate_return_data_post_api_session_id_empty_value():
    """TC-10b: POST — Api-Session-ID передан без значения X-CUSTOMER-SESSION-ID (пустая строка) → 302 Found."""
    token = create_payment_token()
    headers = {**_FORM_HEADERS, "Api-Session-ID": ""}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010c")
def test_gate_return_data_post_no_api_signature():
    """TC-10c: POST — заголовок Api-Signature отсутствует → 302 Found (авторизация не требуется)."""
    token = create_payment_token()
    headers = {**_FORM_HEADERS, "Api-Session-ID": "00000000-0000-4000-8000-000000000001"}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010d")
def test_gate_return_data_post_api_signature_empty_value():
    """TC-10d: POST — Api-Signature передан без значения X-REQUEST-SIGNATURE (пустая строка) → 302 Found."""
    token = create_payment_token()
    headers = {**_FORM_HEADERS, "Api-Signature": ""}
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010e")
def test_gate_return_data_get_no_api_session_id():
    """TC-10e: GET — заголовок Api-Session-ID отсутствует → 302 Found (авторизация не требуется)."""
    token = create_payment_token()
    headers = {"X-SPG-Origin": _SPG_ORIGIN, "Api-Signature": "0" * 64}
    resp = _get_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010f")
def test_gate_return_data_get_api_session_id_empty_value():
    """TC-10f: GET — Api-Session-ID передан без значения X-CUSTOMER-SESSION-ID (пустая строка) → 302 Found."""
    token = create_payment_token()
    headers = {"X-SPG-Origin": _SPG_ORIGIN, "Api-Session-ID": ""}
    resp = _get_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010g")
def test_gate_return_data_get_no_api_signature():
    """TC-10g: GET — заголовок Api-Signature отсутствует → 302 Found (авторизация не требуется)."""
    token = create_payment_token()
    headers = {"X-SPG-Origin": _SPG_ORIGIN, "Api-Session-ID": "00000000-0000-4000-8000-000000000001"}
    resp = _get_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-010h")
def test_gate_return_data_get_api_signature_empty_value():
    """TC-10h: GET — Api-Signature передан без значения X-REQUEST-SIGNATURE (пустая строка) → 302 Found."""
    token = create_payment_token()
    headers = {"X-SPG-Origin": _SPG_ORIGIN, "Api-Signature": ""}
    resp = _get_return_data(token, headers=headers)
    assert resp.status_code == 302, \
        f"Expected 302 (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-011")
def test_gate_return_data_auth_headers_ignored():
    """TC-11: POST с невалидными Api-Session-ID / Api-Signature — заголовки игнорируются, не 4xx auth-ошибка."""
    token = create_payment_token()
    headers = {
        **_FORM_HEADERS,
        "Api-Session-ID": "00000000-0000-0000-0000-000000000001",
        "Api-Signature":  "0" * 64,
    }
    resp = _post_return_data(token, headers=headers)
    assert resp.status_code not in range(401, 404), \
        f"Expected no auth error (headers ignored), got {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────
# X-SPG-ORIGIN (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GD-012")
def test_gate_return_data_missing_x_spg_origin():
    """TC-12: POST без X-SPG-Origin — сервер падает при построении result_url.
    Ожидается 4xx или 5xx (зафиксировать actual у разработчика)."""
    token = create_payment_token()
    resp  = _post_return_data(token, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code not in (200, 302), \
        f"Expected error without X-SPG-Origin, got {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────
# РЕГРЕСС СТАРОГО ЭНДПОИНТА (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GD-014")
def test_gate_return_data_old_endpoint_regression():
    """TC-14: Старый /payments/{token}/confirm с токеном в 3DS — возвращает 302.
    Предусловие: create_payment_token → submit (CVC=111 → 3DS)."""
    token = create_payment_token()
    _submit_payment(token)
    resp  = _post_return_data_old(token)
    assert resp.status_code == 302, \
        f"Old endpoint: Expected 302, got {resp.status_code}: {resp.text[:200]}"
    assert token in resp.headers.get("Location", ""), \
        f"Old endpoint: token not in Location: {resp.headers.get('Location')!r}"
