"""
Тесты проверки совпадения значений полей в родительских и дочерних транзакциях.
VAL-001 — VAL-038

Суть: проверяем, что при несовпадении financial_data / merchant_data в дочерней
операции API возвращает 4xx, а при совпадении — 200.

Охватываемые эндпоинты: /confirm, /capture, /refund, /cancel.
GET-эндпоинты (/transactions?order_id, /transactions/{id}) — проверяются в секции
"Актуальность данных в GET" без подачи тела запроса.

Проверяемые поля:
  financial_data  : amount, currency
  merchant_data   : order_id, description, webhook_url
"""
import pytest

from conftest import (
    post_operation,
    post_transaction,
    get_request,
    BASE_URL,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_error_response,
    assert_transaction_response,
    gen_order_id,
    make_block_payin,
    make_completed_payin,
)
from _helpers.polling import poll_status
import _helpers.config as _cfg

# Карта с CVV < 500 → транзакция попадает в waiting_3DS
_CARD_3DS = {**CARD_DETAILS, "cvv": "123"}

# Значения родительской транзакции (payin с capture_mode=manual)
_PARENT_AMOUNT   = _cfg.BLOCK_PAYIN_AMOUNT   # 1000
_PARENT_CURRENCY = "RUB"
_PARENT_DESC     = MERCHANT_DATA.get("description", "Order payment")
_PARENT_WEBHOOK  = MERCHANT_DATA.get("webhook_url", "https://merchant.com/webhook")

# Значения, которые ТОЧНО не совпадают с родительскими
_WRONG_AMOUNT   = _PARENT_AMOUNT + 1         # 1001
_WRONG_CURRENCY = "USD"
_WRONG_ORDER_ID = "WRONG_ORDER_ID_mismatch"
_WRONG_DESC     = "Wrong description mismatch"
_WRONG_WEBHOOK  = "https://wrong-webhook.example.com/hook"


# ─────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────

def _make_waiting_3ds(oid: str) -> int:
    """Создаёт payin в статусе waiting_3DS. Возвращает transaction_id."""
    body = {
        "type": "payin",
        "merchant_data": {**MERCHANT_DATA, "order_id": oid},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": _CARD_3DS},
    }
    resp = post_transaction(body)
    if resp.status_code != 201:
        pytest.skip(f"Не удалось создать 3DS-транзакцию: {resp.status_code}: {resp.text}")
    tid = resp.json()["transaction_id"]
    if resp.json().get("status") != "waiting_3DS":
        try:
            poll_status(tid, "waiting_3DS")
        except Exception as exc:
            pytest.skip(f"Транзакция {tid} не достигла waiting_3DS: {exc}")
    return tid


def _confirm_body(oid: str, amount: int = _PARENT_AMOUNT, currency: str = _PARENT_CURRENCY) -> dict:
    """Тело для /confirm с параметризованными financial_data и merchant_data.order_id."""
    return {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": amount, "currency": currency},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares", "md": "test_md"}},
        },
    }


# ─────────────────────────────────────────────
# financial_data.amount — несовпадение
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-001")
def test_confirm_amount_mismatch():
    """confirm: amount отличается от родительской транзакции → 4xx."""
    oid = gen_order_id("val001_con_amt")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(oid, amount=_WRONG_AMOUNT))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении amount, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-002")
def test_capture_amount_mismatch():
    """capture: amount отличается от родительской (authorized) транзакции → 4xx."""
    oid = gen_order_id("val002_cap_amt")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _WRONG_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении amount, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-003")
def test_refund_amount_partial():
    """refund: amount меньше родительского — частичный возврат разрешён → 200."""
    oid = gen_order_id("val003_ref_partial")
    tid = make_completed_payin(oid)
    partial_amount = _cfg.PAYIN_AMOUNT // 2   # 5000 из 10000
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": partial_amount, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201), (
        f"Ожидался 200 при частичном возврате, получен {resp.status_code}: {resp.text}"
    )
    assert_transaction_response(resp.json())


@pytest.mark.tcid("VAL-004")
def test_refund_amount_exact():
    """refund: amount равен родительскому — полный возврат → 200."""
    oid = gen_order_id("val004_ref_full")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201), (
        f"Ожидался 200 при полном возврате, получен {resp.status_code}: {resp.text}"
    )
    assert_transaction_response(resp.json())


