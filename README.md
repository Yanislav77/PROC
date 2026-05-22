# PROC — CORE REST API Test Suite

Интеграционные тесты для CORE REST API платёжного шлюза.
Тесты делают реальные HTTP-запросы к препрод-окружению — никаких моков.

**821 тест** в 13 файлах, покрывают все эндпоинты API.

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

### Суммы и валюты → конкретный файл теста

Каждый тест содержит `financial_data` с суммой и валютой. Найдите нужный тест
и поменяйте прямо там. Сумма указывается в минимальных единицах: `10000` = 100.00 RUB.

---

### Токен для rebill → `tests/test_payin_other.py`

В тестах `test_payin_token_rebill` используется токен карты:

```python
"details": {"token": "b928586b-e6ec-4400-9039-e36f19c0094c"},
```

Это заглушка. Замените на реальный токен, который вернул API в ответе на Payin с `is_recurrent=True`.

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

| Конфигурация | Файл | Тестов |
|---|---|---|
| **All Tests** | все файлы | 821 |
| **Auth** | `test_auth.py` | 25 |
| **Payin Card** | `test_payin_card.py` | 165 |
| **Payin Other** | `test_payin_other.py` | 30 |
| **Payout** | `test_payout.py` | 120 |
| **Customer Data** | `test_customer_data.py` | 250 |
| **Get Transactions** | `test_get_transactions.py` | 30 |
| **Capture** | `test_capture.py` | 30 |
| **Cancel** | `test_cancel.py` | 30 |
| **Confirm** | `test_confirm.py` | 32 |
| **Refund** | `test_refund.py` | 35 |
| **Payment Links** | `test_payment_links.py` | 38 |
| **Merchant** | `test_merchant.py` | 18 |
| **Subscriptions** | `test_subscriptions.py` | 18 |

Выберите нужный → нажмите ▶.

Также можно кликнуть правой кнопкой на любом файле или функции в боковой панели
и выбрать **Run**.

### Через терминал

```bash
# все тесты
pytest

# один файл
pytest tests/test_payin_card.py
pytest tests/test_payout.py

# один конкретный тест
pytest tests/test_payin_card.py::test_payin_card_auto_capture

# по ID тест-кейса (маркер @pytest.mark.tcid)
pytest -k "PC-001"

# остановиться на первой ошибке
pytest -x

# полный вывод при падении
pytest --tb=long

# показать HTTP-запросы и ответы внутри тестов
pytest -s
```

---

## 5. Что делают тесты

Каждый тест помечен уникальным идентификатором вида `@pytest.mark.tcid("XX-NNN")`.
Этот ID отображается в HTML-отчёте (папка `reports/`).

---

### `test_auth.py` — авторизация и подпись запросов (25 тестов, A-001…A-025)

Проверяют механизм HMAC-SHA256 подписи и заголовки авторизации.

| Сценарий | Ожидаемый статус |
|---|---|
| Корректный запрос проходит | 201 |
| Дублирующий `Api-Idempotency-Key` | 409 |
| Подпись из нулей | 401 / 403 |
| Отсутствует `Api-Terminal-ID` | 400 / 401 / 403 |
| Отсутствует `Api-Timestamp` | 400 / 401 / 403 |
| Timestamp старше 5 минут | 400 |
| Timestamp в будущем на 5+ минут | 400 |
| Неизвестный терминал | 401 / 403 / 404 |
| Пустой `Api-Signature` | 401 / 403 |

---

### `test_payin_card.py` — Payin картой (165 тестов, PC-001…PC-165)

Самый большой файл. Покрывает создание транзакций через карту: happy path, валидация полей карты, параметры потока (`capture_mode`, `is_recurrent`, `threed_secure`), граничные значения сумм и форматов.

| Группа | Примеры сценариев |
|---|---|
| Happy path | auto-capture, manual-capture, рекуррентный Payin |
| Карта | невалидный PAN, истёкшая карта, отсутствие cvv/holder/expiry |
| financial_data | нулевая/отрицательная сумма, неверная валюта |
| flow_data | неверный capture_mode, отсутствие threed_secure |
| customer_data | обязательные поля, форматы |
| Ответ | transaction_id — int, status в допустимом множестве, created_at ISO 8601 |

---

### `test_payin_other.py` — Payin другими методами (30 тестов, PO-001…PO-030)

Payin через P2P, QR-код, мобильный платёж и токен (rebill).

