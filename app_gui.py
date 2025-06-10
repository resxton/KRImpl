import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import glob
import os
import time
import threading
import random
import re
import platform

# === Импорты из проекта ===
from frame import Frame
from hamming import encode_4bit, decode_7bit
from connection import Connection, ConnectionState
from config import SerialConfig, print_serial_config

def generate_address() -> int:
    """Генерирует случайный адрес, исключая специальные адреса."""
    while True:
        addr = random.randint(0x02, 0x7E)
        if addr != Frame.BROADCAST_ADDR:
            return addr

def parse_address(addr_str: str) -> int | None:
    """Парсит строку адреса в целое число, возвращает None при ошибке."""
    try:
        if not addr_str:
            return None
        addr_str = addr_str.strip().lower()
        if not addr_str.startswith('0x'):
            addr_str = '0x' + addr_str
        addr = int(addr_str, 16)
        if 0x00 <= addr <= 0x7F:
            return addr
        else:
            raise ValueError
    except ValueError:
        return None

def send_frame(ser, frame: Frame):
    """Отправляет фрейм через serial порт с кодированием Хэмминга."""
    if not ser.is_open:
        raise serial.SerialException("Порт закрыт")
    for byte in frame.to_bytes():
        upper_nibble = (byte >> 4) & 0x0F
        lower_nibble = byte & 0x0F
        encoded_upper = encode_4bit(upper_nibble)
        encoded_lower = encode_4bit(lower_nibble)
        ser.write(bytes([0xFF, encoded_upper, 0xFF]))
        ser.write(bytes([0xFF, encoded_lower, 0xFF]))
        time.sleep(0.01)

def read_byte(ser) -> int:
    """Читает байт с декодированием Хэмминга."""
    data = []
    while len(data) < 2:
        byte = ser.read(1)
        if not byte:
            return None
        if byte == b'\xFF':
            encoded = ser.read(1)
            stop_byte = ser.read(1)
            if not encoded or stop_byte != b'\xFF':
                continue
            decoded = decode_7bit(encoded[0])
            data.append(decoded)
    return (data[0] << 4) | data[1]

def read_frame(ser) -> Frame:
    """Читает и парсит фрейм из serial порта."""
    buffer = bytearray()
    while True:
        byte = read_byte(ser)
        if byte is None:
            return None
        buffer.append(byte)
        if len(buffer) >= 5:
            try:
                length = buffer[4]
                if len(buffer) >= length + 6:
                    return Frame.from_bytes(buffer)
            except Exception as e:
                print(f"Ошибка при разборе фрейма: {e}")
                buffer.clear()

