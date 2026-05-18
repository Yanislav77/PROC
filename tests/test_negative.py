import hashlib
import hmac
import json
import time

import pytest
import requests

from conftest import BASE_URL, TERMINAL_ID, post, auth_headers


class TestMissingRequiredFields:
    def test_missing_type(self, card_payin_payload):
        payload = {k: v for k, v in card_payin_payload.items() if k != "type"}
        response = post(body=payload)
        assert response.status_code in (400, 422)
        data = response.json()
        assert "error" in data or "message" in data

    def test_missing_amount(self, card_payin_payload):
        payload = {k: v for k, v in card_payin_payload.items() if k != "amount"}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_missing_currency(self, card_payin_payload):
        payload = {k: v for k, v in card_payin_payload.items() if k != "currency"}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_missing_order_id(self, card_payin_payload):
        payload = {k: v for k, v in card_payin_payload.items() if k != "order_id"}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_missing_card_number(self, card_payin_payload):
        payload = card_payin_payload.copy()
        payload["card"] = {k: v for k, v in payload["card"].items() if k != "number"}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_empty_body(self):
        response = post(body={})
        assert response.status_code in (400, 422)


class TestInvalidValues:
    def test_invalid_card_number(self, card_payin_payload):
        payload = card_payin_payload.copy()
        payload["card"] = {**payload["card"], "number": "0000000000000000"}
        response = post(body=payload)
        assert response.status_code in (400, 422, 200)
        if response.status_code == 200:
            assert response.json().get("status") in ("declined", "error", "failed")

    def test_negative_amount(self, card_payin_payload):
        payload = {**card_payin_payload, "amount": -100}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_zero_amount(self, card_payin_payload):
        payload = {**card_payin_payload, "amount": 0}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_invalid_currency(self, card_payin_payload):
        payload = {**card_payin_payload, "currency": "XXX"}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_expired_card(self, card_payin_payload):
        payload = card_payin_payload.copy()
        payload["card"] = {**payload["card"], "exp_year": "2020", "exp_month": "01"}
        response = post(body=payload)
        assert response.status_code in (400, 422, 200)
        if response.status_code == 200:
            assert response.json().get("status") in ("declined", "error", "failed")

    def test_invalid_cvv(self, card_payin_payload):
        payload = card_payin_payload.copy()
        payload["card"] = {**payload["card"], "cvv": "99"}
        response = post(body=payload)
        assert response.status_code in (400, 422)

    def test_invalid_type(self, card_payin_payload):
        payload = {**card_payin_payload, "type": "unknown_type"}
        response = post(body=payload)
        assert response.status_code in (400, 422)


class TestInvalidSignature:
    def _post_with_bad_signature(self, body: dict, bad_sig: str) -> requests.Response:
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "Api-Terminal-ID": TERMINAL_ID,
            "Api-Timestamp": timestamp,
            "Api-Signature": bad_sig,
        }
        return requests.post(BASE_URL, json=body, headers=headers)

    def test_wrong_signature(self, card_payin_payload):
        response = self._post_with_bad_signature(card_payin_payload, "invalidsignature")
        assert response.status_code in (401, 403)

    def test_empty_signature(self, card_payin_payload):
        response = self._post_with_bad_signature(card_payin_payload, "")
        assert response.status_code in (400, 401, 403)

    def test_missing_terminal_id(self, card_payin_payload):
        timestamp = str(int(time.time()))
        body_str = json.dumps(card_payin_payload, separators=(",", ":"))
        headers = {
            "Content-Type": "application/json",
            "Api-Timestamp": timestamp,
            "Api-Signature": "somesig",
        }
        response = requests.post(BASE_URL, json=card_payin_payload, headers=headers)
        assert response.status_code in (400, 401, 403)

    def test_missing_timestamp_header(self, card_payin_payload):
        headers = {
            "Content-Type": "application/json",
            "Api-Terminal-ID": TERMINAL_ID,
            "Api-Signature": "somesig",
        }
        response = requests.post(BASE_URL, json=card_payin_payload, headers=headers)
        assert response.status_code in (400, 401, 403)

    def test_tampered_body(self, card_payin_payload):
        """Signature computed for original body but different body is sent."""
        timestamp = str(int(time.time()))
        original_body_str = json.dumps(card_payin_payload, separators=(",", ":"))
        message = "\n".join(["POST", TERMINAL_ID, timestamp, original_body_str]).encode()
        from conftest import SECRET_KEY
        sig = hmac.new(SECRET_KEY, message, hashlib.sha256).hexdigest()

        tampered = {**card_payin_payload, "amount": 99999}
        headers = {
            "Content-Type": "application/json",
            "Api-Terminal-ID": TERMINAL_ID,
            "Api-Timestamp": timestamp,
            "Api-Signature": sig,
        }
        response = requests.post(BASE_URL, json=tampered, headers=headers)
        assert response.status_code in (401, 403)


class TestIdempotency:
    def test_duplicate_order_id_rejected(self, card_payin_payload):
        """Same order_id sent twice — second request must be deduplicated."""
        first = post(body=card_payin_payload)
        assert first.status_code == 200

        second = post(body=card_payin_payload)
        assert second.status_code in (200, 409)
        if second.status_code == 200:
            first_id = first.json().get("transaction_id")
            second_id = second.json().get("transaction_id")
            assert first_id == second_id, "Duplicate order_id must return the same transaction"

    def test_idempotency_different_amount_rejected(self, card_payin_payload):
        """Same order_id but different amount — must be rejected."""
        first = post(body=card_payin_payload)
        assert first.status_code == 200

        conflicting = {**card_payin_payload, "amount": card_payin_payload["amount"] + 1}
        second = post(body=conflicting)
        assert second.status_code in (400, 409, 422)

    def test_unique_order_ids_both_accepted(self):
        """Two requests with distinct order_ids — both must succeed."""
        base = {
            "type": "payin",
            "method": "card",
            "amount": 100,
            "currency": "USD",
            "card": {
                "number": "4111111111111111",
                "exp_month": "12",
                "exp_year": "2030",
                "cvv": "123",
            },
            "customer": {"name": "Test User", "email": "test@example.com"},
        }
        first = post(body={**base, "order_id": f"unique-{int(time.time())}-1"})
        second = post(body={**base, "order_id": f"unique-{int(time.time())}-2"})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json().get("transaction_id") != second.json().get("transaction_id")
