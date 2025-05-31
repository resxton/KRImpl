class HammingCodec:
    @staticmethod
    def encode_4bit(data: int) -> int:
        """Кодирование 4-битного числа в 7-битное с кодом Хэмминга."""
        d1 = (data >> 0) & 1
        d2 = (data >> 1) & 1
        d3 = (data >> 2) & 1
        d4 = (data >> 3) & 1
        p1 = d1 ^ d2 ^ d4
        p2 = d1 ^ d3 ^ d4
        p3 = d2 ^ d3 ^ d4
        return (p1 | (p2 << 1) | (d1 << 2) | (p3 << 3) | (d2 << 4) | (d3 << 5) | (d4 << 6))

    @staticmethod
    def decode_7bit(encoded: int) -> int:
        """Декодирование 7-битного числа в 4-битное с исправлением ошибок."""
        p1 = (encoded >> 0) & 1
        p2 = (encoded >> 1) & 1
        d1 = (encoded >> 2) & 1
        p3 = (encoded >> 3) & 1
        d2 = (encoded >> 4) & 1
        d3 = (encoded >> 5) & 1
        d4 = (encoded >> 6) & 1

        # Вычисление синдромов
        s1 = p1 ^ d1 ^ d2 ^ d4
        s2 = p2 ^ d1 ^ d3 ^ d4
        s3 = p3 ^ d2 ^ d3 ^ d4
        
        # Определение позиции ошибки
        error_pos = s1 + (s2 << 1) + (s3 << 2)
        if error_pos:
            encoded ^= (1 << (error_pos - 1))
            
        # Извлечение информационных битов
        return (d1 << 0) | (d2 << 1) | (d3 << 2) | (d4 << 3)

    @staticmethod
    def encode_byte(byte: int) -> bytes:
        """Кодирование байта в последовательность с маркерами."""
        upper_nibble = (byte >> 4) & 0x0F
        lower_nibble = byte & 0x0F
        
        encoded_upper = HammingCodec.encode_4bit(upper_nibble)
        encoded_lower = HammingCodec.encode_4bit(lower_nibble)
        
        return bytes([
            0xFF, encoded_upper, 0xFE,
            0xFF, encoded_lower, 0xFE
        ])

    @staticmethod
    def decode_stream(data: bytes) -> bytes:
        """Декодирование потока байтов с маркерами."""
        result = bytearray()
        i = 0
        while i < len(data):
            if data[i] == 0xFF and i + 2 < len(data) and data[i + 2] == 0xFE:
                decoded = HammingCodec.decode_7bit(data[i + 1])
                result.append(decoded)
                i += 3
            else:
                i += 1
        
        # Собираем пары nibbles в байты
        final_result = bytearray()
        for i in range(0, len(result), 2):
            if i + 1 < len(result):
                byte = (result[i] << 4) | result[i + 1]
                final_result.append(byte)
        
        return bytes(final_result) 