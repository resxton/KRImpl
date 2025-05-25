import os
import glob
import serial
import serial.tools.list_ports
import time
from frame import Frame

def list_serial_ports():
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
        if byte == b'\xFF':  # Старт кадра
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
    print(f"[{sender_addr:02X} → {receiver_addr:02X}] Отправлен ACK")

def send_frame(ser, data: bytes):
    for byte in data:
        upper_nibble = (byte >> 4) & 0x0F
        lower_nibble = byte & 0x0F

        encoded_upper = hamming_encode_4bit(upper_nibble)
        encoded_lower = hamming_encode_4bit(lower_nibble)

        ser.write(bytes([0xFF, encoded_upper, 0xFE]))
        ser.write(bytes([0xFF, encoded_lower, 0xFE]))
        time.sleep(0.01)

def hamming_encode_4bit(data: int) -> int:
    d1 = (data >> 0) & 1
    d2 = (data >> 1) & 1
    d3 = (data >> 2) & 1
    d4 = (data >> 3) & 1
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return (p1 | (p2 << 1) | (d1 << 2) | (p3 << 3) | (d2 << 4) | (d3 << 5) | (d4 << 6))

def main():
    MY_ADDR = int(input("Введите адрес текущего узла (например, 0x01): "), 16)

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
    print(f"Ожидание данных на {port}...")

    buffer = bytearray()
    in_frame = False

    try:
        while True:
            byte = read_frame(ser)
            if not byte:
                continue

            b = byte[0]

            if b == 0xFF and not in_frame:
                buffer = bytearray([b])
                in_frame = True
            elif in_frame:
                buffer.append(b)
                if b == 0xFF and len(buffer) >= 6:
                    try:
                        frame = Frame.from_bytes(buffer)

                        # Проверяем адрес назначения
                        if frame.receiver != MY_ADDR and frame.receiver != Frame.BROADCAST_ADDR:
                            print(f"[Служебно] Кадр не для меня, адрес {frame.receiver:02X}")
                        else:
                            # Обрабатываем тип кадра
                            if frame.frame_type == Frame.TYPE_I:
                                text = frame.data.decode('utf-8', errors='replace').strip()
                                print(f"[{frame.sender:02X} → {frame.receiver:02X}] Текст: {text}")
                                # Отправляем ACK в ответ
                                send_ack(ser, frame.sender, frame.receiver)
                            elif frame.frame_type == Frame.TYPE_ACK:
                                print(f"[{frame.sender:02X}] Принят ACK")
                            elif frame.frame_type == Frame.TYPE_RET:
                                print(f"[{frame.sender:02X}] Запрошен RET — повтор отправки (не реализован)")
                                # Здесь можно добавить логику повторной отправки
                            elif frame.frame_type == Frame.TYPE_LINK:
                                print(f"[{frame.sender:02X}] Установка соединения")
                            elif frame.frame_type == Frame.TYPE_UPLINK:
                                print(f"[{frame.sender:02X}] Разрыв соединения")
                            else:
                                print(f"[{frame.sender:02X}] Неизвестный тип кадра: {frame.frame_type:02X}")

                    except Exception as e:
                        print("Ошибка при разборе кадра:", e)
                    in_frame = False

    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
