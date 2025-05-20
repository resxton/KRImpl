import serial
import time

def hamming_encode_4bit(data: int) -> int:
    """Кодирует 4 бита в 7-битный код Хэмминга."""
    d1 = (data >> 0) & 1
    d2 = (data >> 1) & 1
    d3 = (data >> 2) & 1
    d4 = (data >> 3) & 1
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return (p1 | (p2 << 1) | (d1 << 2) | (p3 << 3) | (d2 << 4) | (d3 << 5) | (d4 << 6))

def send_frame(ser, data: bytes):
    """Отправляет данные в формате кадра с кодированием Хэмминга."""
    for byte in data:
        upper_nibble = (byte >> 4) & 0x0F  # Первые 4 бита
        lower_nibble = byte & 0x0F         # Последние 4 бита
        
        encoded_upper = hamming_encode_4bit(upper_nibble)
        encoded_lower = hamming_encode_4bit(lower_nibble)
        
        ser.write(bytes([0xFF, encoded_upper, 0xFE]))  # Старт + данные + стоп
        ser.write(bytes([0xFF, encoded_lower, 0xFE]))
        time.sleep(0.01)  # Задержка для стабильности

def main():
    port = '/dev/ttys033'  # Ваш порт
    ser = serial.Serial(port, baudrate=9600, timeout=1)
    
    try:
        while True:
            message = input("Введите сообщение (или 'exit'): ")
            if message.lower() == 'exit':
                break
            
            print(f"Отправка: {message}")
            send_frame(ser, (message + '\n').encode('utf-8'))
            
    finally:
        ser.close()

if __name__ == "__main__":
    main()