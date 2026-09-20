import os, time, hmac, hashlib, logging, math, datetime, json, threading, sys, subprocess
from urllib.parse import urlencode
import requests
from dotenv import load_dotenv
import gui
import vk_control

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, '.env'))

API_KEY = os.getenv('YOBIT_API_KEY') or ''
SECRET = os.getenv('YOBIT_SECRET') or ''
SYMBOL = os.getenv('SYMBOL', 'BTC_USD').lower()
BASE_ASSET, QUOTE_ASSET = SYMBOL.split('_', 1)
LEVERAGE = int(os.getenv('LEVERAGE', '2'))
ORDER_TYPE = os.getenv('ORDER_TYPE', 'LIMIT').upper()
SIDE = os.getenv('SIDE', 'BUY').upper()
QTY_FIXED = float(os.getenv('QTY') or 0)
PRICE = float(os.getenv('PRICE') or 0)
SL_PRICE = float(os.getenv('SL_PRICE') or 0)
TP_PRICE = float(os.getenv('TP_PRICE') or 0)
POLL = int(os.getenv('POLL_INTERVAL_SEC', '5'))
LOG_FILE = os.path.join(BASE_DIR, os.getenv('LOG_FILE', 'bot.log'))
MAX_ORDERS = int(os.getenv('MAX_ORDERS', '5'))
MAX_NOTIONAL = float(os.getenv('MAX_NOTIONAL_PER_ORDER_USD', '50'))
MAX_LEVERAGE = int(os.getenv('MAX_LEVERAGE', '20'))
DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'
MODE = os.getenv('MODE', 'monitor').lower()

CAPITAL_ASSET = os.getenv('CAPITAL_ASSET', QUOTE_ASSET.upper()).upper()
RISK_PERCENT = float(os.getenv('RISK_PERCENT', '20'))
MIN_QTY = float(os.getenv('MIN_QTY', '0'))
MAX_QTY = float(os.getenv('MAX_QTY', '0'))
STEP_SIZE = float(os.getenv('STEP_SIZE', '0.000001'))

SCHEDULE = os.getenv('SCHEDULE', '24/7').upper()
TRADE_WINDOWS = os.getenv('TRADE_WINDOWS', '')

VK_TOKEN = os.getenv('VK_TOKEN', '')
VK_PEER_ID = os.getenv('VK_PEER_ID', '')
VK_API_VERSION = os.getenv('VK_API_VERSION', '5.199')
VK_API_URL = 'https://api.vk.com/method/'

AUTO_COOLDOWN_SEC = int(os.getenv('AUTO_COOLDOWN_SEC', '300'))
SL_PERCENT = float(os.getenv('SL_PERCENT', '5'))
TP_PERCENT = float(os.getenv('TP_PERCENT', '10'))
CLOSE_ORDER_TYPE = os.getenv('CLOSE_ORDER_TYPE', 'MARKET').upper()
STATE_FILE = os.path.join(BASE_DIR, os.getenv('STATE_FILE', 'position.json'))

VK_GROUP_ID = os.getenv('VK_GROUP_ID', '')
VK_ADMIN_IDS = os.getenv('VK_ADMIN_IDS', '')

EXCHANGE = os.getenv('EXCHANGE', 'yobit').lower()
MEXC_API_KEY = os.getenv('MEXC_API_KEY') or ''
MEXC_SECRET = os.getenv('MEXC_SECRET') or ''

TRADE_FEE = float(os.getenv('TRADE_FEE', '0.2'))
REPORT_FILE = os.path.join(BASE_DIR, os.getenv('REPORT_FILE', 'report.json'))

# --- Демо-режим: 0 = без ограничений, N = дней демо ---
DEMO_DAYS = int(os.getenv('DEMO_DAYS', '0'))
DEMO_MARKER = os.path.join(BASE_DIR, '.demo_start')
DEMO_MAX_DAYS = int(os.getenv('DEMO_DAYS', '0'))

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

BASE_PUBLIC = 'https://yobit.net/api/3'
BASE_TRADE = 'https://yobit.net/tapi/'

MEXC_BASE = 'https://api.mexc.com'
MEXC_PUBLIC = 'https://api.mexc.com/api/v3'

WINDOWS = []
if TRADE_WINDOWS:
    for part in TRADE_WINDOWS.split(','):
        part = part.strip()
        if not part:
            continue
        start_s, end_s = part.split('-')
        start = datetime.datetime.strptime(start_s.strip(), '%H:%M').time()
        end = datetime.datetime.strptime(end_s.strip(), '%H:%M').time()
        WINDOWS.append((start, end))

_last_vk = 0.0
_fired_alerts = set()
_nonce_counter = None
_MIN_AMOUNTS = {}
_bot_gui = None
_paused = False


def gui_log(msg, status=None):
    logging.info(msg)
    if _bot_gui is not None:
        _bot_gui.log(msg, status)


