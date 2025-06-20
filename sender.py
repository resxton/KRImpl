import serial
import serial.tools.list_ports
import time
import os
import glob
import sys
import locale
from hamming import encode_4bit, decode_7bit
from frame import Frame
from connection import Connection, ConnectionState
import select
import random
from config import SerialConfig, configure_port, print_serial_config

MY_ADDR = random.randint(0x40, 0x7E)  # Случайный адрес отправителя (верхняя половина диапазона)

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

def parse_address(addr_str: str) -> int | None:
    """Парсит адрес из строки в формате 0xXX."""
    try:
        # Убираем пробелы и переводим в нижний регистр
        addr_str = addr_str.strip().lower()
        
        # Проверяем формат 0xXX
        if not addr_str.startswith('0x'):
            addr_str = '0x' + addr_str
            
        # Преобразуем в число
        addr = int(addr_str, 16)
        
        # Проверяем диапазон
        if 0x00 <= addr <= 0x7F:
            return addr
        else:
            print_status_message("Адрес должен быть в диапазоне 0x00-0x7F", "error")
            return None
    except ValueError:
        print_status_message("Неверный формат адреса. Используйте формат 0xXX или XX (hex)", "error")
        return None

def encode_and_send_byte(ser, byte: int):
    """Кодирует и отправляет один байт."""
    upper_nibble = (byte >> 4) & 0x0F
    lower_nibble = byte & 0x0F
    
    encoded_upper = encode_4bit(upper_nibble)
    encoded_lower = encode_4bit(lower_nibble)
    
    # Отправляем каждую половину байта с маркерами
    ser.write(bytes([0xFF, encoded_upper, 0xFF]))
    ser.write(bytes([0xFF, encoded_lower, 0xFF]))
    time.sleep(0.01)

def send_frame(ser, frame: Frame):
    """Отправляет фрейм."""
    for byte in frame.to_bytes():
        encode_and_send_byte(ser, byte)

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

def get_status_prompt(connection: Connection) -> str:
    """Возвращает красиво отформатированный статус для промпта."""
    state = connection.state
    if state == ConnectionState.CONNECTED:
        return f"\033[32m[CONNECTED to {connection.remote_nick}]\033[0m"
    elif state == ConnectionState.CONNECTING:
        return f"\033[33m[CONNECTING to {connection.remote_nick}...]\033[0m"
    elif state == ConnectionState.DISCONNECTING:
        return f"\033[33m[DISCONNECTING from {connection.remote_nick}...]\033[0m"
    else:
        return "\033[31m[DISCONNECTED]\033[0m"

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
    print("  \033[32mconnect\033[0m    - установить соединение")
    print("  \033[31mdisconnect\033[0m - разорвать соединение")
    print("  \033[36mstatus\033[0m     - показать статус соединения")
    print("  \033[36mconfig\033[0m     - настроить параметры порта")
    print("  \033[33mexit\033[0m       - выход")
    print("  \033[36mhelp\033[0m       - показать эту справку")
    print("\033[1mЧтобы отправить сообщение, просто введите текст.\033[0m\n")

def check_for_response(ser, connection):
    """Проверяет наличие ответа от получателя."""
    if ser.in_waiting:
        frame = read_frame(ser)
        if frame:
            if frame.frame_type == Frame.TYPE_ACK:
                if connection.state == ConnectionState.CONNECTING:
                    print_status_message(f"Получено подтверждение установки соединения от {connection.remote_nick}", "success")
                elif connection.state == ConnectionState.DISCONNECTING:
                    print_status_message(f"Получено подтверждение разрыва соединения от {connection.remote_nick}", "success")
                else:
                    print_status_message(f"Сообщение доставлено {connection.remote_nick}", "success")
            else:
                print_status_message(f"Получен ответ типа 0x{frame.frame_type:02X} от {connection.remote_nick}", "info")
            
            old_state = connection.state
            connection.handle_frame(frame)
            
            if old_state != connection.state:
                if connection.state == ConnectionState.CONNECTED:
                    print_status_message(f"Соединение с {connection.remote_nick} установлено!", "success")
                elif connection.state == ConnectionState.DISCONNECTED:
                    print_status_message(f"Соединение с {connection.remote_nick} закрыто", "warning")
                    return True  # Сигнализируем, что соединение закрыто
    return False