# === Главное окно с вкладками ===
class SerialAppTabs:
    """Главный класс приложения UART GUI, управляющий вкладками и соединением."""
    def __init__(self, root):
        self.root = root
        self.root.title("UART GUI")
        self.root.geometry("800x500")
        self.root.resizable(True, True)

        self.node_addr = generate_address()
        self.nickname = f"0x{self.node_addr:02X}"
        self.ser = None
        self.connection = None
        self.running = False
        self.config = SerialConfig.load()

        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Helvetica", 12), padding=[10, 5])
        style.configure("TButton", font=("Helvetica", 10), padding=6)
        style.configure("TLabel", font=("Helvetica", 10))
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"))

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=5, expand=True, fill="both")

        self.sender_tab = ttk.Frame(self.notebook)
        self.receiver_tab = ttk.Frame(self.notebook)
        self.config_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.sender_tab, text="Отправитель")
        self.notebook.add(self.receiver_tab, text="Получатель")
        self.notebook.add(self.config_tab, text="⚙️ Настройки")

        self.sender_panel = GUIModulePanel(
            self.sender_tab,
            app=self,
            is_sender=True,
            node_addr=self.node_addr,
            nickname=self.nickname,
            on_nickname_change=self.update_nickname
        )
        self.receiver_panel = GUIModulePanel(
            self.receiver_tab,
            app=self,
            is_sender=False,
            node_addr=self.node_addr,
            nickname=self.nickname,
            on_nickname_change=self.update_nickname
        )
        self.config_panel = ConfigPanel(self.config_tab)

    def start_serial(self, port):
        """Открывает serial порт и запускает цикл чтения."""
        if self.ser is not None:
            messagebox.showerror("Ошибка", "Серийный порт уже открыт.")
            return
        try:
            self.ser = serial.Serial(port, **self.config.to_dict())
            self.running = True
            self.log(f"Подключено к {port}, адрес: 0x{self.node_addr:02X}, никнейм: {self.nickname}")
            thread = threading.Thread(target=self.read_loop, daemon=True)
            thread.start()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть порт: {e}")

    def read_loop(self):
        """Цикл чтения фреймов, обрабатывает входящие сообщения и таймауты."""
        while self.running:
            try:
                # Проверка таймаута соединения
                if self.connection and self.connection.is_connection_timeout():
                    self.log(f"[TIMEOUT] Соединение с {self.connection.remote_nick} разорвано из-за неактивности", color="red")
                    self.connection = None
                    self.update_status_indicator("red")
                
                # Проверка таймаута для повторных попыток
                if self.connection:
                    retry_frame = self.connection.check_timeout()
                    if retry_frame:
                        send_frame(self.ser, retry_frame)
                        self.log(f"[RETRY] Повторная отправка {'TYPE_LINK' if retry_frame.frame_type == Frame.TYPE_LINK else 'TYPE_UPLINK'} к 0x{self.connection.remote_addr:02X}", color="yellow")
                    elif self.connection.state == ConnectionState.DISCONNECTED:
                        self.log(f"[ERROR] Не удалось установить соединение с 0x{self.connection.remote_addr:02X} после {self.connection.max_retries} попыток", color="red")
                        self.connection = None
                        self.update_status_indicator("red")

                frame = read_frame(self.ser)
                if frame:
                    if frame.receiver != self.node_addr and frame.receiver != Frame.BROADCAST_ADDR:
                        continue
                    if not self.connection:
                        self.connection = Connection(self.node_addr, frame.sender, local_nick=self.nickname)
                    old_state = self.connection.state
                    response = self.connection.handle_frame(frame)
                    if response:
                        send_frame(self.ser, response)
                    if old_state != self.connection.state:
                        color = {"DISCONNECTED": "red", "CONNECTING": "yellow", "CONNECTED": "green", "DISCONNECTING": "yellow"}[self.connection.state.value]
                        self.update_status_indicator(color)
                        self.log(f"[STATE] {self.connection}", color="green")
                    if frame.frame_type == Frame.TYPE_I and self.connection.is_connected():
                        try:
                            msg = frame.data.decode('utf-8')
                            self.receiver_panel.log(f"[{self.connection.remote_nick}]: {msg}", color="light_purple")
                        except:
                            self.log("[ERROR] Ошибка декодирования", color="red")
            except Exception as e:
                self.log(f"[ERROR] {e}", color="red")
            time.sleep(0.1)

    def update_status_indicator(self, color):
        """Обновляет цвет индикатора состояния в обеих панелях."""
        self.sender_panel.status_label.configure(foreground=color)
        self.receiver_panel.status_label.configure(foreground=color)

    def update_nickname(self, new_nickname: str, source_panel):
        """Обновляет никнейм во всех панелях и соединении."""
        self.nickname = new_nickname
        if source_panel == self.sender_panel:
            self.receiver_panel.update_nickname(new_nickname)
        else:
            self.sender_panel.update_nickname(new_nickname)
        if self.connection:
            self.connection.local_nick = new_nickname

    def log(self, message, color="white"):
        """Логирует сообщение в обеих вкладках (кроме сообщений данных)."""
        self.sender_panel.log(message, color)
        self.receiver_panel.log(message, color)

    def close(self):
        """Закрывает приложение и serial порт."""
        self.running = False
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception as e:
            self.log(f"Ошибка при закрытии порта: {e}", color="red")
        self.sender_panel.close()
        self.receiver_panel.close()

