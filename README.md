# PROC — CORE REST API Test Suite

Интеграционные тесты для CORE REST API платёжного шлюза.
Тесты делают реальные HTTP-запросы к препрод-окружению — никаких моков.

---

## Содержание

1. [Установка с нуля](#1-установка-с-нуля)
2. [Получить свежие изменения](#2-получить-свежие-изменения)
3. [Что и где настраивать](#3-что-и-где-настраивать)
4. [Как запускать тесты](#4-как-запускать-тесты)
5. [Что делают тесты](#5-что-делают-тесты)
6. [Как читать результат](#6-как-читать-результат)
7. [Частые ошибки и что с ними делать](#7-частые-ошибки-и-что-с-ними-делать)

---

## 1. Установка с нуля

### Python

1. Скачайте Python на [python.org/downloads](https://www.python.org/downloads/)
2. Запустите установщик и **обязательно поставьте галочку «Add Python to PATH»**
3. Нажмите «Install Now»
4. Проверка: откройте PowerShell и введите `python --version` — должна появиться версия

### Проект в PyCharm

1. Скачайте репозиторий: кнопка **Code → Download ZIP** на GitHub, распакуйте
   (или `git clone https://github.com/Yanislav77/PROC.git`)
2. Откройте PyCharm → **File → Open** → выберите папку `PROC`

### Виртуальное окружение

Виртуальное окружение — изолированная папка с Python и пакетами для этого проекта.
Нужно создать один раз.

1. **File → Settings → Project: PROC → Python Interpreter**
2. Нажмите шестерёнку ⚙ → **Add Interpreter → Add Local Interpreter**
3. **Virtualenv Environment → New**, путь оставьте как есть → **OK**

### Зависимости

Откройте `requirements.txt` в PyCharm — появится жёлтая плашка **Install requirements**.
Нажмите её.

Или в терминале PyCharm (**View → Tool Windows → Terminal**):
```
pip install -r requirements.txt
```

---

## 2. Получить свежие изменения

Когда в репозиторий добавляются новые тесты или правки, нужно стянуть их к себе.

### Через PyCharm (проще всего)

**Git → Update Project** (или `Ctrl+T` / `⌘T` на Mac) → **OK**.

PyCharm скачает последние изменения и объединит их с вашими локальными файлами.

### Через терминал

Откройте терминал в папке проекта и выполните:

```
git pull
```

Если появилось сообщение вроде `Already up to date` — у вас уже последняя версия.
Если обновились файлы — установите зависимости на случай, если они изменились:

```
pip install -r requirements.txt
```

### Важно: файл `.env` при обновлении не трогается

`.env` не хранится в репозитории, поэтому `git pull` никогда не перезапишет ваш секрет и ID терминала.
Если после обновления тесты стали падать с ошибкой авторизации — проверьте, что `.env` на месте.

---

## 3. Что и где настраивать

### Секрет и ID терминала → файл `.env`

В корне проекта есть `.env.example`. Создайте рядом файл `.env`:

```
copy .env.example .env
```

Откройте `.env` и заполните:

```
SERVICE_SECRET=вставьте_сюда_секрет
TERMINAL_ID=374
```

- `SERVICE_SECRET` — секрет для подписи запросов. Берётся из настроек платёжного шлюза.
- `TERMINAL_ID` — ID вашего терминала.

> `.env` не попадает в git, секрет виден только у вас локально.

---

### Данные карты, клиента, мерчанта → `tests/conftest.py`

Откройте `tests/conftest.py` и найдите блок `SHARED PAYLOADS`.
Там словари с тестовыми данными, которые используются во всех файлах тестов:

**Карта** (`CARD_DETAILS`):
```python
CARD_DETAILS = {
    "pan":          "4111111111111111",  # номер карты
    "holder":       "JOHN DOE",          # имя (латиницей)
    "expiry_month": "05",                # месяц истечения
    "expiry_year":  "27",                # год истечения (две цифры)
    "cvv":          "666",
}
```

**Мерчант** (`MERCHANT_DATA`):
```python
MERCHANT_DATA = {
    "order_id":    "order_1111",                    # ID заказа
    "description": "Order payment",
    "webhook_url": "https://merchant.com/webhook",  # URL для уведомлений от API
    "return_url":  "https://merchant.com/return",
}
```

**Клиент** (`CUSTOMER_DATA`) — контакты, паспорт, браузер. Меняйте если нужно,
но для запуска тестов трогать не обязательно.

Изменения в этих словарях автоматически применятся ко всем тестам.

---

### Суммы, валюты, телефон → конкретный файл теста

Каждый тест содержит `financial_data` с суммой и валютой. Найдите нужный тест
и поменяйте прямо там. Например, в `test_payin_card`:

```python
"financial_data": {"amount": 10000, "currency": "RUB"},
```

Сумма указывается в минимальных единицах: `10000` = 100.00 RUB.

Телефон для мобильного платежа — в `test_payin_mobile`:
```python
"transaction_data": {"method": "mobile", "details": {"phone": "+345283494512"}},
```

---

### Токен для rebill → `tests/test_happy_path.py`

В тестах `test_rebill` и `test_rebill_block` используется токен карты:

```python
"details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
```

Это заглушка. Замените на реальный токен, который вернул API в ответе на Payin.

---

### URL API → `tests/conftest.py`

```python
_API_BASE            = "https://papiv3preprod.testpaygate.com/api/v1"
BASE_URL             = f"{_API_BASE}/transactions"
SUBSCRIPTIONS_URL    = f"{_API_BASE}/subscriptions"
PAYMENT_LINKS_URL    = f"{_API_BASE}/payment-links"
MERCHANT_BALANCE_URL = f"{_API_BASE}/merchant/balance"
```

Чтобы переключиться на другой стенд — измените только строку `_API_BASE`, все URL обновятся автоматически.

---

## 4. Как запускать тесты

### Через PyCharm (проще всего)

В правом верхнем углу PyCharm есть выпадающий список конфигураций.
Там готовы варианты для каждого файла тестов:

| Конфигурация | Что запускает |
|---|---|
| **All Tests** | все тесты сразу |
| **Happy Path** | `test_happy_path.py` — позитивные сценарии |
| **Negative** | `test_negative.py` — негативные сценарии |
| **Get Transactions** | `test_get_transactions.py` — GET-запросы |
| **Operations** | `test_operations.py` — capture, cancel, confirm, refund |
| **Payout Methods** | `test_payout_methods.py` — все методы выплат |
| **Payment Links** | `test_payment_links.py` — платёжные ссылки |
| **Merchant** | `test_merchant.py` — баланс мерчанта |
| **Subscriptions** | `test_subscriptions.py` — управление подписками |

Выберите нужный → нажмите ▶.

Также можно кликнуть правой кнопкой на любом файле или функции в боковой панели
и выбрать **Run**.

### Через терминал

```bash
# все тесты
pytest

# один файл
pytest tests/test_happy_path.py
pytest tests/test_operations.py

# один конкретный тест
pytest tests/test_happy_path.py::test_payin_card

# остановиться на первой ошибке
pytest -x

# полный вывод при падении
pytest --tb=long

# показать print() внутри тестов
pytest -s
```

---

## 5. Что делают тесты

### `test_happy_path.py` — позитивные сценарии создания транзакций

Проверяют, что каждый тип транзакции создаётся успешно (HTTP 201)
и в ответе есть все обязательные поля.

| Тест | Что проверяет |
|---|---|
| `test_payin_card` | Payin картой, автосписание (`capture=auto`) |
| `test_payin_p2p` | Payin через P2P |
| `test_payin_qr` | Payin через QR-код |
| `test_payin_mobile` | Payin через мобильный платёж |
| `test_payin_block` | Payin картой с холдом (`capture=manual`) |
| `test_recurrent` | Рекуррентный платёж по данным предыдущей транзакции |
| `test_payout` | Выплата на карту |
| `test_rebill` | Ребилл по токену карты, автосписание |
| `test_rebill_block` | Ребилл по токену карты с холдом |
| `test_refund` | Частичный возврат по существующей транзакции |
| `test_payin_card_without_flow_data` | flow_data необязателен |
| `test_payin_card_without_webhook_url` | webhook_url необязателен |

Тесты `test_recurrent`, `test_rebill`, `test_rebill_block`, `test_refund` автоматически
создают один Payin перед запуском и переиспользуют его `transaction_id` — это происходит
один раз на весь прогон.

---

### `test_negative.py` — негативные сценарии создания транзакций

Проверяют, что API корректно отклоняет невалидные запросы.

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_missing_top_level_field` | Отсутствие одного из 5 обязательных полей (5 вариантов) | 422 |
| `test_invalid_transaction_type` | Неизвестный `type` | 422 |
| `test_negative_amount` | Отрицательная сумма | 422 |
| `test_zero_amount` | Нулевая сумма | 422 |
| `test_invalid_currency` | Несуществующий код валюты | 422 |
| `test_missing_currency` | Поле `currency` отсутствует | 422 |
| `test_missing_merchant_order_id` | Нет `order_id` в `merchant_data` | 422 |
| `test_invalid_card_pan` | PAN из 4 цифр | 422 |
| `test_expired_card` | Истёкший срок карты | 422 |
| `test_missing_card_required_field` | Каждое из 5 обязательных полей карты (5 вариантов) | 422 |
| `test_invalid_signature` | Подпись из нулей | 401 / 403 |
| `test_missing_signature_header` | Заголовок `Api-Signature` отсутствует | 400 / 401 / 403 |
| `test_missing_terminal_id_header` | Заголовок `Api-Terminal-ID` отсутствует | 400 / 401 / 403 |
| `test_unknown_terminal_id` | Несуществующий терминал | 401 / 403 / 404 |
| `test_idempotency_key_deduplication` | Повтор с тем же ключом → тот же `transaction_id` | 201 + 200/201 |
| `test_invalid_json_body` | Тело не является JSON | 400 / 422 |
| `test_refund_nonexistent_transaction` | Возврат по несуществующей транзакции | 404 / 422 |
| `test_refund_amount_exceeds_original` | Сумма возврата больше оригинала | 400 / 422 |
| `test_timestamp_too_old` | Timestamp старше 5 минут | 401 / 403 |

---

### `test_get_transactions.py` — получение транзакций

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_get_transaction_by_id` | GET `/{id}` — возвращает транзакцию с нужными полями | 200 |
| `test_get_transaction_fields` | Типы и форматы полей ответа | 200 |
| `test_get_transaction_status_is_valid` | Статус входит в список допустимых значений | 200 |
| `test_get_transactions_by_order_id` | GET `?order_id=` — возвращает массив | 200 |
| `test_get_transaction_not_found` | GET по несуществующему ID | 404 |
| `test_get_by_order_id_not_found` | GET по несуществующему order_id | 404 |
| `test_get_by_order_id_missing_param` | GET без параметра order_id | 400 / 422 |
| `test_get_transaction_no_auth` | Без заголовков авторизации | 400 / 401 / 403 |
| `test_get_transaction_invalid_signature` | Подпись из нулей | 401 / 403 |
| `test_get_transaction_missing_terminal_id` | Нет `Api-Terminal-ID` | 400 / 401 / 403 |
| `test_get_transaction_missing_timestamp` | Нет `Api-Timestamp` | 400 / 401 / 403 |

---

### `test_operations.py` — операции над транзакциями

#### Capture — списание заблокированных средств

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_capture_after_block` | Списание после Payin с `capture=manual` | 200 / 201 |
| `test_capture_partial_amount` | Частичное списание | 200 / 201 |
| `test_capture_without_webhook_url` | Без необязательного `webhook_url` | 200 / 201 |
| `test_capture_nonexistent_transaction` | Несуществующая транзакция | 404 |
| `test_capture_missing_financial_data` | Нет `financial_data` | 400 / 422 |
| `test_capture_missing_merchant_data` | Нет `merchant_data` | 400 / 422 |
| `test_capture_missing_order_id` | Нет `order_id` | 400 / 422 |
| `test_capture_missing_amount` | Нет `amount` | 400 / 422 |
| `test_capture_missing_currency` | Нет `currency` | 400 / 422 |
| `test_capture_invalid_currency` | Невалидный код валюты | 400 / 422 |
| `test_capture_zero_amount` | Нулевая сумма | 400 / 422 |
| `test_capture_negative_amount` | Отрицательная сумма | 400 / 422 |

#### Cancel — отмена транзакции

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_cancel_transaction` | Отмена транзакции с холдом | 200 / 201 |
| `test_cancel_with_description` | С необязательным `description` | 200 / 201 |
| `test_cancel_nonexistent_transaction` | Несуществующая транзакция | 404 |
| `test_cancel_missing_financial_data` | Нет `financial_data` | 400 / 422 |
| `test_cancel_missing_merchant_data` | Нет `merchant_data` | 400 / 422 |
| `test_cancel_missing_order_id` | Нет `order_id` | 400 / 422 |

#### Confirm — подтверждение ожидающего действия (3DS, redirect и т.д.)

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_confirm_nonexistent_transaction` | Несуществующая транзакция | 404 |
| `test_confirm_missing_result` | Нет поля `result` | 400 / 422 |
| `test_confirm_missing_financial_data` | Нет `financial_data` | 400 / 422 |
| `test_confirm_missing_merchant_data` | Нет `merchant_data` | 400 / 422 |
| `test_confirm_missing_order_id` | Нет `order_id` | 400 / 422 |
| `test_confirm_invalid_result_type` | Неизвестный тип `result` | 400 / 422 |
| `test_confirm_threed_secure_missing_pares` | Нет `pares` в 3DS result | 400 / 422 |
| `test_confirm_threed_secure_missing_md` | Нет `md` в 3DS result | 400 / 422 |
| `test_confirm_generic_missing_confirmed` | Нет `confirmed` в redirect result | 400 / 422 |

#### Refund — дополнительные поля возврата

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_refund_missing_merchant_data` | Нет `merchant_data` | 400 / 422 |
| `test_refund_missing_financial_data` | Нет `financial_data` | 400 / 422 |
| `test_refund_missing_order_id` | Нет `order_id` | 400 / 422 |
| `test_refund_missing_currency` | Нет `currency` | 400 / 422 |
| `test_refund_missing_amount` | Нет `amount` | 400 / 422 |
| `test_refund_zero_amount` | Нулевая сумма | 400 / 422 |
| `test_refund_negative_amount` | Отрицательная сумма | 400 / 422 |
| `test_refund_invalid_currency` | Невалидный код валюты | 400 / 422 |

---

### `test_payout_methods.py` — все методы выплат

#### Happy path

| Тест | Метод | Что проверяет |
|---|---|---|
| `test_payout_mobile` | mobile | phone обязателен |
| `test_payout_mobile_with_provider` | mobile | с необязательным provider |
| `test_payout_sbp_with_phone_and_bank` | sbp | phone и bank (оба необязательны) |
| `test_payout_sbp_without_details` | sbp | без details |
| `test_payout_wallet` | wallet | id обязателен |
| `test_payout_wallet_with_brand` | wallet | с необязательным brand |
| `test_payout_bank_account_with_swift` | bank_account | счёт + SWIFT |
| `test_payout_bank_account_with_pix` | bank_account | PIX (Бразилия) |
| `test_payout_bank_account_minimal` | bank_account | без details |
| `test_payout_token` | token | token обязателен |

#### Негативные сценарии

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_payout_card_missing_pan` | Нет `pan` | 422 |
| `test_payout_card_missing_holder` | Нет `holder` | 422 |
| `test_payout_card_missing_details` | Нет `details` | 422 |
| `test_payout_mobile_missing_phone` | Нет `phone` | 422 |
| `test_payout_mobile_missing_details` | Нет `details` | 422 |
| `test_payout_wallet_missing_id` | Нет `id` | 422 |
| `test_payout_wallet_missing_details` | Нет `details` | 422 |
| `test_payout_token_missing_token` | Нет `token` | 422 |
| `test_payout_token_missing_details` | Нет `details` | 422 |
| `test_payout_unknown_method` | Неизвестный метод | 422 |
| `test_payout_negative_amount` | Отрицательная сумма | 422 |
| `test_payout_zero_amount` | Нулевая сумма | 422 |
| `test_payout_invalid_currency` | Невалидный код валюты | 422 |

---

### `test_payment_links.py` — платёжные ссылки

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_create_payment_link` | Создание ссылки, обязательные поля ответа | 201 |
| `test_create_payment_link_response_fields` | Типы полей ответа, валидность URL | 201 |
| `test_create_payment_link_with_flow_data` | С необязательным flow_data | 201 |
| `test_create_payment_link_with_recurrent_flow` | is_recurrent=True | 201 |
| `test_create_payment_link_with_manual_capture` | capture_mode=manual | 201 |
| `test_create_payment_link_without_webhook_url` | Без необязательного webhook_url | 201 |
| `test_create_payment_link_without_return_url` | Без необязательного return_url | 201 |
| `test_create_payment_link_minimal_customer_data` | Пустой customer_data (все поля необязательны) | 201 |
| `test_create_payment_link_usd` | Валюта USD | 201 |
| `test_payment_link_missing_required_field` | Каждое из 3 обязательных полей (3 варианта) | 422 |
| `test_payment_link_missing_order_id` | Нет order_id в merchant_data | 422 |
| `test_payment_link_negative_amount` | Отрицательная сумма | 422 |
| `test_payment_link_zero_amount` | Нулевая сумма | 422 |
| `test_payment_link_invalid_currency` | Невалидный код валюты | 422 |
| `test_payment_link_missing_currency` | Нет currency | 422 |
| `test_payment_link_missing_amount` | Нет amount | 422 |
| `test_payment_link_invalid_capture_mode` | Невалидный capture_mode | 422 |
| `test_payment_link_no_auth` | Без авторизации | 400 / 401 / 403 |
| `test_payment_link_invalid_signature` | Подпись из нулей | 401 / 403 |

---

### `test_merchant.py` — баланс мерчанта

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_get_merchant_balance` | Получение баланса, обязательные поля | 200 |
| `test_get_merchant_balance_currency_format` | currency — 3-символьный ISO-код | 200 |
| `test_get_merchant_balance_no_auth` | Без авторизации | 400 / 401 / 403 |
| `test_get_merchant_balance_invalid_signature` | Подпись из нулей | 401 / 403 |
| `test_get_merchant_balance_missing_terminal_id` | Нет Api-Terminal-ID | 400 / 401 / 403 |
| `test_get_merchant_balance_missing_timestamp` | Нет Api-Timestamp | 400 / 401 / 403 |
| `test_get_merchant_balance_unknown_terminal` | Несуществующий терминал | 401 / 403 / 404 |

---

### `test_subscriptions.py` — управление подписками

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_cancel_nonexistent_subscription` | DELETE по несуществующему UUID | 404 |
| `test_cancel_subscription_invalid_token_format` | Токен не в формате UUID | 400 / 404 / 422 |
| `test_cancel_subscription_no_auth` | Без авторизации | 400 / 401 / 403 |
| `test_cancel_subscription_invalid_signature` | Подпись из нулей | 401 / 403 |
| `test_cancel_subscription_missing_terminal_id` | Нет Api-Terminal-ID | 400 / 401 / 403 |
| `test_cancel_subscription_missing_timestamp` | Нет Api-Timestamp | 400 / 401 / 403 |

---

## 6. Как читать результат

### В PyCharm

После запуска внизу открывается панель **Run**:
- Зелёный кружок — тест прошёл
- Красный крестик — тест упал
- Кликните на упавший тест — справа появится подробный вывод

### В терминале

Успешный прогон:
```
tests/test_happy_path.py::test_payin_card   PASSED  [ 5%]
tests/test_happy_path.py::test_payin_p2p    PASSED  [ 6%]
...
85 passed in 42.10s
```

Упавший тест:
```
FAILED tests/test_happy_path.py::test_payin_card
AssertionError: Expected 201, got 401: {"error":"invalid signature"}
```

Что смотреть:
- **Имя теста** — какой сценарий упал
- **Статус-код** (`got 401`) — что ответил сервер
- **Тело ответа** (`{"error":"invalid signature"}`) — конкретная причина

---

## 7. Частые ошибки и что с ними делать

---

### `Expected 201, got 401` или `403` — неверная авторизация

Проверьте файл `.env`:
- Правильный ли `SERVICE_SECRET`?
- Правильный ли `TERMINAL_ID`?

Также убедитесь, что время на вашей машине корректное — подпись включает текущее
время, и сервер отклоняет запросы с расхождением более 5 минут.

---

### `Expected 201, got 422` — невалидное тело запроса

API вернул ошибку валидации. Ответ содержит причину:
```
AssertionError: Expected 201, got 422: {"error": "invalid pan format"}
```
Читайте текст ошибки — там написано, что именно не так.
Проверьте `CARD_DETAILS`, `MERCHANT_DATA` в `tests/conftest.py`.

---

### `Expected 201, got 404` — неверный URL или нет доступа

Проверьте `_API_BASE` в `tests/conftest.py` и доступность препрода (VPN).

---

### `ERROR at setup` на тестах `test_recurrent` / `test_rebill` / `test_refund` / операциях

```
ERROR tests/test_happy_path.py::test_recurrent - AssertionError: Setup Payin failed: ...
```

Перед этими тестами автоматически выполняется Payin, и он упал.
Сначала запустите базовый тест отдельно:
```
pytest tests/test_happy_path.py::test_payin_card -v --tb=long
```
Исправьте причину его падения — остальные тесты тоже заработают.

---

### `ConnectionError` или `Timeout`

Нет сети или нет доступа к препроду. Проверьте подключение / VPN.

---

### Тест упал, хочу увидеть полный ответ API

Запустите с флагами `-s --tb=long`:
```
pytest tests/test_happy_path.py::test_payin_card -s --tb=long
```

Или добавьте в тест временный `print` и запустите с `-s`:
```python
resp = post_transaction(body)
print(resp.status_code, resp.text)  # временно для отладки
assert_success(resp)
```