@pytest.mark.tcid("VAL-005")
def test_refund_amount_exceeds_parent():
    """refund: amount больше родительского → 4xx."""
    oid = gen_order_id("val005_ref_exceed")
    tid = make_completed_payin(oid)
    over_amount = _cfg.PAYIN_AMOUNT + 1
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": over_amount, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при amount > родительского, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-006")
def test_cancel_amount_mismatch():
    """cancel: amount отличается от родительской (authorized) транзакции → 4xx."""
    oid = gen_order_id("val006_can_amt")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _WRONG_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении amount, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


# ─────────────────────────────────────────────
# financial_data.currency — несовпадение
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-007")
def test_confirm_currency_mismatch():
    """confirm: currency отличается от родительской → 4xx."""
    oid = gen_order_id("val007_con_cur")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(oid, currency=_WRONG_CURRENCY))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении currency, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-008")
def test_capture_currency_mismatch():
    """capture: currency отличается от родительской → 4xx."""
    oid = gen_order_id("val008_cap_cur")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _WRONG_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении currency, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-009")
def test_refund_currency_mismatch():
    """refund: currency отличается от родительской → 4xx."""
    oid = gen_order_id("val009_ref_cur")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _WRONG_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении currency, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-010")
def test_cancel_currency_mismatch():
    """cancel: currency отличается от родительской → 4xx."""
    oid = gen_order_id("val010_can_cur")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _WRONG_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении currency, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-011")
def test_confirm_currency_lowercase():
    """confirm: currency в нижнем регистре 'rub' при родительской 'RUB'.
    Фиксируем поведение: ошибка формата (400) или ошибка несовпадения (4xx)."""
    oid = gen_order_id("val011_con_cur_lc")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(oid, currency="rub"))
    # Допустимы оба варианта: ошибка типа/формата или ошибка несовпадения
    assert resp.status_code >= 400, (
        f"Ожидался 4xx для currency='rub', получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


# ─────────────────────────────────────────────
# merchant_data.order_id — несовпадение
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-012")
def test_confirm_order_id_mismatch():
    """confirm: order_id отличается от родительской транзакции → 4xx."""
    oid = gen_order_id("val012_con_oid")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(_WRONG_ORDER_ID))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении order_id, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-013")
def test_capture_order_id_mismatch():
    """capture: order_id отличается от родительской (authorized) транзакции → 4xx."""
    oid = gen_order_id("val013_cap_oid")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": _WRONG_ORDER_ID},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении order_id, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-014")
def test_refund_order_id_mismatch():
    """refund: order_id отличается от родительской транзакции → 4xx."""
    oid = gen_order_id("val014_ref_oid")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": _WRONG_ORDER_ID},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении order_id, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-015")
def test_cancel_order_id_mismatch():
    """cancel: order_id отличается от родительской (authorized) транзакции → 4xx."""
    oid = gen_order_id("val015_can_oid")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": _WRONG_ORDER_ID},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении order_id, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


# ─────────────────────────────────────────────
# merchant_data.description — несовпадение и отсутствие
# (только capture, refund, cancel — у confirm этого поля нет)
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-016")
def test_capture_description_mismatch():
    """capture: description отличается от родительской транзакции.
    Фиксируем поведение: 4xx (ошибка несовпадения) или 200 (игнорируется)."""
    oid = gen_order_id("val016_cap_desc")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid, "description": _WRONG_DESC},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при несовпадении description: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-017")
def test_refund_description_mismatch():
    """refund: description отличается от родительской транзакции.
    Фиксируем поведение: 4xx (ошибка несовпадения) или 200 (игнорируется)."""
    oid = gen_order_id("val017_ref_desc")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid, "description": _WRONG_DESC},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при несовпадении description: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-018")
def test_cancel_description_mismatch():
    """cancel: description отличается от родительской транзакции.
    Фиксируем поведение: 4xx (ошибка несовпадения) или 200 (игнорируется)."""
    oid = gen_order_id("val018_can_desc")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid, "description": _WRONG_DESC},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при несовпадении description: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-019")
