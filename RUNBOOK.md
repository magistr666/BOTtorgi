# YoBit Futures Bot — инструкция по запуску и тесту

## 1) Установка
- Установите Python 3.11+ и добавьте в PATH.
- В PowerShell, в папке C:\yobit_bot:
  pip install -U pip
  pip install python-dotenv requests

## 2) Ключи
- В личном кабинете YoBit создайте API-ключ с правами «Торговля» (Trade).
- Скопируйте Key и Secret в .env (YOBIT_API_KEY, YOBIT_SECRET).
- Не коммитьте .env.

## 3) Настройка .env
- SYMBOL=BTC_USD, LEVERAGE=2, SIDE=BUY, ORDER_TYPE=LIMIT
- QTY=0 (авто от капитала) или фиксированное значение
- PRICE= пусто (текущая цена)
- SL_PRICE=, TP_PRICE= (алерты)
- CAPITAL_ASSET=USD, RISK_PERCENT=20
- SCHEDULE=24/7 или TRADE_WINDOWS=
- SMTP_* для email-уведомлений
- DRY_RUN=true, MODE=monitor

## 4) Мониторинг
- MODE=monitor, DRY_RUN=true → python bot.py
- Проверьте bot.log: баланс, цена, нет ошибок.

## 5) Тест торговли (dry-run)
- MODE=trade, DRY_RUN=true
- Проверьте SYMBOL, RISK_PERCENT, LEVERAGE, MAX_NOTIONAL
- python bot.py → в логе «DRY_RUN: PLACE ...»

## 6) Реальная сделка (малый объём)
- DRY_RUN=false
- Малый RISK_PERCENT, LIMIT по цене чуть хуже рынка
- python bot.py → проверьте ActiveOrders/email

## 7) Расписание
- SCHEDULE=24/7 — всегда
- SCHEDULE=WINDOWS, TRADE_WINDOWS="10:00-18:00,20:00-22:00"
- Вне окна бот пропускает сделки (лог «Вне торгового окна»)

## 8) Email-уведомления
- SMTP_HOST=smtp.yandex.ru, SMTP_PORT=465, EMAIL_SSL=true
- SMTP_USER, SMTP_PASS (для Яндекс — пароль приложения)
- MAIL_TO — получатель
- Проверьте отправку письма при DRY_RUN-сделке

## 9) Частые ошибки
- Ошибка подписи: Secret полностью, без пробелов
- Nonce: точное время на ПК
- Nonce too low: подождите/перезапустите
- Недостаточно маржи: уменьшите QTY/LEVERAGE
- Notional превышен: уменьшите RISK_PERCENT/QTY

## 10) Чек-лист перед реальной сделкой
- DRY_RUN=false, MODE=trade
- SYMBOL/SIDE/ORDER_TYPE/QTY/LEVERAGE корректны
- Notional ≤ MAX_NOTIONAL_PER_ORDER_USD
- SL/TP заданы при необходимости
- Email настроен и проверен
- В логе нет ошибок авторизации