def check_connection_timeout(ser, connection) -> bool:
    """Проверяет таймауты соединения и возвращает True, если все попытки исчерпаны."""
    retry_frame = connection.check_timeout()
    if retry_frame:
        if connection.retry_count >= connection.max_retries:
            print_status_message(f"Узел 0x{connection.remote_addr:02X} недоступен после {connection.max_retries} попыток", "error")
            return True
        print_status_message(f"Повторная попытка {connection.retry_count} из {connection.max_retries}...", "warning")
        send_frame(ser, retry_frame)
    return False

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

    # Запрашиваем никнейм
    nickname = safe_input("Введите ваш никнейм (Enter для адреса по умолчанию): ").strip()
    if not nickname:
        nickname = f"0x{MY_ADDR:02X}"
    
    # Загружаем или создаем конфигурацию порта
    config = SerialConfig.load()
    if not config:
        config = configure_port()
        if not config:
            return
    
    print_serial_config(config)
    ser = serial.Serial(port, **config.to_dict())
    print(f"Подключено к {port}")
    print(f"Ваш адрес: \033[1;33m0x{MY_ADDR:02X}\033[0m")
    print(f"Ваш никнейм: \033[1;36m{nickname}\033[0m")
    
    connection = None
    print_help()
    
    try:
        while True:
            # Проверяем таймауты если есть активное соединение
            if connection:
                # Проверяем таймаут соединения
                if connection.is_connection_timeout():
                    print_status_message(f"Соединение с {connection.remote_nick} разорвано по таймауту", "warning")
                    connection = None
                    continue
                
                # Проверяем ответы
                if check_for_response(ser, connection):
                    connection = None  # Обнуляем соединение если оно было закрыто
            
            # Проверяем ввод пользователя
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                prompt = get_status_prompt(connection) if connection else "\033[1;37m[READY]\033[0m"
                user_input = safe_input(f"{prompt}> ").strip()
                if not user_input:
                    continue
                
                # Команду приводим к нижнему регистру для проверки
                command = user_input.lower()
                    
                if command == 'exit':
                    if connection and connection.state == ConnectionState.CONNECTED:
                        print_status_message("Разрываем соединение перед выходом...", "warning")
                        send_frame(ser, connection.disconnect())
                    break
                    
                elif command == 'help':
                    print_help()
                    
                elif command == 'status':
                    if connection:
                        print("\n" + str(connection))
                        if connection.state == ConnectionState.CONNECTING:
                            print_status_message(f"Попытка {connection.retry_count} из {connection.max_retries}", "info")
                    else:
                        print_status_message(f"Нет активного соединения. Ваш адрес: 0x{MY_ADDR:02X}", "info")
                    
                elif command == 'config':
                    # Сохраняем текущие настройки
                    old_config = config
                    
                    # Настраиваем новые параметры
                    new_config = configure_port()
                    if new_config:
                        # Если конфигурация изменилась
                        if new_config != old_config:
                            # Сохраняем новую конфигурацию
                            new_config.save()
                            config = new_config
                            print_status_message("Конфигурация сохранена", "success")
                            print_status_message("Для применения новых настроек перезапустите программу", "warning")
                        else:
                            print_status_message("Конфигурация не изменилась", "info")
                    
                elif command.startswith('connect'):
                    if connection:
                        print_status_message("Уже есть активное соединение", "error")
                        continue
                        
                    # Парсим адрес из команды или запрашиваем его
                    parts = command.split()
                    if len(parts) > 1:
                        remote_addr = parse_address(parts[1])
                    else:
                        addr_input = safe_input("Введите адрес узла (в формате 0xXX): ")
                        remote_addr = parse_address(addr_input)
                    
                    if remote_addr is None:
                        continue
                        
                    connection = Connection(MY_ADDR, remote_addr, local_nick=nickname)
                    try:
                        frame = connection.connect()
                        print_status_message(f"Отправка запроса на соединение с 0x{connection.remote_addr:02X}...", "info")
                        send_frame(ser, frame)
                    except ValueError as e:
                        print_status_message(f"Ошибка: {e}", "error")
                        connection = None
                        
                elif command == 'disconnect':
                    if not connection:
                        print_status_message("Нет активного соединения", "error")
                        continue
                        
                    try:
                        frame = connection.disconnect()
                        print_status_message(f"Отправка запроса на разрыв соединения с 0x{connection.remote_addr:02X}...", "warning")
                        send_frame(ser, frame)
                    except ValueError as e:
                        print_status_message(f"Ошибка: {e}", "error")
                        
                else:
                    if not connection:
                        print_status_message("Ошибка: нет активного соединения", "error")
                        continue
                        
                    if not connection.is_connected():
                        print_status_message("Ошибка: соединение не установлено", "error")
                        continue
                        
                    # Используем оригинальный текст user_input для отправки сообщения
                    frame = connection.create_frame(Frame.TYPE_I, user_input.encode('utf-8'))
                    print_status_message(f"Отправка [0x{frame.sender:02X} → 0x{frame.receiver:02X}]: {user_input}", "info")
                    send_frame(ser, frame)
            
    except KeyboardInterrupt:
        print_status_message("\nЗавершение работы...", "warning")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
