"""
Тесты эндпоинтов действий над сессией:
  POST /api/v1/payment-sessions/{payment_token}/actions/transfer/cancel          (аналог /payments/{payment_token}/cancellation-by-user)
  POST /api/v1/payment-sessions/{payment_token}/actions/transfer/change-requisite (аналог /payments/{payment_token}/reselect)
  POST /api/v1/payment-sessions/{payment_token}/actions/transfer/confirm         (аналог /payments/{payment_token}/user_action)
"""