| Метод | Примеры сценариев |
|---|---|
| p2p | happy path, manual capture, с description, нулевая сумма → 400 |
| qr | happy path, is_recurrent=True, отрицательная сумма → 400, action в ответе |
| mobile | phone обязателен, формат E.164, provider опционален, phone=null → 400 |
| token | token — UUID, отсутствие parent_transaction_id, несуществующий UUID |

---

### `test_payout.py` — Выплаты (120 тестов, PY-001…PY-120)

Покрывает все методы выплат: карта, SBP, кошелёк, банковский счёт, мобильный, токен.

| Метод | Примеры сценариев |
|---|---|
| card | happy path, без expiry, PAN/holder/cvv обязательны |
| sbp | с phone+bank, без details, с holder → 201 |
| wallet | id обязателен, с brand |
| bank_account | SWIFT, PIX (Бразилия), без details |
| mobile | phone обязателен, E.164 |
| token | token обязателен |
| Общие негативные | нулевая/отрицательная сумма, неверная валюта, null поля → 400 |

---

### `test_customer_data.py` — Данные клиента (250 тестов, CD-001…CD-250)

Детальная валидация всех полей `customer_data`: контакты, персональные данные, данные браузера, паспортные данные. Граничные значения, форматы, обязательность полей.

---

### `test_get_transactions.py` — Получение транзакций (30 тестов, GT-001…GT-030)

GET `/api/v1/transactions/{id}` и GET `/api/v1/transactions?order_id=`.

| Сценарий | Ожидаемый статус |
|---|---|
| GET по существующему ID | 200 |
| GET по несуществующему ID | 404 |
| GET по order_id — массив в ответе | 200 |
| GET по несуществующему order_id | 404 |
| Без параметра order_id | 400 / 422 |
| Без авторизации / неверная подпись | 400 / 401 / 403 |
| PAN и CVV не возвращаются в ответе | 200 |
| masked_pan в нужном формате | 200 |
| transaction_id — int, created_at в полях | 200 |

---

### `test_capture.py` — Списание заблокированных средств (30 тестов, CAP-001…CAP-030)

POST `/api/v1/transactions/{id}/capture`.

| Сценарий | Ожидаемый статус |
|---|---|
| Списание после Payin manual-capture | 200 / 201 |
| Частичное списание | 200 / 201 |
| Несуществующая транзакция | 404 |
| Дублирующий idempotency key | 409 |
| Отсутствует idempotency key | 400 |
| Отсутствуют обязательные поля | 400 / 422 |
| Нулевая / отрицательная сумма | 400 / 422 |
| Auto-capture Payin → повторный capture | 409 |
| Ответ содержит merchant_data, created_at | 200 / 201 |

---

### `test_cancel.py` — Отмена транзакции (30 тестов, CAN-001…CAN-030)

POST `/api/v1/transactions/{id}/cancel`.

| Сценарий | Ожидаемый статус |
|---|---|
| Отмена Payin с холдом | 200 / 201 |
| С необязательным description | 200 / 201 |
| Несуществующая транзакция | 404 |
| Дублирующий idempotency key | 409 |
| Отсутствует idempotency key | 400 |
| Auto-capture Payin → cancel | 409 |
| Пустые financial_data / merchant_data | 400 |

---

### `test_confirm.py` — Подтверждение ожидающего действия (32 теста, CON-001…CON-032)

POST `/api/v1/transactions/{id}/confirm` — используется после 3DS или redirect.

| Сценарий | Ожидаемый статус |
|---|---|
| Несуществующая транзакция | 404 |
| Отсутствует поле result | 400 / 422 |
| Неизвестный тип result | 400 / 422 |
| 3DS: отсутствует pares или md | 400 / 422 |
| redirect: отсутствует confirmed | 400 / 422 |
| Дублирующий idempotency key | 409 |
| result.type = null | 400 |
| pares = пустая строка | 400 |
| Пустые financial_data | 400 |

---

### `test_refund.py` — Возвраты (35 тестов, RF-001…RF-035)

POST `/api/v1/transactions/{id}/refund`.

| Сценарий | Ожидаемый статус |
|---|---|
| Частичный возврат | 200 / 201 |
| Полный возврат | 200 / 201 |
| Сумма превышает оригинал | 400 / 422 |
| Несуществующая транзакция | 404 |
| Возврат по отменённой транзакции | 409 |
| Возврат по Payout | 409 |
| Несоответствие валюты | 400 / 409 |
| Дублирующий idempotency key | 409 |
| Отсутствует idempotency key | 400 |
| amount = null | 400 |
| Минимальная сумма = 1 | 200 / 201 |

