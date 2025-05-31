import tkinter as tk
from tkinter import ttk, scrolledtext
import serial
import serial.tools.list_ports
import glob
import os
import time
import threading
import random
from enum import Enum

# === Твои модули ===
from frame import Frame
from hamming import encode_4bit, decode_7bit
from connection import Connection, ConnectionState


# === Парсер адреса ===
def parse_address(addr_str: str) -> int | None:
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


# === Отправка фрейма с Хэммингом ===
def send_frame(ser, frame: Frame):
    for byte in frame.to_bytes():
        upper_nibble = (byte >> 4) & 0x0F
        lower_nibble = byte & 0x0F
        encoded_upper = encode_4bit(upper_nibble)
        encoded_lower = encode_4bit(lower_nibble)
        ser.write(bytes([0xFF, encoded_upper, 0xFF]))
        ser.write(bytes([0xFF, encoded_lower, 0xFF]))
        time.sleep(0.01)


# === Чтение фрейма ===
def read_frame(ser) -> Frame:
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


def read_byte(ser) -> int:
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


# === Конфигурация порта ===
class SerialConfig:
    def __init__(self, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1.0):
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout

    def to_dict(self):
        return {
            'baudrate': self.baudrate,
            'bytesize': self.bytesize,
            'parity': self.parity,
            'stopbits': self.stopbits,
            'timeout': self.timeout
        }

    @staticmethod
    def load():
        try:
            with open("serial_config.json", "r") as f:
                data = json.load(f)
                return SerialConfig(**data)
        except Exception:
            return SerialConfig()

    def save(self):
        with open("serial_config.json", "w") as f:
            json.dump({
                'baudrate': self.baudrate,
                'bytesize': self.bytesize,
                'parity': self.parity,
                'stopbits': self.stopbits,
                'timeout': self.timeout
            }, f)


# === Главное окно с вкладками ===
class SerialAppTabs:
    def __init__(self, root):
        self.root = root
        self.root.title("UART GUI")
        self.root.geometry("800x500")
        self.root.resizable(True, True)

        # Стили
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Helvetica", 12), padding=[10, 5])
        style.configure("TButton", font=("Helvetica", 10), padding=6)
        style.configure("TLabel", font=("Helvetica", 10))
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"))

        # Notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=5, expand=True, fill="both")

        self.sender_tab = ttk.Frame(self.notebook)
        self.receiver_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.sender_tab, text="Отправитель")
        self.notebook.add(self.receiver_tab, text="Получатель")

        # Панели
        self.sender_panel = GUIModulePanel(self.sender_tab, is_sender=True)
        self.receiver_panel = GUIModulePanel(self.receiver_tab, is_sender=False)

    def close(self):
        self.sender_panel.close()
        self.receiver_panel.close()


