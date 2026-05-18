# PROC — CORE REST API Test Suite

Интеграционные тесты для CORE REST API платёжного шлюза (препрод-окружение).
Тесты делают реальные HTTP-запросы к API — мокирования нет.

---

## Содержание

1. [Первый запуск — с нуля](#первый-запуск--с-нуля)
2. [Структура проекта](#структура-проекта)
3. [Как это работает — архитектура за 5 минут](#как-это-работает--архитектура-за-5-минут)
4. [Конфигурация перед запуском](#конфигурация-перед-запуском)
5. [Запуск тестов](#запуск-тестов)
5. [Как читать вывод pytest](#как-читать-вывод-pytest)
6. [Файл conftest.py — общий фундамент](#файл-conftestpy--общий-фундамент)
7. [Позитивные тесты — test_happy_path.py](#позитивные-тесты--test_happy_pathpy)
8. [Негативные тесты — test_negative.py](#негативные-тесты--test_negativepy)
9. [Как изменить тесты](#как-изменить-тесты)
10. [Диагностика ошибок](#диагностика-ошибок)

---

## Первый запуск — с нуля

Если вы никогда не работали с Python и PyCharm — следуйте этим шагам по порядку.

---

### Шаг 1 — Установить Python

1. Откройте https://www.python.org/downloads/ и скачайте последнюю версию для Windows
2. Запустите установщик
3. **Обязательно** поставьте галочку **"Add Python to PATH"** на первом экране
4. Нажмите "Install Now"
5. Проверьте установку: откройте PowerShell и введите `python --version` — должна появиться версия

---

### Шаг 2 — Открыть проект в PyCharm

1. Скачайте репозиторий:
   - Нажмите зелёную кнопку **Code** → **Download ZIP** на GitHub
   - Распакуйте в удобное место (например, `C:\Projects\PROC`)
   - Или клонируйте через Git: `git clone https://github.com/Yanislav77/PROC.git`
2. Откройте PyCharm
3. **File → Open** → выберите папку `PROC`

---

### Шаг 3 — Создать виртуальное окружение (venv)

Виртуальное окружение — изолированная копия Python для этого проекта.
Это нужно, чтобы установленные пакеты не конфликтовали с другими проектами.

1. В PyCharm: **File → Settings → Project: PROC → Python Interpreter**
2. Нажмите шестерёнку ⚙ → **Add Interpreter → Add Local Interpreter**
3. Выберите **Virtualenv Environment** → **New**
4. Путь оставьте как есть (PyCharm создаст папку `venv` внутри проекта)
5. Base interpreter — выберите только что установленный Python
6. Нажмите **OK**

---

### Шаг 4 — Установить зависимости

**Вариант А — через PyCharm (проще):**

Откройте файл `requirements.txt` в PyCharm.
В верхней части появится жёлтая плашка с кнопкой **Install requirements** — нажмите её.

**Вариант Б — через терминал:**

Откройте терминал в PyCharm (**View → Tool Windows → Terminal**) и выполните:
```
pip install -r requirements.txt
```

---

### Шаг 5 — Создать файл .env с секретом

В корне проекта есть файл `.env.example`. Создайте рядом файл `.env`:

**В терминале PyCharm:**
```
copy .env.example .env
```

Откройте `.env` и заполните:
```
SERVICE_SECRET=вставьте_сюда_реальный_секрет
TERMINAL_ID=374
```

> `.env` не попадает в git — он добавлен в `.gitignore`. Секрет остаётся только у вас локально.

---

### Шаг 6 — Настроить pytest в PyCharm

1. **File → Settings → Tools → Python Integrated Tools**
2. В поле **Default test runner** выберите **pytest**
3. Нажмите **OK**

---

### Шаг 7 — Запустить тесты

**Через готовые конфигурации (самый простой способ):**

В правом верхнем углу PyCharm есть выпадающий список с конфигурациями запуска.
После открытия проекта там появятся три готовых варианта:

- **All Tests** — запустить все тесты
- **Happy Path** — только позитивные тесты
- **Negative** — только негативные тесты

Выберите нужный и нажмите зелёную кнопку ▶.

**Через интерфейс файлов:**

В боковой панели (Project) откройте `tests/` → кликните правой кнопкой на
`test_happy_path.py` → **Run 'pytest in test_happy_path.py'**

**Через встроенный терминал:**
```
pytest
```

---

### Как читать результат в PyCharm

После запуска внизу откроется панель **Run**. Там:

- **зелёный кружок** — тест прошёл
- **красный крестик** — тест упал
- Кликните на упавший тест → справа появится подробный вывод с причиной

Пример упавшего теста:
```
FAILED test_payin_card
AssertionError: Expected 201, got 401: {"error": "invalid signature"}
```
Читаем: тест `test_payin_card` упал, сервер вернул 401 с сообщением "invalid signature" —
значит неверный `SERVICE_SECRET` в файле `.env`.

---

## Структура проекта

```
PROC/
├── pytest.ini               # настройки запуска pytest
├── requirements.txt         # зависимости Python
└── tests/
    ├── conftest.py          # конфиг, подпись, хелперы, общие данные, фикстуры
    ├── test_happy_path.py   # позитивные сценарии (все типы транзакций)
    └── test_negative.py     # негативные сценарии и граничные случаи
```

**`pytest.ini`** — говорит pytest искать тесты в папке `tests/` и включает флаги
`-v` (подробный вывод) и `--tb=short` (короткий traceback при падении).

**`requirements.txt`** — только два пакета: `pytest` и `requests`.

---

## Как это работает — архитектура за 5 минут

```
pytest
  └── собирает тесты из tests/
        ├── перед первым тестом загружает tests/conftest.py
        │     (BASE_URL, терминалы, секрет, хелперы, константы, фикстуры)
        ├── test_happy_path.py — позитивные тесты
        │     каждая функция test_* формирует тело запроса,
        │     вызывает post_transaction() → requests.post() → API
        │     и проверяет ответ через assert_success()
        └── test_negative.py — негативные тесты
              каждая функция намеренно ломает что-то одно,
              затем проверяет, что API вернул ожидаемый код ошибки
```

Каждый HTTP-запрос к API обязан содержать заголовки:

| Заголовок | Что содержит |
|---|---|
| `Content-Type` | `application/json` |
| `Api-Terminal-ID` | ID терминала (зависит от метода платежа) |
| `Api-Timestamp` | Unix-время в секундах на момент отправки |
| `Api-Signature` | HMAC-SHA256 подпись (см. ниже) |
| `Api-Idempotency-Key` | UUID v4, уникальный для каждого запроса |

### Формула подписи

```
HMAC-SHA256(
    key   = SERVICE_SECRET,
    input = "POST\n{Api-Terminal-ID}\n{Api-Timestamp}\n{raw_body}"
)
```

`raw_body` — это тело запроса в компактном JSON без пробелов
(например: `{"type":"payin","amount":100}`).
Результат — hex-строка из 64 символов, передаётся в `Api-Signature`.

---

## Конфигурация перед запуском

Все настройки хранятся в файле `.env` в корне проекта (см. Шаг 5 выше).
**Не редактируйте `conftest.py`** — он читает значения из `.env` автоматически.

```
SERVICE_SECRET=ваш_секрет   # секрет для подписи запросов
TERMINAL_ID=374              # ID вашего терминала
```

`BASE_URL` уже настроен на препрод в `conftest.py` и менять его не нужно:
```
https://papiv3preprod.testpaygate.com/api/v1/transactions
```

---

## Запуск тестов

**Из PyCharm** — см. Шаг 7 выше (через конфигурации или правый клик на файле).

**Из терминала:**

```bash
# все тесты
pytest

# только позитивные
pytest tests/test_happy_path.py

# только негативные
pytest tests/test_negative.py

# один конкретный тест
pytest tests/test_happy_path.py::test_payin_card

# остановиться на первой ошибке
pytest -x

# полный traceback вместо короткого
pytest --tb=long

# показать print() внутри тестов (полезно при отладке)
pytest -s
```

---

## Как читать вывод pytest

Пример успешного прогона:
```
tests/test_happy_path.py::test_payin_card      PASSED  [ 11%]
tests/test_happy_path.py::test_payin_p2p       PASSED  [ 22%]
...
tests/test_negative.py::test_missing_top_level_field[type]  PASSED
```

Пример падения:
```
FAILED tests/test_happy_path.py::test_payin_card
─────────────────── short test summary ───────────────────
AssertionError: Expected 201, got 401: {"error":"invalid signature"}
```

Что читать в первую очередь:
- **Статус-код** — `got 401` — запрос не прошёл авторизацию
- **Тело ответа** — `{"error":"invalid signature"}` — конкретная причина
- **Имя теста** — `test_payin_card` — какой сценарий упал

---

## Файл conftest.py — общий фундамент

`conftest.py` — это специальный файл pytest, который автоматически загружается
перед всеми тестами в папке. Здесь хранится всё общее.

### Константы-данные

```python
CUSTOMER_DATA   # полный объект покупателя: контакты, паспорт, браузер, payer_id
MERCHANT_DATA   # данные мерчанта: order_id, webhook_url, return_url, description
CARD_DETAILS    # данные карты: pan, holder, expiry_month/year, cvv
THREED          # параметры 3DS: {"challenge_window_size": "05"}
```

Эти константы импортируются в тест-файлы и подставляются в тела запросов.
Чтобы изменить тестовые данные (например, номер карты) — меняйте здесь,
и изменение применится ко всем тестам сразу.

### Функции

**`calc_signature(method, terminal_id, timestamp, raw_body)`**
Считает HMAC-SHA256 подпись. Вызывается внутри `make_headers()`.
Менять не нужно, если не меняется алгоритм подписи.

**`make_headers(terminal_id, raw_body, method="POST")`**
Собирает словарь всех заголовков запроса: подпись, таймстамп, idempotency key.
Каждый вызов генерирует новый UUID для `Api-Idempotency-Key`.

**`post_transaction(body, terminal_id=None)`**
Главный хелпер для отправки транзакции. Если `terminal_id` не передан —
используется `TERMINALS["default"]`. Сериализует тело, формирует заголовки,
отправляет POST на `BASE_URL`.

### Фикстура `payin_transaction_id`

```python
@pytest.fixture(scope="session")
def payin_transaction_id():
    ...
```

`scope="session"` означает, что фикстура выполняется **один раз за весь прогон**,
а не перед каждым тестом. Она делает реальный Payin card и возвращает его
`transaction_id`. Этот ID нужен тестам, которые требуют существующей транзакции:
`test_recurrent`, `test_rebill`, `test_rebill_block`, `test_refund`,
`test_refund_amount_exceeds_original`.

Если этот Payin упадёт — все зависящие от него тесты пропустятся с ошибкой
`ERROR at setup`. Это нормально: проблема в сетапе, не в самих тестах.

---

## Позитивные тесты — test_happy_path.py

### Хелпер `assert_success(resp, expected_type)`

Вызывается в каждом позитивном тесте. Проверяет:
1. HTTP статус == `201`
2. В теле ответа есть поля: `transaction_id`, `type`, `status`,
   `merchant_data`, `financial_data`, `created_at`
3. Если передан `expected_type` — поле `type` в ответе совпадает с ним
4. В заголовках ответа есть `Api-Terminal-ID` и `Api-Idempotency-Key`

Возвращает распарсенный JSON ответа, чтобы тест мог делать дополнительные проверки.

---

### test_payin_card

**Что проверяет:** базовый Payin картой с автоматическим списанием.

**Терминал:** `default` (374)

**Ключевые поля запроса:**
- `flow_data.is_recurrent = True` — разрешает сохранить данные карты для будущих рекуррентных платежей
- `flow_data.capture_mode = "auto"` — деньги списываются сразу
- `transaction_data.method = "card"` — метод оплаты: карта
- `financial_data.amount = 10000` — сумма в минимальных единицах (10000 = 100.00 RUB)

**Дополнительные проверки:** сумма и валюта в ответе совпадают с запросом.

---

### test_payin_p2p

**Что проверяет:** Payin через P2P-перевод.

**Терминал:** `p2p` (502) — у P2P обязательно свой терминал, иначе API вернёт ошибку.

**Отличие от card:** в `transaction_data` нет `details` (не нужны данные карты),
метод — `"p2p"`.

---

### test_payin_mobile

**Что проверяет:** Payin через мобильный платёж.

**Терминал:** `mobile` (503)

**Особенность:** в `transaction_data.details` передаётся номер телефона.
Валюта — `CAD` (отличается от остальных тестов, чтобы охватить ещё одну валюту).

---

### test_payin_block

**Что проверяет:** блокировку (холд) средств без немедленного списания.

**Терминал:** `default` (374)

**Ключевое отличие от `test_payin_card`:**
- `flow_data.capture_mode = "manual"` — средства блокируются, но не списываются.
  Для списания нужен отдельный запрос на подтверждение (capture).

**Дополнительная проверка статуса:** ожидается `processing`, `authorized` или `pending`
(не `completed` / `success`, потому что деньги ещё не списаны).

---

### test_recurrent

**Что проверяет:** рекуррентный платёж по сохранённым данным предыдущей транзакции.

**Зависимость:** требует фикстуру `payin_transaction_id` — ID транзакции из `test_payin_card`
(точнее, из сетап-фикстуры в `conftest.py`).

**Ключевое поле:** `transaction_data.parent_transaction_id` — ссылка на родительскую
транзакцию, по которой API знает, какую карту использовать.

---

### test_payout

**Что проверяет:** выплату на карту (в отличие от Payin — деньги идут клиенту).

**Терминал:** `default` (374)

**Отличие от Payin:** `type = "payout"`. В `assert_success` передаётся
`expected_type="payout"`, чтобы убедиться, что API вернул правильный тип.

**Примечание:** `order_id` задан как `"order_9987"` (отличается от `MERCHANT_DATA`,
где `"order_1111"`) — чтобы не было конфликта дедупликации.

---

### test_rebill

**Что проверяет:** ребилл — повторное списание по токену карты.

**Зависимость:** `payin_transaction_id`

**Отличие от recurrent:** метод оплаты — `"token"` (не `"card"`), передаётся
UUID токена карты в `transaction_data.details.token`. Сам токен должен быть реальным
(привязан к карте из предыдущего Payin). Текущий токен в тесте — заглушка,
которую нужно заменить на реальный.

---

### test_rebill_block

**Что проверяет:** ребилл с блокировкой — то же, что rebill, но `capture_mode = "manual"`.
Деньги блокируются без списания.

**Зависимость:** `payin_transaction_id`

---

### test_refund

**Что проверяет:** возврат средств по существующей транзакции.

**Зависимость:** `payin_transaction_id`

**Особенность URL:** запрос идёт не на `BASE_URL`, а на
`{BASE_URL}/{transaction_id}/refund` — поэтому в тесте вручную собираются
заголовки через `make_headers()` и выполняется `requests.post()` напрямую.

**Сумма возврата:** 1000 (10.00 RUB) — частичный возврат от оригинальных 10000.

---

## Негативные тесты — test_negative.py

### Хелпер `VALID_PAYIN_BODY`

Базовое валидное тело Payin. В каждом негативном тесте берётся эта константа
и **намеренно ломается одно поле**. Так проще читать тест и понимать,
что именно проверяется.

### Хелпер `assert_error(resp, expected_status)`

Проверяет:
1. HTTP статус == `expected_status`
2. Тело ответа — валидный JSON-объект (API не должен возвращать HTML или пустой ответ даже при ошибке)

### Хелпер `post_raw(body, terminal_id=None)`

Аналог `post_transaction()`, но принимает произвольное тело.
Подпись при этом считается **корректная** — это важно: тест проверяет валидацию
тела, а не авторизацию.

---

### Группа: отсутствие обязательных полей

**`test_missing_top_level_field`** — параметризованный тест, запускается 6 раз,
по одному для каждого обязательного поля верхнего уровня:
`type`, `merchant_data`, `financial_data`, `flow_data`, `customer_data`, `transaction_data`.

Каждый раз берётся `VALID_PAYIN_BODY` и из него удаляется одно поле.
Ожидаемый ответ: `422 Unprocessable Entity`.

**`test_missing_merchant_field`** — параметризованный, проверяет отсутствие
`order_id` и `webhook_url` внутри `merchant_data`. Ожидается `422`.

---

### Группа: невалидные значения

| Тест | Что ломается | Ожидаемый статус |
|---|---|---|
| `test_invalid_transaction_type` | `type = "unknown_type"` | 422 |
| `test_negative_amount` | `amount = -100` | 422 |
| `test_zero_amount` | `amount = 0` | 422 |
| `test_invalid_currency` | `currency = "INVALID"` | 422 |
| `test_missing_currency` | поле `currency` удалено | 422 |
| `test_invalid_card_pan` | `pan = "1234"` (слишком короткий) | 422 |
| `test_expired_card` | `expiry_year = "20"`, `expiry_month = "01"` | 422 |
| `test_missing_cvv` | поле `cvv` удалено | 422 |

---

### Группа: авторизация

**`test_invalid_signature`**
Отправляет запрос с подписью из 64 нулей. Ожидается `401` или `403`.
Подпись считается некорректной — сервер должен отклонить запрос до валидации тела.

**`test_missing_signature_header`**
Убирает заголовок `Api-Signature` полностью. Ожидается `400`, `401` или `403`.

**`test_missing_terminal_id_header`**
Убирает заголовок `Api-Terminal-ID`. Ожидается `400`, `401` или `403`.
(Подпись при этом тоже некорректная — она считалась бы с учётом terminal_id.)

**`test_unknown_terminal_id`**
Отправляет запрос от имени несуществующего терминала `99999`.
Подпись при этом корректно посчитана для этого терминала, но терминал не зарегистрирован.
Ожидается `401`, `403` или `404`.

---

### Группа: дедупликация

**`test_idempotency_key_deduplication`**

Идемпотентность означает: если отправить два одинаковых запроса с одним
`Api-Idempotency-Key`, сервер должен вернуть один и тот же результат,
не создавая новую транзакцию.

Тест:
1. Отправляет первый запрос — ожидает `201` и сохраняет `transaction_id`
2. Отправляет второй запрос с тем же `Api-Idempotency-Key` (но другим `Api-Timestamp`
   и подписью) — ожидает `200` или `201`
3. Проверяет, что оба ответа вернули **одинаковый** `transaction_id`

---

### Группа: прочие

**`test_invalid_json_body`**
Отправляет строку `"this is not json"` в теле с `Content-Type: application/json`.
Подпись считается от этой строки (чтобы пройти авторизацию и дойти до парсинга).
Ожидается `400` или `422`.

**`test_refund_nonexistent_transaction`**
Делает рефанд на URL `{BASE_URL}/nonexistent-id-000000/refund`.
Ожидается `404` (транзакция не найдена) или `422`.

**`test_refund_amount_exceeds_original`**
Пытается вернуть `99999999` (≫ суммы оригинальной транзакции в 10000).
Ожидается `400` или `422`.
Зависит от фикстуры `payin_transaction_id`.

---

## Как изменить тесты

### Поменять тестовые данные (карта, клиент, мерчант)

Всё в `tests/conftest.py`, блок `SHARED PAYLOADS`:

```python
CARD_DETAILS = {
    "pan": "4111111111111111",   # ← номер карты
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",        # ← год истечения (2 цифры)
    "cvv": "666",
}
```

Изменение здесь автоматически применится ко всем тестам.

### Добавить новый позитивный тест

В `tests/test_happy_path.py` добавьте функцию `test_что_то_новое()`:

```python
def test_payin_card_eur():
    body = {
        "type": "payin",
        "merchant_data": MERCHANT_DATA,
        "financial_data": {"amount": 500, "currency": "EUR"},
        "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
        "customer_data": CUSTOMER_DATA,
        "transaction_data": {"method": "card", "details": CARD_DETAILS},
    }
    resp = post_transaction(body)
    assert_success(resp, expected_type="payin")
```

### Добавить новый негативный тест

В `tests/test_negative.py` добавьте функцию, которая ломает одно поле и
проверяет ожидаемый статус:

```python
def test_missing_flow_data_capture_mode():
    flow = {k: v for k, v in VALID_PAYIN_BODY["flow_data"].items() if k != "capture_mode"}
    body = {**VALID_PAYIN_BODY, "flow_data": flow}
    resp = post_raw(body)
    assert_error(resp, 422)
```

### Сменить терминал или добавить новый

В `tests/conftest.py`:

```python
TERMINALS = {
    "default": "374",
    "p2p":     "502",
    "mobile":  "503",
    "crypto":  "600",   # ← новый терминал
}
```

В тесте передавайте `terminal_id=TERMINALS["crypto"]` в `post_transaction()`.

---

## Диагностика ошибок

### `Expected 201, got 401` или `403`

Проблема с авторизацией. Проверьте:
- `SERVICE_SECRET` в `conftest.py` — правильный ли секрет?
- `TERMINALS["default"]` — правильный ли ID терминала?
- Время на машине — подпись включает `Api-Timestamp`, сервер может
  отклонять запросы с отклонением более N секунд от текущего времени.

### `Expected 201, got 422`

Тело запроса не прошло валидацию. Ответ API содержит детали:
```
AssertionError: Expected 201, got 422: {"error": "invalid pan format"}
```
Смотрите на текст после двоеточия — там конкретная причина.

### `Expected 201, got 404`

Неправильный URL или несуществующий ресурс.
Проверьте `BASE_URL` в `conftest.py` и доступность препрода.

### `ERROR at setup` на тестах `test_recurrent` / `test_rebill` / `test_refund`

```
ERROR tests/test_happy_path.py::test_recurrent - AssertionError: Setup Payin failed: ...
```

Падает фикстура `payin_transaction_id` — базовый Payin не прошёл.
Запустите отдельно `test_payin_card` чтобы убедиться что базовый сценарий работает:
```bash
pytest tests/test_happy_path.py::test_payin_card -v --tb=long
```

### `ConnectionError` / `Timeout`

Нет доступа до препрода. Проверьте сеть / VPN.
Таймаут у всех запросов — 30 секунд (`timeout=30` в `post_transaction`).

### Тест упал, но хочу увидеть полный ответ API

```bash
pytest tests/test_happy_path.py::test_payin_card -s --tb=long
```

Либо добавьте в тест временный `print`:
```python
resp = post_transaction(body)
print(resp.status_code, resp.text)   # ← временно для отладки
assert_success(resp)
```
и запустите с флагом `-s`.
