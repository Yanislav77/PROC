# PROC — CORE REST API Test Suite

Интеграционные тесты для CORE REST API платёжного шлюза.
Тесты делают реальные HTTP-запросы к препрод-окружению — никаких моков.

---

## Содержание

1. [Установка с нуля](#1-установка-с-нуля)
2. [Что и где настраивать](#2-что-и-где-настраивать)
3. [Как запускать тесты](#3-как-запускать-тесты)
4. [Что делают тесты](#4-что-делают-тесты)
5. [Как читать результат](#5-как-читать-результат)
6. [Частые ошибки и что с ними делать](#6-частые-ошибки-и-что-с-ними-делать)

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

## 2. Что и где настраивать

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

Откройте `tests/conftest.py` и найдите блок `SHARED PAYLOADS` (строки ~55–115).
Там три словаря с тестовыми данными:

**Карта** (`CARD_DETAILS`):
```python
CARD_DETAILS = {
    "pan":          "4111111111111111",  # номер карты
    "holder":       "JOHN DOE",          # имя (латиницей)
    "expiry_month": "05",                # месяц истечения
    "expiry_year":  "27",               # год истечения (две цифры)
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

### Суммы, валюты, телефон → `tests/test_happy_path.py`

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
BASE_URL = "https://papiv3preprod.testpaygate.com/api/v1/transactions"
```

Если нужно переключиться на другой стенд — меняйте здесь.

---

## 3. Как запускать тесты

### Через PyCharm (проще всего)

В правом верхнем углу PyCharm есть выпадающий список конфигураций.
Там уже готовы три варианта:

| Конфигурация | Что запускает |
|---|---|
| **All Tests** | все тесты |
| **Happy Path** | только позитивные (`test_happy_path.py`) |
| **Negative** | только негативные (`test_negative.py`) |

Выберите нужный → нажмите ▶.

Также можно кликнуть правой кнопкой на любом файле или функции в боковой панели
и выбрать **Run**.

### Через терминал

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

# полный вывод при падении
pytest --tb=long

# показать print() внутри тестов
pytest -s
```

---

## 4. Что делают тесты

### Позитивные тесты (`test_happy_path.py`)

Проверяют, что каждый тип транзакции создаётся успешно (HTTP 201)
и в ответе есть все обязательные поля.

| Тест | Что проверяет |
|---|---|
| `test_payin_card` | Payin картой, автосписание (`capture=auto`) |
| `test_payin_p2p` | Payin через P2P |
| `test_payin_mobile` | Payin через мобильный платёж |
| `test_payin_block` | Payin картой с холдом (`capture=manual`) — деньги блокируются, но не списываются |
| `test_recurrent` | Рекуррентный платёж по данным предыдущей транзакции |
| `test_payout` | Выплата на карту |
| `test_rebill` | Ребилл по токену карты, автосписание |
| `test_rebill_block` | Ребилл по токену карты с холдом |
| `test_refund` | Частичный возврат по существующей транзакции |

Тесты `test_recurrent`, `test_rebill`, `test_rebill_block`, `test_refund` перед запуском
автоматически создают один Payin и берут его `transaction_id`. Этот Payin выполняется
один раз на весь прогон.

---

### Негативные тесты (`test_negative.py`)

Проверяют, что API корректно отклоняет невалидные запросы.

| Тест | Что проверяет | Ожидаемый статус |
|---|---|---|
| `test_missing_top_level_field` | Отсутствие одного из 6 обязательных полей (6 вариантов) | 422 |
| `test_invalid_transaction_type` | Неизвестный `type` | 422 |
| `test_negative_amount` | Отрицательная сумма | 422 |
| `test_zero_amount` | Нулевая сумма | 422 |
| `test_invalid_currency` | Несуществующий код валюты | 422 |
| `test_missing_currency` | Поле `currency` отсутствует | 422 |
| `test_missing_merchant_field` | Нет `order_id` или `webhook_url` (2 варианта) | 422 |
| `test_invalid_card_pan` | PAN из 4 цифр | 422 |
| `test_expired_card` | Истёкший срок карты | 422 |
| `test_missing_cvv` | Поле `cvv` отсутствует | 422 |
| `test_invalid_signature` | Подпись из нулей | 401 / 403 |
| `test_missing_signature_header` | Заголовок `Api-Signature` отсутствует | 400 / 401 / 403 |
| `test_missing_terminal_id_header` | Заголовок `Api-Terminal-ID` отсутствует | 400 / 401 / 403 |
| `test_unknown_terminal_id` | Несуществующий терминал | 401 / 403 / 404 |
| `test_idempotency_key_deduplication` | Повтор с тем же `Api-Idempotency-Key` → тот же `transaction_id` | 201 + 200/201 |
| `test_invalid_json_body` | Тело не является JSON | 400 / 422 |
| `test_refund_nonexistent_transaction` | Возврат по несуществующей транзакции | 404 / 422 |
| `test_refund_amount_exceeds_original` | Сумма возврата больше оригинала | 400 / 422 |

---

## 5. Как читать результат

### В PyCharm

После запуска внизу открывается панель **Run**:
- Зелёный кружок — тест прошёл
- Красный крестик — тест упал
- Кликните на упавший тест — справа появится подробный вывод

### В терминале

Успешный прогон:
```
tests/test_happy_path.py::test_payin_card   PASSED  [ 11%]
tests/test_happy_path.py::test_payin_p2p    PASSED  [ 22%]
...
26 passed in 14.32s
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

## 6. Частые ошибки и что с ними делать

---

### `Expected 201, got 401` или `403` — неверная авторизация

Проверьте файл `.env`:
- Правильный ли `SERVICE_SECRET`?
- Правильный ли `TERMINAL_ID`?

Также убедитесь, что время на вашей машине корректное — подпись включает текущее
время, и сервер отклоняет запросы с большим расхождением.

---

### `Expected 201, got 422` — невалидное тело запроса

API вернул ошибку валидации. Ответ содержит причину:
```
AssertionError: Expected 201, got 422: {"error": "invalid pan format"}
```
Читайте текст ошибки — там написано, что именно не так.
Проверьте `CARD_DETAILS`, `MERCHANT_DATA` в `tests/conftest.py`.

---

### `Expected 201, got 404` — неверный URL

Проверьте `BASE_URL` в `tests/conftest.py` и доступность препрода (VPN).

---

### `ERROR at setup` на тестах `test_recurrent` / `test_rebill` / `test_refund`

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
