import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import time
import os
import glob
import threading

# === Класс Frame из файла frame.py ===
from frame import Frame

# === Функции кодирования/декодирования Хэмминга ===
def hamming_encode_4bit(data: int) -> int:
    d1 = (data >> 0) & 1
    d2 = (data >> 1) & 1
    d3 = (data >> 2) & 1
    d4 = (data >> 3) & 1
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return (p1 | (p2 << 1) | (d1 << 2) | (p3 << 3) | (d2 << 4) | (d3 << 5) | (d4 << 6))

def send_frame(ser, data: bytes):
    for byte in data:
        upper_nibble = (byte >> 4) & 0x0F
        lower_nibble = byte & 0x0F
        encoded_upper = hamming_encode_4bit(upper_nibble)
        encoded_lower = hamming_encode_4bit(lower_nibble)
        ser.write(bytes([0xFF, encoded_upper, 0xFE]))
        ser.write(bytes([0xFF, encoded_lower, 0xFE]))
        time.sleep(0.005)

def hamming_decode_7bit(encoded: int) -> int:
    p1 = (encoded >> 0) & 1
    p2 = (encoded >> 1) & 1
    d1 = (encoded >> 2) & 1
    p3 = (encoded >> 3) & 1
    d2 = (encoded >> 4) & 1
    d3 = (encoded >> 5) & 1
    d4 = (encoded >> 6) & 1
    s1 = p1 ^ d1 ^ d2 ^ d4
    s2 = p2 ^ d1 ^ d3 ^ d4
    s3 = p3 ^ d2 ^ d3 ^ d4
    error_pos = s1 + (s2 << 1) + (s3 << 2)
    if error_pos:
        encoded ^= (1 << (error_pos - 1))
    return (d1 << 0) | (d2 << 1) | (d3 << 2) | (d4 << 3)

def read_frame(ser) -> bytes:
    data = []
    while len(data) < 2:
        byte = ser.read(1)
        if not byte:
            return None
        if byte == b'\xFF':
            encoded = ser.read(1)
            stop_byte = ser.read(1)
            if not encoded or stop_byte != b'\xFE':
                continue
            decoded = hamming_decode_7bit(encoded[0])
            data.append(decoded)
    return bytes([(data[0] << 4) | data[1]])

def send_ack(ser, receiver_addr, sender_addr):
    ack_frame = Frame(receiver=receiver_addr, sender=sender_addr, frame_type=Frame.TYPE_ACK)
    send_frame(ser, ack_frame.to_bytes())

# === Окно с вкладками Sender и Receiver ===
class SerialAppTabs:
    def __init__(self, root):
        self.root = root
        self.root.title("UART Приложение")
        self.root.geometry("800x500")
        self.root.resizable(True, True)

        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Helvetica", 12), padding=[10, 5])
        style.configure("TButton", font=("Helvetica", 10), padding=6)
        style.configure("TLabel", font=("Helvetica", 10))
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"))

        # Notebook для вкладок
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=10, expand=True, fill='both')

        # Создаем вкладки
        self.sender_tab = ttk.Frame(self.notebook)
        self.receiver_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.sender_tab, text="Отправитель")
        self.notebook.add(self.receiver_tab, text="Получатель")

        # Собираем интерфейсы
        self.sender = BaseSerialPanel(self.sender_tab, is_sender=True)
        self.receiver = BaseSerialPanel(self.receiver_tab, is_sender=False)

    def close(self):
        self.sender.close()
        self.receiver.close()


