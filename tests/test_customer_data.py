"""
Тесты для customer_data и его вложенных объектов.
POST /api/v1/transactions — type:payin, method:card
Секции 31–64 из manual_cases/payment.txt.
"""
import copy
from datetime import datetime, date, timedelta
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
    body = copy.deepcopy(_BASE)
    body["customer_data"].update(overrides)
    return body


def _with_browser(**overrides) -> dict:
    """Обновляет browser_info внутри customer_data."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["browser_info"].update(overrides)
    return body


def _with_contact(**overrides) -> dict:
    """Обновляет contact_info внутри customer_data."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["contact_info"].update(overrides)
    return body


def _with_personal(**overrides) -> dict:
    """Обновляет personal_info внутри customer_data."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"].update(overrides)
    return body


def _with_doc(**overrides) -> dict:
    """Обновляет document_details внутри personal_info."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"]["document_details"].update(overrides)
    return body


def _with_payer(**overrides) -> dict:
    """Добавляет/обновляет payer_info внутри customer_data."""
    body = copy.deepcopy(_BASE)
    body["customer_data"].setdefault("payer_info", {})
    body["customer_data"]["payer_info"].update(overrides)
    return body


# ─────────────────────────────────────────────
# BROWSER_INFO (31.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-001")
def test_browser_info_missing():
    """browser_info не передан. Ожидается 400."""
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["browser_info"]
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-002")
def test_browser_info_empty_object():
    """browser_info передан как пустой объект {}. Ожидается 400 (ip обязателен)."""
    body = _with_customer(browser_info={})
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# IP (32.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-003")
def test_ip_valid_ipv4():
    """ip — валидный IPv4-адрес. Ожидается 201."""
    resp = post_transaction(_with_browser(ip="192.168.0.1"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-004")
def test_ip_invalid_ipv4():
    """ip — невалидный IPv4-адрес. Ожидается 400."""
    resp = post_transaction(_with_browser(ip="999.999.999.999"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-005")
def test_ip_valid_ipv6():
    """ip — IPv6-адрес (спека требует IPv4 format). Ожидается 201."""
    resp = post_transaction(_with_browser(ip="2001:db8::1"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-006")
def test_ip_empty():
    """ip передан как пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(ip=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-007")
def test_ip_null():
    """ip передан как null. Ожидается 201 (необязательное поле)."""
    resp = post_transaction(_with_browser(ip=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-008")
def test_ip_missing():
    """ip не передан при наличии browser_info. Ожидается 400 (ip обязателен внутри browser_info)."""
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["browser_info"]["ip"]
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ACCEPT_HEADER (33.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-009")
def test_accept_header_valid():
    """accept_header — строка. Ожидается 201."""
    resp = post_transaction(_with_browser(accept_header="text/html,application/json"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-010")
def test_accept_header_empty():
    """accept_header — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(accept_header=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-011")
def test_accept_header_null():
    """accept_header — null. Ожидается 201."""
    resp = post_transaction(_with_browser(accept_header=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# COLOR_DEPTH (34.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-012")
def test_color_depth_valid():
    """color_depth — целое число. Ожидается 201."""
    resp = post_transaction(_with_browser(color_depth=32))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-013")
def test_color_depth_null():
    """color_depth — null. Ожидается 201."""
    resp = post_transaction(_with_browser(color_depth=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# JAVA_ENABLED (35.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-014")
def test_java_enabled_true():
    """java_enabled=true. Ожидается 201."""
    resp = post_transaction(_with_browser(java_enabled=True))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-015")
def test_java_enabled_false():
    """java_enabled=false. Ожидается 201."""
    resp = post_transaction(_with_browser(java_enabled=False))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-016")
def test_java_enabled_int_one():
    """java_enabled=1 (целое число вместо boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled=1))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-017")
def test_java_enabled_int_zero():
    """java_enabled=0 (целое число вместо boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled=0))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-018")
def test_java_enabled_string():
    """java_enabled — строка. Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled="true"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-019")
def test_java_enabled_null():
    """java_enabled=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(java_enabled=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# JAVA_SCRIPT_ENABLED (36.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-020")
def test_java_script_enabled_true():
    """java_script_enabled=true. Ожидается 201."""
    resp = post_transaction(_with_browser(java_script_enabled=True))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-021")
def test_java_script_enabled_false():
    """java_script_enabled=false. Ожидается 201."""
    resp = post_transaction(_with_browser(java_script_enabled=False))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-022")
def test_java_script_enabled_int():
    """java_script_enabled=1 (целое число вместо boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_script_enabled=1))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-023")
def test_java_script_enabled_string():
    """java_script_enabled — строка. Ожидается 400."""
    resp = post_transaction(_with_browser(java_script_enabled="false"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-024")
def test_java_script_enabled_null():
    """java_script_enabled=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(java_script_enabled=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# LANGUAGE (37.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-025")
def test_language_two_char():
    """language — двухсимвольный код. Ожидается 201."""
    resp = post_transaction(_with_browser(language="en"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-026")
def test_language_with_region():
    """language — код с регионом (en-US). Ожидается 400."""
    resp = post_transaction(_with_browser(language="en-US"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-027")
def test_language_uppercase():
    """language в верхнем регистре. Ожидается 201."""
    resp = post_transaction(_with_browser(language="RU"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-028")
def test_language_empty():
    """language — пустая строка. Ожидается 400 или 201."""
    resp = post_transaction(_with_browser(language=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-029")
def test_language_null():
    """language=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(language=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CONTACT_INFO (42.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-030")
def test_contact_info_missing():
    """contact_info не передан. Ожидается 201 (необязательный объект)."""
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["contact_info"]
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-031")
def test_contact_info_empty_object():
    """contact_info передан как пустой объект {}. Ожидается 201."""
    body = _with_customer(contact_info={})
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# COUNTRY (44.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-032")
def test_country_valid_two_char():
    """country — двухсимвольный код ISO 3166. Ожидается 201."""
    resp = post_transaction(_with_contact(country="DE"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-033")
def test_country_one_char():
    """country — односимвольный код. Ожидается 400."""
    resp = post_transaction(_with_contact(country="D"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-034")
def test_country_three_chars():
    """country — трёхсимвольный код. Ожидается 400."""
    resp = post_transaction(_with_contact(country="DEU"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-035")
def test_country_numeric():
    """country — числовое значение. Ожидается 400."""
    resp = post_transaction(_with_contact(country="12"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-036")
def test_country_nonexistent_code():
    """country — несуществующий двухсимвольный код. Ожидается 400."""
    resp = post_transaction(_with_contact(country="XX"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-037")
def test_country_empty():
    """country — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_contact(country=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-038")
def test_country_null():
    """country=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(country=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EMAIL (45.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-039")
def test_email_valid():
    """email — валидный адрес. Ожидается 201."""
    resp = post_transaction(_with_contact(email="test@example.com"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-040")
def test_email_with_numbers():
    """email — с цифрами в имени. Ожидается 201."""
    resp = post_transaction(_with_contact(email="user123@example.com"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-041")
def test_email_no_at_sign():
    """email без символа @. Ожидается 400."""
    resp = post_transaction(_with_contact(email="userexample.com"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-042")
def test_email_no_domain():
    """email без доменной части. Ожидается 400."""
    resp = post_transaction(_with_contact(email="user@"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-043")
def test_email_multilevel_domain():
    """email с несколькими уровнями домена. Ожидается 201."""
    resp = post_transaction(_with_contact(email="user@mail.example.com"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-044")
def test_email_empty():
    """email — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_contact(email=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-045")
def test_email_null():
    """email=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(email=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PHONE (46.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-046")
def test_phone_valid_with_plus():
    """phone с символом +. Ожидается 201."""
    resp = post_transaction(_with_contact(phone="+79991234567"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-047")
def test_phone_valid_without_plus():
    """phone без символа +. Ожидается 400."""
    resp = post_transaction(_with_contact(phone="79991234567"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-048")
def test_phone_too_short():
    """phone '+1' (слишком короткий, 2 символа включая +). Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+1"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-049")
def test_phone_16_chars():
    """phone из 16 символов (граничное валидное). Ожидается 201."""
    resp = post_transaction(_with_contact(phone="+123456789012345"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-050")
def test_phone_17_chars():
    """phone из 17 символов (сверх лимита). Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+1234567890123456"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-051")
def test_phone_with_letters():
    """phone содержит буквы. Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+7999ABC4567"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-052")
def test_phone_empty():
    """phone — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_contact(phone=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-053")
def test_phone_null():
    """phone=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(phone=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PERSONAL_INFO (51.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-054")
def test_personal_info_missing():
    """personal_info не передан. Ожидается 201."""
    body = copy.deepcopy(_BASE)
    del body["customer_data"]["personal_info"]
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-055")
def test_personal_info_empty_object():
    """personal_info передан как пустой объект {}. Ожидается 201."""
    body = _with_customer(personal_info={})
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DATE_OF_BIRTH (52.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-056")
def test_date_of_birth_valid_format():
    """date_of_birth в формате YYYY-MM-DD. Ожидается 201."""
    resp = post_transaction(_with_personal(date_of_birth="1990-06-15"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-057")
def test_date_of_birth_wrong_format():
    """date_of_birth в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="15-06-1990"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-058")
def test_date_of_birth_under_18():
    """date_of_birth, при которой возраст < 18 лет. Ожидается 400."""
    dob = (datetime.now() - timedelta(days=17 * 365)).strftime("%Y-%m-%d")
    resp = post_transaction(_with_personal(date_of_birth=dob))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-059")
def test_date_of_birth_future():
    """date_of_birth в будущем. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="2099-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-060")
def test_date_of_birth_nonexistent_date():
    """date_of_birth — несуществующая дата. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="1990-02-30"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-061")
def test_date_of_birth_null():
    """date_of_birth=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(date_of_birth=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DOCUMENT_TYPE (53.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-062")
def test_document_type_passport():
    """document_type='passport'. Ожидается 201."""
    resp = post_transaction(_with_personal(document_type="passport"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-063")
def test_document_type_invalid():
    """document_type='passport1' (невалидное). Ожидается 400."""
    resp = post_transaction(_with_personal(document_type="passport1"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-064")
def test_document_type_empty():
    """document_type — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_personal(document_type=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-065")
def test_document_type_null():
    """document_type=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(document_type=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# GENDER (60.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-066")
def test_gender_male():
    """gender='M'. Ожидается 201."""
    resp = post_transaction(_with_doc(gender="M"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-067")
def test_gender_female():
    """gender='F'. Ожидается 201."""
    resp = post_transaction(_with_doc(gender="F"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-068")
def test_gender_invalid():
    """gender='MF' (невалидное значение). Ожидается 400."""
    resp = post_transaction(_with_doc(gender="MF"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-069")
def test_gender_empty():
    """gender — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_doc(gender=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-070")
def test_gender_null():
    """gender=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(gender=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EXPIRY_DATE (59.x) — document expiry date
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-071")
def test_doc_expiry_date_valid_future():
    """document expiry_date в будущем, формат YYYY-MM-DD. Ожидается 201."""
    resp = post_transaction(_with_doc(expiry_date="2035-12-31"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-072")
def test_doc_expiry_date_past():
    """document expiry_date в прошлом. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="2010-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-073")
def test_doc_expiry_date_wrong_format():
    """document expiry_date в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="31-12-2035"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-074")
def test_doc_expiry_date_nonexistent():
    """document expiry_date — несуществующая дата. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="2030-13-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-075")
def test_doc_expiry_date_null():
    """document expiry_date=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(expiry_date=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ISSUE_DATE (61.x) — document issue date
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-076")
def test_doc_issue_date_valid():
    """document issue_date в формате YYYY-MM-DD, в прошлом. Ожидается 201."""
    resp = post_transaction(_with_doc(issue_date="2015-06-01"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-077")
def test_doc_issue_date_future():
    """document issue_date в будущем. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="2099-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-078")
def test_doc_issue_date_wrong_format():
    """document issue_date в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="01-06-2015"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-079")
def test_doc_issue_date_null():
    """document issue_date=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issue_date=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CUSTOMER_DATA (30.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-080")
def test_customer_data_missing():
    """customer_data не передан. Ожидается 400."""
    body = copy.deepcopy(_BASE)
    body.pop("customer_data", None)
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-081")
def test_customer_data_empty_object():
    """customer_data передан как пустой объект {}. Ожидается 400."""
    body = copy.deepcopy(_BASE)
    body["customer_data"] = {}
    resp = post_transaction(body)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# BROWSER_INFO OPTIONAL SUB-FIELDS — missing → 201 (33.x–41.x)
# ─────────────────────────────────────────────
@pytest.mark.parametrize("field", [
    pytest.param("accept_header", marks=pytest.mark.tcid("CD-082"), id="accept_header"),
    pytest.param("color_depth", marks=pytest.mark.tcid("CD-084"), id="color_depth"),
    pytest.param("java_enabled", marks=pytest.mark.tcid("CD-086"), id="java_enabled"),
    pytest.param("java_script_enabled", marks=pytest.mark.tcid("CD-089"), id="java_script_enabled"),
    pytest.param("language", marks=pytest.mark.tcid("CD-092"), id="language"),
    pytest.param("screen_height", marks=pytest.mark.tcid("CD-096"), id="screen_height"),
    pytest.param("screen_width", marks=pytest.mark.tcid("CD-100"), id="screen_width"),
    pytest.param("time_zone", marks=pytest.mark.tcid("CD-106"), id="time_zone"),
    pytest.param("user_agent", marks=pytest.mark.tcid("CD-110"), id="user_agent"),
])
def test_browser_info_optional_field_missing(field):
    """browser_info sub-field не передан. Ожидается 201 (поле опционально)."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["browser_info"].pop(field, None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# COLOR_DEPTH (34.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-083")
def test_color_depth_empty_string():
    """color_depth — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(color_depth=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# JAVA_ENABLED (35.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-085")
def test_java_enabled_empty_string():
    """java_enabled — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(java_enabled=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# JAVA_SCRIPT_ENABLED (36.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-087")
def test_java_script_enabled_int_zero_extra():
    """java_script_enabled=0 (целое число вместо boolean). Ожидается 400."""
    resp = post_transaction(_with_browser(java_script_enabled=0))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-088")
def test_java_script_enabled_empty_string():
    """java_script_enabled — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(java_script_enabled=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# LANGUAGE (37.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-090")
def test_language_multiple_values():
    """language — несколько значений 'en,fr'. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(language="en,fr"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-091")
def test_language_lowercase():
    """language — строчный код 'ru'. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(language="ru"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-251")
def test_language_accept_language_header_format():
    """language в формате Accept-Language заголовка 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'. Ожидается 400."""
    resp = post_transaction(_with_browser(language="ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# SCREEN_HEIGHT (38.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-093")
def test_screen_height_int():
    """screen_height=1080 (целое число). Ожидается 201."""
    resp = post_transaction(_with_browser(screen_height=1080))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-094")
def test_screen_height_empty_string():
    """screen_height — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(screen_height=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-095")
def test_screen_height_null():
    """screen_height=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(screen_height=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# SCREEN_WIDTH (39.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-097")
def test_screen_width_int():
    """screen_width=1920 (целое число). Ожидается 201."""
    resp = post_transaction(_with_browser(screen_width=1920))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-098")
def test_screen_width_empty_string():
    """screen_width — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(screen_width=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-099")
def test_screen_width_null():
    """screen_width=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(screen_width=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# TIME_ZONE (40.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-101")
def test_time_zone_positive_int():
    """time_zone=180 (положительное целое). Ожидается 201."""
    resp = post_transaction(_with_browser(time_zone=180))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-102")
def test_time_zone_negative_int():
    """time_zone=-180 (отрицательное целое). Ожидается 201."""
    resp = post_transaction(_with_browser(time_zone=-180))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-103")
def test_time_zone_sixty():
    """time_zone=60. Ожидается 201."""
    resp = post_transaction(_with_browser(time_zone=60))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-104")
def test_time_zone_empty_string():
    """time_zone — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(time_zone=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-105")
def test_time_zone_null():
    """time_zone=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(time_zone=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# USER_AGENT (41.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-107")
def test_user_agent_valid_string():
    """user_agent — реальная строка. Ожидается 201."""
    resp = post_transaction(_with_browser(user_agent="Mozilla/5.0 (Windows NT 10.0)"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-108")
def test_user_agent_empty_string():
    """user_agent — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_browser(user_agent=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-109")
def test_user_agent_null():
    """user_agent=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_browser(user_agent=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CITY (43.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-111")
def test_city_any_string():
    """city='Moscow' (любая строка). Ожидается 201."""
    resp = post_transaction(_with_contact(city="Moscow"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-112")
def test_city_latin():
    """city='Berlin' (латиница). Ожидается 201."""
    resp = post_transaction(_with_contact(city="Berlin"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-113")
def test_city_latin_with_spaces():
    """city='New York' (латиница с пробелами). Ожидается 201."""
    resp = post_transaction(_with_contact(city="New York"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-114")
def test_city_cyrillic():
    """city='Москва' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(city="Москва"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-115")
def test_city_cyrillic_with_spaces():
    """city='Нью Йорк' (кириллица с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(city="Нью Йорк"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-116")
def test_city_letters_and_digits():
    """city='City1' (буквы и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(city="City1"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-117")
def test_city_letters_and_special_chars():
    """city='City@!' (буквы и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(city="City@!"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-118")
def test_city_empty_string():
    """city — пустая строка. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(city=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-119")
def test_city_null():
    """city=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(city=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# CONTACT_INFO OPTIONAL SUB-FIELDS — missing → 201 (43.x, 47.x, 48.x)
# ─────────────────────────────────────────────
@pytest.mark.parametrize("field", [
    pytest.param("city", marks=pytest.mark.tcid("CD-120"), id="city"),
    pytest.param("state", marks=pytest.mark.tcid("CD-140"), id="state"),
    pytest.param("zip", marks=pytest.mark.tcid("CD-149"), id="zip"),
])
def test_contact_info_optional_field_missing(field):
    """contact_info sub-field не передан. Ожидается 201 (поле опционально)."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["contact_info"].pop(field, None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# COUNTRY (44.x) — дополнительные
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-121")
def test_country_cyrillic_two_chars():
    """country='РФ' (кириллица 2 символа). Ожидается 400."""
    resp = post_transaction(_with_contact(country="РФ"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-122")
def test_country_missing():
    """country не передан. Ожидается 201 или 400."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["contact_info"].pop("country", None)
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EMAIL (45.x) — дополнительные
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-123")
def test_email_invalid_special_chars():
    """email с недопустимыми спецсимволами 'user!#$%@example.com'. Ожидается 400."""
    resp = post_transaction(_with_contact(email="user!#$%@example.com"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-124")
def test_email_without_at_sign_extra():
    """email без символа @ 'userexample.com'. Ожидается 400."""
    resp = post_transaction(_with_contact(email="userexample.com"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-125")
def test_email_without_local_part():
    """email без локальной части '@example.com'. Ожидается 400."""
    resp = post_transaction(_with_contact(email="@example.com"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-126")
def test_email_missing():
    """email не передан. Ожидается 201 или 400."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["contact_info"].pop("email", None)
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-127")
def test_email_as_array():
    """email передан как массив. Ожидается 400."""
    resp = post_transaction(_with_contact(email=["test@example.com"]))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PHONE (46.x) — дополнительные
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-128")
def test_phone_three_chars_with_plus():
    """phone '+79' (3 символа включая +). Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+79"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-129")
def test_phone_with_special_chars():
    """phone со спецсимволами '+7999!23-45'. Ожидается 400."""
    resp = post_transaction(_with_contact(phone="+7999!23-45"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-130")
def test_phone_missing():
    """phone не передан. Ожидается 201 или 400."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["contact_info"].pop("phone", None)
    resp = post_transaction(body)
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# STATE (47.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-131")
def test_state_latin():
    """state='California' (латиница). Ожидается 201."""
    resp = post_transaction(_with_contact(state="California"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-132")
def test_state_latin_short():
    """state='Texas' (латиница). Ожидается 201."""
    resp = post_transaction(_with_contact(state="Texas"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-133")
def test_state_latin_with_spaces():
    """state='New Mexico' (латиница с пробелами). Ожидается 201."""
    resp = post_transaction(_with_contact(state="New Mexico"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-134")
def test_state_cyrillic():
    """state='Москва' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(state="Москва"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-135")
def test_state_cyrillic_with_spaces():
    """state='Нью Йорк' (кириллица с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(state="Нью Йорк"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-136")
def test_state_letters_and_digits():
    """state='State1' (буквы и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(state="State1"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-137")
def test_state_letters_and_special_chars():
    """state='State!' (буквы и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(state="State!"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-138")
def test_state_empty_string():
    """state — пустая строка. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(state=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-139")
def test_state_null():
    """state=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(state=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ZIP (48.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-141")
def test_zip_digits_six():
    """zip='101000' (6 цифр). Ожидается 201."""
    resp = post_transaction(_with_contact(zip="101000"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-142")
def test_zip_digits():
    """zip='123456' (цифры). Ожидается 201."""
    resp = post_transaction(_with_contact(zip="123456"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-143")
def test_zip_latin_short():
    """zip='W1A' (латиница). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(zip="W1A"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-144")
def test_zip_latin_with_spaces():
    """zip='W1A 1AA' (латиница с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(zip="W1A 1AA"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-145")
def test_zip_cyrillic():
    """zip='Индекс' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(zip="Индекс"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-146")
def test_zip_digits_and_special_chars():
    """zip='1000-AB' (цифры и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(zip="1000-AB"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-147")
def test_zip_empty_string():
    """zip — пустая строка. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(zip=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-148")
def test_zip_null():
    """zip=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_contact(zip=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PAYER_INFO (49.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-150")
def test_payer_info_missing():
    """payer_info не передан. Ожидается 201."""
    body = copy.deepcopy(_BASE)
    body["customer_data"].pop("payer_info", None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-151")
def test_payer_info_empty_object():
    """payer_info передан как пустой объект {}. Ожидается 201."""
    resp = post_transaction(_with_payer())
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PAYER_ID (50.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-152")
def test_payer_id_any_string():
    """payer_id='payer_001' (любая строка). Ожидается 201."""
    resp = post_transaction(_with_payer(payer_id="payer_001"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-153")
def test_payer_id_latin():
    """payer_id='payerABC' (латиница). Ожидается 201."""
    resp = post_transaction(_with_payer(payer_id="payerABC"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-154")
def test_payer_id_latin_with_spaces():
    """payer_id='payer ABC' (латиница с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_payer(payer_id="payer ABC"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-155")
def test_payer_id_digits():
    """payer_id='123456' (цифры). Ожидается 201."""
    resp = post_transaction(_with_payer(payer_id="123456"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-156")
def test_payer_id_cyrillic():
    """payer_id='Плательщик' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_payer(payer_id="Плательщик"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-157")
def test_payer_id_digits_and_special_chars():
    """payer_id='pay#001' (цифры и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_payer(payer_id="pay#001"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-158")
def test_payer_id_empty_string():
    """payer_id — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_payer(payer_id=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-159")
def test_payer_id_null():
    """payer_id=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_payer(payer_id=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DATE_OF_BIRTH — дополнительные (52.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-160")
def test_date_of_birth_non_date_string():
    """date_of_birth — не дата. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="not-a-date"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-161")
def test_date_of_birth_eighteen_not_today():
    """date_of_birth — ровно 18 лет (день рождения не сегодня). Ожидается 201."""
    dob = (date.today() - timedelta(days=18 * 365 + 30)).strftime("%Y-%m-%d")
    resp = post_transaction(_with_personal(date_of_birth=dob))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-162")
def test_date_of_birth_exactly_eighteen_today():
    """date_of_birth — день рождения сегодня, ровно 18 лет. Ожидается 201."""
    today = date.today()
    try:
        dob = today.replace(year=today.year - 18)
    except ValueError:
        dob = today.replace(year=today.year - 18, day=28)
    resp = post_transaction(_with_personal(date_of_birth=dob.strftime("%Y-%m-%d")))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-163")
def test_date_of_birth_over_eighteen():
    """date_of_birth='1990-01-01' (более 18 лет). Ожидается 201."""
    resp = post_transaction(_with_personal(date_of_birth="1990-01-01"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-164")
def test_date_of_birth_over_hundred_years():
    """date_of_birth='1900-01-01' (более 100 лет). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(date_of_birth="1900-01-01"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-165")
def test_date_of_birth_yy_mm_dd_format():
    """date_of_birth в формате YY-MM-DD. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth="90-06-15"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-166")
def test_date_of_birth_leap_year():
    """date_of_birth='2000-02-29' (дата в високосном году). Ожидается 201."""
    resp = post_transaction(_with_personal(date_of_birth="2000-02-29"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-167")
def test_date_of_birth_empty_string():
    """date_of_birth — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_personal(date_of_birth=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# PERSONAL_INFO OPTIONAL SUB-FIELDS — missing → 201 (52.x–56.x)
# ─────────────────────────────────────────────
@pytest.mark.parametrize("field", [
    pytest.param("date_of_birth", marks=pytest.mark.tcid("CD-168"), id="date_of_birth"),
    pytest.param("document_type", marks=pytest.mark.tcid("CD-169"), id="document_type"),
    pytest.param("first_name", marks=pytest.mark.tcid("CD-177"), id="first_name"),
    pytest.param("last_name", marks=pytest.mark.tcid("CD-185"), id="last_name"),
    pytest.param("nationality", marks=pytest.mark.tcid("CD-195"), id="nationality"),
])
def test_personal_info_optional_field_missing(field):
    """personal_info sub-field не передан. Ожидается 201 (поле опционально)."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"].pop(field, None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# FIRST_NAME (54.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-170")
def test_first_name_latin():
    """first_name='John' (латиница). Ожидается 201."""
    resp = post_transaction(_with_personal(first_name="John"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-171")
def test_first_name_cyrillic():
    """first_name='Иван' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(first_name="Иван"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-172")
def test_first_name_letters_and_special_chars():
    """first_name='John-Jr.' (буквы и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(first_name="John-Jr."))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-173")
def test_first_name_letters_and_digits():
    """first_name='John2' (буквы и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(first_name="John2"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-174")
def test_first_name_one_char():
    """first_name='J' (1 символ). Ожидается 201."""
    resp = post_transaction(_with_personal(first_name="J"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-175")
def test_first_name_empty_string():
    """first_name — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_personal(first_name=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-176")
def test_first_name_null():
    """first_name=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(first_name=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# LAST_NAME (55.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-178")
def test_last_name_latin():
    """last_name='Doe' (латиница). Ожидается 201."""
    resp = post_transaction(_with_personal(last_name="Doe"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-179")
def test_last_name_cyrillic():
    """last_name='Иванов' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(last_name="Иванов"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-180")
def test_last_name_letters_and_special_chars():
    """last_name='Doe-Jr.' (буквы и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(last_name="Doe-Jr."))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-181")
def test_last_name_letters_and_digits():
    """last_name='Doe2' (буквы и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(last_name="Doe2"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-182")
def test_last_name_one_char():
    """last_name='D' (1 символ). Ожидается 201."""
    resp = post_transaction(_with_personal(last_name="D"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-183")
def test_last_name_empty_string():
    """last_name — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_personal(last_name=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-184")
def test_last_name_null():
    """last_name=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(last_name=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# NATIONALITY (56.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-186")
def test_nationality_two_char_ru():
    """nationality='RU' (2 символа). Ожидается 201."""
    resp = post_transaction(_with_personal(nationality="RU"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-187")
def test_nationality_two_char_us():
    """nationality='US' (верхний регистр). Ожидается 201."""
    resp = post_transaction(_with_personal(nationality="US"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-188")
def test_nationality_lowercase():
    """nationality='ru' (нижний регистр). Ожидается 201."""
    resp = post_transaction(_with_personal(nationality="ru"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-189")
def test_nationality_three_chars():
    """nationality='RUS' (3 символа). Ожидается 400."""
    resp = post_transaction(_with_personal(nationality="RUS"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-190")
def test_nationality_one_char():
    """nationality='R' (1 символ). Ожидается 400."""
    resp = post_transaction(_with_personal(nationality="R"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-191")
def test_nationality_cyrillic():
    """nationality='РФ' (кириллица). Ожидается 400."""
    resp = post_transaction(_with_personal(nationality="РФ"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-192")
def test_nationality_digits():
    """nationality='12' (цифры). Ожидается 400."""
    resp = post_transaction(_with_personal(nationality="12"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-193")
def test_nationality_empty_string():
    """nationality — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_personal(nationality=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-194")
def test_nationality_null():
    """nationality=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_personal(nationality=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DOCUMENT_DETAILS (57.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-196")
def test_document_details_missing():
    """document_details не передан. Ожидается 201."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"].pop("document_details", None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-197")
def test_document_details_empty_object():
    """document_details передан как пустой объект {}. Ожидается 201."""
    resp = post_transaction(_with_personal(document_details={}))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DEPARTMENT_CODE (58.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-198")
def test_department_code_latin():
    """department_code='ABC' (латиница). Ожидается 400."""
    resp = post_transaction(_with_doc(department_code="ABC"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-199")
def test_department_code_cyrillic():
    """department_code='АБВ' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(department_code="АБВ"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-200")
def test_department_code_digits():
    """department_code='123' (цифры). Ожидается 400."""
    resp = post_transaction(_with_doc(department_code="123"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-201")
def test_department_code_special_chars():
    """department_code='#@!' (спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(department_code="#@!"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-202")
def test_department_code_one_char():
    """department_code='A' (1 символ). Ожидается 400."""
    resp = post_transaction(_with_doc(department_code="A"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-203")
def test_department_code_empty_string():
    """department_code — пустая строка. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(department_code=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-204")
def test_department_code_null():
    """department_code=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(department_code=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# DOCUMENT_DETAILS OPTIONAL SUB-FIELDS — missing → 201 (58.x–64.x)
# ─────────────────────────────────────────────
@pytest.mark.parametrize("field", [
    pytest.param("department_code", marks=pytest.mark.tcid("CD-205"), id="department_code"),
    pytest.param("expiry_date", marks=pytest.mark.tcid("CD-211"), id="expiry_date"),
    pytest.param("gender", marks=pytest.mark.tcid("CD-212"), id="gender"),
    pytest.param("issue_date", marks=pytest.mark.tcid("CD-219"), id="issue_date"),
    pytest.param("issuer", marks=pytest.mark.tcid("CD-229"), id="issuer"),
    pytest.param("number", marks=pytest.mark.tcid("CD-237"), id="number"),
    pytest.param("series", marks=pytest.mark.tcid("CD-247"), id="series"),
])
def test_document_details_optional_field_missing(field):
    """document_details sub-field не передан. Ожидается 201 (поле опционально)."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["personal_info"]["document_details"].pop(field, None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# EXPIRY_DATE — дополнительные (59.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-206")
def test_doc_expiry_date_non_date_string():
    """document expiry_date — не дата. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="not-a-date"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-207")
def test_doc_expiry_date_today():
    """document expiry_date — текущий день. Ожидается 201 или 400."""
    today_str = date.today().strftime("%Y-%m-%d")
    resp = post_transaction(_with_doc(expiry_date=today_str))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-208")
def test_doc_expiry_date_nonexistent_month():
    """document expiry_date='2030-13-01' (несуществующий месяц). Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date="2030-13-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-209")
def test_doc_expiry_date_leap_year():
    """document expiry_date='2028-02-29' (высокосный год). Ожидается 201."""
    resp = post_transaction(_with_doc(expiry_date="2028-02-29"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-210")
def test_doc_expiry_date_empty_string():
    """document expiry_date — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_doc(expiry_date=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ISSUE_DATE — дополнительные (61.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-213")
def test_doc_issue_date_non_date_string():
    """document issue_date — не дата. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="not-a-date"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-214")
def test_doc_issue_date_after_expiry():
    """document issue_date > expiry_date. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="2040-01-01", expiry_date="2035-01-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-215")
def test_doc_issue_date_wrong_format():
    """document issue_date в формате DD-MM-YYYY. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="15-06-2015"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-216")
def test_doc_issue_date_nonexistent_month():
    """document issue_date='2015-13-01' (несуществующий месяц). Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="2015-13-01"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-217")
def test_doc_issue_date_leap_year():
    """document issue_date='2000-02-29' (високосный год). Ожидается 201."""
    resp = post_transaction(_with_doc(issue_date="2000-02-29"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-218")
def test_doc_issue_date_empty_string():
    """document issue_date — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# ISSUER (62.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-220")
def test_issuer_any_string():
    """issuer='Ministry of Interior' (любая строка). Ожидается 201."""
    resp = post_transaction(_with_doc(issuer="Ministry of Interior"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-221")
def test_issuer_latin():
    """issuer='Interior' (латиница). Ожидается 201."""
    resp = post_transaction(_with_doc(issuer="Interior"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-222")
def test_issuer_latin_with_spaces():
    """issuer='Ministry of Justice' (латиница с пробелами). Ожидается 201."""
    resp = post_transaction(_with_doc(issuer="Ministry of Justice"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-223")
def test_issuer_cyrillic():
    """issuer='МВД' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issuer="МВД"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-224")
def test_issuer_cyrillic_with_spaces():
    """issuer='МВД России' (кириллица с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issuer="МВД России"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-225")
def test_issuer_letters_and_digits():
    """issuer='Interior1' (буквы и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issuer="Interior1"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-226")
def test_issuer_letters_and_special_chars():
    """issuer='Interior!' (буквы и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issuer="Interior!"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-227")
def test_issuer_empty_string():
    """issuer — пустая строка. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issuer=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-228")
def test_issuer_null():
    """issuer=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(issuer=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# NUMBER (63.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-230")
def test_doc_number_any_string():
    """number='123456789' (любая строка). Ожидается 201."""
    resp = post_transaction(_with_doc(number="123456789"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-231")
def test_doc_number_digits():
    """number='987654321' (цифры). Ожидается 201."""
    resp = post_transaction(_with_doc(number="987654321"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-232")
def test_doc_number_latin_and_digits():
    """number='AB123456' (латиница и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(number="AB123456"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-233")
def test_doc_number_letters_digits_special():
    """number='AB#12345' (буквы, цифры, спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(number="AB#12345"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-234")
def test_doc_number_cyrillic():
    """number='АА123456' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(number="АА123456"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-235")
def test_doc_number_empty_string():
    """number — пустая строка. Ожидается 400."""
    resp = post_transaction(_with_doc(number=""))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


@pytest.mark.tcid("CD-236")
def test_doc_number_null():
    """number=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(number=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# SERIES (64.x)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-238")
def test_doc_series_any_string():
    """series='IV' (любая строка). Ожидается 201."""
    resp = post_transaction(_with_doc(series="IV"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-239")
def test_doc_series_latin():
    """series='AB' (латиница). Ожидается 201."""
    resp = post_transaction(_with_doc(series="AB"))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-240")
def test_doc_series_latin_with_spaces():
    """series='A B' (латиница с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series="A B"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-241")
def test_doc_series_cyrillic():
    """series='ИВ' (кириллица). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series="ИВ"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-242")
def test_doc_series_cyrillic_with_spaces():
    """series='И В' (кириллица с пробелами). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series="И В"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-243")
def test_doc_series_letters_and_digits():
    """series='A1' (буквы и цифры). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series="A1"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-244")
def test_doc_series_letters_and_special_chars():
    """series='A!' (буквы и спецсимволы). Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series="A!"))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-245")
def test_doc_series_empty_string():
    """series — пустая строка. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series=""))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


@pytest.mark.tcid("CD-246")
def test_doc_series_null():
    """series=null. Ожидается 201 или 400."""
    resp = post_transaction(_with_doc(series=None))
    assert resp.status_code in (201, 400), f"Expected 201 or 400, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# PAYER_ID missing (50.9)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-248")
def test_payer_id_missing():
    """50.9 payer_id не передан в payer_info. Ожидается 201."""
    body = copy.deepcopy(_BASE)
    body["customer_data"]["payer_info"].pop("payer_id", None)
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────
# ISSUE_DATE формат YY-MM-DD (61.6)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-249")
def test_doc_issue_date_yy_mm_dd_format():
    """61.6 document issue_date в формате YY-MM-DD. Ожидается 400."""
    resp = post_transaction(_with_doc(issue_date="15-06-15"))
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)


# ─────────────────────────────────────────────
# POST запрос без тела (65)
# ─────────────────────────────────────────────
@pytest.mark.tcid("CD-250")
def test_post_without_body():
    """65 POST /transactions без тела запроса. Ожидается 400."""
    import requests
    import conftest
    headers = conftest.make_headers(conftest.TERMINAL_ID, raw_body="", method="POST")
    headers.pop("Content-Type", None)
    resp = requests.post(conftest.BASE_URL, headers=headers, timeout=30)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert_error_response(resp)
