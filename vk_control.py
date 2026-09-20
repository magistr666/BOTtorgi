import time
import logging
import threading

import requests


def _api(method, params, token):
    params = dict(params)
    params['access_token'] = token
    params['v'] = '5.199'
    r = requests.get(f'https://api.vk.com/method/{method}', params=params, timeout=15)
    r.raise_for_status()
    j = r.json()
    if 'error' in j:
        raise RuntimeError(j['error'].get('error_msg', 'unknown vk error'))
    return j.get('response')


def _send(token, peer_id, text):
    try:
        requests.post('https://api.vk.com/method/messages.send', data={
            'access_token': token,
            'v': '5.199',
            'peer_id': peer_id,
            'message': text,
            'random_id': int(time.time() * 1000) % 1000000000,
        }, timeout=15)
    except Exception as e:
        logging.error(f"VK send reply failed: {e}")


def start(handler, token, group_id, peer_id, admin_ids):
    threading.Thread(target=_loop, args=(handler, token, group_id, peer_id, admin_ids),
                     daemon=True).start()


def _loop(handler, token, group_id, peer_id, admin_ids):
    error_delay = 5
    while True:
        try:
            lp = _api('groups.getLongPollServer', {'group_id': group_id}, token)
            server = lp.get('server')
            key = lp.get('key')
            ts = lp.get('ts')
            logging.info("VK Long Poll started")
            while True:
                try:
                    r = requests.get(server, params={
                        'act': 'a_check',
                        'key': key,
                        'ts': ts,
                        'wait': 25,
                    }, timeout=35)
                    r.raise_for_status()
                    d = r.json()
                    failed = d.get('failed')
                    if failed:
                        logging.warning(f"VK longpoll failed={failed}, reconnecting")
                        break
                    ts = d.get('ts', ts)
                    for upd in d.get('updates', []) or []:
                        if upd.get('type') != 'message_new':
                            continue
                        obj = upd.get('object', {}) or {}
                        msg = obj.get('message', obj) or {}
                        from_id = str(msg.get('from_id') or '')
                        text = msg.get('text') or ''
                        logging.info(f"VK incoming from {from_id}: {text[:80]}")
                        if not text.strip():
                            continue
                        if admin_ids and from_id not in admin_ids:
                            logging.warning(f"VK ignored from {from_id} (not admin)")
                            continue
                        try:
                            reply = handler(text)
                        except Exception as e:
                            reply = f'Error processing command: {e}'
                        if reply:
                            target = msg.get('peer_id') or peer_id
                            _send(token, target, reply)
                except Exception as e:
                    logging.error(f"VK longpoll poll error: {e}")
                    time.sleep(error_delay)
                    break
        except Exception as e:
            logging.error(f"VK longpoll error: {e}")
            time.sleep(error_delay)