# === Панель подключения (общая для Sender и Receiver) ===
class BaseSerialPanel:
    def __init__(self, parent, is_sender=True):
        self.parent = parent
        self.is_sender = is_sender

        self.ser = None
        self.running = False
        self.my_addr = 0x01
        self.port_map = {}

        # UI
        self.create_widgets()

    def create_widgets(self):
        grid_opts = {'padx': 10, 'pady': 5, 'sticky': 'ew'}

        # Выбор порта
        ttk.Label(self.parent, text="Выберите порт:", style="Header.TLabel").grid(row=0, column=0, **grid_opts)
        self.port_var = tk.StringVar()
        self.port_menu = ttk.OptionMenu(self.parent, self.port_var, [])
        self.port_menu.grid(row=0, column=1, **grid_opts)
        self.refresh_btn = ttk.Button(self.parent, text="Обновить порты", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=2, **grid_opts)

        # Адрес узла
        ttk.Label(self.parent, text="Адрес узла (hex):", style="Header.TLabel").grid(row=1, column=0, **grid_opts)
        self.addr_entry = ttk.Entry(self.parent)
        self.addr_entry.insert(0, "01")
        self.addr_entry.grid(row=1, column=1, **grid_opts)
        self.connect_btn = ttk.Button(self.parent, text="Установить соединение", command=self.start_serial)
        self.connect_btn.grid(row=1, column=2, **grid_opts)

        # Поле сообщения (только для отправителя)
        if self.is_sender:
            ttk.Label(self.parent, text="Сообщение:", style="Header.TLabel").grid(row=2, column=0, **grid_opts)
            self.msg_entry = ttk.Entry(self.parent)
            self.msg_entry.grid(row=2, column=1, **grid_opts)
            self.send_btn = ttk.Button(self.parent, text="Отправить", command=self.send_message)
            self.send_btn.grid(row=2, column=2, **grid_opts)

        # Лог
        self.log_text = scrolledtext.ScrolledText(self.parent, height=15, wrap=tk.WORD, state='disabled')
        self.log_text.grid(row=3 if self.is_sender else 2, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')

        # Расширение по сетке
        for i in range(4):
            self.parent.grid_rowconfigure(i, weight=1)
        for i in range(3):
            self.parent.grid_columnconfigure(i, weight=1)

        self.refresh_ports()

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

        # Сортировка по номеру
        def extract_number(port):
            try:
                return int(''.join(filter(str.isdigit, port)))
            except ValueError:
                return float('inf')  # Если нет цифр — в конец

        all_ports.sort(key=extract_number)

        for port in all_ports:
            name = os.path.basename(port)
            num = ''.join(filter(str.isdigit, name))
            display_name = f"Порт {num}" if num else f"Порт {name}"
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

        try:
            self.my_addr = int(self.addr_entry.get(), 16)
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат адреса.")
            return

        try:
            self.ser = serial.Serial(port, baudrate=9600, timeout=0.1)
            self.log(f"Подключено к {display_name} ({port}), адрес: 0x{self.my_addr:02X}")
            self.running = True
            if self.is_sender:
                self.send_btn.config(state=tk.NORMAL)
            else:
                thread = threading.Thread(target=self.read_loop, daemon=True)
                thread.start()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть порт: {e}")

    def send_message(self):
        msg = self.msg_entry.get()
        if not msg or not self.ser or not self.running:
            return
        try:
            frame = Frame(
                receiver=Frame.BROADCAST_ADDR,
                sender=self.my_addr,
                frame_type=Frame.TYPE_I,
                data=(msg + '\n').encode('utf-8')
            )
            send_frame(self.ser, frame.to_bytes())
            self.log(f"[{self.my_addr:02X} → BROADCAST] Отправлено: {msg}")
        except Exception as e:
            self.log(f"Ошибка отправки: {e}")

    def read_loop(self):
        buffer = bytearray()
        in_frame = False
        while self.running:
            try:
                byte = read_frame(self.ser)
                if byte:
                    b = byte[0]
                    if b == 0xFF and not in_frame:
                        buffer = bytearray([b])
                        in_frame = True
                    elif in_frame:
                        buffer.append(b)
                        if b == 0xFF and len(buffer) >= 6:
                            try:
                                frame = Frame.from_bytes(buffer)
                                if frame.receiver != self.my_addr and frame.receiver != Frame.BROADCAST_ADDR:
                                    self.log(f"[Служебно] Кадр не для меня, адрес {frame.receiver:02X}")
                                else:
                                    if frame.frame_type == Frame.TYPE_I:
                                        text = frame.data.decode('utf-8', errors='replace').strip()
                                        self.log(f"[{frame.sender:02X} → {frame.receiver:02X}] Получено: {text}")
                                        send_ack(self.ser, frame.sender, frame.receiver)
                            except Exception as e:
                                self.log(f"Ошибка разбора кадра: {e}")
                            in_frame = False
            except Exception as e:
                self.log(f"Ошибка чтения: {e}")
            time.sleep(0.01)

    def log(self, message):
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