CUSTOMER_DATA = {
    "contact_info": {
        "email": "user@example.com",
        "phone": "+19991231212",
        "country": "US",
        "city": "New York",
        "zip": "10001",
        "state": "NY",
    },
    "personal_info": {
        "first_name": "John",
        "last_name": "Doe",
        "date_of_birth": "1990-05-25",
        "nationality": "JP",
        "document_type": "passport",
        "document_details": {
            "number": "11223344",
            "issue_date": "2020-05-25",
            "expiry_date": "2030-05-25",
            "gender": "M",
            "issuer": "string",
            "department_code": "032-018",
            "series": "string",
        },
    },
    "browser_info": {
        "screen_height": 1080,
        "screen_width": 1920,
        "time_zone": -120,
        "color_depth": 24,
        "user_agent": "Mozilla/5.0",
        "accept_header": "application/json",
        "java_enabled": False,
        "java_script_enabled": True,
        "ip": "192.168.1.1",
        "language": "ru",
    },
    "payer_info": {"payer_id": "payer_abc123"},
}

MERCHANT_DATA = {
    "order_id": "order_1111",
    "description": "Order payment",
    "webhook_url": "https://merchant.com/webhook",
    "return_url": "https://merchant.com/return",
}

# Non-3DS, success (Mastercard)
CARD_DETAILS = {
    "pan": "5413000000000000",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# Non-3DS, decline (Visa)
CARD_DECLINE = {
    "pan": "4716000000000007",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# 3DS challenge, success (Visa)
CARD_3DS = {
    "pan": "4539000000000002",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# 3DS challenge, decline (MIR)
CARD_3DS_DECLINE = {
    "pan": "2204000000000000",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# 3DS redirect, success (Visa)
CARD_3DS_REDIRECT = {
    "pan": "4929000000000000",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# 3DS redirect, decline (Visa)
CARD_3DS_REDIRECT_DECLINE = {
    "pan": "4556000000000000",
    "holder": "JOHN DOE",
    "expiry_month": "05",
    "expiry_year": "27",
    "cvv": "666",
}

# Async card (Case 4): NEW->PENDING->(CHARGED|REJECTED), delay = amount in seconds (max 20s).
CARD_ASYNC = {**CARD_DETAILS, "pan": "4242424242424242"}

CARDS = {
    "default":               CARD_DETAILS,
    "decline":               CARD_DECLINE,
    "3ds":                   CARD_3DS,
    "3ds_decline":           CARD_3DS_DECLINE,
    "3ds_redirect":          CARD_3DS_REDIRECT,
    "3ds_redirect_decline":  CARD_3DS_REDIRECT_DECLINE,
    "async":                 CARD_ASYNC,
}

THREED = {"challenge_window_size": "05"}