def vk_command(text):
    global _paused, SYMBOL, CAPITAL_ASSET
    cmd = text.strip().lower()
    if cmd == 'стоп' or cmd == 'stop' or cmd == 'остановить торговлю':
        _paused = True
        gui_log("Торговля остановлена (команда ВК)", "Пауза")
        return "Торговля остановлена. Для возобновления напишите «Старт»"
    if cmd == 'старт' or cmd == 'start' or cmd == 'возобновить':
        _paused = False
        gui_log("Торговля возобновлена (команда ВК)", "Работаю")
        return "Торговля возобновлена"
    if cmd.startswith('пара ') or cmd.startswith('pair ') or cmd.startswith('set pair '):
        parts = text.split(None, 2)
        if len(parts) < 2:
            return "Укажите пару: пара BTC_USDT"
        new_pair = parts[-1].strip().lower().replace('-', '_')
        if '_' not in new_pair:
            return "Формат: пара BTC_USDT"
        try:
            base, quote = new_pair.split('_', 1)
        except Exception:
            return "Неверный формат. Пример: пара BTC_USDT"
        SYMBOL = new_pair
        CAPITAL_ASSET = quote.upper()
        gui_log(f"Пара изменена на {SYMBOL}", f"Пара: {SYMBOL}")
        state = load_state()
        state['position'] = None
        save_state(state)
        return f"Пара изменена на {SYMBOL.upper()}. Предыдущая позиция сброшена."
    if cmd in ('проверка', 'status', 'статус', 'check'):
        return bot_status()
    if cmd in ('отчёт', 'отчет', 'report', 'прибыль', 'profit'):
        return bot_profit()
    if cmd in ('сделки', 'trade history', 'history', 'история сделок', 'последние сделки'):
        return bot_trades()
    if cmd in ('исполнено', 'исполнено ордера', 'filled', 'executed', 'сколько исполнено'):
        return bot_filled()
    if cmd in ('пары', 'список пар', 'pairs', 'list pairs'):
        return bot_pairs_list()
    if cmd in ('авто пара', 'авто', 'auto pair', 'auto'):
        return bot_auto_pair()
    if cmd.startswith('выбор ') or cmd.startswith('select '):
        return bot_pairs_select(text)
    if cmd in ('команды', 'помощь', 'help', 'справка', 'все команды'):
        return bot_help()

    # Распознавание по первому слову: «проверка как дела» → Проверка
    first = cmd.split()[0] if cmd.split() else ''
    if first in ('проверка', 'статус', 'check', 'статус', 'проверь'):
        return bot_status()
    if first in ('стоп', 'stop', 'пауза'):
        _paused = True
        gui_log("Торговля остановлена (команда ВК)", "Пауза")
        return "Торговля остановлена. Для возобновления напишите «Старт»"
    if first in ('старт', 'start', 'поехали', 'работай'):
        _paused = False
        gui_log("Торговля возобновлена (команда ВК)", "Работаю")
        return "Торговля возобновлена"
    if first in ('отчёт', 'отчет', 'прибыль', 'report'):
        return bot_profit()
    if first in ('сделки', 'сделка', 'history', 'история'):
        return bot_trades()
    if first in ('исполнено', 'исполнение', 'filled'):
        return bot_filled()
    if first in ('пары', 'список'):
        return bot_pairs_list()
    if first in ('команды', 'помощь', 'help'):
        return bot_help()
    return None


def bot_help():
    return "\n".join([
        "Доступные команды:",
        "",
        "Стоп / Старт — пауза и возобновление торговли",
        "Проверка — баланс, цена, текущая позиция",
        "Отчёт — чистая прибыль, ROI, статистика сделок",
        "Сделки — последние закрытые сделки",
        "Исполнено — сколько от текущего ордера исполнено",
        "Пары — список ликвидных пар по номерам",
        "Выбор N — выбрать пару по номеру из списка",
        "Авто пара — бот сам найдёт дешёвую ликвидную пару под баланс",
        "Пара BTC_USDT — сменить пару вручную",
        "",
        "Команды работают на YoBit и MEXC (переключение в .env: EXCHANGE=...).",
    ])


_PAIRS_CACHE = []


def bot_pairs_list():
    global _PAIRS_CACHE
    try:
        pairs = available_pairs()
        _PAIRS_CACHE = pairs
        lines = ["Доступные пары (выберите номер командой «выбор N»):"]
        for i, p in enumerate(pairs, 1):
            lines.append(f"{i}. {p}")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка при получении списка пар: {e}"


def bot_auto_pair():
    global SYMBOL, CAPITAL_ASSET
    try:
        pairs = available_pairs()
        if not pairs:
            return "Не удалось найти пары."
        new_pair = pairs[0]
        SYMBOL = new_pair
        CAPITAL_ASSET = new_pair.split('_', 1)[1].upper()
        gui_log(f"Авто-выбор пары: {SYMBOL}", f"Пара: {SYMBOL}")
        state = load_state()
        state['position'] = None
        state['next_side'] = 'BUY'
        save_state(state)
        return f"Авто-выбор: пара {SYMBOL.upper()} (самая дешёвая активная под баланс)."
    except Exception as e:
        return f"Ошибка авто-выбора пары: {e}"


def bot_pairs_select(text):
    global SYMBOL, CAPITAL_ASSET, _PAIRS_CACHE
    parts = text.split()
    if len(parts) < 2 or not parts[-1].isdigit():
        return "Укажите номер из списка: выбор 3"
    idx = int(parts[-1]) - 1
    if not _PAIRS_CACHE:
        try:
            _PAIRS_CACHE = available_pairs()
        except Exception as e:
            return f"Ошибка: {e}"
    if idx < 0 or idx >= len(_PAIRS_CACHE):
        return "Неверный номер. Напишите «пары» для списка."
    new_pair = _PAIRS_CACHE[idx]
    SYMBOL = new_pair
    CAPITAL_ASSET = new_pair.split('_', 1)[1].upper()
    gui_log(f"Пара изменена на {SYMBOL} (выбор из списка)", f"Пара: {SYMBOL}")
    state = load_state()
    state['position'] = None
    save_state(state)
    return f"Пара изменена на {SYMBOL.upper()}. Предыдущая позиция сброшена."


