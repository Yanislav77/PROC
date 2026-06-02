# PROC — CORE REST API Test Suite

Интеграционные тесты для CORE REST API платёжного шлюза.
Тесты делают реальные HTTP-запросы к препрод-окружению — никаких моков.

**1200+ тестов** в 31 файле, покрывают все эндпоинты API.

---

## Содержание

1. [Установка с нуля](#1-установка-с-нуля)
2. [Получить свежие изменения](#2-получить-свежие-изменения)
3. [Что и где настраивать](#3-что-и-где-настраивать)
   - [Секрет и ID терминала → `.env`](#секрет-и-id-терминала--файл-env)
   - [Разные терминалы → `terminals.json`](#разные-терминалы-для-разных-файлов-тестов--terminalsjson)
   - [Данные карты, клиента, мерчанта](#данные-карты-клиента-мерчанта--tests_helperspayloadspy)
   - [Суммы и валюты](#суммы-и-валюты--конкретный-файл-теста)
   - [URL API](#url-api--tests_helpersconfigpy)
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
- `TERMINAL_ID` — ID вашего терминала. Используется по умолчанию для **всех** тестов (если не переопределён в `terminals.json`).

> `.env` не попадает в git, секрет виден только у вас локально.

---

### Разные терминалы для разных файлов тестов → `terminals.json`

По умолчанию все тесты используют `TERMINAL_ID` и `SERVICE_SECRET` из `.env`.
Если для отдельных файлов нужен другой терминал — создайте файл `terminals.json` в корне проекта:

```
copy terminals.json.example terminals.json
```

Откройте `terminals.json` и укажите нужные значения:

```json
{
    "payin/test_3ds.py": {
        "TERMINAL_ID": "3649",
        "SERVICE_SECRET": "секрет_другого_терминала"
    },
    "general/test_auth.py": {
        "TERMINAL_ID": "9999",
        "SERVICE_SECRET": "ещё_один_секрет"
    }
}
```

**Ключи** — пути к файлам тестов относительно папки `tests/`, через косую черту `/`.

Полный список возможных ключей:

| Ключ | Что тестирует |
|---|---|
| `payin/test_card.py` | Оплата картой |
| `payin/test_3ds.py` | 3DS-аутентификация |
| `payin/test_p2p.py` | P2P-переводы |
| `payin/test_qr.py` | QR-оплата |
| `payin/test_mobile.py` | Мобильные платежи (payin) |
| `payin/test_token.py` | Токенизированные карты (payin) |
| `payin/test_rebill_block.py` | Block/Rebill (двухстадийные и рекуррентные) |
| `payout/test_card.py` | Выплата на карту |
| `payout/test_token.py` | Выплата по токену |
| `payout/test_mobile.py` | Выплата на мобильный |
| `payout/test_sbp.py` | Выплата по СБП |
| `payout/test_wallet.py` | Выплата на кошелёк |
| `payout/test_bank_account.py` | Выплата на банковский счёт |
| `payout/test_validation.py` | Валидация полей payout |
| `operations/test_capture.py` | Подтверждение (capture) |
| `operations/test_cancel.py` | Отмена (cancel) |
| `operations/test_refund.py` | Возврат (refund) |
| `operations/test_confirm.py` | Подтверждение 3DS |
| `operations/test_confirm_user_action.py` | Подтверждение user-action (P2P, redirect и др.) |
| `general/test_auth.py` | Авторизация и подпись |
| `general/test_customer_data.py` | Данные клиента |
| `general/test_get_transactions.py` | Получение транзакций |
| `general/test_merchant.py` | Мерчант API |
| `general/test_payment_links.py` | Платёжные ссылки |
| `general/test_subscriptions.py` | Подписки |

> Тесты в `web_form/` используют отдельную авторизацию (`CUSTOMER_MAC_KEY`) и не управляются через `terminals.json`.

**Пример: один основной терминал + отдельный для 3DS**

`.env`:
```
TERMINAL_ID=1111
SERVICE_SECRET=основной_секрет
DB_HOST=...
```

`terminals.json`:
```json
{
    "payin/test_3ds.py": {
        "TERMINAL_ID": "3649",
        "SERVICE_SECRET": "секрет_3ds_терминала"
    }
}
```

Все тесты, кроме `test_3ds.py`, будут использовать терминал `1111`. `test_3ds.py` — терминал `3649`.

**Правила:**
- Файлы, которых нет в `terminals.json`, используют дефолтные креды из `.env`
- Если одно из полей (`TERMINAL_ID` или `SERVICE_SECRET`) оставить пустым — будет использовано дефолтное значение из `.env`
- Переопределение действует на весь файл целиком: все тесты внутри него пойдут с указанным терминалом
- Подмена происходит автоматически перед каждым тестом и восстанавливается после — другие тесты не затрагиваются

> `terminals.json` не попадает в git (он в `.gitignore`) — секреты видны только локально.
> Структура файла описана в `terminals.json.example`.

---

### Данные карты, клиента, мерчанта → `tests/_helpers/payloads.py`

Откройте `tests/_helpers/payloads.py`. Там словари с тестовыми данными, которые используются во всех файлах тестов:

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

### URL API → `tests/_helpers/config.py`

```python
_API_BASE            = "https://papiv3preprod.testpaygate.com/api/v1"
BASE_URL             = f"{_API_BASE}/transactions"
SUBSCRIPTIONS_URL    = f"{_API_BASE}/subscriptions"
PAYMENT_LINKS_URL    = "https://web3preprod.testpaygate.com/api/v1/payment-links"
MERCHANT_BALANCE_URL = f"{_API_BASE}/merchant/balance"
```

Чтобы переключиться на другой стенд — измените только строку `_API_BASE`, все URL обновятся автоматически.

---

## 4. Как запускать тесты

### Через PyCharm (проще всего)

В правом верхнем углу PyCharm есть выпадающий список конфигураций.
Там готовы варианты для каждого файла тестов:

| Конфигурация | Папка / файл |
|---|---|
| **All Tests** | `tests/` |
| **Payin** | `tests/payin/` |
| **Payin Card** | `tests/payin/test_card.py` |
| **Payout** | `tests/payout/` |
| **Operations** | `tests/operations/` |
| **Capture** | `tests/operations/test_capture.py` |
| **Cancel** | `tests/operations/test_cancel.py` |
| **Confirm** | `tests/operations/test_confirm.py` |
| **Refund** | `tests/operations/test_refund.py` |
| **Auth** | `tests/general/test_auth.py` |
| **Get Transactions** | `tests/general/test_get_transactions.py` |
| **Payment Links** | `tests/general/test_payment_links.py` |
| **Merchant** | `tests/general/test_merchant.py` |
| **Subscriptions** | `tests/general/test_subscriptions.py` |

Выберите нужный → нажмите ▶.

Также можно кликнуть правой кнопкой на любом файле или функции в боковой панели
и выбрать **Run**.

### Через терминал

```bash
# все тесты
pytest

# папка целиком
pytest tests/payin/
pytest tests/payout/
pytest tests/operations/
pytest tests/web_form/

# один файл
pytest tests/operations/test_refund.py
pytest tests/operations/test_capture.py
pytest tests/payin/test_card.py
pytest tests/payin/test_rebill_block.py

# один конкретный тест по имени функции
pytest tests/operations/test_refund.py::test_refund_partial
pytest tests/operations/test_capture.py::test_capture_full

# параметризованный тест — нужен node-id с параметром в квадратных скобках
pytest "tests/general/test_customer_data.py::test_browser_info_optional_field_missing[accept_header]"

# по ID тест-кейса (маркер @pytest.mark.tcid)
pytest -k "RF-001"
pytest -k "CAP-031"
pytest -k "RB-022"
pytest -k "CD-082"

# остановиться на первой ошибке
pytest -x

# подробный вывод (имена всех тестов)
pytest -v

# показать print/HTTP-вывод внутри тестов
pytest -s

# полный traceback при падении
pytest --tb=long

# комбинация флагов
pytest tests/operations/test_refund.py -v -s --tb=long
```

#### Параметризованные тесты

Некоторые тесты в `test_customer_data.py` параметризованы — один тест-метод
запускается с несколькими наборами данных и получает отдельный ID кейса для каждого параметра.
Например, `test_browser_info_optional_field_missing` запускается 9 раз (CD-082…CD-110).

Node-id такого теста выглядит как:
```
tests/general/test_customer_data.py::test_browser_info_optional_field_missing[accept_header]
```

Чтобы запустить только нужный параметр:
```bash
pytest "tests/general/test_customer_data.py::test_browser_info_optional_field_missing[language]"
```

---

## 5. Что делают тесты

Каждый тест помечен уникальным идентификатором вида `@pytest.mark.tcid("XX-NNN")`.
Этот ID отображается в HTML-отчёте (папка `reports/`).

Структура тестов:
```
tests/
├── conftest.py                        — общие фикстуры и хелперы
├── _helpers/                          — вспомогательные модули
│   ├── config.py                      — URL, таймауты, суммы по умолчанию
│   ├── payloads.py                    — CARD_DETAILS, MERCHANT_DATA, CUSTOMER_DATA
│   ├── factories.py                   — make_block_payin, make_completed_payin и др.
│   ├── http_client.py                 — post_transaction, post_operation, get_request
│   ├── signatures.py                  — HMAC-подпись запросов
│   └── validators.py                  — assert_transaction_response, assert_error_response
├── payin/                             — входящие платежи
│   ├── test_card.py                   — карточные Payin (PC-xxx)
│   ├── test_3ds.py                    — 3DS-флоу (3DS-xxx)
│   ├── test_p2p.py                    — метод p2p (P2P-xxx)
│   ├── test_qr.py                     — метод qr (QR-xxx)
│   ├── test_mobile.py                 — метод mobile (MOB-xxx)
│   ├── test_token.py                  — метод token (PT-xxx)
│   └── test_rebill_block.py           — block/rebill (RB-xxx)
├── payout/                            — выплаты (PY-xxx)
│   ├── test_card.py
│   ├── test_token.py
│   ├── test_mobile.py
│   ├── test_sbp.py
│   ├── test_wallet.py
│   ├── test_bank_account.py
│   └── test_validation.py             — общая валидация полей
├── operations/                        — операции над транзакциями
│   ├── test_capture.py                — списание (CAP-xxx)
│   ├── test_cancel.py                 — отмена (CAN-xxx)
│   ├── test_confirm.py                — подтверждение 3DS/redirect (CON-xxx)
│   ├── test_confirm_user_action.py    — подтверждение user-action (CON-xxx)
│   └── test_refund.py                 — возврат (RF-xxx)
├── general/                           — общие сценарии
│   ├── test_auth.py                   — авторизация (A-xxx)
│   ├── test_get_transactions.py       — GET статус (GT-xxx)
│   ├── test_customer_data.py          — данные клиента (CD-xxx)
│   ├── test_payment_links.py          — платёжные ссылки (PL-xxx)
│   ├── test_merchant.py               — баланс мерчанта (MB-xxx)
│   └── test_subscriptions.py          — подписки (SB-xxx)
└── web_form/                          — Web Form API (payment-sessions)
    ├── test_session.py                — GET сессии (GP-xxx)
    ├── test_session_bin.py            — BIN-lookup (BI-xxx)
    ├── test_session_phone.py          — lookup по телефону (PH-xxx)
    ├── test_session_transactions.py   — submit card/cardless (TX-xxx, CL-xxx)
    ├── test_session_ui.py             — UI-логи и события (UL-xxx, UE-xxx)
    └── test_session_ws.py             — WebSocket (WS-xxx)
```

---

### `general/test_auth.py` — авторизация и подпись запросов (25 тестов, A-001…A-025)

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

### `payin/test_card.py` — Payin картой (171 тест, PC-001…PC-171)

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

### `payin/test_3ds.py` — 3DS-флоу (1 тест, 3DS-001)

Использует карту с CVV 550, которая инициирует `waiting_action` с редиректом.

| Сценарий | Ожидаемый статус |
|---|---|
| redirect URL в ответе не закодирован URL-encode | 200 |

---

### `payin/test_p2p.py`, `test_qr.py`, `test_mobile.py`, `test_token.py` — Payin другими методами

Payin через P2P, QR-код, мобильный платёж и токен (rebill).

| Метод | Тестов | Примеры сценариев |
|---|---|---|
| p2p | 48 | happy path, manual capture, с description, нулевая сумма → 400 |
| qr | 45 | happy path, is_recurrent=True, отрицательная сумма → 400, action в ответе |
| mobile | 61 | phone обязателен, формат E.164, provider опционален, phone=null → 400 |
| token | 52 | token — UUID, отсутствие parent_transaction_id, несуществующий UUID |

---

### `payin/test_rebill_block.py` — Block и Rebill (27 тестов, RB-001…RB-030)

Двухстадийные (block/capture) и рекуррентные (rebill) транзакции.

| Группа | Сценарии |
|---|---|
| Базовые комбинации | auto→auto rebill, auto→manual rebill + capture, manual + capture→rebill |
| Частичный capture | partial capture (часть суммы), 10× по 100 = 1000 → completed |
| Частичный cancel | 10× по 100 = 1000 → cancelled |
| Смешанные операции | cancel 300 → capture 700 → completed; capture 300 → cancel 700 → completed |
| Негативные | capture > авторизованной суммы → 4xx; cancel после full capture → 409 |
| Негативные | cancel auto-capture транзакции → 409; cancel amount=0 → 400; банк отказывает capture → 4xx |
| Токены | recurrent_token является UUID v4; is_recurrent=false → withdrawal_token |
| Цепочки | token1 → token2 → rebill; токен другого терминала → 403/404 |

---

### `payout/` — Выплаты (141 тест, PY-001…PY-119)

Покрывает все методы выплат: карта, SBP, кошелёк, банковский счёт, мобильный, токен, валидация.

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

### `general/test_customer_data.py` — Данные клиента (231 тест, CD-001…CD-251)

Детальная валидация всех полей `customer_data`: контакты, персональные данные, данные браузера, паспортные данные. Граничные значения, форматы, обязательность полей.

Многие тесты параметризованы — проверяют одно правило сразу по нескольким полям.
Например, тест `test_browser_info_optional_field_missing` запускается 9 раз:
по одному для каждого необязательного поля `browser_info`.

| Группа | Примеры сценариев |
|---|---|
| Обязательные поля | CD-001…CD-020: отсутствие type, financial_data, flow_data и т.д. |
| browser_info | CD-082…CD-110: необязательные поля — каждое можно опустить |
| contact | CD-120…CD-149: email, phone, имя — обязательность и форматы |
| personal | CD-168…CD-195: birth_date, gender, nationality — форматы |
| document_details | CD-205…CD-251: тип документа, номер, даты |

---

### `general/test_get_transactions.py` — Получение транзакций (50 тестов, GT-001…GT-050)

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

### `operations/test_capture.py` — Списание заблокированных средств (32 теста, CAP-001…CAP-032)

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
| description в ответе — из запроса capture, не из родительской транзы | 200 / 201 |

---

### `operations/test_cancel.py` — Отмена транзакции (33 теста, CAN-001…CAN-033)

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
| description в ответе — из запроса cancel, не из родительской транзы | 200 / 201 |

---

### `operations/test_confirm.py` — Подтверждение ожидающего действия (66 тестов, CON-001…CON-075)

POST `/api/v1/transactions/{id}/confirm` — используется после 3DS или redirect.

| Группа | Сценарии | Ожидаемый статус |
|---|---|---|
| Негативные | Несуществующая транзакция | 404 |
| Негативные | Отсутствует `result`, `financial_data`, `merchant_data` | 400 |
| Негативные | Неизвестный тип result | 400 |
| Негативные | 3DS: отсутствует `pares` или `md` | 400 |
| Негативные | Пустое тело / невалидный JSON / JSON-массив | 400 |
| Структура | `result.type` = null, пустой `result` | 400 |
| Структура | `pares` или `md` — только пробелы | 400 |
| Структура | `amount` — строка или float; `currency` — нижний регистр | 400 |
| Структура | `order_id` — пустая строка или null | 400 |
| Структура | `transaction_id` в теле vs path — path побеждает | 404 |
| Авторизация | Подпись из нулей / от другого тела / неверный терминал | 401 / 403 |
| Авторизация | Timestamp старый / будущий / нечисловой / float | 400 / 401 |
| Авторизация | `Api-Terminal-ID` нечисловой; отсутствует idempotency key | 400 / 401 / 403 |
| Методы | GET / PUT вместо POST | 404 / 405 |
| Идемпотентность | Одинаковый ключ, разное тело — кэшированный ответ | 200 / 409 |
| Happy path | 3DS success — статус processing | 200 |
| Happy path | 3DS-redirect success — статус processing | 200 |
| Happy path | 3DS-redirect неверный тип → 4xx | 400 |
| Ответ | Обязательные поля присутствуют, created_at ISO-8601 UTC | 200 |
| Ответ | Нет внутренних полей (schema leakage) | — |
| Ответ | `transaction_id` в ответе = path-параметру | 200 |
| Ответ | `created_at` в ответе = `created_at` оригинальной транзакции | 200 |
| Ответ | Echo заголовков `Api-Terminal-ID` / `Api-Idempotency-Key` | 200 |

---

### `operations/test_confirm_user_action.py` — Подтверждение user-action (3 теста, CON-046…CON-048)

POST `/api/v1/transactions/{id}/confirm` для транзакций в статусе `waiting_action`.
Достигается через P2P (method=p2p).

| Тип подтверждения | Сценарии |
|---|---|
| transfer_card | подтверждение / отклонение P2P-перевода |
| redirect | подтверждение / отклонение редиректа |
| transfer_phone, transfer_qr, transfer_account, top_up_mobile | аналогично |

---

### `operations/test_refund.py` — Возвраты (48 тестов, RF-001…RF-036+)

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
| description в ответе — из запроса refund, не из родительской транзы | 200 / 201 |

---

### `general/test_payment_links.py` — Платёжные ссылки (62 теста, PL-001…PL-061)

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

### `general/test_merchant.py` — Баланс мерчанта (25 тестов, MB-001…MB-025)

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

### `general/test_subscriptions.py` — Управление подписками (37 тестов, SB-001…SB-039)

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

### `web_form/` — Web Form API (132 теста)

Тесты API веб-формы платёжной сессии (`https://web3preprod.testpaygate.com`).
Используют отдельную авторизацию: `Api-Session-ID` + HMAC-SHA256 по `CUSTOMER_MAC_KEY`.

| Файл | ID | Что тестирует |
|---|---|---|
| `test_session.py` | GP-001…GP-014 | GET `/api/v1/payment-sessions/{token}` — получение сессии |
| `test_session_bin.py` | BI-001…BI-016 | POST `.../bin` — BIN-lookup по номеру карты |
| `test_session_phone.py` | PH-001…PH-018 | POST `.../phone` — lookup страны по номеру телефона |
| `test_session_transactions.py` | TX-001…TX-023, CL-001…CL-021 | POST `.../transactions/card` и `.../cardless` — сабмит платежа |
| `test_session_ui.py` | UL-001…UL-014, UE-001…UE-014 | POST `.../ui/logs` и `.../ui/events` — UI-логи и события |
| `test_session_ws.py` | WS-001…WS-012 | GET `.../ws` — WebSocket-соединение |

| Сценарии (общие для web_form) | Ожидаемый результат |
|---|---|
| Несуществующий / невалидный payment_token | 400 / 404 |
| Отсутствует Api-Session-ID или Api-Signature | 400 / 401 |
| Неверная подпись | 401 |
| Обязательные поля ответа присутствуют | 200 / 201 |
| Повторный сабмит (double_confirmation) | 200, пустое тело |
| WS: подключение, получение состояния, push 3DS_method | соответствующие WS-фреймы |

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
tests/payin/test_card.py::test_payin_card_auto_capture   PASSED
...
1273 passed in 640.15s
```

Упавший тест:
```
FAILED tests/payin/test_card.py::test_payin_card_auto_capture
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
Проверьте `CARD_DETAILS`, `MERCHANT_DATA` в `tests/_helpers/payloads.py`.

---

### `Expected 201, got 404` — неверный URL или нет доступа

Проверьте `_API_BASE` в `tests/_helpers/config.py` и доступность препрода (VPN).

---

### `ERROR at setup` на тестах с fixture `payin_transaction_id` или `payin_block_transaction_id`

```
ERROR tests/payin/test_token.py::test_payin_token_rebill - AssertionError: Setup Payin failed: ...
```

Перед этими тестами автоматически выполняется Payin, и он упал.
Сначала запустите базовый тест отдельно:
```
pytest tests/payin/test_card.py::test_payin_card_auto_capture -v --tb=long
```
Исправьте причину его падения — остальные тесты тоже заработают.

---

### `ConnectionError` или `Timeout`

Нет сети или нет доступа к препроду. Проверьте подключение / VPN.

---

### Тест упал, хочу увидеть полный ответ API

Запустите с флагами `-s --tb=long`:
```
pytest tests/payin/test_card.py::test_payin_card_auto_capture -s --tb=long
```

Или откройте HTML-отчёт в `reports/` — там уже есть полный HTTP-запрос и ответ для каждого теста.

---

### Тесты работают слишком медленно

Между тестами есть задержка (защита от rate-limiting препрода).
Управляется через переменные окружения или `.env`:

```
TEST_DELAY=1.0    # пауза между тестами, секунд (по умолчанию 3.0)
SETUP_DELAY=0.5   # пауза после создания родительской транзакции (по умолчанию 1.0)
```

Пример запуска с уменьшенной задержкой:
```
TEST_DELAY=1.0 pytest tests/general/test_merchant.py
```

или в `.env`:
```
TEST_DELAY=1.0
SETUP_DELAY=0.5
```
