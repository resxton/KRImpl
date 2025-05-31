class Frame:
    START_BYTE = 0xFF
    STOP_BYTE = 0xFF
    BROADCAST_ADDR = 0x7F

    # Типы кадров
    TYPE_I = 0x01      # Информационный
    TYPE_LINK = 0x02   # Установка соединения
    TYPE_UPLINK = 0x03 # Разрыв соединения
    TYPE_ACK = 0x04    # Подтверждение
    TYPE_RET = 0x05    # Запрос повтора

    # Описания типов фреймов
    FRAME_TYPES = {
        TYPE_I: "Информационный",
        TYPE_LINK: "Установка соединения",
        TYPE_UPLINK: "Разрыв соединения",
        TYPE_ACK: "Подтверждение",
        TYPE_RET: "Запрос повтора"
    }

    def __init__(self, receiver: int, sender: int, frame_type: int, data: bytes = b''):
        self.receiver = receiver
        self.sender = sender
        self.frame_type = frame_type
        self.data = data

    def to_bytes(self) -> bytes:
        length = len(self.data)
        result = bytes([
            self.START_BYTE,
            self.receiver,
            self.sender,
            self.frame_type,
            length
        ]) + self.data + bytes([self.STOP_BYTE])
        return result

    @staticmethod
    def from_bytes(raw: bytes) -> 'Frame':
        if len(raw) < 6:
            raise ValueError("Кадр слишком короткий")
        if raw[0] != Frame.START_BYTE or raw[-1] != Frame.STOP_BYTE:
            raise ValueError("Неверные старт/стоп байты")

        receiver = raw[1]
        sender = raw[2]
        frame_type = raw[3]
        length = raw[4]

        if len(raw) != 6 + length:
            raise ValueError(f"Длина кадра: {len(raw)}, ожидаемая: {6 + length}")

        data = raw[5:-1]
        return Frame(receiver, sender, frame_type, data)

    def __repr__(self):
        return (f"Frame(to=0x{self.receiver:02X}, from=0x{self.sender:02X}, "
                f"type=0x{self.frame_type:02X}, data={self.data})")