# === Вкладка настроек порта ===
class ConfigPanel:
    """Класс для вкладки настроек serial порта."""
    def __init__(self, parent):
        self.parent = parent
        self.config = SerialConfig.load()
        self.create_widgets()

    def create_widgets(self):
        """Создает элементы интерфейса для настройки порта."""
        grid_opts = {'padx': 10, 'pady': 5, 'sticky': 'ew'}
        ttk.Label(self.parent, text="Скорость:", style="Header.TLabel").grid(row=0, column=0, **grid_opts)
        self.baud_var = tk.StringVar(value=str(self.config.baudrate))
        self.baud_combo = ttk.Combobox(self.parent, textvariable=self.baud_var, values=[
            300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200
        ])
        self.baud_combo.grid(row=0, column=1, **grid_opts)
        ttk.Label(self.parent, text="Четность:", style="Header.TLabel").grid(row=1, column=0, **grid_opts)
        self.parity_var = tk.StringVar(value=self.config.parity)
        ttk.Combobox(self.parent, textvariable=self.parity_var, values=['N', 'E', 'O']).grid(row=1, column=1, **grid_opts)
        ttk.Label(self.parent, text="Биты данных:", style="Header.TLabel").grid(row=2, column=0, **grid_opts)
        self.bits_var = tk.IntVar(value=self.config.bytesize)
        ttk.Spinbox(self.parent, from_=5, to=8, textvariable=self.bits_var).grid(row=2, column=1, **grid_opts)
        ttk.Label(self.parent, text="Стоп-биты:", style="Header.TLabel").grid(row=3, column=0, **grid_opts)
        self.stop_var = tk.DoubleVar(value=self.config.stopbits)
        ttk.Spinbox(self.parent, from_=1, to=2, increment=0.5, textvariable=self.stop_var).grid(row=3, column=1, **grid_opts)
        ttk.Label(self.parent, text="Таймаут чтения:", style="Header.TLabel").grid(row=4, column=0, **grid_opts)
        self.timeout_var = tk.DoubleVar(value=self.config.timeout)
        ttk.Entry(self.parent, textvariable=tk.StringVar(value=str(self.config.timeout))).grid(row=4, column=1, **grid_opts)
        ttk.Button(self.parent, text="Сохранить", command=self.save_config).grid(row=5, column=0, columnspan=2, pady=10)

    def save_config(self):
        """Сохраняет конфигурацию порта."""
        try:
            self.config.baudrate = int(self.baud_var.get())
            self.config.parity = self.parity_var.get()
            self.config.bytesize = self.bits_var.get()
            self.config.stopbits = self.stop_var.get()
            self.config.timeout = float(self.timeout_var.get())
            self.config.save()
            messagebox.showinfo("OK", "Конфигурация порта сохранена.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Неверные данные: {e}")

