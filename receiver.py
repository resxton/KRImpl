import os
import glob
import serial
import serial.tools.list_ports

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

def hamming_decode_7bit(encoded: int) -> int:
    """Декодирует 7-битный код Хэмминга в 4 бита данных."""
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
        encoded ^= (1 << (error_pos - 1))  # Исправляем ошибку

    return (d1 << 0) | (d2 << 1) | (d3 << 2) | (d4 << 3)

def read_frame(ser) -> bytes:
    """Читает два 7-битных кода и собирает байт."""
    data = []

    while len(data) < 2:
        byte = ser.read(1)
        if not byte:
            return None

        if byte == b'\xFF':  # Старт кадра
            encoded = ser.read(1)
            stop_byte = ser.read(1)
            if not encoded or stop_byte != b'\xFE':
                continue  # Пропускаем ошибочные кадры
            decoded = hamming_decode_7bit(encoded[0])
            data.append(decoded)

    return bytes([(data[0] << 4) | data[1]])

def main():
    ports = list_serial_ports()

    use_manual = False
    if not ports:
        use_manual = True
    else:
        answer = input("Вы хотите выбрать порт из списка? (y/n): ").lower()
        use_manual = answer == 'n'

    if use_manual:
        port = input("Введите путь к порту вручную (например, /dev/ttys034): ")
    else:
        index = int(input("Выберите порт по номеру: "))
        if index < 0 or index >= len(ports):
            print("Неверный выбор порта.")
            return
        port = ports[index] if isinstance(ports[index], str) else ports[index].device

    ser = serial.Serial(port, baudrate=9600, timeout=1)

    buffer = bytearray()
    print(f"Ожидание данных на {port}...")

    try:
        while True:
            byte = read_frame(ser)
            if byte:
                buffer += byte
                if byte == b'\n' or byte == b'\r':
                    try:
                        print("Принято:", buffer.decode('utf-8').strip())
                    except UnicodeDecodeError:
                        print("Ошибка декодирования:", buffer.hex())
                    buffer.clear()
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
