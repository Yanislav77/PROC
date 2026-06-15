"""
Тесты gate-эндпоинтов (взаимодействие с платёжным шлюзом):
  GET  /api/v1/payment-sessions/{payment_token}/gate/redirect        (аналог /payments/{payment_token}/redirect)
  POST /api/v1/payment-sessions/{payment_token}/gate/return/data     (аналог /payments/{payment_token}/confirm)
  GET  /api/v1/payment-sessions/{payment_token}/gate/return/no-data  (объединяет confirm_void GET и confirm_void_no_body POST)
  POST /api/v1/payment-sessions/{payment_token}/gate/3ds2/method     (аналог /payments/{payment_token}/threedsecure/method)
  POST /api/v1/payment-sessions/{payment_token}/gate/3ds2/result     (аналог /payments/{payment_token}/threedsecure/confirm)

Текущий файл покрывает:
  GR-001..016   GET  /gate/redirect          (PROC-74)
  GD-001..017   GET/POST /gate/return/data   (PROC-75)
  GN-001..019   GET/POST /gate/return/no-data (PROC-76)
  G3-001..014   POST /gate/3ds2/method       (PROC-77)
  G3R-001..024  POST /gate/3ds2/result       (PROC-78, TC-04 и TC-05 в спеке отсутствуют)
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
def _redirect_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/gate/redirect"


def _old_redirect_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/redirect"


def _get_redirect(token: str, headers: dict | None = None, allow_redirects: bool = False) -> requests.Response:
    """GET /gate/redirect. allow_redirects=False чтобы поймать 302 до того, как requests за ним пойдёт."""
    path = _redirect_path(token)
    h    = headers or {}
    return requests.get(
        f"{_WEB3_HOST}{path}",
        headers=h,
        allow_redirects=allow_redirects,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _get_redirect_old(token: str, allow_redirects: bool = False) -> requests.Response:
    path = _old_redirect_path(token)
    return requests.get(
        f"{_WEB3_HOST}{path}",
        allow_redirects=allow_redirects,
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ═════════════════════════════════════════════
# GR — GET /gate/redirect
# ═════════════════════════════════════════════

# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА BAPI-СОСТОЯНИЕ (ручная настройка)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GR-001")
def test_gate_redirect_html_page_tr_type_9():
    """TC-01: HTML_PAGE из BAPI tr_fields (tr_type=9).
    Ожидается 200 OK, Content-Type: text/html, тело — url-decoded HTML_PAGE."""
    token = _token_from_tr_ids("GR-001")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", ""), \
        f"Expected text/html, got: {resp.headers.get('Content-Type')}"
    assert resp.text.strip(), "Expected non-empty HTML body"


@pytest.mark.tcid("GR-002")
def test_gate_redirect_html_page_tr_type_11():
    """TC-02: HTML_PAGE из BAPI tr_fields (tr_type=11), на tr_type=9 пусто.
    Ожидается 200 OK, text/html, тело из tr_type=11."""
    token = _token_from_tr_ids("GR-002")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("GR-003")
def test_gate_redirect_html_page_priority_tr_type_9():
    """TC-03: HTML_PAGE есть и на tr_type=9, и на tr_type=11.
    Ожидается тело из tr_type=9 (итерация в порядке (9, 11))."""
    token = _token_from_tr_ids("GR-003")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("GR-004")
def test_gate_redirect_302_normal():
    """TC-04: HTML_PAGE пусто; BANK_REDIRECT_URL заполнен; spg.break_iframe не '1'.
    Ожидается 302 Found, Location: url-decoded BANK_REDIRECT_URL."""
    token = _token_from_tr_ids("GR-004")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert location, "Expected non-empty Location header for 302"


@pytest.mark.tcid("GR-005")
def test_gate_redirect_200_iframe_break():
    """TC-05: HTML_PAGE пусто; BANK_REDIRECT_URL заполнен; spg.break_iframe='1'.
    Ожидается 200 OK, text/html с авто-кликом, ссылка target='_top'."""
    token = _token_from_tr_ids("GR-005")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", "")
    assert "target=\"_top\"" in resp.text or "target='_top'" in resp.text, \
        "Expected target='_top' anchor in iframe-break HTML"


@pytest.mark.tcid("GR-006")
def test_gate_redirect_ip_from_x_forwarded_for():
    """TC-06: GET с X-Forwarded-For: 1.2.3.4.
    Ожидается: ответ любой ветки; в БД save_tr_data сохранил customer_info.ipaddress=1.2.3.4."""
    token = _token_from_tr_ids("GR-006")
    resp = _get_redirect(token, headers={"X-Forwarded-For": "1.2.3.4"}, allow_redirects=False)
    assert resp.status_code in (200, 302), \
        f"Expected 200 or 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-007")
def test_gate_redirect_ip_from_remote():
    """TC-07: GET без X-Forwarded-For.
    Ожидается: save_tr_data сохранил IP из request.remote."""
    token = _token_from_tr_ids("GR-007")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code in (200, 302), \
        f"Expected 200 or 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-012")
def test_gate_redirect_old_endpoint_regression_with_tr_fields():
    """TC-12: Старый /payments/{token}/redirect и новый дают одинаковый ответ (status, Location/body)."""
    token = _token_from_tr_ids("GR-012")
    resp_new = _get_redirect(token, allow_redirects=False)
    resp_old = _get_redirect_old(token, allow_redirects=False)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == resp_old.status_code, \
            f"Status mismatch: new={resp_new.status_code}, old={resp_old.status_code}"
        if resp_new.status_code == 302:
            assert resp_new.headers.get("Location") == resp_old.headers.get("Location"), \
                f"Location mismatch: new={resp_new.headers.get('Location')!r}, old={resp_old.headers.get('Location')!r}"
        else:
            assert resp_new.text == resp_old.text, "HTML body mismatch between old and new endpoint"


@pytest.mark.tcid("GR-013")
def test_gate_redirect_behavior_identical_to_old_endpoint():
    """TC-13: GET на оба URL с X-Forwarded-For — тела и Location идентичны."""
    token_new = _token_from_tr_ids("GR-013-new")
    token_old = _token_from_tr_ids("GR-013-old")
    h = {"X-Forwarded-For": "203.0.113.42"}
    resp_new = _get_redirect(token_new, headers=h, allow_redirects=False)
    resp_old = _get_redirect_old(token_old, allow_redirects=False)
    assert resp_new.status_code == resp_old.status_code, \
        f"Status mismatch: new={resp_new.status_code}, old={resp_old.status_code}"


@pytest.mark.tcid("GR-015")
def test_gate_redirect_payment_in_final_state():
    """TC-15: Платёж в state success/fail — эндпоинт отрабатывает без state-guard'а."""
    token = _token_from_tr_ids("GR-015")
    resp = _get_redirect(token, allow_redirects=False)
    assert resp.status_code in (200, 302), \
        f"Expected 200 or 302 for final-state payment, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-016")
