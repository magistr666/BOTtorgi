# YoBit Futures Bot — риск-менеджмент и валидация

## Лимиты и проверки перед Trade
- Notional: QTY * PRICE ≤ MAX_NOTIONAL_PER_ORDER_USD (по умолчанию 50 USD)
- Плечо: 1 ≤ LEVERAGE ≤ MAX_LEVERAGE (по умолчанию 20)
- DRY_RUN: true — только логирование/email, без Trade
- MAX_ORDERS: ограничение числа активных ордеров на пару
- SYMBOL: только разрешённые пары (белый список)

## Расчёт лота от капитала
- capital = free + locked по CAPITAL_ASSET
- notional = capital * RISK_PERCENT / 100
- qty = notional / цена
- Ограничения: MIN_QTY ≤ qty ≤ MAX_QTY (0 = без ограничения)
- Округление вниз до STEP_SIZE (шаг лота биржи)

## Расписание
- SCHEDULE=24/7 — торговля всегда
- SCHEDULE=WINDOWS + TRADE_WINDOWS="10:00-18:00,20:00-22:00"
- Поддержка окон, пересекающих полночь (например 22:00-02:00)

## Проверка маржи (консервативно)
- equity ≈ свободные средства + PnL
- margin_used ≈ notional / LEVERAGE
- buffer = 10–20%
- Отклонять, если margin_used * (1 + buffer) > equity

## SL/TP
- SL_PRICE/TP_PRICE: алерты и email при достижении цены
- Для BOTH: поддерживать LONG и/или SHORT по необходимости

## Уведомления
- Email через SMTP (SSL/TLS), MAIL_TO
- Тема/тело: сделки, алерты SL/TP, ошибки
- MIN_EMAIL_INTERVAL_SEC — защита от спама (по умолчанию 60 с)

## Безопасность
- Ключи только с правами торговли; храните в .env вне VCS
- IP-ограничения по возможности
- Начинайте с DRY_RUN=true и малого объёма