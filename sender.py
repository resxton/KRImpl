import serial
import serial.tools.list_ports
import time
import os
import glob
import sys
import locale
from hamming import encode_4bit
from frame import Frame

MY_ADDR = 0x02  # Адрес отправителя
RECV_ADDR = 0x01  # Адрес получателя

def safe_input(prompt: str) -> str:
    """Безопасный ввод с поддержкой UTF-8 и редактирования."""
    try:
        # Устанавливаем локаль для корректной работы с UTF-8
        if sys.platform == 'darwin':
            locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')
        return input(prompt).strip()
    except UnicodeDecodeError:
        # Если возникла ошибка декодирования, пробуем другую кодировку
        try:
            if sys.platform == 'darwin':
                return input(prompt.encode('utf-8').decode(sys.stdin.encoding)).strip()
            return input(prompt).strip()
        except UnicodeDecodeError:
            # Если всё ещё ошибка, возвращаем пустую строку
            print("Ошибка при вводе текста. Попробуйте ещё раз.")
            return ""

def encode_and_send_byte(ser, byte: int):
    """Кодирует и отправляет один байт."""
    upper_nibble = (byte >> 4) & 0x0F
    lower_nibble = byte & 0x0F
    
    encoded_upper = encode_4bit(upper_nibble)
    encoded_lower = encode_4bit(lower_nibble)
    
    ser.write(bytes([0xFF, encoded_upper, 0xFE]))
    ser.write(bytes([0xFF, encoded_lower, 0xFE]))
    time.sleep(0.01)

def send_frame(ser, message: str):
    """Создает и отправляет информационный фрейм."""
    frame = Frame(
        receiver=RECV_ADDR,
        sender=MY_ADDR,
        frame_type=Frame.TYPE_I,
        data=message.encode('utf-8')
    )
    
    # Отправляем каждый байт фрейма
    for byte in frame.to_bytes():
        encode_and_send_byte(ser, byte)

def list_serial_ports():
    """Возвращает список доступных COM-портов, включая виртуальные от socat."""
    ports = list(serial.tools.list_ports.comports())
    found = {p.device for p in ports}
    additional_ports = []

    for pattern in ["/dev/ttys*", "/dev/pts/*"]:
        for dev in glob.glob(pattern):
            if dev not in found and os.access(dev, os.R_OK | os.W_OK):
                additional_ports.append(dev)

    all_ports = list(ports) + additional_ports
    print("Доступные порты:")
    for i, port in enumerate(all_ports):
        if isinstance(port, str):
            print(f"{i}: {port} — виртуальный")
        else:
            print(f"{i}: {port.device} — {port.description}")
    return all_ports

def main():
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1:
        try:
            port_number = sys.argv[1]
            port = f"/dev/ttys{port_number.zfill(3)}"
            if not os.path.exists(port):
                print(f"Порт {port} не существует")
                return
        except ValueError:
            print("Некорректный номер порта")
            return
    else:
        ports = list_serial_ports()
        if not ports:
            port = safe_input("Введите путь к порту вручную (например, /dev/ttys034): ")
        else:
            index = int(safe_input("Выберите порт по номеру: "))
            if index < 0 or index >= len(ports):
                print("Неверный выбор порта.")
                return
            port = ports[index] if isinstance(ports[index], str) else ports[index].device

    ser = serial.Serial(port, baudrate=9600, timeout=1)
    print(f"Подключено к {port}")
    
    try:
        while True:
            message = safe_input("Введите сообщение (или 'exit'): ")
            if not message:  # Пропускаем пустые сообщения
                continue
            if message.lower() == 'exit':
                break
            
            print(f"Отправка [{MY_ADDR:02X} → {RECV_ADDR:02X}]: {message}")
            send_frame(ser, message)
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
