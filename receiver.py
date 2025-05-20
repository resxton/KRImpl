import serial

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
    port = '/dev/ttys034'
    ser = serial.Serial(port, baudrate=9600, timeout=1)
    
    buffer = bytearray()
    print("Ожидание данных...")
    
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