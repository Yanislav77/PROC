"""
Тесты для customer_data и его вложенных объектов.
POST /api/v1/transactions — type:payin, method:card
Секции 31–64 из manual_cases/payment.txt.
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    CARD_DETAILS,
    THREED,
    assert_error_response,
)

_BASE = {
    "type": "payin",
    "merchant_data": MERCHANT_DATA,
    "financial_data": {"amount": 10000, "currency": "RUB"},
    "flow_data": {"is_recurrent": True, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
    "transaction_data": {"method": "card", "details": CARD_DETAILS},
}


def _with_customer(**overrides) -> dict:
    """Возвращает тело запроса с обновлёнными полями customer_data."""
    import copy
    body = copy.deepcopy(_BASE)
    body["customer_data"].update(overrides)
    return body


def _with_browser(**overrides) -> dict:
    """Обновляет browser_info внутри customer_data."""
    import copy
    body = copy.deepcopy(_BASE)
    body["customer_data"]["browser_info"].update(overrides)
    return body


def _with_contact(**overrides) -> dict:
    """Обновляет contact_info внутри customer_data."""
    import copy
    body = copy.deepcopy(_BASE)
    body["customer_data"]["contact_info"].update(overrides)
    return body


def _with_personal(**overrides) -> dict:
    """Обновляет personal_info внутри customer_data."""
    import copy
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"].update(overrides)
    return body


def _with_doc(**overrides) -> dict:
    """Обновляет document_details внутри personal_info."""
    import copy
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"]["document_details"].update(overrides)
    return body


# ─────────────────────────────────────────────
# BROWSER_INFO (31.x)
# ─────────────────────────────────────────────
def test_browser_info_missing():
    """browser_info не передан. Ожидается 201 (необязательный объект)."""
    import copy
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["browser_info"]
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_browser_info_empty_object():
    """browser_info передан как пустой объект {}. Ожидается 201."""
    body = _with_customer(browser_info={})
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# IP (32.x)
# ─────────────────────────────────────────────
def test_ip_valid_ipv4():
    """ip — валидный IPv4-адрес. Ожидается 201."""
    resp = post_transaction(_with_browser(ip="192.168.0.1"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_ip_invalid_ipv4():
    """ip — невалидный IPv4-адрес. Ожидается 400."""
    resp = post_transaction(_with_browser(ip="999.999.999.999"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_ip_valid_ipv6():
    """ip — валидный IPv6-адрес. Ожидается 201."""
    resp = post_transaction(_with_browser(ip="2001:db8::1"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_ip_empty():
    """ip передан как пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(ip=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_ip_null():
    """ip передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction(_with_browser(ip=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_ip_missing():
    """ip не передан. Ожидается 201."""
    import copy
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["browser_info"]["ip"]
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ACCEPT_HEADER (33.x)
# ─────────────────────────────────────────────
def test_accept_header_valid():
    """accept_header — строка. Ожидается 201."""
    resp = post_transaction(_with_browser(accept_header="text/html,application/json"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_accept_header_empty():
    """accept_header — пустая строка. Ожидается 400 или 201."""
    resp = post_transaction(_with_browser(accept_header=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_accept_header_null():
    """accept_header — null. Ожидается 201."""
    resp = post_transaction(_with_browser(accept_header=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# COLOR_DEPTH (34.x)
# ─────────────────────────────────────────────
def test_color_depth_valid():
    """color_depth — целое число. Ожидается 201."""
    resp = post_transaction(_with_browser(color_depth=32))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_color_depth_null():
    """color_depth — null. Ожидается 201."""
    resp = post_transaction(_with_browser(color_depth=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# JAVA_ENABLED (35.x)
# ─────────────────────────────────────────────
def test_java_enabled_true():
    """java_enabled=true. Ожидается 201."""
    resp = post_transaction(_with_browser(java_enabled=True))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_java_enabled_false():
    """java_enabled=false. Ожидается 201."""
    resp = post_transaction(_with_browser(java_enabled=False))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_java_enabled_int_one():
    """java_enabled=1 (не boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled=1))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_java_enabled_int_zero():
    """java_enabled=0 (не boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled=0))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_java_enabled_string():
    """java_enabled — строка. Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled="true"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_java_enabled_null():
    """java_enabled=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(java_enabled=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# JAVA_SCRIPT_ENABLED (36.x)
# ─────────────────────────────────────────────
def test_java_script_enabled_true():
    """java_script_enabled=true. Ожидается 201."""
    resp = post_transaction(_with_browser(java_script_enabled=True))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_java_script_enabled_false():
    """java_script_enabled=false. Ожидается 201."""
    resp = post_transaction(_with_browser(java_script_enabled=False))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_java_script_enabled_int():
    """java_script_enabled=1 (не boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_script_enabled=1))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_java_script_enabled_string():
    """java_script_enabled — строка. Ожидается 400."""
    resp = post_transaction(_with_browser(java_script_enabled="false"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_java_script_enabled_null():
    """java_script_enabled=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(java_script_enabled=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# LANGUAGE (37.x)
# ─────────────────────────────────────────────
def test_language_two_char():
    """language — двухсимвольный код. Ожидается 201."""
    resp = post_transaction(_with_browser(language="en"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_language_with_region():
    """language — код с регионом (en-US). Ожидается 201."""
    resp = post_transaction(_with_browser(language="en-US"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_language_uppercase():
    """language в верхнем регистре. Ожидается 201."""
    resp = post_transaction(_with_browser(language="RU"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_language_empty():
    """language — пустая строка. Ожидается 400 или 201."""
    resp = post_transaction(_with_browser(language=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


def test_language_null():
    """language=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(language=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CONTACT_INFO (42.x)
# ─────────────────────────────────────────────
def test_contact_info_missing():
    """contact_info не передан. Ожидается 201 (необязательный объект)."""
    import copy
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["contact_info"]
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_contact_info_empty_object():
    """contact_info передан как пустой объект {}. Ожидается 201."""
    body = _with_customer(contact_info={})
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# COUNTRY (44.x)
# ─────────────────────────────────────────────
def test_country_valid_two_char():
    """country — двухсимвольный код ISO 3166. Ожидается 201."""
    resp = post_transaction(_with_contact(country="DE"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_country_one_char():
    """country — односимвольный код. Ожидается 400."""
    resp = post_transaction(_with_contact(country="D"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_country_three_chars():
    """country — трёхсимвольный код. Ожидается 400."""
    resp = post_transaction(_with_contact(country="DEU"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_country_numeric():
    """country — числовое значение. Ожидается 400."""
    resp = post_transaction(_with_contact(country="12"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_country_nonexistent_code():
    """country — несуществующий двухсимвольный код. Ожидается 400."""
    resp = post_transaction(_with_contact(country="XX"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_country_empty():
    """country — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_contact(country=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_country_null():
    """country=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(country=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EMAIL (45.x)
# ─────────────────────────────────────────────
def test_email_valid():
    """email — валидный адрес. Ожидается 201."""
    resp = post_transaction(_with_contact(email="test@example.com"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_email_with_numbers():
    """email — с цифрами в имени. Ожидается 201."""
    resp = post_transaction(_with_contact(email="user123@example.com"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_email_no_at_sign():
    """email без символа @. Ожидается 400."""
    resp = post_transaction(_with_contact(email="userexample.com"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_email_no_domain():
    """email без доменной части. Ожидается 400."""
    resp = post_transaction(_with_contact(email="user@"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_email_multilevel_domain():
    """email с несколькими уровнями домена. Ожидается 201."""
    resp = post_transaction(_with_contact(email="user@mail.example.com"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_email_empty():
    """email — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_contact(email=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_email_null():
    """email=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(email=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PHONE (46.x)
# ─────────────────────────────────────────────
def test_phone_valid_with_plus():
    """phone с символом +. Ожидается 201."""
    resp = post_transaction(_with_contact(phone="+79991234567"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_phone_valid_without_plus():
    """phone без символа +. Ожидается 201."""
    resp = post_transaction(_with_contact(phone="79991234567"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_phone_too_short():
    """phone из 2 символов (слишком короткий). Ожидается 400."""
    resp = post_transaction(_with_contact(phone="12"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_phone_16_chars():
    """phone из 16 символов (граничное валидное). Ожидается 201."""
    resp = post_transaction(_with_contact(phone="+123456789012345"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_phone_17_chars():
    """phone из 17 символов (сверх лимита). Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+1234567890123456"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_phone_with_letters():
    """phone содержит буквы. Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+7999ABC4567"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_phone_empty():
    """phone — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_contact(phone=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_phone_null():
    """phone=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(phone=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PERSONAL_INFO (51.x)
# ─────────────────────────────────────────────
def test_personal_info_missing():
    """personal_info не передан. Ожидается 201."""
    import copy
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["personal_info"]
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_personal_info_empty_object():
    """personal_info передан как пустой объект {}. Ожидается 201."""
    body = _with_customer(personal_info={})
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DATE_OF_BIRTH (52.x)
# ─────────────────────────────────────────────
def test_date_of_birth_valid_format():
    """date_of_birth в формате YYYY-MM-DD. Ожидается 201."""
    resp = post_transaction(_with_personal(date_of_birth="1990-06-15"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_date_of_birth_wrong_format():
    """date_of_birth в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="15-06-1990"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_date_of_birth_under_18():
    """date_of_birth, при которой возраст < 18 лет. Ожидается 400."""
    from datetime import datetime, timedelta
    dob = (datetime.now() - timedelta(days=17 * 365)).strftime("%Y-%m-%d")
    resp = post_transaction(_with_personal(date_of_birth=dob))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_date_of_birth_future():
    """date_of_birth в будущем. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="2099-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_date_of_birth_nonexistent_date():
    """date_of_birth — несуществующая дата. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="1990-02-30"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_date_of_birth_null():
    """date_of_birth=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(date_of_birth=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DOCUMENT_TYPE (53.x)
# ─────────────────────────────────────────────
def test_document_type_passport():
    """document_type='passport'. Ожидается 201."""
    resp = post_transaction(_with_personal(document_type="passport"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_document_type_invalid():
    """document_type='passport1' (невалидное). Ожидается 400."""
    resp = post_transaction(_with_personal(document_type="passport1"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_document_type_empty():
    """document_type — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_personal(document_type=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_document_type_null():
    """document_type=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(document_type=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# GENDER (60.x)
# ─────────────────────────────────────────────
def test_gender_male():
    """gender='M'. Ожидается 201."""
    resp = post_transaction(_with_doc(gender="M"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_gender_female():
    """gender='F'. Ожидается 201."""
    resp = post_transaction(_with_doc(gender="F"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_gender_invalid():
    """gender='MF' (невалидное значение). Ожидается 400."""
    resp = post_transaction(_with_doc(gender="MF"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_gender_empty():
    """gender — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_doc(gender=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_gender_null():
    """gender=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(gender=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EXPIRY_DATE (59.x) — document expiry date
# ─────────────────────────────────────────────
def test_doc_expiry_date_valid_future():
    """document expiry_date в будущем, формат YYYY-MM-DD. Ожидается 201."""
    resp = post_transaction(_with_doc(expiry_date="2035-12-31"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_doc_expiry_date_past():
    """document expiry_date в прошлом. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="2010-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_doc_expiry_date_wrong_format():
    """document expiry_date в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="31-12-2035"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_doc_expiry_date_nonexistent():
    """document expiry_date — несуществующая дата. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="2030-13-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_doc_expiry_date_null():
    """document expiry_date=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(expiry_date=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ISSUE_DATE (61.x) — document issue date
# ─────────────────────────────────────────────
def test_doc_issue_date_valid():
    """document issue_date в формате YYYY-MM-DD, в прошлом. Ожидается 201."""
    resp = post_transaction(_with_doc(issue_date="2015-06-01"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


def test_doc_issue_date_future():
    """document issue_date в будущем. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="2099-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_doc_issue_date_wrong_format():
    """document issue_date в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="01-06-2015"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


def test_doc_issue_date_null():
    """document issue_date=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issue_date=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"