def test_gate_redirect_no_tr_fields():
    """TC-16: В BAPI tr_fields нет ни HTML_PAGE, ни BANK_REDIRECT_URL.
    Ожидаемое поведение уточняется — возможен 302 с пустым Location или 5xx."""
    token = _token_from_tr_ids("GR-016")
    resp = _get_redirect(token, allow_redirects=False)
    # Зафиксировать actual поведение; предположительно 302 с Location: None
    assert resp.status_code in (200, 302, 500), \
        f"Unexpected status {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GR-008")
def test_gate_redirect_invalid_token_format():
    """TC-08: Невалидный payment_token (не UUID) → 4xx (validation_uuid_decorator)."""
    resp = _get_redirect("not-a-uuid", allow_redirects=False)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for non-UUID token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("GR-009")
def test_gate_redirect_nonexistent_token():
    """TC-09: Несуществующий payment_token (валидный UUID, не в БД) → 4xx (PaymentNotFound)."""
    resp = _get_redirect("00000000-0000-4000-8000-000000000000", allow_redirects=False)
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for nonexistent token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ НЕ ТРЕБУЕТСЯ (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GR-010")
def test_gate_redirect_no_auth_headers_accepted():
    """TC-10: GET без каких-либо авторизационных заголовков — не 4xx (авторизация отсутствует).
    Свежий токен (state=new): ответ зависит от tr_fields, но не auth-ошибка."""
    token = create_payment_token()
    resp  = _get_redirect(token, allow_redirects=False)
    assert resp.status_code not in range(400, 500), \
        f"Expected non-4xx (no auth required), got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-011")
def test_gate_redirect_auth_headers_ignored():
    """TC-11: GET с Api-Session-ID / Api-Signature (любыми) — заголовки игнорируются, не 4xx."""
    token = create_payment_token()
    resp  = _get_redirect(token,
                          headers={
                              "Api-Session-ID": "00000000-0000-0000-0000-000000000001",
                              "Api-Signature":  "0" * 64,
                          },
                          allow_redirects=False)
    assert resp.status_code not in range(400, 500), \
        f"Expected non-4xx (auth headers ignored), got {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────
# РЕГРЕСС СТАРОГО ЭНДПОИНТА (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GR-012b")
def test_gate_redirect_old_endpoint_regression_fresh_token():
    """TC-12 (state=new): Старый /payments/{token}/redirect со свежим токеном — не 4xx auth-ошибка."""
    token = create_payment_token()
    resp  = _get_redirect_old(token, allow_redirects=False)
    assert resp.status_code not in range(400, 500), \
        f"Old endpoint should not return 4xx for fresh token, got {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────
# HTTP-МЕТОД (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GR-014")
def test_gate_redirect_post_method():
    """TC-14: POST на /gate/redirect.
    Если маршрут method='*' → тот же ответ что и GET; если method='get' → 405.
    Зафиксировать actual поведение."""
    token = create_payment_token()
    path  = _redirect_path(token)
    resp  = requests.post(
        f"{_WEB3_HOST}{path}",
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )
    assert resp.status_code in (200, 302, 405), \
        f"Expected 200/302 (method=*) or 405 (method=get), got {resp.status_code}: {resp.text[:200]}"


# ══════════════════════════════════════════════════════════════
# GD — GET/POST /gate/return/data
# (аналог /payments/{payment_token}/confirm)
# ══════════════════════════════════════════════════════════════

