def encode_4bit(data: int) -> int:
    """Кодирует 4 бита в 7-битный код Хэмминга."""
    d1 = (data >> 0) & 1
    d2 = (data >> 1) & 1
    d3 = (data >> 2) & 1
    d4 = (data >> 3) & 1
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p3 = d2 ^ d3 ^ d4
    return (p1 | (p2 << 1) | (d1 << 2) | (p3 << 3) | (d2 << 4) | (d3 << 5) | (d4 << 6))

def decode_7bit(encoded: int) -> int:
    """Декодирует 7-битный код Хэмминга в 4 бита."""
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

    