---

### `test_payment_links.py` — Платёжные ссылки (38 тестов, PL-001…PL-038)

POST `/api/v1/payment-links`.

| Сценарий | Ожидаемый статус |
|---|---|
| Создание ссылки, обязательные поля ответа | 201 |
| С flow_data (is_recurrent, capture_mode) | 201 |
| Без webhook_url / return_url | 201 |
| Отсутствие обязательного поля | 400 |
| Отрицательная / нулевая сумма | 400 |
| Неверная валюта / capture_mode | 400 |
| Без авторизации / неверная подпись | 400 / 401 / 403 |
| Дублирующий idempotency key | 409 |
| Отсутствует idempotency key | 400 |
| return_url с query-параметрами | 201 |
| link_data.url — строка, начинается с http | 201 |
| financial_data = null | 400 |

---

### `test_merchant.py` — Баланс мерчанта (18 тестов, MB-001…MB-018)

GET `/api/v1/merchant/balance`.

| Сценарий | Ожидаемый статус |
|---|---|
| Получение баланса, обязательные поля | 200 |
| currency — 3-символьный ISO-код | 200 |
| POST / DELETE вместо GET | 404 / 405 |
| Без авторизации / неверная подпись | 400 / 401 / 403 |
| Истёкший timestamp | 400 / 401 / 403 |
| Idempotency key игнорируется (GET) | 200 |

---

### `test_subscriptions.py` — Управление подписками (18 тестов, SB-001…SB-018)

DELETE `/api/v1/subscriptions/{token}`.

| Сценарий | Ожидаемый статус |
|---|---|
| DELETE по несуществующему UUID | 404 |
| Токен не в формате UUID | 400 / 404 |
| Слишком короткий / числовой токен | 400 / 404 |
| UUID с заглавными буквами | 400 / 404 |
| Без авторизации / неверная подпись | 400 / 401 / 403 |
| POST / GET вместо DELETE | 404 / 405 |
| Лишний сегмент URL | 400 / 404 / 405 |
| Content-Type ответа — application/json | 200 |
| Idempotency key не требуется (DELETE) | 404 / 409 |

---

## 6. Как читать результат

### HTML-отчёт (автоматически)

После каждого прогона в папке `reports/` создаётся HTML-файл вида
`2026-05-22_14-30-00_all.html`. Откройте его в браузере:
- Левая панель — список всех тестов с маркерами PASSED/FAILED и ID кейса
- Клик на тест — справа видны полный HTTP-запрос и ответ
- Первый упавший тест открывается автоматически

### В PyCharm

После запуска внизу открывается панель **Run**:
- Зелёный кружок — тест прошёл
- Красный крестик — тест упал
- Кликните на упавший тест — справа появится подробный вывод

### В терминале

Успешный прогон:
```
tests/test_payin_card.py::test_payin_card_auto_capture   PASSED
...
821 passed in 410.32s
```

Упавший тест:
```
FAILED tests/test_payin_card.py::test_payin_card_auto_capture
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

### `Expected 201, got 400` / `422` — невалидное тело запроса

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

### `ERROR at setup` на тестах с fixture `payin_transaction_id` или `payin_block_transaction_id`

```
ERROR tests/test_payin_other.py::test_payin_token_rebill - AssertionError: Setup Payin failed: ...
```

Перед этими тестами автоматически выполняется Payin, и он упал.
Сначала запустите базовый тест отдельно:
```
pytest tests/test_payin_card.py::test_payin_card_auto_capture -v --tb=long
```
Исправьте причину его падения — остальные тесты тоже заработают.

---

### `ConnectionError` или `Timeout`

Нет сети или нет доступа к препроду. Проверьте подключение / VPN.

---

### Тест упал, хочу увидеть полный ответ API

Запустите с флагами `-s --tb=long`:
```
pytest tests/test_payin_card.py::test_payin_card_auto_capture -s --tb=long
```

Или откройте HTML-отчёт в `reports/` — там уже есть полный HTTP-запрос и ответ для каждого теста.

---

### Тесты работают слишком медленно

Между тестами есть задержка 3 секунды (защита от rate-limiting препрода).
Изменить её можно через переменную окружения:

```
TEST_DELAY=1.0 pytest tests/test_merchant.py
```

или в `.env`:
```
TEST_DELAY=1.0
```