def test_capture_description_absent():
    """capture: description отсутствует в запросе, но есть в родительской транзакции.
    Фиксируем поведение: ошибка (4xx) или игнорируется (200)."""
    oid = gen_order_id("val019_cap_no_desc")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid},   # description намеренно пропущен
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при отсутствии description: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-020")
def test_refund_description_absent():
    """refund: description отсутствует в запросе, но есть в родительской транзакции.
    Фиксируем поведение: ошибка (4xx) или игнорируется (200)."""
    oid = gen_order_id("val020_ref_no_desc")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},   # description намеренно пропущен
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при отсутствии description: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-021")
def test_cancel_description_absent():
    """cancel: description отсутствует в запросе, но есть в родительской транзакции.
    Фиксируем поведение: ошибка (4xx) или игнорируется (200)."""
    oid = gen_order_id("val021_can_no_desc")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},   # description намеренно пропущен
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при отсутствии description: {resp.status_code}: {resp.text}"
    )


# ─────────────────────────────────────────────
# merchant_data.webhook_url — несовпадение и отсутствие
# (только capture, refund, cancel)
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-022")
def test_capture_webhook_url_mismatch():
    """capture: webhook_url отличается от родительской транзакции.
    Фиксируем поведение: 4xx (ошибка несовпадения) или 200 (игнорируется)."""
    oid = gen_order_id("val022_cap_wh")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid, "webhook_url": _WRONG_WEBHOOK},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при несовпадении webhook_url: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-023")
def test_refund_webhook_url_mismatch():
    """refund: webhook_url отличается от родительской транзакции.
    Фиксируем поведение: 4xx (ошибка несовпадения) или 200 (игнорируется)."""
    oid = gen_order_id("val023_ref_wh")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid, "webhook_url": _WRONG_WEBHOOK},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при несовпадении webhook_url: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-024")
def test_cancel_webhook_url_mismatch():
    """cancel: webhook_url отличается от родительской транзакции.
    Фиксируем поведение: 4xx (ошибка несовпадения) или 200 (игнорируется)."""
    oid = gen_order_id("val024_can_wh")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid, "webhook_url": _WRONG_WEBHOOK},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при несовпадении webhook_url: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-025")
def test_capture_webhook_url_absent():
    """capture: webhook_url отсутствует в запросе, но есть в родительской транзакции.
    Фиксируем поведение: ошибка (4xx) или игнорируется (200)."""
    oid = gen_order_id("val025_cap_no_wh")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid},   # webhook_url намеренно пропущен
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при отсутствии webhook_url: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-026")
def test_refund_webhook_url_absent():
    """refund: webhook_url отсутствует в запросе, но есть в родительской транзакции.
    Фиксируем поведение: ошибка (4xx) или игнорируется (200)."""
    oid = gen_order_id("val026_ref_no_wh")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},   # webhook_url намеренно пропущен
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при отсутствии webhook_url: {resp.status_code}: {resp.text}"
    )


@pytest.mark.tcid("VAL-027")
def test_cancel_webhook_url_absent():
    """cancel: webhook_url отсутствует в запросе, но есть в родительской транзакции.
    Фиксируем поведение: ошибка (4xx) или игнорируется (200)."""
    oid = gen_order_id("val027_can_no_wh")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},   # webhook_url намеренно пропущен
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201, 400, 409, 422), (
        f"Неожиданный статус при отсутствии webhook_url: {resp.status_code}: {resp.text}"
    )


# ─────────────────────────────────────────────
# Комбинированные несовпадения
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-028")
def test_confirm_all_fields_mismatch():
    """confirm: все три обязательных поля (order_id, amount, currency) неверны одновременно → 4xx.
    Фиксируем: какая ошибка возвращается первой."""
    oid = gen_order_id("val028_con_all")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(
        _WRONG_ORDER_ID,
        amount=_WRONG_AMOUNT,
        currency=_WRONG_CURRENCY,
    ))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении всех полей, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)
    # Логируем порядок ошибок для документации
    try:
        err_body = resp.json()
        print(f"\n[VAL-028] Первая ошибка при несовпадении всех полей: {err_body}")
    except Exception:
        pass


