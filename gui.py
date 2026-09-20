import queue
import threading

try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk
    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False


class BotGui:
    def __init__(self, on_close=None):
        self.on_close = on_close
        self.queue = queue.Queue()
        self.dash_queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.root = None

    def build(self):
        self.root = tk.Tk()
        self.root.title("Crypto Bot — торговля и мониторинг бирж")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        dash_frame = tk.LabelFrame(self.root, text="Мониторинг ликвидных пар", padx=8, pady=6)
        dash_frame.pack(fill="x", padx=10, pady=(10, 4))

        columns = ("Биржа", "Пара", "Цена", "bid/ask", "Объём 24h")
        self.tree = ttk.Treeview(dash_frame, columns=columns, show="headings", height=7, selectmode="none")
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("Биржа", width=70)
        self.tree.column("Пара", width=100)
        self.tree.column("Цена", width=110)
        self.tree.column("bid/ask", width=180)
        self.tree.column("Объём 24h", width=130)
        self.tree.pack(fill="x")

        header = tk.Frame(self.root, padx=10, pady=4)
        header.pack(fill="x")
        self.status_var = tk.StringVar(value="Запуск...")
        tk.Label(header, textvariable=self.status_var, font=("Consolas", 11, "bold")).pack(anchor="w")

        self.text = scrolledtext.ScrolledText(self.root, wrap="word", font=("Consolas", 10), state="disabled")
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.root.after(100, self._poll_queue)
        self.root.after(250, self._poll_dash)
        self.root.mainloop()

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == 'log':
                    self._append(payload)
        except (queue.Empty, ValueError):
            pass
        if self.root is not None:
            self.root.after(100, self._poll_queue)

    def _poll_dash(self):
        try:
            while True:
                rows = self.dash_queue.get_nowait()
                self._update_dash(rows)
        except queue.Empty:
            pass
        if self.root is not None:
            self.root.after(500, self._poll_dash)

    def _update_dash(self, rows):
        if self.root is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in rows:
            self.tree.insert("", "end", values=r)

    def _append(self, msg):
        if self.root is None:
            return
        self.text.config(state="normal")
        self.text.insert("end", msg + "\n")
        self.text.see("end")
        self.text.config(state="disabled")

    def _on_close(self):
        self.stop_flag.set()
        if self.on_close:
            self.on_close()
        if self.root is not None:
            self.root.destroy()

    def log(self, msg, status=None):
        if not TK_AVAILABLE or self.root is None:
            return
        self.queue.put(('log', msg))
        if status is not None:
            self.queue.put(('status', status))

    def update_dashboard(self, rows):
        if not TK_AVAILABLE or self.root is None:
            return
        self.dash_queue.put(rows)

    def shutdown(self):
        self.stop_flag.set()
        if self.root is not None:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass