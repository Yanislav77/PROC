# PROC — CORE REST API Test Suite

Интеграционные тесты для CORE REST API (платёжный шлюз).

## Структура проекта

```
PROC/
├── pytest.ini               # настройки pytest
├── requirements.txt         # зависимости
└── tests/
    ├── conftest.py          # конфиг, подпись, хелперы, фикстуры
    ├── test_happy_path.py   # позитивные сценарии
    └── test_negative.py     # негативные сценарии и граничные случаи
```

## Конфигурация

Перед запуском отредактируйте `tests/conftest.py`:

```python
SERVICE_SECRET = "your_service_secret_here"  # ← вставить реальный секрет

TERMINALS = {
    "default": "374",   # терминал для card / payout / refund
    "p2p":     "502",   # терминал для p2p payin
    "mobile":  "503",   # терминал для mobile payin
}
```

`BASE_URL` уже указывает на препрод:
```
https://papiv3preprod.testpaygate.com/api/v1/transactions
```

## Подпись запросов

Каждый запрос подписывается HMAC-SHA256. Сообщение для подписи:

```
METHOD\nApi-Terminal-ID\nApi-Timestamp\nraw_body
```

- `raw_body` — тело запроса в компактном JSON (без пробелов)
- `Api-Timestamp` — Unix-время в секундах
- Результирующий hex-дайджест передаётся в заголовке `Api-Signature`
- Каждый запрос также содержит уникальный `Api-Idempotency-Key` (UUID v4)

## Установка

```bash
pip install -r requirements.txt
```

## Запуск тестов

```bash
# все тесты
pytest

# только позитивные
pytest tests/test_happy_path.py

# только негативные
pytest tests/test_negative.py

# остановиться на первой ошибке
pytest -x

# подробный вывод при падении
pytest --tb=long
```

## Покрытие тестами

### Позитивные сценарии (`test_happy_path.py`)

| Тест | Метод / терминал | Сценарий |
|---|---|---|
| `test_payin_card` | card / default (374) | Payin картой, `is_recurrent=True`, `capture=auto` |
| `test_payin_p2p` | p2p / p2p (502) | Payin через P2P |
| `test_payin_mobile` | mobile / mobile (503) | Payin через мобильный платёж |
| `test_payin_block` | card / default (374) | Блокировка средств, `capture=manual` |
| `test_recurrent` | card / default (374) | Рекуррентный платёж с `parent_transaction_id` |
| `test_payout` | card / default (374) | Выплата на карту |
| `test_rebill` | token / default (374) | Ребилл по токену, `capture=auto` |
| `test_rebill_block` | token / default (374) | Ребилл-блок по токену, `capture=manual` |
| `test_refund` | — | Возврат через `/{transaction_id}/refund` |

Тесты `test_recurrent`, `test_rebill`, `test_rebill_block`, `test_refund` используют
фикстуру `payin_transaction_id` (session-scoped): один реальный Payin делается один раз
для всей сессии.

Хелпер `assert_success` проверяет в каждом ответе:
- HTTP 201
- поля: `transaction_id`, `type`, `status`, `merchant_data`, `financial_data`, `created_at`
- заголовки ответа: `Api-Terminal-ID`, `Api-Idempotency-Key`

### Негативные сценарии (`test_negative.py`)

| Тест | Ожидаемый статус | Сценарий |
|---|---|---|
| `test_missing_top_level_field[type/merchant_data/…]` | 422 | Отсутствие каждого из 6 обязательных полей верхнего уровня |
| `test_invalid_transaction_type` | 422 | Неизвестный `type` |
| `test_negative_amount` | 422 | Отрицательная сумма |
| `test_zero_amount` | 422 | Нулевая сумма |
| `test_invalid_currency` | 422 | Несуществующий код валюты |
| `test_missing_currency` | 422 | Отсутствие поля `currency` |
| `test_missing_merchant_field[order_id/webhook_url]` | 422 | Отсутствие обязательных полей в `merchant_data` |
| `test_invalid_card_pan` | 422 | PAN из 4 цифр |
| `test_expired_card` | 422 | Истёкший срок карты |
| `test_missing_cvv` | 422 | Отсутствие CVV |
| `test_invalid_signature` | 401 / 403 | Нулевая подпись |
| `test_missing_signature_header` | 400 / 401 / 403 | Заголовок `Api-Signature` отсутствует |
| `test_missing_terminal_id_header` | 400 / 401 / 403 | Заголовок `Api-Terminal-ID` отсутствует |
| `test_unknown_terminal_id` | 401 / 403 / 404 | Несуществующий терминал `99999` |
| `test_idempotency_key_deduplication` | 201 + 200/201 | Повтор с тем же `Api-Idempotency-Key` → тот же `transaction_id` |
| `test_invalid_json_body` | 400 / 422 | Тело не является валидным JSON |
| `test_refund_nonexistent_transaction` | 404 / 422 | Возврат по несуществующему `transaction_id` |
| `test_refund_amount_exceeds_original` | 400 / 422 | Сумма возврата превышает оригинальную транзакцию |