def available_pairs():
    if EXCHANGE == 'mexc':
        d = mexc_public_get('defaultSymbols', {})
        syms = d.get('data', []) or []
        out = []
        for s in syms:
            if isinstance(s, dict):
                s = s.get('symbol', '')
            s = s.strip()
            if s.endswith('USDT'):
                out.append(s[:-4] + '_USDT')
        return out[:15]
    info = public_get('info')
    pairs = info.get('pairs', {})
    usdt_pairs = []
    for p, meta in pairs.items():
        if p.endswith('_usdt') and (meta.get('hidden') == 0 or meta.get('hidden') is None):
            min_am = float(meta.get('min_amount', 0) or 0)
            if min_am > 0:
                usdt_pairs.append((p, min_am))
    if not usdt_pairs:
        return ['FLOKI_USDT']
    all_prices = {}
    batch = [p for p, _ in usdt_pairs]
    try:
        t = public_get('ticker/' + '-'.join(batch))
    except Exception:
        return ['FLOKI_USDT']
    for p in batch:
        d = t.get(p) or {}
        last = d.get('last') or 0
        buy = d.get('buy') or 0
        vol_cur = d.get('vol_cur') or 0
        all_prices[p] = (float(last), float(buy), float(vol_cur))
    pair_prices = []
    min_usd_vol = float(os.getenv('MIN_PAIR_VOLUME_USD', '1'))
    for p, min_am in usdt_pairs:
        last, buy, vol_cur = all_prices.get(p, (0, 0, 0))
        if last <= 0 or buy <= 0:
            continue
        usd_vol = vol_cur * last
        if usd_vol < min_usd_vol:
            continue
        pair_prices.append((min_am * last, p))
    pair_prices.sort(key=lambda r: r[0])
    if not pair_prices:
        return ['FLOKI_USDT']
    try:
        capital = equity_capital()
        max_cost = max(capital * RISK_PERCENT / 100.0 * LEVERAGE, MAX_NOTIONAL)
        affordable = [p for cost, p in pair_prices if cost <= max_cost]
        best = affordable[0] if affordable else pair_prices[0][1]
    except Exception:
        best = pair_prices[0][1]
    sorted_pairs = [p for _, p in pair_prices]
    if best not in sorted_pairs:
        sorted_pairs.insert(0, best)
    return [p.upper() for p in sorted_pairs[:15]]


def bot_trades():
    try:
        trades = recent_trades(3)
        if not trades:
            return "Сделок пока нет."
        lines = ["Последние сделки:"]
        for t in trades:
            tm = t.get('time')
            tstr = datetime.datetime.fromtimestamp(tm).strftime('%H:%M %d.%m') if tm else '?'
            lines.append(f"{tstr} | {t['side']} {t['amount']:.8g} @ {t['rate']:.6g} = {t['total']:.6g} {CAPITAL_ASSET}")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка при получении сделок: {e}"


def bot_filled():
    try:
        state = load_state()
        pos = state.get('position') or {}
        if not pos:
            return "Сейчас нет открытой позиции."
        qty_target = float(pos.get('qty') or 0)
        side = pos.get('side', '').upper()
        lines = [f"Исполнение ордера {side} {SYMBOL.upper()}"]
        filled_total = 0.0
        if EXCHANGE == 'mexc':
            trades = mexc_my_trades(SYMBOL, 50)
            for t in trades or []:
                if t.get('symbol') == mexc_unify_symbol(SYMBOL):
                    filled_total += float(t.get('qty') or 0)
        else:
            data = trade_api('TradeHistory', {'pair': SYMBOL, 'count': '50', 'order': 'DESC'})
            if data:
                trades = (data.get('trades') or {}).get(SYMBOL, [])
                for t in trades or []:
                    filled_total += float(t.get('amount') or 0)
        filled_total = min(filled_total, qty_target)
        remaining = max(qty_target - filled_total, 0)
        pct = (filled_total / qty_target * 100) if qty_target > 0 else 0
        lines.append(f"Ордер: {qty_target:.8g} {BASE_ASSET.upper()}")
        lines.append(f"Исполнено: {filled_total:.8g} ({pct:.1f}%)")
        lines.append(f"Осталось: {remaining:.8g}")
        if pct >= 99.9:
            lines.append("Статус: полностью исполнен")
        elif pct > 0:
            lines.append("Статус: частично исполнен")
        else:
            lines.append("Статус: ожидает исполнения")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка при проверке исполнения: {e}"


def bot_profit():
    try:
        report = load_report()
        trades = report.get('trades', [])
        if not trades:
            return "Закрытых сделок нет. Отчёт появится после первой закрытой сделки."
        start_cap = report.get('start_capital')
        closed_sum = report.get('closed_sum', 0.0)
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        total_fee = sum(t.get('fee', 0) for t in trades)
        total_net = sum(t.get('net', 0) for t in trades)
        count = len(trades)
        wins = sum(1 for t in trades if t.get('net', 0) > 0)
        losses = sum(1 for t in trades if t.get('net', 0) <= 0)
        winrate = wins / count * 100 if count > 0 else 0
        current_capital = equity_capital()
        if start_cap and start_cap > 0:
            roi = (current_capital - start_cap) / start_cap * 100
        else:
            roi = 0.0
        lines = [
            f"Отчёт о прибыли",
            f"Стартовый капитал: {start_cap:.6g} {CAPITAL_ASSET}" if start_cap else "Стартовый капитал: ---",
            f"Текущий баланс: {current_capital:.6g} {CAPITAL_ASSET}",
            f"Общий PnL: {total_pnl:.6g} / Комиссии: {total_fee:.6g} / Чистая: {total_net:.6g}",
            f"ROI: {roi:+.2f}%",
            f"Сделок: {count} (wins: {wins}, losses: {losses}, winrate: {winrate:.0f}%)",
        ]
        if trades:
            last = trades[-1]
            lines.append(f"Последняя: {last.get('side')} {last.get('pair')} -> {last.get('hit')} net {last.get('net', 0):.6g}")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка при расчёте отчёта: {e}"