# === Общий класс для работы с портом и GUI ===
class GUIModulePanel:
    def __init__(self, parent, is_sender=True):
        self.parent = parent
        self.is_sender = is_sender
        self.ser = None
        self.running = False
        self.config = SerialConfig.load()
        self.my_addr = random.randint(0x02, 0x7E)  # Единый адрес для узла
        self.nickname = f"0x{self.my_addr:02X}"
        self.connection = None
        self.port_map = {}

        # UI
        self.create_widgets()
        self.refresh_ports()

    def create_widgets(self):
        grid_opts = {'padx': 10, 'pady': 3, 'sticky': 'ew'}

        # === Выбор порта ===
        ttk.Label(self.parent, text="Порт:", style="Header.TLabel").grid(row=0, column=0, **grid_opts)
        self.port_var = tk.StringVar()
        self.port_menu = ttk.OptionMenu(self.parent, self.port_var, [])
        self.port_menu.grid(row=0, column=1, **grid_opts)
        self.refresh_btn = ttk.Button(self.parent, text="Обновить", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=2, **grid_opts)

        # === Адрес узла ===
        ttk.Label(self.parent, text="Адрес:", style="Header.TLabel").grid(row=1, column=0, **grid_opts)
        self.addr_label = ttk.Label(self.parent, text=f"0x{self.my_addr:02X}")
        self.addr_label.grid(row=1, column=1, **grid_opts)

        # === Никнейм ===
        ttk.Label(self.parent, text="Никнейм:", style="Header.TLabel").grid(row=2, column=0, **grid_opts)
        self.nick_entry = ttk.Entry(self.parent)
        self.nick_entry.insert(0, self.nickname)
        self.nick_entry.grid(row=2, column=1, **grid_opts)

        # === Подключение ===
        self.connect_btn = ttk.Button(self.parent, text="Подключиться", command=self.start_serial)
        self.connect_btn.grid(row=2, column=2, **grid_opts)

        # === Команды (выпадающий список) ===
        ttk.Label(self.parent, text="Команды:", style="Header.TLabel").grid(row=3, column=0, **grid_opts)
        self.cmd_options = ['connect', 'disconnect', 'status', 'config', 'exit']
        self.cmd_var = tk.StringVar()
        self.cmd_combo = ttk.Combobox(self.parent, textvariable=self.cmd_var, values=self.cmd_options, width=10)
        self.cmd_combo.grid(row=3, column=1, **grid_opts)
        self.cmd_combo.bind("<<ComboboxSelected>>", self.on_command_selected)

        # === Адрес для connect ===
        self.addr_label_cmd = ttk.Label(self.parent, text="Адрес:")
        self.addr_entry = ttk.Entry(self.parent)
        self.addr_label_cmd.grid(row=4, column=0, **grid_opts)
        self.addr_entry.grid(row=4, column=1, **grid_opts)
        self.addr_label_cmd.grid_remove()
        self.addr_entry.grid_remove()

        # === Кнопка выполнения ===
        self.exec_btn = ttk.Button(self.parent, text="Выполнить", command=self.handle_command)
        self.exec_btn.grid(row=4, column=2, **grid_opts)
        self.exec_btn.grid_remove()

        # === Сообщение ===
        if self.is_sender:
            ttk.Label(self.parent, text="Сообщение:", style="Header.TLabel").grid(row=5, column=0, **grid_opts)
            self.msg_entry = ttk.Entry(self.parent)
            self.msg_entry.grid(row=5, column=1, **grid_opts)
            self.send_msg_btn = ttk.Button(self.parent, text="Отправить", command=self.send_message)
            self.send_msg_btn.grid(row=5, column=2, **grid_opts)

        # === Лог ===
        self.log_text = scrolledtext.ScrolledText(self.parent, height=10, wrap=tk.WORD, state='disabled')
        self.log_text.grid(row=6 if self.is_sender else 5, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')

        # Расширение по сетке
        for i in range(7 if self.is_sender else 6):
            self.parent.grid_rowconfigure(i, weight=1)
        for i in range(3):
            self.parent.grid_columnconfigure(i, weight=1)

    def on_command_selected(self, event=None):
        selected = self.cmd_var.get()
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
        cmd = self.cmd_var.get().strip().lower()
        if not cmd:
            return

        if cmd == 'connect':
            addr_str = self.addr_entry.get().strip()
            remote_addr = parse_address(addr_str)
            if remote_addr is None:
                self.log("Ошибка: неверный формат адреса.", color="red")
                return

            if not self.connection:
                nickname = self.nick_entry.get() or self.nickname
                self.connection = Connection(self.my_addr, remote_addr, local_nick=nickname)
                try:
                    frame = self.connection.connect()
                    send_frame(self.ser, frame)
                    self.log(f"[CONNECTING to 0x{remote_addr:02X}]...")
                except Exception as e:
                    self.log(f"Ошибка подключения: {e}", color="red")
            else:
                self.log("Уже есть активное соединение.", color="red")

        elif cmd == 'disconnect':
            if self.connection:
                try:
                    frame = self.connection.disconnect()
                    send_frame(self.ser, frame)
                    self.log(f"[DISCONNECT from {self.connection.remote_nick}]")
                    self.connection = None
                except Exception as e:
                    self.log(f"Ошибка разрыва: {e}", color="red")
            else:
                self.log("Нет активного соединения.", color="red")

        elif cmd == 'status':
            if self.connection:
                self.log(str(self.connection))
            else:
                self.log("Нет активного соединения.")

        elif cmd == 'config':
            self.open_config_window()

        elif cmd == 'exit':
            self.root.destroy()

    def open_config_window(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Настройка порта")
        config_window.geometry("300x200")

        ttk.Label(config_window, text="Скорость:", style="Header.TLabel").grid(row=0, column=0, padx=10, pady=5)
        self.baud_var = tk.StringVar(value=str(self.config.baudrate))
        ttk.Entry(config_window, textvariable=self.baud_var).grid(row=0, column=1)

        ttk.Label(config_window, text="Четность:", style="Header.TLabel").grid(row=1, column=0, padx=10, pady=5)
        self.parity_var = tk.StringVar(value=self.config.parity)
        ttk.Combobox(config_window, textvariable=self.parity_var, values=['N', 'E', 'O']).grid(row=1, column=1)

        ttk.Label(config_window, text="Биты данных:", style="Header.TLabel").grid(row=2, column=0, padx=10, pady=5)
        self.bits_var = tk.IntVar(value=self.config.bytesize)
        ttk.Spinbox(config_window, from_=5, to=8, textvariable=self.bits_var).grid(row=2, column=1)

        ttk.Label(config_window, text="Стоп-биты:", style="Header.TLabel").grid(row=3, column=0, padx=10, pady=5)
        self.stop_var = tk.DoubleVar(value=self.config.stopbits)
        ttk.Spinbox(config_window, from_=1, to=2, increment=0.5, textvariable=self.stop_var).grid(row=3, column=1)

        def save_config():
            try:
                self.config.baudrate = int(self.baud_var.get())
                self.config.parity = self.parity_var.get()
                self.config.bytesize = self.bits_var.get()
                self.config.stopbits = self.stop_var.get()
                self.config.save()
                messagebox.showinfo("OK", "Настройки сохранены.")
                config_window.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Неверные данные: {e}")

        ttk.Button(config_window, text="Сохранить", command=save_config).grid(row=4, column=0, columnspan=2, pady=10)

    def refresh_ports(self):
        ports = list(serial.tools.list_ports.comports())
        found = {p.device for p in ports}
        additional_ports = []
        for pattern in ["/dev/ttys*", "/dev/pts/*"]:
            for dev in glob.glob(pattern):
                if dev not in found and os.access(dev, os.R_OK | os.W_OK):
                    additional_ports.append(dev)
        all_ports = [p.device for p in ports] + additional_ports
        menu = self.port_menu['menu']
        menu.delete(0, 'end')
        self.port_map.clear()

        def extract_number(port):
            try:
                return int(''.join(filter(str.isdigit, port)))
            except ValueError:
                return float('inf')

        all_ports.sort(key=extract_number)
        for port in all_ports:
            name = os.path.basename(port)
            num = ''.join(filter(str.isdigit, name))
            display_name = num if num else name
            self.port_map[display_name] = port
            menu.add_command(label=display_name, command=lambda name=display_name: self.port_var.set(name))

        if self.port_map:
            first_port = next(iter(self.port_map))
            self.port_var.set(first_port)

    def start_serial(self):
        display_name = self.port_var.get()
        port = self.port_map.get(display_name)
        if not port:
            messagebox.showerror("Ошибка", "Не выбран порт.")
            return

        self.nickname = self.nick_entry.get() or f"0x{self.my_addr:02X}"

        try:
            self.ser = serial.Serial(port, **self.config.to_dict())
            self.running = True
            self.log(f"Подключено к {port}, адрес: 0x{self.my_addr:02X}, никнейм: {self.nickname}")
            thread = threading.Thread(target=self.read_loop, daemon=True)
            thread.start()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть порт: {e}")

    def send_message(self):
        msg = self.msg_entry.get()
        if not msg or not self.connection or not self.connection.is_connected():
            self.log("Соединение не установлено или сообщение пустое.", color="red")
            return
        try:
            frame = self.connection.create_frame(Frame.TYPE_I, msg.encode('utf-8'))
            send_frame(self.ser, frame)
            self.log(f"[SEND] {msg}")
        except Exception as e:
            self.log(f"Ошибка отправки: {e}", color="red")

    def read_loop(self):
        while self.running:
            try:
                frame = read_frame(self.ser)
                if frame:
                    if frame.receiver != self.my_addr and frame.receiver != Frame.BROADCAST_ADDR:
                        continue

                    if not self.connection:
                        self.connection = Connection(
                            self.my_addr, frame.sender, local_nick=self.nickname
                        )

                    conn = self.connection
                    old_state = conn.state
                    response = conn.handle_frame(frame)

                    if old_state != conn.state:
                        self.log(f"[STATE] {conn}", color="green")

                    if response:
                        send_frame(self.ser, response)

                    if frame.frame_type == Frame.TYPE_I:
                        try:
                            msg = frame.data.decode('utf-8')
                            self.log(f"[{conn.remote_nick}]: {msg}", color="blue")
                        except:
                            self.log("[ERROR] Ошибка декодирования", color="red")
            except Exception as e:
                self.log(f"[ERROR] {e}", color="red")
            time.sleep(0.1)

    def log(self, message, color="black"):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)

    def close(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()


# === Запуск приложения ===
if __name__ == "__main__":
    root = tk.Tk()
    app = SerialAppTabs(root)
    root.mainloop()