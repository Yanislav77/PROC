"""
Тесты WebSocket-эндпоинта:
  GET /api/v1/payment-sessions/{payment_token}/ws  (аналог /payments/{payment_token}/ws)

Авторизация на handshake отсутствует — поведение идентично старому эндпоинту.
Протокол: JSON-фреймы поверх WS (3DS_method, confirmation, push состояния).

WS-013..014 используют WebSocketApp (threading): on_ping подавляет авто-pong в websocket-client ≥ 1.3.
"""
import json
import threading
import time

import pytest
import websocket

_WEB3_HOST  = "web3preprod.testpaygate.com"
_BASE_PATH  = f"wss://{_WEB3_HOST}/api/v1/payment-sessions"
_OLD_BASE   = f"wss://{_WEB3_HOST}/payments"
_WS_TIMEOUT = 10  # секунд, таймаут на recv


def _connect(token: str) -> websocket.WebSocket:
    return websocket.create_connection(f"{_BASE_PATH}/{token}/ws", timeout=_WS_TIMEOUT)


def _recv_json(ws: websocket.WebSocket) -> dict:
    return json.loads(ws.recv())


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("WS-001")
def test_ws_handshake_success(payment_token):
    """Handshake успешен, сервер шлёт init-сообщение с payment_id и state."""
    ws = _connect(payment_token)
    try:
        msg = _recv_json(ws)
        assert "payment_id" in msg, f"Missing payment_id in init: {msg}"
        assert "state"      in msg, f"Missing state in init: {msg}"
        assert "state_data" in msg, f"Missing state_data in init: {msg}"
    finally:
        ws.close()


@pytest.mark.tcid("WS-002")
def test_ws_init_service_params(payment_token):
    """Init-сообщение содержит флаги параметров сервиса."""
    ws = _connect(payment_token)
    try:
        msg = _recv_json(ws)
        for field in ("is_address_req", "is_ch_name_req", "is_phone_req", "is_email_req"):
            assert field in msg, f"Missing field '{field}' in init: {msg}"
    finally:
        ws.close()


@pytest.mark.tcid("WS-003")
@pytest.mark.slow
def test_ws_heartbeat_keeps_connection(payment_token):
    """Соединение остаётся живым > 10 сек (ping/pong проходит). Тест медленный (~12 сек)."""
    ws = _connect(payment_token)
    try:
        ws.recv()  # init message
        ws.settimeout(_WS_TIMEOUT + 5)
        time.sleep(12)
        # ping/pong обрабатывается websocket-client автоматически;
        # если соединение разорвалось — ping() выбросит исключение
        ws.ping()
    finally:
        ws.close()


@pytest.mark.tcid("WS-009")
def test_ws_client_close_graceful(payment_token):
    """Клиент закрывает соединение — сервер принимает close frame без ошибок."""
    ws = _connect(payment_token)
    ws.recv()  # init message
    ws.close()  # не должно бросать исключений


@pytest.mark.tcid("WS-012")
def test_ws_no_auth_headers_accepted(payment_token):
    """Handshake без кастомных заголовков — 101 Switching Protocols (авторизация не требуется)."""
    ws = websocket.create_connection(
        f"{_BASE_PATH}/{payment_token}/ws",
        timeout=_WS_TIMEOUT,
        header={},
    )
    try:
        msg = _recv_json(ws)
        assert "payment_id" in msg
    finally:
        ws.close()


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: handshake
# ─────────────────────────────────────────────
@pytest.mark.tcid("WS-004")
def test_ws_invalid_token_format():
    """Невалидный UUID в path — handshake отклоняется с 4xx (validation_uuid_decorator)."""
    with pytest.raises(websocket.WebSocketBadStatusException) as exc_info:
        websocket.create_connection(
            f"{_BASE_PATH}/not-a-uuid/ws",
            timeout=_WS_TIMEOUT,
        )
    status = exc_info.value.status_code
    assert status in range(400, 500), f"Expected 4xx for invalid UUID token, got {status}"


# ─────────────────────────────────────────────
# НЕГАТИВНЫЕ: WS-фреймы
# ─────────────────────────────────────────────
@pytest.mark.tcid("WS-005")
def test_ws_nonexistent_payment_id_in_message(payment_token):
    """3DS_method с несуществующим paymentId — сервер закрывает соединение."""
    ws = _connect(payment_token)
    try:
        ws.recv()  # init message
        ws.send(json.dumps({
            "type":      "3DS_method",
            "paymentId": "00000000-0000-0000-0000-deadbeef0000",
        }))
        ws.settimeout(5)
        try:
            ws.recv()
        except websocket.WebSocketConnectionClosedException:
            pass  # ожидаемое поведение
    finally:
        ws.close()


