import serial
import serial.tools.list_ports
import time
import os
import glob
from frame import Frame

MY_ADDR = 0x02
RECV_ADDR = 0x01

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
        time.sleep(0.01)

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
    
    try:
        while True:
            message = input("Введите сообщение (или 'exit'): ")
            if message.lower() == 'exit':
                break

            frame = Frame(receiver=RECV_ADDR, sender=MY_ADDR, frame_type=Frame.TYPE_I, data=message.encode('utf-8'))
            send_frame(ser, frame.to_bytes())
            print(f"Отправлено: {frame}")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
