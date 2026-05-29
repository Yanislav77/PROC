"""
Тесты gate-эндпоинтов (возврат со страницы банка):
  GET  /api/v1/payment-sessions/{payment_token}/gate/redirect        (аналог /payments/{payment_token}/redirect)
  POST /api/v1/payment-sessions/{payment_token}/gate/return/data     (аналог /payments/{payment_token}/confirm)
  GET  /api/v1/payment-sessions/{payment_token}/gate/return/no-data  (объединяет confirm_void GET и confirm_void_no_body POST)
"""
