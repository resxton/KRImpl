import os
import glob
import serial
import serial.tools.list_ports
import sys
import time
import random
import select
from hamming import decode_7bit, encode_4bit
from frame import Frame
from connection import Connection, ConnectionState
from config import SerialConfig, configure_port, print_serial_config

def generate_address() -> int:
    """Генерирует случайный адрес, исключая специальные адреса."""
    while True:
        # Генерируем адрес от 0x02 до 0x3F (нижняя половина диапазона)
        addr = random.randint(0x02, 0x3F)
        if addr != Frame.BROADCAST_ADDR:  # Исключаем широковещательный адрес
            return addr

def print_address_banner(addr: int, nickname: str):
    """Выводит красивый баннер с адресом узла."""
    print("\n" + "=" * 50)
    print(f"\033[1;36m{'АДРЕС УЗЛА':^50}\033[0m")
    print("=" * 50)
    print(f"\033[1;33m{'0x{:02X}'.format(addr):^50}\033[0m")
    print(f"\033[1;36m{nickname:^50}\033[0m")
    print("=" * 50 + "\n")
    print("\033[1;37mИспользуйте этот адрес при подключении к узлу.\033[0m\n")

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

def print_status_message(message: str, status: str = "info"):
    """Выводит статусное сообщение в соответствующем цвете."""
    colors = {
        "error": "\033[31m",  # красный
        "success": "\033[32m", # зеленый
        "info": "\033[36m",    # голубой
        "warning": "\033[33m"  # желтый
    }
    color = colors.get(status, colors["info"])
    print(f"{color}{message}\033[0m")

def print_help():
    """Выводит справку по командам."""
    print("\n\033[1mДоступные команды:\033[0m")
    print("  \033[36mstatus\033[0m     - показать статус соединений")
    print("  \033[33mexit\033[0m       - выход")
    print("  \033[36mhelp\033[0m       - показать эту справку")
    print("\033[1mВсе входящие сообщения будут отображаться автоматически.\033[0m\n")

def safe_input(prompt: str = "") -> str:
    """Безопасное чтение команды из stdin."""
    try:
        return input(prompt)
    except EOFError:
        return "exit"
    except KeyboardInterrupt:
        return "exit"

def main():
    # Генерируем случайный адрес для этого узла
    MY_ADDR = generate_address()
    
    # Запрашиваем никнейм
    nickname = input("Введите ваш никнейм (Enter для адреса по умолчанию): ").strip()
    if not nickname:
        nickname = f"0x{MY_ADDR:02X}"
    
    print_address_banner(MY_ADDR, nickname)
    
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

    # Загружаем конфигурацию порта
    config = SerialConfig.load()
    if not config:
        print_status_message("Ошибка: не найдена конфигурация порта", "error")
        print_status_message("Запустите sender.py для настройки параметров", "info")
        return
    
    print_serial_config(config)
    ser = serial.Serial(port, **config.to_dict())
    print_status_message(f"\nОжидание подключений на {port}...", "info")
    print(f"Адрес узла: \033[1;33m0x{MY_ADDR:02X}\033[0m")
    print(f"Никнейм: \033[1;36m{nickname}\033[0m")
    
    # Словарь соединений по адресам отправителей
    connections = {}
    print_help()
    
    try:
        while True:
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                command = safe_input("\033[1;37m[READY]\033[0m> ").strip().lower()
                
                if command == 'exit':
                    raise KeyboardInterrupt
                    
                elif command == 'help':
                    print_help()
                    
                elif command == 'status':
                    if connections:
                        print("\n=== Активные соединения ===")
                        for addr, conn in connections.items():
                            print(str(conn))
                    else:
                        print_status_message("Нет активных соединений", "info")
                        
                else:
                    print_status_message("Неизвестная команда. Введите 'help' для справки.", "error")
            
            # Проверяем входящие данные
            frame = read_frame(ser)
            if frame:
                # Проверяем, что фрейм предназначен нам
                if frame.receiver != MY_ADDR and frame.receiver != Frame.BROADCAST_ADDR:
                    continue
                
                # Получаем или создаем объект соединения
                if frame.sender not in connections:
                    connections[frame.sender] = Connection(MY_ADDR, frame.sender, local_nick=nickname)
                    print_status_message(f"Новое соединение от узла 0x{frame.sender:02X}", "info")
                
                connection = connections[frame.sender]
                old_state = connection.state
                
                # Обрабатываем фрейм и получаем ответ если нужен
                response = connection.handle_frame(frame)
                
                # Логируем изменение состояния соединения
                if old_state != connection.state:
                    if connection.state == ConnectionState.CONNECTED:
                        print_status_message(f"Установлено соединение с {connection.remote_nick} (0x{connection.remote_addr:02X})", "success")
                    elif connection.state == ConnectionState.DISCONNECTED:
                        print_status_message(f"Разорвано соединение с {connection.remote_nick} (0x{connection.remote_addr:02X})", "warning")
                
                if response:
                    print_status_message(f"Отправка {Frame.FRAME_TYPES.get(response.frame_type, f'0x{response.frame_type:02X}')} → {connection.remote_nick}", "info")
                    send_frame(ser, response)
                
                # Выводим сообщение если это информационный фрейм
                if frame.frame_type == Frame.TYPE_I and connection.is_connected():
                    try:
                        text = frame.data.decode('utf-8')
                        print(f"\033[1;32m[{connection.remote_nick} → {connection.local_nick}]\033[0m {text}")
                    except UnicodeDecodeError:
                        print_status_message(f"[{connection.remote_nick} → {connection.local_nick}] Ошибка декодирования сообщения", "error")
            
            # Проверяем все соединения на таймауты
            for addr in list(connections.keys()):
                connection = connections[addr]
                if connection.is_connection_timeout():
                    print_status_message(f"Соединение с {connection.remote_nick} (0x{connection.remote_addr:02X}) разорвано по таймауту", "error")
                    connections.pop(addr)
            
            # Небольшая задержка для снижения нагрузки на процессор
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print_status_message("\nЗавершение работы...", "warning")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