def bot_status():
    global _paused
    try:
        t = ticker(SYMBOL)
        last = t.get('last') or t.get('sell') or t.get('buy') or 0
        bid = t.get('buy') or 0
        ask = t.get('sell') or 0
        capital = equity_capital()
        state = load_state()
        pos = state.get('position') or {}
        if pos:
            pl_pct = 0.0
            if pos.get('entry_price'):
                cur = last or pos['entry_price']
                if pos['side'] == 'buy':
                    pl_pct = (cur - pos['entry_price']) / pos['entry_price'] * 100
                else:
                    pl_pct = (pos['entry_price'] - cur) / pos['entry_price'] * 100
        else:
            pl_pct = 0.0
        lines = [
            f"Статус бота",
            f"Режим: {'ПАУЗА' if _paused else 'РАБОТАЕТ'}",
            f"Биржа: {EXCHANGE.upper()}",
            f"Пара: {SYMBOL.upper()}",
            f"Цена: {last:.6g} (bid {bid:.6g} / ask {ask:.6g})",
            f"Баланс {CAPITAL_ASSET}: {capital:.6g}",
        ]
        if pos:
            lines.append(f"Позиция: {pos['side'].upper()} {pos.get('qty')} @ {pos.get('entry_price')}")
            lines.append(f"SL: {pos.get('sl')} | TP: {pos.get('tp')}")
            lines.append(f"PnL: {pl_pct:+.2f}%")
        else:
            lines.append("Позиция: нет")
        lines.append(f"Следующая: {state.get('next_side')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка при проверке: {e}"


def nonce():
    global _nonce_counter
    base = int(time.time())
    if _nonce_counter is None or _nonce_counter < base:
        _nonce_counter = base
    _nonce_counter += 1
    return str(_nonce_counter)


def sign_payload(payload):
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha512).hexdigest()