# === Общий класс панели подключения ===
class GUIModulePanel:
    """Класс для панелей отправителя и получателя."""
    def __init__(self, parent, app, is_sender=True, node_addr=None, nickname=None, on_nickname_change=None):
        self.parent = parent
        self.app = app
        self.is_sender = is_sender
        self.my_addr = node_addr
        self.nickname = nickname
        self.port_map = {}
        self.on_nickname_change = on_nickname_change
        self.create_widgets()
        self.refresh_ports()

    def update_nickname(self, new_nickname: str):
        """Обновляет никнейм в интерфейсе."""
        self.nickname = new_nickname
        self.nick_entry.delete(0, tk.END)
        self.nick_entry.insert(0, new_nickname)

    def create_widgets(self):
        """Создает элементы интерфейса."""
        grid_opts = {'padx': '10', 'pady': 3, 'sticky': 'ew'}
        ttk.Label(self.parent, text="Порт:", style="Header.TLabel").grid(row=0, column=0, **grid_opts)
        self.port_var = tk.StringVar()
        self.port_menu = ttk.OptionMenu(self.parent, self.port_var, '')
        self.port_menu.grid(row=0, column=1, **grid_opts)
        self.refresh_btn = ttk.Button(self.parent, text="Обновить", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=2, **grid_opts)
        ttk.Label(self.parent, text="Адрес:", style="Header.TLabel").grid(row=1, column=0, **grid_opts)
        self.addr_label = ttk.Label(self.parent, text=f"0x{self.my_addr:02X}")
        self.addr_label.grid(row=1, column=1, **grid_opts)
        self.status_label = ttk.Label(self.parent, text="●", foreground="red")
        self.status_label.grid(row=1, column=2, padx=5)
        ttk.Label(self.parent, text="Никнейм:", style="Header.TLabel").grid(row=2, column=0, **grid_opts)
        self.nick_entry = ttk.Entry(self.parent)
        self.nick_entry.insert(0, self.nickname)
        self.nick_entry.grid(row=2, column=1, **grid_opts)
        self.nick_entry.bind('<KeyRelease>', self._on_nickname_changed)
        self.connect_btn = ttk.Button(self.parent, text="Подключиться", command=self.start_serial)
        self.connect_btn.grid(row=2, column=2, **grid_opts)
        ttk.Label(self.parent, text="Команды:", style="Header.TLabel").grid(row=3, column=0, **grid_opts)
        self.cmd_options = ['connect', 'disconnect', 'status', 'config', 'exit']
        self.cmd_var = tk.StringVar()
        self.cmd_combo = ttk.Combobox(self.parent, textvariable=self.cmd_var, values=self.cmd_options, width=10)
        self.cmd_combo.grid(row=3, column=1, **grid_opts)
        self.cmd_combo.bind("<<ComboboxSelected>>", self.on_command_selected)
        self.addr_label_cmd = ttk.Label(self.parent, text="Адрес:")
        self.addr_entry = ttk.Entry(self.parent)
        self.addr_label_cmd.grid(row=4, column=0, **grid_opts)
        self.addr_entry.grid(row=4, column=1, **grid_opts)
        self.addr_entry.bind('<KeyRelease>', self.validate_address)
        self.addr_label_cmd.grid_remove()
        self.addr_entry.grid_remove()
        self.exec_btn = ttk.Button(self.parent, text="Выполнить", command=self.handle_command)
        self.exec_btn.grid(row=4, column=2, **grid_opts)
        self.exec_btn.grid_remove()
        if self.is_sender:
            ttk.Label(self.parent, text="Сообщение:", style="Header.TLabel").grid(row=5, column=0, **grid_opts)
            self.msg_entry = ttk.Entry(self.parent)
            self.msg_entry.grid(row=5, column=1, **grid_opts)
            self.send_msg_btn = ttk.Button(self.parent, text="Отправить", command=self.send_message)
            self.send_msg_btn.grid(row=5, column=2, **grid_opts)
        self.log_text = scrolledtext.ScrolledText(self.parent, height=10, background="#1E1E1E", wrap=tk.WORD, state='disabled')
        self.log_text.grid(row=6 if self.is_sender else 5, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')
        self.log_text.tag_configure("red", foreground="red")
        self.log_text.tag_configure("light_purple", foreground="#D7BDE2")
        self.log_text.tag_configure("green", foreground="green")
        self.log_text.tag_configure("white", foreground="white")
        ttk.Button(self.parent, text="Очистить лог", command=self.clear_log).grid(row=7 if self.is_sender else 6, column=2, pady=5)
        for i in range(8 if self.is_sender else 7):
            self.parent.grid_rowconfigure(i, weight=1)
        for i in range(3):
            self.parent.grid_columnconfigure(i, weight=1)

    def _on_nickname_changed(self, event):
        """Обработчик изменения никнейма."""
        if self.on_nickname_change:
            new_nickname = self.nick_entry.get()
            self.nickname = new_nickname
            self.on_nickname_change(new_nickname, self)

    def validate_address(self, event):
        """Валидирует введённый адрес в реальном времени."""
        addr_str = self.addr_entry.get().strip()
        if parse_address(addr_str) is None and addr_str:
            self.addr_entry.configure(foreground="red")
        else:
            self.addr_entry.configure(foreground="green")

    def clear_log(self):
        """Очищает текстовое поле лога."""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def on_command_selected(self, event=None):
        """Обработчик выбора команды."""
        selected = self.cmd_combo.get()
        if selected == 'connect':
            self.addr_label_cmd.grid()
            self.addr_entry.grid()
            self.exec_btn.grid()
        elif selected in ['disconnect', 'status', 'config', 'exit']:
            self.addr_label_cmd.grid_remove()
            self.addr_entry.grid_remove()
            self.exec_btn.grid()
        else:
            self.addr_label_cmd.grid_remove()
            self.addr_entry.grid_remove()
            self.exec_btn.grid_remove()

    def handle_command(self):
        """Обрабатывает выбранную команду."""
        cmd = self.cmd_var.get().strip().lower()
        if not cmd:
            return
        if cmd == 'connect':
            if self.app.connection:
                self.log("Уже есть активное соединение.", color="red")
                return
            addr_str = self.addr_entry.get().strip()
            remote_addr = parse_address(addr_str)
            if remote_addr is None:
                self.log("Ошибка: неверный формат адреса", color="red")
                return
            if not self.app.ser:
                self.log("Сначала подключитесь к порту.", color="red")
                return
            self.app.connection = Connection(self.app.node_addr, remote_addr, local_nick=self.app.nickname)
            try:
                frame = self.app.connection.connect()
                send_frame(self.app.ser, frame)
                self.log(f"[INFO] Подключение к 0x{remote_addr:02X}...", color="white")
            except Exception as e:
                self.log(f"Ошибка подключения: {e}", color="red")
        elif cmd == 'disconnect':
            if self.app.connection:
                try:
                    frame = self.app.connection.disconnect()
                    send_frame(self.app.ser, frame)
                    self.log(f"[INFO] Отключение от {self.app.connection.remote_nick}", color="white")
                    self.app.connection = None
                    self.app.update_status_indicator("red")
                except Exception as e:
                    self.log(f"Ошибка отключения: {e}", color="red")
            else:
                self.log("Нет активного соединения.", color="red")
        elif cmd == 'status':
            if self.app.connection:
                self.log(str(self.app.connection), color="white")
            else:
                self.log("Нет активного соединения.", color="white")
        elif cmd == 'config':
            self.open_config_window()
        elif cmd == 'exit':
            self.app.close()
            self.app.root.destroy()

    def refresh_ports(self):
        """Обновляет список доступных портов с отладочным выводом."""
        print("[DEBUG] Обновление списка портов...")
        ports = list(serial.tools.list_ports.comports())
        found = {p.device for p in ports}
        additional_ports = []

        # Шаблоны для macOS и Unix-подобных систем
        patterns = ["/dev/ttys*", "/dev/tty.*"]
        if platform.system() == "Windows":
            patterns = []  # На Windows полагаемся только на pyserial

        # Собираем дополнительные порты через glob
        for pattern in patterns:
            for dev in glob.glob(pattern):
                if os.access(dev, os.R_OK | os.W_OK):
                    print(f"[DEBUG] Найден порт через glob: {dev}")
                    if dev not in found:
                        additional_ports.append(dev)
                else:
                    print(f"[DEBUG] Порт {dev} исключён: нет прав доступа")

        # Добавляем порты из pyserial
        for p in ports:
            print(f"[DEBUG] Порт через pyserial: {p.device}")
            if p.device not in found:  # Уже добавлено в found
                print(f"[DEBUG] Порт {p.device} уже в списке")
            elif os.access(p.device, os.R_OK | os.W_OK):
                print(f"[DEBUG] Порт {p.device} доступен")
            else:
                print(f"[DEBUG] Порт {p.device} исключён: нет прав доступа")

        all_ports = [p.device for p in ports] + additional_ports
        self.parent.after(0, lambda: self.port_menu['menu'].delete(0, 'end'))
        self.port_map.clear()

        # Парсим и сортируем порты
        def extract_number(port):
            match = re.search(r'\d+$', port)
            return int(match.group()) if match else float('inf')

        all_ports.sort(key=extract_number)
        for port in all_ports:
            match = re.search(r'\d+$', port)
            port_num = str(int(match.group())) if match else os.path.basename(port)
            display_name = f"Порт {port_num}"
            print(f"[DEBUG] Отображаемый порт: {display_name} -> {port}")
            self.port_map[display_name] = port
            self.parent.after(0, lambda name=display_name: self.port_menu['menu'].add_command(
                label=name, command=lambda n=name: self.port_var.set(n)))

        if self.port_map:
            first_port = next(iter(self.port_map))
            self.parent.after(0, lambda: self.port_var.set(first_port))
            print(f"[DEBUG] Выбран порт по умолчанию: {first_port}")
        else:
            print("[DEBUG] Порты не найдены или недоступны")
            self.log("[INFO] Не найдено доступных портов.", color="red")

    def start_serial(self):
        """Открывает serial порт."""
        display_name = self.port_var.get()
        port = self.port_map.get(display_name)
        if not port:
            self.log("Ошибка: не выбран порт.", color="red")
            messagebox.showerror("Ошибка", "Не выбран порт")
            return
        self.app.start_serial(port)

    def send_message(self):
        """Отправляет сообщение через serial порт."""
        msg = self.msg_entry.get()
        if not msg or not self.app.connection or not self.app.connection.is_connected():
            self.log("Ошибка: Соединение не установлено или сообщение пустое.", color="red")
            return
        try:
            frame = self.app.connection.create_frame(Frame.TYPE_I, msg.encode('utf-8'))
            send_frame(self.app.ser, frame)
            self.log(f"[SEND] {msg}", color="green")
        except Exception as e:
            self.log(f"[ERROR] Ошибка отправки: {e}", color="red")

    def log(self, message, color="white"):
        """Логирует сообщение в текстовое поле с цветом."""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{message}\n", color)
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)

    def open_config_window(self):
        """Открывает окно конфигурации (заглушка)."""
        pass

    def close(self):
        """Очищает ресурсы панели."""
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialAppTabs(root)
    root.mainloop()