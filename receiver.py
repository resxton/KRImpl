import os
import glob
import serial
import serial.tools.list_ports
import sys
import time
from hamming import decode_7bit, encode_4bit
from frame import Frame
from connection import Connection, ConnectionState

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
            if not encoded or stop_byte != b'\xFF':
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

def encode_and_send_byte(ser, byte: int):
    """Кодирует и отправляет один байт."""
    upper_nibble = (byte >> 4) & 0x0F
    lower_nibble = byte & 0x0F
    
    encoded_upper = encode_4bit(upper_nibble)
    encoded_lower = encode_4bit(lower_nibble)
    
    ser.write(bytes([0xFF, encoded_upper, 0xFF]))
    ser.write(bytes([0xFF, encoded_lower, 0xFF]))
    time.sleep(0.01)

def send_frame(ser, frame: Frame):
    """Отправляет фрейм."""
    for byte in frame.to_bytes():
        encode_and_send_byte(ser, byte)

def print_frame_details(frame: Frame):
    """Выводит подробную информацию о фрейме."""
    print("\n=== Получен новый фрейм ===")
    # print(f"Адрес отправителя: 0x{frame.sender:02X}")
    # print(f"Адрес получателя: 0x{frame.receiver:02X}")
    print(f"Тип фрейма: 0x{frame.frame_type:02X}")
    # print(f"Длина данных: {len(frame.data)} байт")
    # print("Содержимое фрейма (hex):", ' '.join([f'{b:02X}' for b in frame.to_bytes()]))
    # if frame.frame_type == Frame.TYPE_I:
    #     try:
    #         text = frame.data.decode('utf-8')
    #         print(f"Декодированное сообщение: {text}")
    #     except UnicodeDecodeError:
    #         print("Ошибка декодирования UTF-8")
    print("=" * 30)

def get_frame_type_name(frame_type: int) -> str:
    """Возвращает текстовое описание типа фрейма."""
    types = {
        Frame.TYPE_I: "Информационный кадр",
        Frame.TYPE_LINK: "Установка соединения",
        Frame.TYPE_UPLINK: "Разрыв соединения",
        Frame.TYPE_ACK: "Подтверждение",
        Frame.TYPE_RET: "Запрос повтора"
    }
    return types.get(frame_type, "Неизвестный тип")

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
    
    # Словарь соединений по адресам отправителей
    connections = {}

    try:
        while True:
            frame = read_frame(ser)
            if frame:
                print_frame_details(frame)
                
                # Проверяем, что фрейм предназначен нам
                if frame.receiver != MY_ADDR and frame.receiver != Frame.BROADCAST_ADDR:
                    continue
                
                # Получаем или создаем объект соединения
                if frame.sender not in connections:
                    connections[frame.sender] = Connection(MY_ADDR, frame.sender)
                
                connection = connections[frame.sender]
                print(f"Состояние соединения: {connection.state.value}")
                
                # Обрабатываем фрейм и получаем ответ если нужен
                response = connection.handle_frame(frame)
                if response:
                    print(f"Отправка ответа типа 0x{response.frame_type:02X}")
                    send_frame(ser, response)
                
                # Выводим сообщение если это информационный фрейм
                if frame.frame_type == Frame.TYPE_I and connection.is_connected():
                    try:
                        text = frame.data.decode('utf-8')
                        print(f"[{frame.sender:02X} → {frame.receiver:02X}] {text}")
                    except UnicodeDecodeError:
                        print(f"[{frame.sender:02X} → {frame.receiver:02X}] Ошибка декодирования сообщения")
                
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