@pytest.mark.tcid("VAL-029")
def test_confirm_only_order_id_mismatch():
    """confirm: amount и currency верные, order_id неверный → 4xx."""
    oid = gen_order_id("val029_con_oid")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(
        _WRONG_ORDER_ID,
        amount=_PARENT_AMOUNT,
        currency=_PARENT_CURRENCY,
    ))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении только order_id, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-030")
def test_confirm_only_amount_mismatch():
    """confirm: order_id и currency верные, amount неверный → 4xx."""
    oid = gen_order_id("val030_con_amt")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(
        oid,
        amount=_WRONG_AMOUNT,
        currency=_PARENT_CURRENCY,
    ))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении только amount, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-031")
def test_confirm_only_currency_mismatch():
    """confirm: order_id и amount верные, currency неверная → 4xx."""
    oid = gen_order_id("val031_con_cur")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(
        oid,
        amount=_PARENT_AMOUNT,
        currency=_WRONG_CURRENCY,
    ))
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении только currency, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-032")
def test_cancel_all_fields_mismatch():
    """cancel: order_id, amount, currency, description, webhook_url — все неверны → 4xx.
    Фиксируем: какая ошибка возвращается первой."""
    oid = gen_order_id("val032_can_all")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {
            "order_id": _WRONG_ORDER_ID,
            "description": _WRONG_DESC,
            "webhook_url": _WRONG_WEBHOOK,
        },
        "financial_data": {"amount": _WRONG_AMOUNT, "currency": _WRONG_CURRENCY},
    })
    assert resp.status_code >= 400, (
        f"Ожидался 4xx при несовпадении всех полей, получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)
    # Логируем порядок ошибок для документации
    try:
        err_body = resp.json()
        print(f"\n[VAL-032] Первая ошибка при несовпадении всех полей в cancel: {err_body}")
    except Exception:
        pass


# ─────────────────────────────────────────────
# Baseline — корректные запросы не ломаются
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-033")
def test_confirm_all_fields_match():
    """confirm: все поля (order_id, amount, currency) точно совпадают с родительской → 200."""
    oid = gen_order_id("val033_con_ok")
    tid = _make_waiting_3ds(oid)
    resp = post_operation(tid, "confirm", _confirm_body(
        oid,
        amount=_PARENT_AMOUNT,
        currency=_PARENT_CURRENCY,
    ))
    assert resp.status_code in (200, 201), (
        f"Ожидался 200 при совпадении всех полей, получен {resp.status_code}: {resp.text}"
    )
    assert_transaction_response(resp.json())


@pytest.mark.tcid("VAL-034")
def test_capture_all_fields_match():
    """capture: все поля (order_id, amount, currency) точно совпадают с родительской → 200."""
    oid = gen_order_id("val034_cap_ok")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "capture", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201), (
        f"Ожидался 200 при совпадении всех полей, получен {resp.status_code}: {resp.text}"
    )
    assert_transaction_response(resp.json())


@pytest.mark.tcid("VAL-035")
def test_refund_all_fields_match():
    """refund: все поля (order_id, amount, currency) точно совпадают с родительской → 200."""
    oid = gen_order_id("val035_ref_ok")
    tid = make_completed_payin(oid)
    resp = post_operation(tid, "refund", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _cfg.PAYIN_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201), (
        f"Ожидался 200 при совпадении всех полей, получен {resp.status_code}: {resp.text}"
    )
    assert_transaction_response(resp.json())


@pytest.mark.tcid("VAL-036")
def test_cancel_all_fields_match():
    """cancel: все поля (order_id, amount, currency) точно совпадают с родительской → 200."""
    oid = gen_order_id("val036_can_ok")
    tid = make_block_payin(oid)
    resp = post_operation(tid, "cancel", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": _PARENT_AMOUNT, "currency": _PARENT_CURRENCY},
    })
    assert resp.status_code in (200, 201), (
        f"Ожидался 200 при совпадении всех полей, получен {resp.status_code}: {resp.text}"
    )
    assert_transaction_response(resp.json())


