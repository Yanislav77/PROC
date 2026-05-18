import time

import pytest

from conftest import post


class TestPayinCard:
    def test_payin_card_success(self, card_payin_payload):
        response = post(body=card_payin_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")
        assert "transaction_id" in data

    def test_payin_card_returns_transaction_id(self, card_payin_payload):
        response = post(body=card_payin_payload)
        data = response.json()
        assert isinstance(data.get("transaction_id"), str)
        assert len(data["transaction_id"]) > 0


class TestPayinP2P:
    def test_payin_p2p_success(self, p2p_payin_payload):
        response = post(body=p2p_payin_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")

    def test_payin_p2p_returns_payment_url(self, p2p_payin_payload):
        response = post(body=p2p_payin_payload)
        data = response.json()
        assert "payment_url" in data or "transaction_id" in data


class TestPayinMobile:
    def test_payin_mobile_success(self, mobile_payin_payload):
        response = post(body=mobile_payin_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")

    def test_payin_mobile_returns_transaction_id(self, mobile_payin_payload):
        response = post(body=mobile_payin_payload)
        data = response.json()
        assert "transaction_id" in data


class TestPayinBlock:
    def test_payin_block_success(self, block_payin_payload):
        response = post(body=block_payin_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "authorized")

    def test_payin_block_amount_held(self, block_payin_payload):
        response = post(body=block_payin_payload)
        data = response.json()
        assert "transaction_id" in data


class TestRecurrent:
    def test_recurrent_charge_success(self, recurrent_payload):
        response = post(body=recurrent_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")

    def test_recurrent_returns_transaction_id(self, recurrent_payload):
        response = post(body=recurrent_payload)
        data = response.json()
        assert "transaction_id" in data


class TestPayout:
    def test_payout_success(self, payout_payload):
        response = post(body=payout_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")

    def test_payout_returns_transaction_id(self, payout_payload):
        response = post(body=payout_payload)
        data = response.json()
        assert "transaction_id" in data


class TestRebill:
    def test_rebill_success(self, rebill_payload):
        response = post(body=rebill_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")

    def test_rebill_returns_transaction_id(self, rebill_payload):
        response = post(body=rebill_payload)
        data = response.json()
        assert "transaction_id" in data


class TestRebillBlock:
    def test_rebill_block_success(self, rebill_block_payload):
        response = post(body=rebill_block_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "authorized")

    def test_rebill_block_returns_transaction_id(self, rebill_block_payload):
        response = post(body=rebill_block_payload)
        data = response.json()
        assert "transaction_id" in data


class TestRefund:
    def test_refund_success(self, card_payin_payload):
        payin = post(body=card_payin_payload)
        assert payin.status_code == 200
        transaction_id = payin.json().get("transaction_id")

        refund_payload = {
            "type": "refund",
            "transaction_id": transaction_id,
            "amount": card_payin_payload["amount"],
            "order_id": f"order-refund-{int(time.time())}",
        }
        response = post(body=refund_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")

    def test_refund_partial(self, card_payin_payload):
        payin = post(body=card_payin_payload)
        assert payin.status_code == 200
        transaction_id = payin.json().get("transaction_id")

        refund_payload = {
            "type": "refund",
            "transaction_id": transaction_id,
            "amount": card_payin_payload["amount"] // 2,
            "order_id": f"order-refund-partial-{int(time.time())}",
        }
        response = post(body=refund_payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ("success", "pending", "processing")