def mexc_sign(params):
    query = urlencode(params)
    sig = hmac.new(MEXC_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return query + '&signature=' + sig


def mexc_private_get(path, params=None):
    params = params or {}
    params['timestamp'] = int(time.time() * 1000)
    params['recvWindow'] = 5000
    query = mexc_sign(params)
    r = requests.get(f"{MEXC_PUBLIC}/{path}?{query}",
                     headers={'X-MEXC-APIKEY': MEXC_API_KEY}, timeout=15)
    r.raise_for_status()
    return r.json()


def mexc_public_get(path, params=None):
    r = requests.get(f"{MEXC_PUBLIC}/{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def mexc_unify_symbol(symbol):
    return symbol.replace('_', '').upper()


def mexc_ticker(symbol):
    s = mexc_unify_symbol(symbol)
    d = mexc_public_get('ticker/price', {'symbol': s})
    price = float(d.get('price', 0) or 0)
    try:
        d2 = mexc_public_get('ticker/bookTicker', {'symbol': s})
        bid = float(d2.get('bidPrice', 0) or 0)
        ask = float(d2.get('askPrice', 0) or 0)
    except Exception:
        bid = ask = 0
    return {'last': price, 'buy': bid, 'sell': ask}


def mexc_get_balance():
    data = mexc_private_get('account')
    out = {}
    for b in data.get('balances', []) or []:
        out[b['asset']] = float(b.get('free', 0) or 0)
    return out


def mexc_place_order(symbol, side, order_type, qty, price=0, leverage=1):
    params = {
        'symbol': mexc_unify_symbol(symbol),
        'side': side.upper(),
        'type': order_type.upper(),
        'quantity': f"{qty:.8f}",
    }
    if order_type.upper() == 'LIMIT':
        params['price'] = f"{price:.8f}"
        params['timeInForce'] = 'GTC'
    params['timestamp'] = int(time.time() * 1000)
    params['recvWindow'] = 5000
    query = mexc_sign(params)
    r = requests.post(f"{MEXC_PUBLIC}/order?{query}",
                      headers={'X-MEXC-APIKEY': MEXC_API_KEY}, timeout=15)
    r.raise_for_status()
    return r.json()


def mexc_cancel_order(symbol, order_id):
    params = {
        'symbol': mexc_unify_symbol(symbol),
        'orderId': order_id,
        'timestamp': int(time.time() * 1000),
        'recvWindow': 5000,
    }
    query = mexc_sign(params)
    r = requests.delete(f"{MEXC_PUBLIC}/order?{query}",
                        headers={'X-MEXC-APIKEY': MEXC_API_KEY}, timeout=15)
    r.raise_for_status()
    return r.json()


def mexc_active_orders(symbol=None):
    params = {'timestamp': int(time.time() * 1000), 'recvWindow': 5000}
    if symbol:
        params['symbol'] = mexc_unify_symbol(symbol)
    query = mexc_sign(params)
    r = requests.get(f"{MEXC_PUBLIC}/openOrders?{query}",
                     headers={'X-MEXC-APIKEY': MEXC_API_KEY}, timeout=15)
    r.raise_for_status()
    return r.json()


def mexc_my_trades(symbol, limit=3):
    params = {
        'symbol': mexc_unify_symbol(symbol),
        'limit': limit,
        'timestamp': int(time.time() * 1000),
        'recvWindow': 5000,
    }
    query = mexc_sign(params)
    r = requests.get(f"{MEXC_PUBLIC}/myTrades?{query}",
                     headers={'X-MEXC-APIKEY': MEXC_API_KEY}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get('code'):
        raise RuntimeError(data.get('msg', 'mexc myTrades error'))
    return data or []


def recent_trades(limit=3):
    if EXCHANGE == 'mexc':
        trades = mexc_my_trades(SYMBOL, limit)
        out = []
        for t in trades or []:
            out.append({
                'time': t.get('time'),
                'side': 'BUY' if t.get('isBuyer') else 'SELL',
                'amount': float(t.get('qty') or 0),
                'rate': float(t.get('price') or 0),
                'total': float(t.get('quoteQty') or 0),
            })
        return out
    data = trade_api('TradeHistory', {
        'pair': SYMBOL,
        'count': str(limit),
        'order': 'DESC',
    })
    if not data:
        return []
    trades = (data.get('trades') or {}).get(SYMBOL, [])
    out = []
    for t in trades or []:
        out.append({
            'time': t.get('timestamp'),
            'side': (t.get('type') or '').upper(),
            'amount': float(t.get('amount') or 0),
            'rate': float(t.get('rate') or 0),
            'total': float(t.get('amount') or 0) * float(t.get('rate') or 0),
        })
    return out


def mexc_get_info():
    return {'funds': mexc_get_balance()}


def public_get(path, params=None):
    url = f"{BASE_PUBLIC}/{path}"
    if params:
        url += '?' + urlencode(params)
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def trade_api(method, data=None):
    data = data or {}
    data.update({'method': method, 'nonce': nonce()})
    payload = urlencode(data)
    headers = {'Key': API_KEY, 'Sign': sign_payload(payload)}
    r = requests.post(BASE_TRADE, data=data, headers=headers, timeout=15)
    r.raise_for_status()
    j = r.json()
    if not j.get('success', 0):
        raise RuntimeError(j.get('error', 'unknown error'))
    return j.get('return')


def get_info():
    if EXCHANGE == 'mexc':
        return mexc_get_info()
    return trade_api('getInfo')


def active_orders(pair=None):
    if EXCHANGE == 'mexc':
        return mexc_active_orders(pair)
    params = {}
    if pair:
        params['pair'] = pair
    return trade_api('ActiveOrders', params)


def place_order(pair, type_, rate, amount, leverage, live_price=0):
    if EXCHANGE == 'mexc':
        ot = 'MARKET' if live_price else 'LIMIT'
        return mexc_place_order(pair, type_, ot, amount, rate or 0, leverage)
    data = {
        'pair': pair,
        'type': type_,
        'rate': f"{rate:.8f}",
        'amount': f"{amount:.8f}",
        'leverage': str(leverage),
        'use_live_price': str(live_price),
    }
    return trade_api('Trade', data)


def cancel_order(order_id):
    if EXCHANGE == 'mexc':
        return mexc_cancel_order(SYMBOL, order_id)
    return trade_api('CancelOrder', {'order_id': order_id})


def ticker(pair):
    if EXCHANGE == 'mexc':
        return mexc_ticker(pair)
    return public_get(f'ticker/{pair}').get(pair, {})


def is_trading_time():
    if SCHEDULE == '24/7' or not WINDOWS:
        return True
    now = datetime.datetime.now().time()
    for start, end in WINDOWS:
        if start <= end:
            if start <= now <= end:
                return True
        else:
            if now >= start or now <= end:
                return True
    return False


def send_vk(text):
    global _last_vk
    now = time.time()
    if now - _last_vk < 60:
        return False
    if not VK_TOKEN or not VK_PEER_ID:
        return False
    params = {
        'access_token': VK_TOKEN,
        'v': VK_API_VERSION,
        'peer_id': VK_PEER_ID,
        'message': text,
        'random_id': int(time.time() * 1000) % 1000000000,
    }
    try:
        r = requests.post(f"{VK_API_URL}messages.send", data=params, timeout=15)
        r.raise_for_status()
        j = r.json()
        if 'error' in j:
            logging.error(f"VK API error: {j['error']}")
            return False
        _last_vk = now
        logging.info(f"VK sent: {text[:80]}")
        return True
    except Exception as e:
        logging.error(f"VK send failed: {e}")
        return False


def notify(subject, body):
    send_vk(f"{subject}\n{body}")


def equity_capital():
    try:
        info = get_info()
        funds = info.get('funds', {}) or {}
    except Exception as e:
        logging.error(f"get_info failed: {e}")
        return 0.0
    cap = float(funds.get(CAPITAL_ASSET.lower(), 0) or 0)
    return cap


def pair_min_amount(pair):
    global _MIN_AMOUNTS
    if pair in _MIN_AMOUNTS:
        return _MIN_AMOUNTS[pair]
    try:
        if EXCHANGE == 'mexc':
            s = mexc_unify_symbol(pair)
            d = mexc_public_get('exchangeInfo', {})
            for item in d.get('symbols', []) or []:
                if item.get('symbol') == s:
                    _MIN_AMOUNTS[pair] = 1e-8
                    break
            else:
                _MIN_AMOUNTS[pair] = 1e-8
        else:
            info = public_get('info')
            pairs = info.get('pairs', {})
            _MIN_AMOUNTS[pair] = float(pairs.get(pair, {}).get('min_amount', 0) or 0)
    except Exception as e:
        logging.error(f"pair_min_amount failed: {e}")
        _MIN_AMOUNTS[pair] = 0.0
    return _MIN_AMOUNTS[pair]


def compute_qty(price):
    if QTY_FIXED > 0:
        return QTY_FIXED
    capital = equity_capital()
    min_amount = pair_min_amount(SYMBOL)
    max_risk_allowed = float(os.getenv('MAX_RISK_PERCENT', '100'))
    risk = RISK_PERCENT
    notional = capital * risk / 100.0 * LEVERAGE
    if min_amount > 0:
        min_notional = min_amount * price
        while notional < min_notional and risk < max_risk_allowed:
            risk = min(risk * 2, max_risk_allowed)
            notional = capital * risk / 100.0 * LEVERAGE
    qty = notional / price
    if min_amount > 0 and qty < min_amount:
        qty = min_amount
    if MAX_QTY > 0 and qty > MAX_QTY:
        qty = MAX_QTY
    if MIN_QTY > 0 and qty < MIN_QTY:
        qty = MIN_QTY
    if STEP_SIZE > 0:
        qty = math.floor(qty / STEP_SIZE) * STEP_SIZE
        qty = round(qty, 10)
    logging.info(f"Lot calc: capital={capital:.2f} {CAPITAL_ASSET}, risk={RISK_PERCENT}% (auto->{risk:.0f}%), lev={LEVERAGE}, min_am={min_amount}, qty={qty}, notional={notional:.6f}")
    return qty


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {'position': None, 'next_side': SIDE}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def load_report():
    try:
        with open(REPORT_FILE) as f:
            return json.load(f)
    except Exception:
        return {'start_capital': None, 'trades': [], 'closed_sum': 0.0}


def save_report(report):
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def record_closed_trade(side, qty, entry, close_price, hit, fee_pct=None):
    fee_pct = fee_pct if fee_pct is not None else TRADE_FEE
    if side == 'buy':
        pnl = (close_price - entry) * qty
    else:
        pnl = (entry - close_price) * qty
    fee = (qty * (entry + close_price)) * (fee_pct / 100.0)
    net = pnl - fee
    report = load_report()
    if report.get('start_capital') is None:
        report['start_capital'] = equity_capital()
    trade = {
        'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'pair': SYMBOL.upper(),
        'side': side.upper(),
        'qty': qty,
        'entry': entry,
        'close': close_price,
        'hit': hit,
        'pnl': round(pnl, 8),
        'fee': round(fee, 8),
        'net': round(net, 8),
    }
    report['trades'].append(trade)
    report['closed_sum'] = report.get('closed_sum', 0.0) + net
    save_report(report)
    return trade


def get_entry_price():
    t = ticker(SYMBOL)
    bid = t.get('buy') or t.get('last') or 0
    ask = t.get('sell') or t.get('last') or 0
    return bid, ask


def place_market_order(side, qty):
    return place_order(SYMBOL, side, 0, qty, LEVERAGE, live_price=1)


def calc_sl_tp(entry_price, side):
    sl_price = SL_PRICE
    tp_price = TP_PRICE
    if sl_price <= 0:
        sl_price = entry_price * (1 - SL_PERCENT / 100) if side == 'buy' else entry_price * (1 + SL_PERCENT / 100)
    if tp_price <= 0:
        tp_price = entry_price * (1 + TP_PERCENT / 100) if side == 'buy' else entry_price * (1 - TP_PERCENT / 100)
    return sl_price, tp_price


def run_auto():
    gui_log(f"Авто-режим запущен. Биржа: {EXCHANGE.upper()}, пара: {SYMBOL}, плечо: x{LEVERAGE}", "Авто-режим")
    state = load_state()
    cooldown_until = 0.0
    while True:
        try:
            now = time.time()
            if _paused:
                time.sleep(POLL)
                continue
            bid, ask = get_entry_price()
            current_price = ask if state.get('position') and state['position'].get('side') == 'sell' else bid
            if current_price <= 0:
                current_price = ticker(SYMBOL).get('last', 0)
            if state.get('position'):
                pos = state['position']
                side = pos['side']
                qty = pos['qty']
                entry = pos['entry_price']
                sl, tp = pos['sl'], pos['tp']
                gui_log(f"Позиция {side.upper()} {qty} @ {entry} | цена {current_price} | SL {sl} | TP {tp}",
                        f"Позиция: {side.upper()} {qty}")
                hit = None
                hit_price = 0
                if side == 'buy':
                    if sl > 0 and bid <= sl and bid > 0:
                        hit, hit_price = 'SL', bid
                    elif tp > 0 and bid >= tp and bid > 0:
                        hit, hit_price = 'TP', bid
                else:
                    if sl > 0 and ask >= sl and ask > 0:
                        hit, hit_price = 'SL', ask
                    elif tp > 0 and ask <= tp and ask > 0:
                        hit, hit_price = 'TP', ask
                if hit:
                    close_side = 'sell' if side == 'buy' else 'buy'
                    msg = f"Закрытие {side.upper()} по {hit} ({hit_price})"
                    gui_log(msg, f"Закрытие: {hit} {hit_price}")
                    notify(f"[YoBit Bot] {hit} {SYMBOL}", msg)
                    if not DRY_RUN:
                        place_market_order(close_side, qty)
                    record_closed_trade(side, qty, entry, hit_price, hit)
                    state['position'] = None
                    state['next_side'] = 'SELL' if side == 'buy' else 'BUY'
                    cooldown_until = now + AUTO_COOLDOWN_SEC
                    save_state(state)
                    notify(f"Сделка закрыта {SYMBOL}",
                           f"{side.upper()} -> {hit}\nВход: {entry}\nЗакрытие: {hit_price}\nСледующая: {state['next_side']}")
                    continue
            else:
                if now < cooldown_until:
                    time.sleep(POLL)
                    continue
                if not is_trading_time():
                    time.sleep(POLL)
                    continue
                side = state['next_side']
                qty = compute_qty(current_price)
                if qty <= 0:
                    time.sleep(POLL)
                    continue
                if side == 'BUY':
                    entry_price = ask
                else:
                    entry_price = bid
                if entry_price <= 0:
                    time.sleep(POLL)
                    continue
                notional = qty * entry_price
                if notional > MAX_NOTIONAL:
                    gui_log(f"Сумма {notional:.2f} превышает лимит {MAX_NOTIONAL}", "Лимит превышен")
                    time.sleep(POLL)
                    continue
                sl, tp = calc_sl_tp(entry_price, side.lower())
                msg = f"Открытие {side} {qty} @ {entry_price} x{LEVERAGE} SL={sl} TP={tp}"
                gui_log(msg, f"Открытие: {side} {qty}")
                notify(f"[YoBit Bot] Opening {side} {SYMBOL}", msg)
                order_resp = {}
                if not DRY_RUN:
                    if ORDER_TYPE == 'MARKET':
                        order_resp = place_market_order(side.lower(), qty)
                    else:
                        order_resp = place_order(SYMBOL, side.lower(), entry_price, qty, LEVERAGE)
                state['position'] = {
                    'side': side.lower(),
                    'qty': qty,
                    'entry_price': entry_price,
                    'sl': sl,
                    'tp': tp,
                    'time': now,
                }
                state['next_side'] = 'SELL' if side == 'BUY' else 'BUY'
                save_state(state)
                notify(f"[YoBit Bot] Position opened {SYMBOL}",
                       f"Side: {side}\nQty: {qty}\nEntry: {entry_price}\nSL: {sl}\nTP: {tp}\nLeverage: {LEVERAGE}\nResp: {order_resp}")
        except Exception as e:
            gui_log(f"Ошибка: {e}", "Ошибка")
            notify("[YoBit Bot] Auto error", str(e))
        time.sleep(POLL)


def fetch_yobit_liquid(limit=10):
    info = public_get('info')
    pairs = info.get('pairs', {})
    usdt_pairs = []
    for p, meta in pairs.items():
        if p.endswith('_usdt') and (meta.get('hidden') == 0 or meta.get('hidden') is None):
            usdt_pairs.append(p)
    rows = []
    for i in range(0, len(usdt_pairs), 50):
        chunk = usdt_pairs[i:i+50]
        try:
            t = public_get('ticker/' + '-'.join(chunk))
        except Exception:
            continue
        for p in chunk:
            d = t.get(p) or {}
            last = float(d.get('last') or 0)
            buy = float(d.get('buy') or 0)
            ask = float(d.get('sell') or 0)
            vol_cur = float(d.get('vol_cur') or 0)
            if last <= 0 or buy <= 0:
                continue
            usd_vol = vol_cur * last
            if usd_vol < 1:
                continue
            rows.append(('YoBit', p.upper(), f"{last:.6g}",
                         f"{buy:.6g}/{ask:.6g}", f"${usd_vol:.0f}"))
    rows.sort(key=lambda r: float(r[4][1:]), reverse=True)
    return rows[:limit]


def fetch_mexc_liquid(limit=10):
    try:
        d = mexc_public_get('ticker/24hr')
    except Exception:
        return []
    if not isinstance(d, list):
        return []
    lst = [x for x in d if (x.get('symbol') or '').endswith('USDT')]
    lst.sort(key=lambda x: float(x.get('quoteVolume') or 0), reverse=True)
    rows = []
    for x in lst[:limit]:
        sym = x.get('symbol', '')
        last = float(x.get('lastPrice') or 0)
        bid = float(x.get('bidPrice') or 0)
        ask = float(x.get('askPrice') or 0)
        qv = float(x.get('quoteVolume') or 0)
        if last <= 0:
            continue
        rows.append(('MEXC', sym, f"{last:.6g}",
                     f"{bid:.6g}/{ask:.6g}", f"${qv/1e6:.1f}M"))
    return rows


MONITOR_TOP_N = int(os.getenv('MONITOR_TOP_N', '10'))


def dashboard_loop():
    while True:
        try:
            rows = fetch_yobit_liquid(MONITOR_TOP_N) + fetch_mexc_liquid(MONITOR_TOP_N)
            if _bot_gui is not None:
                _bot_gui.update_dashboard(rows)
        except Exception as e:
            logging.error(f"Dashboard error: {e}")
        time.sleep(15)


def run_monitor():
    logging.info("Monitor started. Poll=%ss", POLL)
    while True:
        try:
            t = ticker(SYMBOL)
            price = t.get('last') or t.get('sell') or 0
            capital = equity_capital()
            logging.info(f"Monitor | {SYMBOL} price={price} capital={capital:.2f} {CAPITAL_ASSET}")
            if SL_PRICE > 0:
                key = 'SL'
                hit = price <= SL_PRICE if SIDE == 'BUY' else price >= SL_PRICE
                if hit and key not in _fired_alerts:
                    _fired_alerts.add(key)
                    notify(f"[YoBit Bot] SL hit {SYMBOL}", f"Price {price} crossed SL {SL_PRICE}\nPair: {SYMBOL}")
            if TP_PRICE > 0:
                key = 'TP'
                hit = price >= TP_PRICE if SIDE == 'BUY' else price <= TP_PRICE
                if hit and key not in _fired_alerts:
                    _fired_alerts.add(key)
                    notify(f"[YoBit Bot] TP hit {SYMBOL}", f"Price {price} crossed TP {TP_PRICE}\nPair: {SYMBOL}")
        except Exception as e:
            logging.error(f"Monitor error: {e}")
            notify("[YoBit Bot] Monitor error", str(e))
        time.sleep(POLL)


def run_trade():
    if not API_KEY or not SECRET:
        raise RuntimeError("Не заданы YOBIT_API_KEY/YOBIT_SECRET")
    if not is_trading_time():
        logging.info("Вне торгового окна, пропуск")
        return
    t = ticker(SYMBOL)
    price = PRICE if PRICE > 0 else (t.get('sell') or t.get('last') or 0)
    if price <= 0:
        raise RuntimeError("Не удалось получить цену")
    qty = compute_qty(price)
    if qty <= 0:
        raise RuntimeError("QTY <= 0")
    notional = qty * price
    if notional > MAX_NOTIONAL:
        raise RuntimeError(f"Notional {notional:.2f} > MAX_NOTIONAL {MAX_NOTIONAL}")
    if not (1 <= LEVERAGE <= MAX_LEVERAGE):
        raise RuntimeError("Плечо вне диапазона")
    if DRY_RUN:
        msg = f"DRY_RUN: PLACE {SIDE} {ORDER_TYPE} {qty} @ {price} x{LEVERAGE} on {SYMBOL}"
        logging.info(msg)
        notify("[YoBit Bot] DRY_RUN order", msg)
        return
    resp = place_order(SYMBOL, SIDE.lower(), price, qty, LEVERAGE)
    logging.info(f"Order placed: {resp}")
    notify(f"[YoBit Bot] Order placed {SYMBOL}",
           f"Side: {SIDE}\nType: {ORDER_TYPE}\nQty: {qty}\nPrice: {price}\nLeverage: {LEVERAGE}\nResp: {resp}")


def _demo_marker():
    return DEMO_MARKER


def _demo_expired():
    """Возвращает True, если демо-срок (DEMO_DAYS) истёк. DEMO_DAYS=0 — демо выключено."""
    if DEMO_DAYS <= 0:
        return False
    marker = _demo_marker()
    now = time.time()
    try:
        if os.path.exists(marker):
            with open(marker) as f:
                start = float(f.read().strip())
        else:
            start = now
            try:
                with open(marker, 'w') as f:
                    f.write(str(now))
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                pass
        days = (now - start) / 86400.0
        return days > DEMO_DAYS
    except Exception:
        return False


def _demo_remove_files():
    """Самоудаление файлов бота после окончания демо."""
    targets = [
        os.path.join(BASE_DIR, 'bot.py'),
        os.path.join(BASE_DIR, 'bot.exe'),
        os.path.join(BASE_DIR, 'setup.py'),
        os.path.join(BASE_DIR, 'setup.exe'),
        os.path.join(BASE_DIR, 'gui.py'),
        os.path.join(BASE_DIR, 'vk_control.py'),
        os.path.join(BASE_DIR, '.env'),
        os.path.join(BASE_DIR, 'run_bot_watchdog.bat'),
    ]
    for t in targets:
        try:
            if os.path.exists(t) and os.path.isfile(t):
                os.remove(t)
                logging.info(f"Demo: удалён {t}")
        except Exception as e:
            logging.error(f"Demo: не удалось удалить {t}: {e}")
    # временный bat, который удалит сам себя после паузы
    try:
        killer = os.path.join(BASE_DIR, '_selfdelete.bat')
        pyw = sys.executable.replace('python.exe', 'pythonw.exe')
        with open(killer, 'w') as f:
            f.write('@echo off\r\n')
            f.write('timeout /t 3 /nobreak >nul\r\n')
            f.write(f'del "%~f0"\r\n')
            f.write(f'if exist "{killer}" del "{killer}"\r\n')
            f.write('exit\r\n')
        subprocess.Popen(['cmd', '/c', killer], cwd=BASE_DIR,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        logging.error(f"Demo: самоудаление: {e}")


def main():
    global _bot_gui

    if _demo_expired():
        gui_log("ДЕМО-РЕЖИМ ЗАВЕРШЁН: 21 день использования истёк. Бот заблокирован.", "Демо истекло")
        notify("Демо-режим завершён", "21-дневный период использования истёк. Бот заблокирован.")
        _demo_remove_files()
        return

    def run_bot():
        try:
            if VK_TOKEN and VK_GROUP_ID:
                admins = [s.strip() for s in VK_ADMIN_IDS.split(',') if s.strip()] if VK_ADMIN_IDS else [str(VK_PEER_ID)]
                vk_control.start(vk_command, VK_TOKEN, VK_GROUP_ID, VK_PEER_ID, admins)
                gui_log("Управление через ВК активно", "ВК-управление")
            if MODE == 'auto':
                run_auto()
            elif MODE == 'monitor':
                run_monitor()
            elif MODE == 'trade':
                run_trade()
            else:
                raise ValueError("MODE must be auto|monitor|trade")
        except Exception as e:
            logging.critical(f"Bot thread crashed: {e}", exc_info=True)
            gui_log(f"КРИТИЧЕСКАЯ ОШИБКА: {e}", "Ошибка")

    if gui.TK_AVAILABLE:
        try:
            _bot_gui = gui.BotGui()
            threading.Thread(target=dashboard_loop, daemon=True).start()
            threading.Thread(target=run_bot, daemon=True).start()
            _bot_gui.log(f"Бот запущен. Биржа: {EXCHANGE.upper()}, пара: {SYMBOL}, режим: {MODE}", "Запуск...")
            try:
                _bot_gui.build()
            except Exception:
                pass
            gui_log("Окно GUI закрыто. Бот работает в фоне.", "Фоновый режим")
        except Exception as e:
            logging.error(f"GUI init failed, headless mode: {e}")
            run_bot()
    else:
        run_bot()

    # защита от обрыва — heartbeat и обработка ошибок
    while True:
        try:
            time.sleep(30)
            logging.debug("heartbeat")
        except KeyboardInterrupt:
            gui_log("Бот остановлен (Ctrl+C)", "Остановлен")
            break
        except Exception:
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.critical(f"Main crashed: {e}", exc_info=True)
        # ждём 5 секунд перед выходом, чтобы лог записался
        time.sleep(5)