import os
import glob
import serial
import serial.tools.list_ports
import sys
from hamming import decode_7bit
from frame import Frame

MY_ADDR = 0x01  # Адрес приёмника

def read_byte(ser) -> int:
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
            decoded = decode_7bit(encoded[0])
            data.append(decoded)
    return (data[0] << 4) | data[1]

def read_frame(ser) -> Frame:
    """Читает и собирает фрейм."""
    buffer = bytearray()
    while True:
        byte = read_byte(ser)
        if byte is None:
            return None
        
        buffer.append(byte)
        
        # Проверяем, достаточно ли байт для заголовка фрейма
        if len(buffer) >= 5:
            try:
                # Проверяем длину данных из заголовка
                length = buffer[4]
                if len(buffer) >= length + 6:  # заголовок + данные + стоп-байт
                    return Frame.from_bytes(buffer)
            except Exception as e:
                print(f"Ошибка при разборе фрейма: {e}")
                buffer.clear()

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
            port = input("Введите путь к порту вручную (например, /dev/ttys034): ")
        else:
            index = int(input("Выберите порт по номеру: "))
            if index < 0 or index >= len(ports):
                print("Неверный выбор порта.")
                return
            port = ports[index] if isinstance(ports[index], str) else ports[index].device

    ser = serial.Serial(port, baudrate=9600, timeout=1)
    print(f"Ожидание данных на {port}...")

    try:
        while True:
            frame = read_frame(ser)
            if frame:
                if frame.receiver == MY_ADDR or frame.receiver == Frame.BROADCAST_ADDR:
                    if frame.frame_type == Frame.TYPE_I:
                        text = frame.data.decode('utf-8')
                        print(f"[{frame.sender:02X} → {frame.receiver:02X}] {text}")
                    else:
                        print(f"[{frame.sender:02X} → {frame.receiver:02X}] Неизвестный тип кадра: {frame.frame_type:02X}")
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