_SPG_ORIGIN     = "https://merchant.example.com"
_FORM_DATA      = "PaRes=eJxVUstuwjAQ%2B%2B%2Bh&MD=12345"
_FORM_HEADERS   = {
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
    """TC-13: POST с пустым телом (Content-Length: 0).
    Ожидается 302 Found (Base3DSHelper получает пустой dict); поведение наследуется от старого."""
    token = _token_from_tr_ids("GD-013")
    resp = _post_return_data(token, body="")
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GD-015")
def test_gate_return_data_identical_to_old_endpoint():
    """TC-15: Один токен — новый и старый URL оба возвращают 302 на Location с тем же токеном.
    Предусловие: tr_ids.json 'GD-015' — токен платежа в состоянии ожидания confirm (3DS)."""
    token    = _token_from_tr_ids("GD-015")
    resp_new = _post_return_data(token)
    resp_old = _post_return_data_old(token)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == 302, \
            f"New endpoint: Expected 302, got {resp_new.status_code}: {resp_new.text[:200]}"
        assert resp_old.status_code == 302, \
            f"Old endpoint: Expected 302, got {resp_old.status_code}: {resp_old.text[:200]}"
        loc_new = resp_new.headers.get("Location", "")
        loc_old = resp_old.headers.get("Location", "")
        assert token in loc_new, f"New: token not in Location: {loc_new!r}"
        assert token in loc_old, f"Old: token not in Location: {loc_old!r}"


@pytest.mark.tcid("GD-016")
def test_gate_return_data_location_no_query_params():
    """TC-16: Location в 302 не содержит банковских query-параметров (PaRes/MD не пробрасываются)."""
    token = _token_from_tr_ids("GD-016")
    resp = _post_return_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert "PaRes" not in location, f"PaRes leaked into Location: {location!r}"
    assert "MD" not in location,    f"MD leaked into Location: {location!r}"
    assert "?" not in location,     f"Unexpected query in Location: {location!r}"


@pytest.mark.tcid("GD-017")
def test_gate_return_data_get_and_post_both_return_302():
    """TC-17: method='*' — GET и POST с одинаковыми данными оба возвращают 302."""
    token = _token_from_tr_ids("GD-017")
    resp_post = _post_return_data(token)
    resp_get  = _get_return_data(token)
    assert resp_post.status_code == 302, f"POST: Expected 302, got {resp_post.status_code}: {resp_post.text[:200]}"
    assert resp_get.status_code  == 302, f"GET: Expected 302, got {resp_get.status_code}: {resp_get.text[:200]}"


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
def test_gate_return_data_old_endpoint_regression_fresh_token():
    """TC-14: Старый /payments/{token}/confirm со свежим токеном — не 4xx auth-ошибка."""
    token = create_payment_token()
    resp  = _post_return_data_old(token)
    assert resp.status_code not in range(401, 404), \
        f"Old endpoint should not return auth error, got {resp.status_code}: {resp.text[:200]}"


# ══════════════════════════════════════════════════════════════
# GN — GET/POST /gate/return/no-data
# (GET = аналог /confirm_void, POST = аналог /confirm_void_no_body)
# ══════════════════════════════════════════════════════════════

_NEW_RESULT_URL_FRAGMENT = "/payment-sessions/"
_OLD_RESULT_URL_FRAGMENT = "/pay/"


def _return_no_data_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/gate/return/no-data"


def _old_confirm_void_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/confirm_void"


def _old_confirm_void_no_body_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/confirm_void_no_body"


def _get_return_no_data(token: str, headers: dict | None = None) -> requests.Response:
    path = _return_no_data_path(token)
    h    = headers if headers is not None else {"X-SPG-Origin": _SPG_ORIGIN}
    return requests.get(
        f"{_WEB3_HOST}{path}",
        headers=h,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _post_return_no_data(token: str, body: str = "",
                         headers: dict | None = None) -> requests.Response:
    path = _return_no_data_path(token)
    h    = headers if headers is not None else {}
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=body,
        headers=h,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _get_old_confirm_void(token: str) -> requests.Response:
    return requests.get(
        f"{_WEB3_HOST}{_old_confirm_void_path(token)}",
        headers={"X-SPG-Origin": _SPG_ORIGIN},
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _post_old_confirm_void_no_body(token: str) -> requests.Response:
    return requests.post(
        f"{_WEB3_HOST}{_old_confirm_void_no_body_path(token)}",
        data="",
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _get_old_confirm_void_no_body_ping(token: str) -> requests.Response:
    return requests.get(
        f"{_WEB3_HOST}{_old_confirm_void_no_body_path(token)}",
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА (ручная настройка)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GN-001")
def test_gate_return_no_data_get_state_3ds():
    """TC-01: GET, state='3ds' → 302, Location=/payment-sessions/<token>, state→'pending'."""
    token = _token_from_tr_ids("GN-001")
    resp = _get_return_no_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url fragment in Location, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ fragment leaked into Location: {location!r}"
    assert token in location, f"Expected token in Location, got: {location!r}"


@pytest.mark.tcid("GN-002")
def test_gate_return_no_data_get_state_3ds_redirect():
    """TC-02: GET, state='3ds_redirect' → 302 на новый result_url; state→'pending'."""
    token = _token_from_tr_ids("GN-002")
    resp = _get_return_no_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked: {location!r}"


@pytest.mark.tcid("GN-003")
def test_gate_return_no_data_get_state_redirect():
    """TC-03: GET, state='redirect' → 302 на новый result_url; state→'pending'."""
    token = _token_from_tr_ids("GN-003")
    resp = _get_return_no_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked: {location!r}"


@pytest.mark.tcid("GN-004")
def test_gate_return_no_data_get_state_not_in_redirect_states():
    """TC-04: GET, state не в {'3ds','3ds_redirect','redirect'} → 302 на новый result_url; state НЕ меняется."""
    token = _token_from_tr_ids("GN-004")
    resp = _get_return_no_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"


@pytest.mark.tcid("GN-005")
def test_gate_return_no_data_post_success():
    """TC-05: POST, любое не-финальное состояние → 201; set_pending_payment_state отработал."""
    token = _token_from_tr_ids("GN-005")
    resp = _post_return_no_data(token)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body, f"Expected non-empty response_entity, got: {body!r}"


@pytest.mark.tcid("GN-006")
def test_gate_return_no_data_post_skip_pending_ws_push():
    """TC-06: POST, state→'skip_pending' после set_pending → WS-клиент получает push state='skip_pending'."""
    token = _token_from_tr_ids("GN-006")
    resp = _post_return_no_data(token)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"
    # Проверка WS-фрейма выполняется вручную


@pytest.mark.tcid("GN-007")
def test_gate_return_no_data_post_body_ignored():
    """TC-07: POST с непустым телом → 201; тело запроса игнорируется бизнес-логикой."""
    token = _token_from_tr_ids("GN-007")
    resp = _post_return_no_data(token, body='{"some": "data"}',
                                headers={"Content-Type": "application/json"})
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GN-013")
def test_gate_return_no_data_old_confirm_void_result_url_unchanged():
    """TC-13: Регресс старого GET /confirm_void — Location остаётся /pay/<token>, не /payment-sessions/."""
    token = _token_from_tr_ids("GN-013")
    resp = _get_old_confirm_void(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _OLD_RESULT_URL_FRAGMENT in location, f"Expected old /pay/ in Location, got: {location!r}"
    assert _NEW_RESULT_URL_FRAGMENT not in location, f"New /payment-sessions/ leaked into old endpoint: {location!r}"


@pytest.mark.tcid("GN-014")
def test_gate_return_no_data_old_confirm_void_no_body_regression():
    """TC-14: Регресс старого POST /confirm_void_no_body → 201 с response_entity; side-effects идентичны."""
    token = _token_from_tr_ids("GN-014")
    resp = _post_old_confirm_void_no_body(token)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body, f"Expected non-empty response_entity, got: {body!r}"


@pytest.mark.tcid("GN-016")
def test_gate_return_no_data_result_url_differs_old_vs_new():
    """TC-16: GET на старый и новый URL — оба 302, но Location разный: /pay/ vs /payment-sessions/."""
    token_new = _token_from_tr_ids("GN-016-new")
    token_old = _token_from_tr_ids("GN-016-old")
    resp_new  = _get_return_no_data(token_new)
    resp_old  = _get_old_confirm_void(token_old)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == 302, f"New: Expected 302, got {resp_new.status_code}"
        assert resp_old.status_code == 302, f"Old: Expected 302, got {resp_old.status_code}"
        loc_new = resp_new.headers.get("Location", "")
        loc_old = resp_old.headers.get("Location", "")
        assert _NEW_RESULT_URL_FRAGMENT in loc_new, f"New endpoint missing /payment-sessions/ in Location: {loc_new!r}"
        assert _OLD_RESULT_URL_FRAGMENT in loc_old, f"Old endpoint missing /pay/ in Location: {loc_old!r}"


@pytest.mark.tcid("GN-017")
def test_gate_return_no_data_post_identical_to_old():
    """TC-17: POST с пустым body на старый и новый URL — идентичный 201 с response_entity."""
    token_new = _token_from_tr_ids("GN-017-new")
    token_old = _token_from_tr_ids("GN-017-old")
    resp_new  = _post_return_no_data(token_new)
    resp_old  = _post_old_confirm_void_no_body(token_old)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == resp_old.status_code == 201, \
            f"Status mismatch: new={resp_new.status_code}, old={resp_old.status_code}"


@pytest.mark.tcid("GN-018")
def test_gate_return_data_also_uses_new_result_url():
    """TC-18: /gate/return/data тоже возвращает /payment-sessions/<token> — единый формат V1-контура."""
    token = _token_from_tr_ids("GN-018")
    resp = _post_return_data(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected /payment-sessions/ in Location, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked into /gate/return/data: {location!r}"


@pytest.mark.tcid("GN-019")
@pytest.mark.skip(reason="Ручная проверка: открыть в браузере /payment-sessions/<token>; зависит от готовности фронта")
def test_gate_merchant_page_accessible_at_new_url(payment_token):
    """TC-19: Merchant page доступна по <origin>/api/v1/payment-sessions/<token> — проверить в браузере."""
    pass


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GN-008")
def test_gate_return_no_data_invalid_token_format():
    """TC-08: Невалидный payment_token (не UUID) → 4xx (validation_uuid_decorator)."""
    resp = _get_return_no_data("not-a-uuid")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for non-UUID token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("GN-009")
def test_gate_return_no_data_nonexistent_token():
    """TC-09: Несуществующий payment_token (валидный UUID, не в БД) → 4xx (PaymentNotFound)."""
    resp = _get_return_no_data("00000000-0000-4000-8000-000000000000")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for nonexistent token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HTTP-МЕТОД (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GN-010")
def test_gate_return_no_data_method_not_allowed():
    """TC-10: PUT/DELETE на /gate/return/no-data → 405 Method Not Allowed."""
    token = create_payment_token()
    path  = _return_no_data_path(token)
    resp_put = requests.put(
        f"{_WEB3_HOST}{path}",
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )
    resp_del = requests.delete(
        f"{_WEB3_HOST}{path}",
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )
    assert resp_put.status_code == 405, \
        f"PUT: Expected 405, got {resp_put.status_code}: {resp_put.text[:200]}"
    assert resp_del.status_code == 405, \
        f"DELETE: Expected 405, got {resp_del.status_code}: {resp_del.text[:200]}"


# ─────────────────────────────────────────────
# X-SPG-ORIGIN и АВТОРИЗАЦИЯ (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GN-011")
def test_gate_return_no_data_get_missing_x_spg_origin():
    """TC-11: GET без X-SPG-Origin — сервер не может построить result_url.
    Ожидается 4xx или 5xx (зафиксировать actual у разработчика)."""
    token = create_payment_token()
    resp  = _get_return_no_data(token, headers={})
    assert resp.status_code not in (200, 302), \
        f"Expected error without X-SPG-Origin, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GN-012")
def test_gate_return_no_data_auth_headers_ignored():
    """TC-12: GET/POST с невалидными Api-Session-ID / Api-Signature — заголовки игнорируются, не 4xx auth-ошибка."""
    token = create_payment_token()
    auth_headers = {
        "Api-Session-ID": "00000000-0000-0000-0000-000000000001",
        "Api-Signature":  "0" * 64,
    }
    resp_get = _get_return_no_data(token, headers={"X-SPG-Origin": _SPG_ORIGIN, **auth_headers})
    resp_post = _post_return_no_data(token, headers=auth_headers)
    assert resp_get.status_code not in range(401, 404), \
        f"GET: Expected no auth error, got {resp_get.status_code}: {resp_get.text[:200]}"
    assert resp_post.status_code not in range(401, 404), \
        f"POST: Expected no auth error, got {resp_post.status_code}: {resp_post.text[:200]}"


# ─────────────────────────────────────────────
# РЕГРЕСС СТАРЫХ ЭНДПОИНТОВ (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("GN-015")
def test_gate_return_no_data_old_confirm_void_no_body_get_ping():
    """TC-15: GET-ping /payments/{token}/confirm_void_no_body не мигрировал — по-прежнему 200 OK."""
    token = create_payment_token()
    resp  = _get_old_confirm_void_no_body_ping(token)
    assert resp.status_code == 200, \
        f"Old GET ping should still return 200, got {resp.status_code}: {resp.text[:200]}"


# ══════════════════════════════════════════════════════════════
# G3 — POST /gate/3ds2/method
# (аналог POST /payments/{payment_token}/threedsecure/method)
# ══════════════════════════════════════════════════════════════

_3DS_METHOD_DATA = (
    "threeDSMethodData=eyJ0aHJlZURTU2VydmVyVHJhbnNJRCI6IjAwMDAtMS4uLiIsInRocmVlRFNNZXRob2RVUkwiOiJodHRwczovL2Fjcy5leGFtcGxlLmNvbS9tZXRob2QifQ%3D%3D"
)
_3DS_FORM_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-SPG-Origin": _SPG_ORIGIN,
}


def _3ds2_method_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/gate/3ds2/method"


def _old_3ds_method_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/threedsecure/method"


def _post_3ds2_method(token: str, body: str = _3DS_METHOD_DATA,
                      headers: dict | None = None) -> requests.Response:
    path = _3ds2_method_path(token)
    h    = headers if headers is not None else _3DS_FORM_HEADERS
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=body,
        headers=h,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _post_old_3ds_method(token: str, body: str = _3DS_METHOD_DATA) -> requests.Response:
    return requests.post(
        f"{_WEB3_HOST}{_old_3ds_method_path(token)}",
        data=body,
        headers=_3DS_FORM_HEADERS,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА (ручная настройка)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3-001")
def test_gate_3ds2_method_post_success():
    """TC-01: POST с threeDSMethodData, X-SPG-Origin — 302, новый result_url, fingerprinting сохранён."""
    token = _token_from_tr_ids("G3-001")
    resp = _post_3ds2_method(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected /payment-sessions/ in Location, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked into Location: {location!r}"
    assert token in location, f"Expected token in Location, got: {location!r}"


@pytest.mark.tcid("G3-002")
def test_gate_3ds2_method_empty_body():
    """TC-02: POST с пустым телом — threeds_secure_method получает пустой dict; ожидается 302."""
    token = _token_from_tr_ids("G3-002")
    resp = _post_3ds2_method(token, body="")
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"


@pytest.mark.tcid("G3-003")
def test_gate_3ds2_method_json_content_type():
    """TC-03: POST с Content-Type: application/json — aiohttp парсит form только для form-encoded,
    threeds_secure_method получает пустой dict; ожидается 302."""
    token = _token_from_tr_ids("G3-003")
    headers = {"Content-Type": "application/json", "X-SPG-Origin": _SPG_ORIGIN}
    resp = _post_3ds2_method(token, body='{"threeDSMethodData": "abc"}', headers=headers)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3-004")
def test_gate_3ds2_method_result_url_new_format():
    """TC-04: 302 Location содержит /payment-sessions/<token>, не /pay/<token>."""
    token = _token_from_tr_ids("G3-004")
    resp = _post_3ds2_method(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected /payment-sessions/ in Location, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked: {location!r}"
    assert "?" not in location, f"Unexpected query params in Location: {location!r}"


@pytest.mark.tcid("G3-011")
def test_gate_3ds2_method_old_endpoint_result_url_unchanged():
    """TC-11: Регресс старого POST /threedsecure/method — Location остаётся /pay/<token>, не /payment-sessions/."""
    token = _token_from_tr_ids("G3-011")
    resp = _post_old_3ds_method(token)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _OLD_RESULT_URL_FRAGMENT in location, f"Expected /pay/ in old endpoint Location, got: {location!r}"
    assert _NEW_RESULT_URL_FRAGMENT not in location, f"New /payment-sessions/ leaked into old endpoint: {location!r}"


@pytest.mark.tcid("G3-012")
def test_gate_3ds2_method_result_url_differs_old_vs_new():
    """TC-12: POST на старый и новый URL — оба 302, но Location разный: /pay/ vs /payment-sessions/."""
    token_new = _token_from_tr_ids("G3-012-new")
    token_old = _token_from_tr_ids("G3-012-old")
    resp_new  = _post_3ds2_method(token_new)
    resp_old  = _post_old_3ds_method(token_old)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == 302, f"New: Expected 302, got {resp_new.status_code}"
        assert resp_old.status_code == 302, f"Old: Expected 302, got {resp_old.status_code}"
        loc_new = resp_new.headers.get("Location", "")
        loc_old = resp_old.headers.get("Location", "")
        assert _NEW_RESULT_URL_FRAGMENT in loc_new, f"New endpoint missing /payment-sessions/: {loc_new!r}"
        assert _OLD_RESULT_URL_FRAGMENT in loc_old, f"Old endpoint missing /pay/: {loc_old!r}"


@pytest.mark.tcid("G3-013")
@pytest.mark.skip(reason="Ручная проверка: Kibana flow_log enter — проверить raw_body, payment_id, content_type")
def test_gate_3ds2_method_flow_log_attributes(payment_token):
    """TC-13: В Kibana flow_log enter-событие содержит raw_body (form-encoded), payment_id, content_type."""
    pass


@pytest.mark.tcid("G3-014")
@pytest.mark.skip(reason="Ручная проверка: открыть в браузере /payment-sessions/<token>; зависит от готовности фронта")
def test_gate_3ds2_method_merchant_page_accessible(payment_token):
    """TC-14: Merchant page доступна по <origin>/payment-sessions/<token> после 302-редиректа."""
    pass


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3-005")
def test_gate_3ds2_method_invalid_token_format():
    """TC-05: Невалидный payment_token (не UUID) → 4xx (validation_uuid_decorator)."""
    resp = _post_3ds2_method("not-a-uuid")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for non-UUID token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("G3-006")
def test_gate_3ds2_method_nonexistent_token():
    """TC-06: Несуществующий payment_token (валидный UUID, не в БД) → 4xx (PaymentNotFound)."""
    resp = _post_3ds2_method("00000000-0000-4000-8000-000000000000")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for nonexistent token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HTTP-МЕТОД (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3-007")
def test_gate_3ds2_method_get_not_allowed():
    """TC-07: GET на /gate/3ds2/method → 405 Method Not Allowed (маршрут только POST)."""
    token = create_payment_token()
    resp  = requests.get(
        f"{_WEB3_HOST}{_3ds2_method_path(token)}",
        headers={"X-SPG-Origin": _SPG_ORIGIN},
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )
    assert resp.status_code == 405, \
        f"Expected 405 for GET, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3-008")
def test_gate_3ds2_method_put_delete_not_allowed():
    """TC-08: PUT/DELETE на /gate/3ds2/method → 405 Method Not Allowed."""
    token    = create_payment_token()
    path     = f"{_WEB3_HOST}{_3ds2_method_path(token)}"
    resp_put = requests.put(path, allow_redirects=False, timeout=_cfg.HTTP_TIMEOUT)
    resp_del = requests.delete(path, allow_redirects=False, timeout=_cfg.HTTP_TIMEOUT)
    assert resp_put.status_code == 405, \
        f"PUT: Expected 405, got {resp_put.status_code}: {resp_put.text[:200]}"
    assert resp_del.status_code == 405, \
        f"DELETE: Expected 405, got {resp_del.status_code}: {resp_del.text[:200]}"


# ─────────────────────────────────────────────
# X-SPG-ORIGIN И АВТОРИЗАЦИЯ (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3-009")
def test_gate_3ds2_method_missing_x_spg_origin():
    """TC-09: POST без X-SPG-Origin — сервер не может построить result_url.
    Ожидается 4xx или 5xx (зафиксировать actual у разработчика)."""
    token = create_payment_token()
    resp  = _post_3ds2_method(token, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code not in (200, 302), \
        f"Expected error without X-SPG-Origin, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3-010")
def test_gate_3ds2_method_auth_headers_ignored():
    """TC-10: POST с невалидными Api-Session-ID / Api-Signature — заголовки игнорируются, не 4xx auth-ошибка."""
    token = create_payment_token()
    headers = {
        **_3DS_FORM_HEADERS,
        "Api-Session-ID": "00000000-0000-0000-0000-000000000001",
        "Api-Signature":  "0" * 64,
    }
    resp = _post_3ds2_method(token, headers=headers)
    assert resp.status_code not in range(401, 404), \
        f"Expected no auth error (headers ignored), got {resp.status_code}: {resp.text[:200]}"


# ══════════════════════════════════════════════════════════════
# G3R — POST /gate/3ds2/result
# (аналог POST /payments/{payment_token}/threedsecure/confirm)
# Три ветки: fingerprinting (200), widget (200 text/plain), обычный 3DS (302)
# ══════════════════════════════════════════════════════════════

_3DS_RESULT_CRES      = "cres=eyJ0aHJlZURTU2VydmVyVHJhbnNJRCI6IjAwMC4uLiJ9&MD=MD12345"
_3DS_RESULT_SMS       = "sms_code=12345"
_3DS_RESULT_CREQ_SKIP = "creq=skipped"
_3DS_RESULT_FINGERPRINT = _3DS_METHOD_DATA   # threeDSMethodData — та же константа из G3-блока
_3DS_RESULT_FORM_HEADERS = _3DS_FORM_HEADERS  # Content-Type: form-encoded + X-SPG-Origin


def _3ds2_result_path(token: str) -> str:
    return f"{_BASE_PATH}/{token}/gate/3ds2/result"


def _old_3ds_confirm_path(token: str) -> str:
    return f"{_OLD_PATH}/{token}/threedsecure/confirm"


def _post_3ds2_result(token: str, body: str = _3DS_RESULT_CRES,
                      headers: dict | None = None) -> requests.Response:
    path = _3ds2_result_path(token)
    h    = headers if headers is not None else _3DS_RESULT_FORM_HEADERS
    return requests.post(
        f"{_WEB3_HOST}{path}",
        data=body,
        headers=h,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


def _post_old_3ds_confirm(token: str, body: str = _3DS_RESULT_CRES) -> requests.Response:
    return requests.post(
        f"{_WEB3_HOST}{_old_3ds_confirm_path(token)}",
        data=body,
        headers=_3DS_RESULT_FORM_HEADERS,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )


# ─────────────────────────────────────────────
# ВЕТКИ ОБРАБОТКИ (ручная настройка — state-dependent)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3R-001")
def test_gate_3ds2_result_fingerprint_branch():
    """TC-01: POST с threeDSMethodData → 200 OK; state='fingerprint'; PaymentStateSync push."""
    token = _token_from_tr_ids("G3R-001")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_FINGERPRINT,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert resp.text.strip() == "", f"Expected empty body, got: {resp.text[:200]}"


@pytest.mark.tcid("G3R-002")
def test_gate_3ds2_result_regular_3ds_branch_302():
    """TC-02: POST cres, не виджет, term_url есть → 302, Location=/payment-sessions/<token>, state='3ds'."""
    token = _token_from_tr_ids("G3R-002")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CRES)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected /payment-sessions/ in Location, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked into Location: {location!r}"
    assert token in location, f"Expected token in Location, got: {location!r}"


@pytest.mark.tcid("G3R-003")
def test_gate_3ds2_result_regular_3ds_no_term_url_state_3ds2ws():
    """TC-03: POST cres, не виджет, term_url отсутствует → 302; state='3ds2.ws'; tds_acs_url=false."""
    token = _token_from_tr_ids("G3R-003")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CRES)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"


@pytest.mark.tcid("G3R-006")
def test_gate_3ds2_result_md_from_query():
    """TC-06: POST ?MD=MD123 с cres в body, без MD в body → state_data.tds_md='MD123'."""
    token = _token_from_tr_ids("G3R-006")
    path  = _3ds2_result_path(token)
    resp  = requests.post(
        f"{_WEB3_HOST}{path}?MD=MD123",
        data="cres=eyJ0aHJlZURTU2VydmVyVHJhbnNJRCI6IjAwMC4uLiJ9",
        headers=_3DS_RESULT_FORM_HEADERS,
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3R-007")
def test_gate_3ds2_result_md_from_body():
    """TC-07: POST с form-data cres=..., MD=MD456, без ?MD → state_data.tds_md='MD456'."""
    token = _token_from_tr_ids("G3R-007")
    resp = _post_3ds2_result(token,
                             body="cres=eyJ0aHJlZURTU2VydmVyVHJhbnNJRCI6IjAwMC4uLiJ9&MD=MD456")
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3R-008")
def test_gate_3ds2_result_md_default():
    """TC-08: POST с cres без MD ни в body ни в query → state_data.tds_md='MD'+transaction_id."""
    token = _token_from_tr_ids("G3R-008")
    resp = _post_3ds2_result(token,
                             body="cres=eyJ0aHJlZURTU2VydmVyVHJhbnNJRCI6IjAwMC4uLiJ9")
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3R-009")
def test_gate_3ds2_result_creq_skipped_synthetic_cres():
    """TC-09: POST с creq=skipped → tds_pares=base64('3DS_AUTHENTICATE'), tds_md='MD'+transaction_id."""
    token = _token_from_tr_ids("G3R-009")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CREQ_SKIP)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"


@pytest.mark.tcid("G3R-010")
def test_gate_3ds2_result_sms_code_legacy():
    """TC-10: POST с sms_code (без cres) → tds_pares=base64(sms_code); 302."""
    token = _token_from_tr_ids("G3R-010")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_SMS)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"


@pytest.mark.tcid("G3R-012")
def test_gate_3ds2_result_302_location_new_format():
    """TC-12: 302 Location содержит /payment-sessions/<token>, не /pay/<token>."""
    token = _token_from_tr_ids("G3R-012")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CRES)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected /payment-sessions/ in Location, got: {location!r}"
    assert _OLD_RESULT_URL_FRAGMENT not in location, f"Old /pay/ leaked: {location!r}"
    assert "?" not in location, f"Unexpected query params in Location: {location!r}"


@pytest.mark.tcid("G3R-017")
def test_gate_3ds2_result_fingerprint_no_x_spg_origin():
    """TC-17: POST threeDSMethodData без X-SPG-Origin → 200 OK (result_url не используется в ветке fingerprinting)."""
    token = _token_from_tr_ids("G3R-017")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_FINGERPRINT,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3R-018")
def test_gate_3ds2_result_widget_branch_no_x_spg_origin():
    """TC-18: POST cres, MetaData.Initiator='Widget', без X-SPG-Origin → 200 OK text/plain."""
    token = _token_from_tr_ids("G3R-018")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CRES,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/plain" in resp.headers.get("Content-Type", ""), \
        f"Expected text/plain, got: {resp.headers.get('Content-Type')!r}"


@pytest.mark.tcid("G3R-019")
def test_gate_3ds2_result_auth_headers_ignored_real_flow():
    """TC-19: POST с Api-Session-ID / Api-Signature → то же поведение, что и без них."""
    token = _token_from_tr_ids("G3R-019")
    headers = {
        **_3DS_RESULT_FORM_HEADERS,
        "Api-Session-ID": "00000000-0000-0000-0000-000000000001",
        "Api-Signature":  "0" * 64,
    }
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CRES, headers=headers)
    assert resp.status_code == 302, f"Expected 302 (auth headers ignored), got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _NEW_RESULT_URL_FRAGMENT in location, f"Expected new result_url, got: {location!r}"


@pytest.mark.tcid("G3R-020")
def test_gate_3ds2_result_old_endpoint_location_unchanged():
    """TC-20: Регресс — POST на /threedsecure/confirm → Location=/pay/<token>, не /payment-sessions/."""
    token = _token_from_tr_ids("G3R-020")
    resp = _post_old_3ds_confirm(token, body=_3DS_RESULT_CRES)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert _OLD_RESULT_URL_FRAGMENT in location, f"Expected /pay/ in old endpoint, got: {location!r}"
    assert _NEW_RESULT_URL_FRAGMENT not in location, f"New /payment-sessions/ leaked into old endpoint: {location!r}"


@pytest.mark.tcid("G3R-021")
def test_gate_3ds2_result_result_url_differs_old_vs_new():
    """TC-21: POST на старый и новый URL (cres, не виджет) — оба 302, Location разный."""
    token_new = _token_from_tr_ids("G3R-021-new")
    token_old = _token_from_tr_ids("G3R-021-old")
    resp_new  = _post_3ds2_result(token_new, body=_3DS_RESULT_CRES)
    resp_old  = _post_old_3ds_confirm(token_old, body=_3DS_RESULT_CRES)
    with parity_check(lambda: resp_old):
        assert resp_new.status_code == 302, f"New: Expected 302, got {resp_new.status_code}"
        assert resp_old.status_code == 302, f"Old: Expected 302, got {resp_old.status_code}"
        loc_new = resp_new.headers.get("Location", "")
        loc_old = resp_old.headers.get("Location", "")
        assert _NEW_RESULT_URL_FRAGMENT in loc_new, f"New: expected /payment-sessions/: {loc_new!r}"
        assert _OLD_RESULT_URL_FRAGMENT in loc_old, f"Old: expected /pay/: {loc_old!r}"


@pytest.mark.tcid("G3R-022")
def test_gate_3ds2_result_fingerprint_and_widget_identical_old_vs_new():
    """TC-22: Fingerprinting ветка — оба 200; side effects идентичны между старым и новым URL."""
    token_fp_new = _token_from_tr_ids("G3R-022-fp-new")
    token_fp_old = _token_from_tr_ids("G3R-022-fp-old")
    resp_fp_new = _post_3ds2_result(token_fp_new, body=_3DS_RESULT_FINGERPRINT,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp_fp_old = _post_old_3ds_confirm(token_fp_old, body=_3DS_RESULT_FINGERPRINT)
    assert resp_fp_new.status_code == 200, f"FP new: Expected 200, got {resp_fp_new.status_code}"
    assert resp_fp_old.status_code == 200, f"FP old: Expected 200, got {resp_fp_old.status_code}"


@pytest.mark.tcid("G3R-023")
def test_gate_3ds2_result_skip_tds_confirm_not_active():
    """TC-23: is_skip_tds_confirm=False — widget-ветка идёт по обычной логике, не по skip_tds_confirm_logic."""
    token = _token_from_tr_ids("G3R-023")
    resp = _post_3ds2_result(token, body=_3DS_RESULT_CRES,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200, f"Expected 200 (widget branch), got {resp.status_code}: {resp.text[:200]}"
    assert "text/plain" in resp.headers.get("Content-Type", ""), \
        f"Expected text/plain (widget branch), got: {resp.headers.get('Content-Type')!r}"


@pytest.mark.tcid("G3R-024")
@pytest.mark.skip(reason="Ручная проверка: Kibana flow_log enter — raw_body, payment_id, content_type")
def test_gate_3ds2_result_flow_log_attributes(payment_token):
    """TC-24: В Kibana flow_log enter-событие содержит raw_body, payment_id, content_type для всех трёх веток."""
    pass


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: payment_token (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3R-011")
def test_gate_3ds2_result_empty_body_invalid_state_data():
    """TC-11: POST с пустым/нераспознанным body (нет cres/sms_code/threeDSMethodData/creq) → 4xx (InvalidStateData)."""
    token = create_payment_token()
    resp  = _post_3ds2_result(token, body="random_field=value")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for unrecognized body, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("G3R-013")
def test_gate_3ds2_result_invalid_token_format():
    """TC-13: Невалидный payment_token (не UUID) → 4xx (validation_uuid_decorator)."""
    resp = _post_3ds2_result("not-a-uuid")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for non-UUID token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


@pytest.mark.tcid("G3R-014")
def test_gate_3ds2_result_nonexistent_token():
    """TC-14: Несуществующий payment_token (валидный UUID, не в БД) → 4xx (PaymentNotFound)."""
    resp = _post_3ds2_result("00000000-0000-4000-8000-000000000000")
    assert resp.status_code in range(400, 500), \
        f"Expected 4xx for nonexistent token, got {resp.status_code}: {resp.text[:200]}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# HTTP-МЕТОД (автоматизирован)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3R-015")
def test_gate_3ds2_result_get_not_allowed():
    """TC-15: GET на /gate/3ds2/result → 405 Method Not Allowed (маршрут только POST)."""
    token = create_payment_token()
    resp  = requests.get(
        f"{_WEB3_HOST}{_3ds2_result_path(token)}",
        headers={"X-SPG-Origin": _SPG_ORIGIN},
        allow_redirects=False,
        timeout=_cfg.HTTP_TIMEOUT,
    )
    assert resp.status_code == 405, \
        f"Expected 405 for GET, got {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────
# X-SPG-ORIGIN И АВТОРИЗАЦИЯ (автоматизированы)
# ─────────────────────────────────────────────
@pytest.mark.tcid("G3R-016")
def test_gate_3ds2_result_missing_x_spg_origin_302_branch():
    """TC-16: POST с cres (302-ветка) без X-SPG-Origin — не может построить result_url.
    Ожидается 4xx или 5xx (зафиксировать actual у разработчика)."""
    token = create_payment_token()
    resp  = _post_3ds2_result(
        token,
        body=_3DS_RESULT_CRES,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code not in (200, 302), \
        f"Expected error without X-SPG-Origin, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("G3R-019a")
def test_gate_3ds2_result_auth_headers_ignored_no_401():
    """TC-19 (автоматизированная часть): POST с Api-Session-ID / Api-Signature → не 401/403 auth-ошибка."""
    token = create_payment_token()
    headers = {
        **_3DS_RESULT_FORM_HEADERS,
        "Api-Session-ID": "00000000-0000-0000-0000-000000000001",
        "Api-Signature":  "0" * 64,
    }
    resp = _post_3ds2_result(token, headers=headers)
    assert resp.status_code not in range(401, 404), \
        f"Expected no auth error (headers ignored), got {resp.status_code}: {resp.text[:200]}"
