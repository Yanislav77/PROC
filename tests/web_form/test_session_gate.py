"""
Тесты gate-эндпоинтов (взаимодействие с платёжным шлюзом):
  GET  /api/v1/payment-sessions/{payment_token}/gate/redirect        (аналог /payments/{payment_token}/redirect)
  POST /api/v1/payment-sessions/{payment_token}/gate/return/data     (аналог /payments/{payment_token}/confirm)
  GET  /api/v1/payment-sessions/{payment_token}/gate/return/no-data  (объединяет confirm_void GET и confirm_void_no_body POST)

Текущий файл покрывает:
  GR-001..016  GET /gate/redirect
"""
import pytest
import requests

import _helpers.config as _cfg
from _helpers.validators import assert_error_response
from web_form.conftest import create_payment_token

_WEB3_HOST = "https://web3preprod.testpaygate.com"
_BASE_PATH  = "/api/v1/payment-sessions"
_OLD_PATH   = "/payments"


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
@pytest.mark.skip(reason="Требует платёж с HTML_PAGE в BAPI tr_fields (tr_type=9) — настроить вручную")
def test_gate_redirect_html_page_tr_type_9(payment_token):
    """TC-01: HTML_PAGE из BAPI tr_fields (tr_type=9).
    Ожидается 200 OK, Content-Type: text/html, тело — url-decoded HTML_PAGE."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", ""), \
        f"Expected text/html, got: {resp.headers.get('Content-Type')}"
    assert resp.text.strip(), "Expected non-empty HTML body"


@pytest.mark.tcid("GR-002")
@pytest.mark.skip(reason="Требует платёж с HTML_PAGE в BAPI tr_fields (tr_type=11) — настроить вручную")
def test_gate_redirect_html_page_tr_type_11(payment_token):
    """TC-02: HTML_PAGE из BAPI tr_fields (tr_type=11), на tr_type=9 пусто.
    Ожидается 200 OK, text/html, тело из tr_type=11."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("GR-003")
@pytest.mark.skip(reason="Требует HTML_PAGE на обоих tr_type=9 и 11 с разными значениями — настроить вручную")
def test_gate_redirect_html_page_priority_tr_type_9(payment_token):
    """TC-03: HTML_PAGE есть и на tr_type=9, и на tr_type=11.
    Ожидается тело из tr_type=9 (итерация в порядке (9, 11))."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", "")


@pytest.mark.tcid("GR-004")
@pytest.mark.skip(reason="Требует платёж с BANK_REDIRECT_URL и без break_iframe — настроить вручную")
def test_gate_redirect_302_normal(payment_token):
    """TC-04: HTML_PAGE пусто; BANK_REDIRECT_URL заполнен; spg.break_iframe не '1'.
    Ожидается 302 Found, Location: url-decoded BANK_REDIRECT_URL."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}: {resp.text[:200]}"
    location = resp.headers.get("Location", "")
    assert location, "Expected non-empty Location header for 302"


@pytest.mark.tcid("GR-005")
@pytest.mark.skip(reason="Требует платёж с BANK_REDIRECT_URL и spg.break_iframe='1' — настроить вручную")
def test_gate_redirect_200_iframe_break(payment_token):
    """TC-05: HTML_PAGE пусто; BANK_REDIRECT_URL заполнен; spg.break_iframe='1'.
    Ожидается 200 OK, text/html с авто-кликом, ссылка target='_top'."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert "text/html" in resp.headers.get("Content-Type", "")
    assert "target=\"_top\"" in resp.text or "target='_top'" in resp.text, \
        "Expected target='_top' anchor in iframe-break HTML"


@pytest.mark.tcid("GR-006")
@pytest.mark.skip(reason="Требует платёж с BANK_REDIRECT_URL + X-Forwarded-For — проверить через BAPI — настроить вручную")
def test_gate_redirect_ip_from_x_forwarded_for(payment_token):
    """TC-06: GET с X-Forwarded-For: 1.2.3.4.
    Ожидается: ответ любой ветки; в БД save_tr_data сохранил customer_info.ipaddress=1.2.3.4."""
    resp = _get_redirect(payment_token, headers={"X-Forwarded-For": "1.2.3.4"},
                         allow_redirects=False)
    assert resp.status_code in (200, 302), \
        f"Expected 200 or 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-007")
@pytest.mark.skip(reason="Требует платёж с BANK_REDIRECT_URL — проверить IP через BAPI — настроить вручную")
def test_gate_redirect_ip_from_remote(payment_token):
    """TC-07: GET без X-Forwarded-For.
    Ожидается: save_tr_data сохранил IP из request.remote."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code in (200, 302), \
        f"Expected 200 or 302, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-012")
@pytest.mark.skip(reason="Требует платёж с tr_fields — сравнение ответов вручную — настроить вручную")
def test_gate_redirect_old_endpoint_regression_with_tr_fields(payment_token):
    """TC-12: Старый /payments/{token}/redirect и новый дают одинаковый ответ (status, Location/body)."""
    resp_new = _get_redirect(payment_token, allow_redirects=False)
    resp_old = _get_redirect_old(payment_token, allow_redirects=False)
    assert resp_new.status_code == resp_old.status_code, \
        f"Status mismatch: new={resp_new.status_code}, old={resp_old.status_code}"
    if resp_new.status_code == 302:
        assert resp_new.headers.get("Location") == resp_old.headers.get("Location"), \
            f"Location mismatch: new={resp_new.headers.get('Location')!r}, old={resp_old.headers.get('Location')!r}"
    else:
        assert resp_new.text == resp_old.text, "HTML body mismatch between old and new endpoint"


@pytest.mark.tcid("GR-013")
@pytest.mark.skip(reason="Требует платёж с tr_fields — настроить вручную")
def test_gate_redirect_behavior_identical_to_old_endpoint():
    """TC-13: GET на оба URL с X-Forwarded-For — тела и Location идентичны."""
    token_new = create_payment_token()
    token_old = create_payment_token()
    h = {"X-Forwarded-For": "203.0.113.42"}
    resp_new = _get_redirect(token_new, headers=h, allow_redirects=False)
    resp_old = _get_redirect_old(token_old, allow_redirects=False)
    assert resp_new.status_code == resp_old.status_code, \
        f"Status mismatch: new={resp_new.status_code}, old={resp_old.status_code}"


@pytest.mark.tcid("GR-015")
@pytest.mark.skip(reason="Требует платёж в финальном состоянии (success/fail) — настроить вручную")
def test_gate_redirect_payment_in_final_state(payment_token):
    """TC-15: Платёж в state success/fail — эндпоинт отрабатывает без state-guard'а."""
    resp = _get_redirect(payment_token, allow_redirects=False)
    assert resp.status_code in (200, 302), \
        f"Expected 200 or 302 for final-state payment, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.tcid("GR-016")
@pytest.mark.skip(reason="Требует платёж без HTML_PAGE и BANK_REDIRECT_URL в tr_fields — настроить вручную; уточнить ожидаемое поведение с разработчиком")
def test_gate_redirect_no_tr_fields(payment_token):
    """TC-16: В BAPI tr_fields нет ни HTML_PAGE, ни BANK_REDIRECT_URL.
    Ожидаемое поведение уточняется — возможен 302 с пустым Location или 5xx."""
    resp = _get_redirect(payment_token, allow_redirects=False)
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