@pytest.mark.tcid("WS-010")
def test_ws_invalid_json_frame(payment_token):
    """Битый JSON во фрейме — фиксируем текущее поведение (не падает unhandled)."""
    ws = _connect(payment_token)
    try:
        ws.recv()  # init message
        ws.send("{not_a_json")
        ws.settimeout(3)
        try:
            ws.recv()
        except (websocket.WebSocketTimeoutException, websocket.WebSocketConnectionClosedException):
            pass  # оба варианта допустимы — поведение фиксируется
    finally:
        ws.close()


# ─────────────────────────────────────────────
# КЕЙСЫ С УСЛОВИЕМ НА СОСТОЯНИЕ ПЛАТЕЖА
# ─────────────────────────────────────────────
@pytest.mark.tcid("WS-006")
@pytest.mark.skip(reason="Требует платёж в состоянии ожидания 3DS — настроить вручную")
def test_ws_3ds_method_handling(payment_token):
    """Обработка фрейма 3DS_method — платёж должен быть в 3DS-состоянии."""
    ws = _connect(payment_token)
    try:
        ws.recv()  # init message
        ws.send(json.dumps({"type": "3DS_method", "paymentId": payment_token}))
        msg = _recv_json(ws)
        assert msg, f"Expected state push, got: {msg}"
    finally:
        ws.close()


@pytest.mark.tcid("WS-007")
@pytest.mark.skip(reason="Требует платёж в состоянии ожидания подтверждения — настроить вручную")
def test_ws_confirmation_handling(payment_token):
    """Обработка фрейма confirmation — платёж должен ожидать подтверждения."""
    ws = _connect(payment_token)
    try:
        ws.recv()  # init message
        ws.send(json.dumps({"type": "confirmation", "paymentId": payment_token}))
        msg = _recv_json(ws)
        assert msg, f"Expected state push, got: {msg}"
    finally:
        ws.close()


@pytest.mark.tcid("WS-008")
@pytest.mark.skip(reason="Требует параллельного изменения состояния платежа через REST")
def test_ws_state_push_on_payment_change(payment_token):
    """Push состояния: клиент получает фрейм при изменении платежа извне."""
    ws = _connect(payment_token)
    try:
        ws.recv()  # init message
        ws.settimeout(5)
        msg = _recv_json(ws)
        assert "state" in msg, f"Expected state update, got: {msg}"
    finally:
        ws.close()


# ─────────────────────────────────────────────
# PING / PONG
# ─────────────────────────────────────────────
@pytest.mark.tcid("WS-013")
@pytest.mark.slow
def test_ws_no_pong_closes_connection(payment_token):
    """Без pong-ответа на ping сервер закрывает соединение.
    Максимальное ожидание закрытия — 120 сек. Тест медленный."""
    closed = threading.Event()

    def on_ping(ws, message):
        pass  # намеренно не отвечаем pong

    def on_close(ws, code, msg):
        closed.set()

    ws_app = websocket.WebSocketApp(
        f"{_BASE_PATH}/{payment_token}/ws",
        on_ping=on_ping,
        on_close=on_close,
    )
    threading.Thread(target=ws_app.run_forever, daemon=True).start()
    closed.wait(timeout=120)
    ws_app.keep_running = False
    if ws_app.sock:
        try:
            ws_app.sock.shutdown()
        except Exception:
            pass
    assert closed.is_set(), "Server should close connection when pong responses are suppressed"


@pytest.mark.tcid("WS-014")
@pytest.mark.slow
def test_ws_explicit_pong_keeps_connection(payment_token):
    """Явные pong-ответы на каждый ping удерживают соединение живым 2 мин. Тест медленный (~120 сек)."""
    DURATION = 120
    closed = threading.Event()

    def on_ping(ws, message):
        ws.pong(message)  # явный pong

    def on_close(ws, code, msg):
        closed.set()

    ws_app = websocket.WebSocketApp(
        f"{_BASE_PATH}/{payment_token}/ws",
        on_ping=on_ping,
        on_close=on_close,
    )
    threading.Thread(target=ws_app.run_forever, daemon=True).start()
    try:
        time.sleep(DURATION)
        assert not closed.is_set(), \
            f"Connection should remain open for {DURATION}s with explicit pong responses"
    finally:
        ws_app.keep_running = False
        if ws_app.sock:
            try:
                ws_app.sock.shutdown()
            except Exception:
                pass


# ─────────────────────────────────────────────
# РЕГРЕСС
# ─────────────────────────────────────────────
@pytest.mark.tcid("WS-011")
def test_ws_old_endpoint_regression(payment_token):
    """Регресс: старый /payments/{token}/ws продолжает работать без изменений."""
    ws = websocket.create_connection(
        f"{_OLD_BASE}/{payment_token}/ws",
        timeout=_WS_TIMEOUT,
    )
    try:
        msg = _recv_json(ws)
        assert "payment_id" in msg, f"Missing payment_id in init: {msg}"
        assert "state"      in msg, f"Missing state in init: {msg}"
    finally:
        ws.close()
