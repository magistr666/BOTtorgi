import os
import subprocess
import sys

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
    TK_OK = True
except Exception:
    TK_OK = False

BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
ENV_FILE = os.path.join(BASE_DIR, '.env')
BOT_PY = os.path.join(BASE_DIR, 'bot.py')
BOT_EXE = os.path.join(BASE_DIR, 'bot.exe')
PYTHONW = sys.executable.replace('python.exe', 'pythonw.exe')


def bot_command():
    if getattr(sys, 'frozen', False):
        if os.path.exists(BOT_EXE):
            return [BOT_EXE]
        return []
    if not os.path.exists(PYTHONW):
        return [sys.executable, BOT_PY]
    return [PYTHONW, BOT_PY]


FIELDS = [
    ('EXCHANGE', 'Биржа (yobit / mexc)', False),
    ('YOBIT_API_KEY', 'YoBit API Key', False),
    ('YOBIT_SECRET', 'YoBit Secret', True),
    ('MEXC_API_KEY', 'MEXC API Key', False),
    ('MEXC_SECRET', 'MEXC Secret', True),
    ('SYMBOL', 'Торговая пара (напр. FLOKI_USDT)', False),
    ('LEVERAGE', 'Плечо', False),
    ('CAPITAL_ASSET', 'Валюта капитала (USDT)', False),
    ('RISK_PERCENT', 'Риск % от капитала', False),
    ('MAX_LEVERAGE', 'Макс. плечо', False),
    ('MAX_NOTIONAL_PER_ORDER_USD', 'Макс. сумма ордера (USDT)', False),
    ('DRY_RUN', 'Тестовый режим (true/false)', False),
    ('MODE', 'Режим (auto / monitor / trade)', False),
    ('DEMO_DAYS', 'Демо-срок, дней (0 = без ограничений)', False),
]

VK_FIELDS = [
    ('VK_TOKEN', 'VK токен (vk1.a. ...)', True),
    ('VK_GROUP_ID', 'VK ID группы (напр. 241568635)', False),
    ('VK_PEER_ID', 'VK ID беседы (напр. 2000000001)', False),
    ('VK_ADMIN_IDS', 'ID админов через запятую', False),
]


def load_env():
    data = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                data[k.strip()] = v.strip()
    return data


def save_env(data, comments):
    lines = []
    for comment, keys in comments:
        if comment:
            lines.append(comment)
        for k in keys:
            v = data.get(k, '')
            lines.append(f"{k}={v}")
        lines.append('')
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


class SetupGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Bot - настройки и запуск")
        self.root.geometry("720x780")
        self.env = load_env()
        self.vars = {}
        self.proc = None
        self._build()

    def _build(self):
        pad = {'padx': 10, 'pady': 4}

        tk.Label(self.root, text="Настройки бота (YoBit / MEXC + VK)",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", **pad)

        tk.Label(self.root, text="--- Биржа и торговля ---",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad)
        for key, label, secret in FIELDS:
            row = tk.Frame(self.root)
            row.pack(fill="x", **pad)
            tk.Label(row, text=label, width=32, anchor="w").pack(side="left")
            var = tk.StringVar(value=self.env.get(key, ''))
            entry = tk.Entry(row, textvariable=var, show='*' if secret else '')
            entry.pack(side="left", fill="x", expand=True)
            self.vars[key] = var

        tk.Label(self.root, text="--- Управление через ВКонтакте ---",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad)
        for key, label, secret in VK_FIELDS:
            row = tk.Frame(self.root)
            row.pack(fill="x", **pad)
            tk.Label(row, text=label, width=32, anchor="w").pack(side="left")
            var = tk.StringVar(value=self.env.get(key, ''))
            entry = tk.Entry(row, textvariable=var, show='*' if secret else '')
            entry.pack(side="left", fill="x", expand=True)
            self.vars[key] = var

        btns = tk.Frame(self.root)
        btns.pack(fill="x", **pad)
        tk.Button(btns, text="Сохранить", command=self.save, width=14).pack(side="left", padx=4)
        tk.Button(btns, text="Запустить бота", command=self.start_bot, width=16).pack(side="left", padx=4)
        tk.Button(btns, text="Остановить", command=self.stop_bot, width=12).pack(side="left", padx=4)

        self.status_var = tk.StringVar(value="Бот: не запущен")
        tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10, "bold"),
                 fg="blue").pack(anchor="w", **pad)

        tk.Label(self.root, text="Лог бота (последние строки):",
                 font=("Segoe UI", 9)).pack(anchor="w", **pad)
        self.log_box = scrolledtext.ScrolledText(self.root, height=14, font=("Consolas", 9), state="disabled")
        self.log_box.pack(fill="both", expand=True, **pad)

        self._update_status()
        self._refresh_log()
        self.root.after(2000, self._tick)

    def save(self):
        data = dict(self.env)
        for key, var in self.vars.items():
            data[key] = var.get().strip()
        comments = [
            ("# --- Биржа ---", ['EXCHANGE', 'YOBIT_API_KEY', 'YOBIT_SECRET', 'MEXC_API_KEY', 'MEXC_SECRET',
                                 'SYMBOL', 'LEVERAGE', 'CAPITAL_ASSET', 'RISK_PERCENT',
                                 'MAX_LEVERAGE', 'MAX_NOTIONAL_PER_ORDER_USD', 'DRY_RUN', 'MODE',
                                 'DEMO_DAYS']),
            ("# --- VK ---", ['VK_TOKEN', 'VK_GROUP_ID', 'VK_PEER_ID', 'VK_ADMIN_IDS']),
        ]
        save_env(data, comments)
        messagebox.showinfo("Готово", "Настройки сохранены в .env")

    def start_bot(self):
        self.save()
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("", "Бот уже запущен")
            return
        cmd = bot_command()
        if not cmd:
            messagebox.showerror("", "Не найден bot.exe")
            return
        self.proc = subprocess.Popen(cmd, cwd=BASE_DIR)
        self._update_status()

    def stop_bot(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        subprocess.run(['taskkill', '/F', '/IM', 'pythonw.exe'], capture_output=True)
        self._update_status()

    def _update_status(self):
        running = bool(self.proc and self.proc.poll() is None)
        self.status_var.set("Бот: РАБОТАЕТ" if running else "Бот: не запущен")

    def _tick(self):
        self._update_status()
        self._refresh_log()
        self.root.after(3000, self._tick)

    def _refresh_log(self):
        log_path = os.path.join(BASE_DIR, 'bot.log')
        if not os.path.exists(log_path):
            return
        try:
            size = os.path.getsize(log_path)
            with open(log_path, encoding='utf-8', errors='replace') as f:
                if size > 8000:
                    f.seek(size - 8000)
                    f.readline()
                content = f.read()
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.insert("1.0", content)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        except Exception:
            pass


def main():
    if not TK_OK:
        print("tkinter недоступен")
        return
    root = tk.Tk()
    SetupGui(root)
    root.mainloop()


if __name__ == '__main__':
    main()