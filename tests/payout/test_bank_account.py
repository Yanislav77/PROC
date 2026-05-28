"""
Тесты выплат методом bank_account (type=payout, method=bank_account).
"""
import pytest

from conftest import (
    post_transaction,
    MERCHANT_DATA,
    CUSTOMER_DATA,
    THREED,
    assert_transaction_response,
    assert_error_response,
    gen_order_id,
)

_BASE = {
    "type": "payout",
    "merchant_data": {**MERCHANT_DATA, "order_id": "order_payout_test"},
    "financial_data": {"amount": 1000, "currency": "RUB"},
    "flow_data": {"is_recurrent": False, "capture_mode": "auto", "threed_secure": THREED},
    "customer_data": CUSTOMER_DATA,
}

_VALID = {**_BASE, "transaction_data": {"method": "sbp"}}


def _assert_payout_ok(resp):
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert_transaction_response(data)
    assert data["type"] == "payout"
    return data


def _ba(order_id, **fields):
    """Payout bank_account с переданными полями details."""
    return {
        **_BASE,
        "merchant_data": {**MERCHANT_DATA, "order_id": order_id},
        "transaction_data": {"method": "bank_account", "details": dict(fields)},
    }


# ─────────────────────────────────────────────
# HAPPY PATH
# ─────────────────────────────────────────────
@pytest.mark.tcid("PY-009")
def test_payout_bank_account():
    """Выплата на банковский счёт с SWIFT-реквизитами."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "bank_account",
            "details": {
                "account_number": "40702810000000012345",
                "swift_code": "SABRRUMM",
                "bank_name": "Sberbank",
                "account_holder_name": "JOHN DOE",
            },
        },
    }
    _assert_payout_ok(post_transaction(body))


@pytest.mark.tcid("PY-010")
def test_payout_bank_account_pix():
    """Выплата через PIX (Бразилия)."""
    body = {
        **_BASE,
        "transaction_data": {
            "method": "bank_account",
            "details": {"pix_key": "user@example.com", "account_holder_name": "JOHN DOE"},
        },
    }
    _assert_payout_ok(post_transaction(body))


@pytest.mark.tcid("PY-011")
def test_payout_bank_account_minimal():
    """Выплата на банковский счёт без details — все поля BankAccountDetails необязательны."""
    body = {**_BASE, "transaction_data": {"method": "bank_account"}}
    _assert_payout_ok(post_transaction(body))


@pytest.mark.tcid("PY-110")
def test_payout_bank_account_no_account_number():
    """bank_account.details без account_number — все поля необязательны. Ожидается 201."""
    body = {**_VALID, "transaction_data": {"method": "bank_account", "details": {
        "swift_code": "SABRRUMM",
        "bank_name": "Sberbank",
        "account_holder_name": "JOHN DOE",
    }}}
    resp = post_transaction(body)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# BankAccountDetails validation tests (PY-121..PY-141)
# ---------------------------------------------------------------------------
@pytest.mark.tcid("PY-121")
def test_payout_bank_account_account_number_empty_string():
    """BankAccountDetails.account_number = "" (пустая строка). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_acn_empty"), account_number=""))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-122")
def test_payout_bank_account_account_number_null():
    """BankAccountDetails.account_number = null. Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_acn_null"), account_number=None))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-123")
def test_payout_bank_account_account_number_integer_returns_400():
    """BankAccountDetails.account_number = integer (не строка). Ожидается 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_acn_int"), account_number=40702810000000012345))
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-124")
def test_payout_bank_account_swift_code_8_chars():
    """BankAccountDetails.swift_code = 8 символов (стандартный BIC). Ожидается 201."""
    resp = post_transaction(_ba(gen_order_id("py_ba_swift8"), swift_code="SABRRUMM"))
    assert resp.status_code == 201


@pytest.mark.tcid("PY-125")
def test_payout_bank_account_swift_code_11_chars():
    """BankAccountDetails.swift_code = 11 символов (расширенный BIC). Ожидается 201."""
    resp = post_transaction(_ba(gen_order_id("py_ba_swift11"), swift_code="SABRRUMM123"))
    assert resp.status_code == 201