# ─────────────────────────────────────────────
# Граничные случаи типов данных
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-037")
def test_confirm_amount_as_string():
    """confirm: amount верное значение, но передан как строка → 400 (ошибка типа, не несовпадения).
    Должен отклоняться ещё до проверки совпадения с родительской транзакцией."""
    oid = gen_order_id("val037_con_str_amt")
    tid = _make_waiting_3ds(oid)
    # amount передаётся как строка (корректное значение, но неверный тип)
    resp = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": str(_PARENT_AMOUNT), "currency": _PARENT_CURRENCY},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares", "md": "test_md"}},
        },
    })
    assert resp.status_code == 400, (
        f"Ожидался 400 (ошибка типа amount), получен {resp.status_code}: {resp.text}"
    )
    assert_error_response(resp)


@pytest.mark.tcid("VAL-038")
def test_confirm_amount_as_float():
    """confirm: amount передан как float при совпадающем родительском значении.
    Фиксируем поведение: 400 (ошибка типа) или принятие (200)."""
    oid = gen_order_id("val038_con_flt_amt")
    tid = _make_waiting_3ds(oid)
    # Передаём float, значение которого совпадает с родительским (напр. 1000.0 == 1000)
    resp = post_operation(tid, "confirm", {
        "merchant_data": {"order_id": oid},
        "financial_data": {"amount": float(_PARENT_AMOUNT), "currency": _PARENT_CURRENCY},
        "result": {
            "type": "threed_secure",
            "details": {"data": {"pares": "test_pares", "md": "test_md"}},
        },
    })
    # Оба варианта допустимы: строгая типизация (400) или приведение типов (200)
    assert resp.status_code in (200, 201, 400), (
        f"Неожиданный статус для amount как float: {resp.status_code}: {resp.text}"
    )
    try:
        err_body = resp.json()
        print(f"\n[VAL-038] Поведение при amount как float: статус={resp.status_code}, тело={err_body}")
    except Exception:
        pass


# ─────────────────────────────────────────────
# GET-эндпоинты — актуальность данных родительской транзакции
# ─────────────────────────────────────────────

@pytest.mark.tcid("VAL-GET-01")
def test_get_by_transaction_id_returns_parent_data():
    """GET /transactions/{id} возвращает актуальные данные родительской транзакции."""
    oid = gen_order_id("val_get01")
    tid = make_block_payin(oid)
    resp = get_request(f"{_cfg.BASE_URL}/{tid}")
    assert resp.status_code == 200, (
        f"Ожидался 200 при GET /transactions/{tid}, получен {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    assert_transaction_response(data)
    assert data.get("transaction_id") == tid, (
        f"transaction_id в ответе {data.get('transaction_id')!r} не совпадает с запрошенным {tid!r}"
    )
    assert data.get("merchant_data", {}).get("order_id") == oid, (
        f"order_id в GET-ответе {data.get('merchant_data', {}).get('order_id')!r} "
        f"не совпадает с oid={oid!r}"
    )
    fd = data.get("financial_data", {})
    assert fd.get("amount") == _PARENT_AMOUNT, (
        f"amount в GET-ответе {fd.get('amount')!r} != ожидаемому {_PARENT_AMOUNT!r}"
    )
    assert fd.get("currency") == _PARENT_CURRENCY, (
        f"currency в GET-ответе {fd.get('currency')!r} != ожидаемому {_PARENT_CURRENCY!r}"
    )


@pytest.mark.tcid("VAL-GET-02")
def test_get_by_order_id_returns_parent_data():
    """GET /transactions?order_id=... возвращает список с актуальными данными родительской транзакции."""
    oid = gen_order_id("val_get02")
    tid = make_block_payin(oid)
    resp = get_request(_cfg.BASE_URL, params={"order_id": oid})
    assert resp.status_code == 200, (
        f"Ожидался 200 при GET ?order_id={oid}, получен {resp.status_code}: {resp.text}"
    )
    items = resp.json()
    assert isinstance(items, list) and len(items) > 0, (
        f"Ожидался непустой список транзакций для order_id={oid!r}, получен: {items}"
    )
    tx = next((i for i in items if i.get("transaction_id") == tid), None)
    assert tx is not None, (
        f"Транзакция tid={tid} не найдена в GET ?order_id={oid!r}: {items}"
    )
    assert tx.get("merchant_data", {}).get("order_id") == oid, (
        f"order_id в ответе {tx.get('merchant_data', {}).get('order_id')!r} != {oid!r}"
    )
