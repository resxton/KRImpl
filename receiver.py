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
    """Читает и декодирует кадр."""
    data = []
    while True:
        byte = ser.read(1)
        if not byte:
            return None
        
        if byte == b'\xFF':  # Начало кадра
            encoded = ser.read(1)[0]
            stop_byte = ser.read(1)
            
            if stop_byte == b'\xFE':
                decoded = hamming_decode_7bit(encoded)
                data.append(decoded)
            else:
                print("Ошибка: некорректный стоп-байт")
        
        if len(data) >= 2:  # Собрали полный байт
            return bytes([(data[0] << 4) | data[1]])

def main():
    port = '/dev/ttys034'  # Ваш порт
    ser = serial.Serial(port, baudrate=9600, timeout=1)
    
    try:
        print("Ожидание данных...")
        while True:
            frame = read_frame(ser)
            if frame:
                print(f"Принято: {frame.decode('utf-8', errors='replace')}")
                
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()