@pytest.mark.tcid("PY-126")
def test_payout_bank_account_swift_code_too_short():
    """BankAccountDetails.swift_code слишком короткий (3 символа). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_swift_short"), swift_code="SAB"))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-127")
def test_payout_bank_account_swift_code_empty_string():
    """BankAccountDetails.swift_code = "" (пустая строка). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_swift_empty"), swift_code=""))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-128")
def test_payout_bank_account_swift_code_null():
    """BankAccountDetails.swift_code = null. Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_swift_null"), swift_code=None))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-129")
def test_payout_bank_account_holder_name_empty_string():
    """BankAccountDetails.account_holder_name = "" (пустая строка). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_ahn_empty"), account_holder_name=""))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-130")
def test_payout_bank_account_holder_name_null():
    """BankAccountDetails.account_holder_name = null. Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_ahn_null"), account_holder_name=None))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-131")
def test_payout_bank_account_holder_name_cyrillic():
    """BankAccountDetails.account_holder_name = кириллица. Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_ahn_cyr"), account_holder_name="ИВАН ИВАНОВ"))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-132")
def test_payout_bank_account_holder_name_integer_returns_400():
    """BankAccountDetails.account_holder_name = integer (не строка). Ожидается 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_ahn_int"), account_holder_name=12345))
    assert resp.status_code == 400
    assert_error_response(resp)


@pytest.mark.tcid("PY-133")
def test_payout_bank_account_pix_key_phone():
    """BankAccountDetails.pix_key = телефонный номер. Ожидается 201."""
    resp = post_transaction(_ba(gen_order_id("py_ba_pix_phone"), pix_key="+5511999999999"))
    assert resp.status_code == 201


@pytest.mark.tcid("PY-134")
def test_payout_bank_account_pix_key_cpf():
    """BankAccountDetails.pix_key = CPF (бразильский идентификатор). Ожидается 201."""
    resp = post_transaction(_ba(gen_order_id("py_ba_pix_cpf"), pix_key="123.456.789-09"))
    assert resp.status_code == 201


@pytest.mark.tcid("PY-135")
def test_payout_bank_account_pix_key_empty_string():
    """BankAccountDetails.pix_key = "" (пустая строка). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_pix_empty"), pix_key=""))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-136")
def test_payout_bank_account_ifsc_code_valid():
    """BankAccountDetails.ifsc_code = валидный IFSC. Ожидается 201."""
    resp = post_transaction(_ba(gen_order_id("py_ba_ifsc"), ifsc_code="SBIN0001234"))
    assert resp.status_code == 201


@pytest.mark.tcid("PY-137")
def test_payout_bank_account_ifsc_code_empty_string():
    """BankAccountDetails.ifsc_code = "" (пустая строка). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_ifsc_empty"), ifsc_code=""))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-138")
def test_payout_bank_account_bank_name_empty_string():
    """BankAccountDetails.bank_name = "" (пустая строка). Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_bn_empty"), bank_name=""))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-139")
def test_payout_bank_account_bank_name_null():
    """BankAccountDetails.bank_name = null. Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_bn_null"), bank_name=None))
    assert resp.status_code in (201, 400)


@pytest.mark.tcid("PY-140")
def test_payout_bank_account_all_fields_happy_path():
    """BankAccountDetails со всеми полями одновременно. Ожидается 201."""
    resp = post_transaction(_ba(
        gen_order_id("py_ba_all"),
        account_number="40702810000000012345",
        ifsc_code="SBIN0001234",
        swift_code="SABRRUMM",
        bank_name="Sberbank",
        document_number="1234567890",
        account_holder_name="JOHN DOE",
        account_agency_number="0001",
        account_type_code="CC",
        pix_key="+5511999999999",
        pay_mode="NEFT",
        transit_number="12345",
        financial_institution_number="001",
        bank_branch_name="Main Branch",
        bank_branch_code="001",
    ))
    assert resp.status_code == 201


@pytest.mark.tcid("PY-141")
def test_payout_bank_account_unknown_extra_field():
    """BankAccountDetails с неизвестным дополнительным полем. Ожидается 201 или 400."""
    resp = post_transaction(_ba(gen_order_id("py_ba_extra"), unknown_field="surprise"))
    assert resp.status_code in (201, 400)
