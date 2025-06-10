from enum import Enum
import time
from frame import Frame

class ConnectionState(Enum):
    DISCONNECTED = "DISCONNECTED"   # Нет соединения
    CONNECTING = "CONNECTING"       # Идёт установка соединения
    CONNECTED = "CONNECTED"         # Соединение установлено
    DISCONNECTING = "DISCONNECTING" # Идёт разрыв соединения

class Connection:
    """Класс для управления соединением между узлами."""
    def __init__(self, local_addr: int, remote_addr: int, local_nick: str = None, remote_nick: str = None):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.local_nick = local_nick or f"0x{local_addr:02X}"
        self.remote_nick = remote_nick or f"0x{remote_addr:02X}"
        self.state = ConnectionState.DISCONNECTED
        self.last_activity = None
        self.retry_count = 0
        self.max_retries = 3
        self.timeout = 1.0  # таймаут в секундах
    
    def create_frame(self, frame_type: int, data: bytes = b'') -> Frame:
        """Создает фрейм с учетом адресов отправителя и получателя."""
        if frame_type in [Frame.TYPE_I, Frame.TYPE_LINK]:
            if frame_type == Frame.TYPE_LINK:
                data = self.local_nick.encode('utf-8')
        return Frame(
            receiver=self.remote_addr,
            sender=self.local_addr,
            frame_type=frame_type,
            data=data
        )
    
    def handle_frame(self, frame: Frame) -> Frame | None:
        """Обрабатывает входящий фрейм и возвращает ответный фрейм если нужен."""
        if frame.sender != self.remote_addr or frame.receiver != self.local_addr:
            return None
        self.last_activity = time.time()
        if frame.frame_type == Frame.TYPE_LINK:
            try:
                self.remote_nick = frame.data.decode('utf-8')
            except:
                self.remote_nick = f"0x{frame.sender:02X}"
            self.state = ConnectionState.CONNECTED
            return Frame(
                receiver=self.remote_addr,
                sender=self.local_addr,
                frame_type=Frame.TYPE_ACK,
                data=self.local_nick.encode('utf-8')
            )
        elif frame.frame_type == Frame.TYPE_UPLINK:
            self.state = ConnectionState.DISCONNECTED
            return self.create_frame(Frame.TYPE_ACK)
        elif frame.frame_type == Frame.TYPE_ACK:
            if self.state == ConnectionState.CONNECTING:
                try:
                    self.remote_nick = frame.data.decode('utf-8')
                except:
                    self.remote_nick = f"0x{frame.sender:02X}"
                self.state = ConnectionState.CONNECTED
            elif self.state == ConnectionState.DISCONNECTING:
                self.state = ConnectionState.DISCONNECTED
        elif frame.frame_type == Frame.TYPE_I and self.state == ConnectionState.CONNECTED:
            return self.create_frame(Frame.TYPE_ACK)
        return None
    
    def connect(self) -> Frame:
        """Инициирует установку соединения."""
        if self.state != ConnectionState.DISCONNECTED:
            raise ValueError("Попытка установить соединение в неверном состоянии")
        self.state = ConnectionState.CONNECTING
        self.last_activity = time.time()
        self.retry_count = 0
        return self.create_frame(Frame.TYPE_LINK)
    
    def disconnect(self) -> Frame:
        """Инициирует разрыв соединения."""
        if self.state != ConnectionState.CONNECTED:
            raise ValueError("Попытка разорвать несуществующее соединение")
        self.state = ConnectionState.DISCONNECTING
        self.last_activity = time.time()
        self.retry_count = 0
        return self.create_frame(Frame.TYPE_UPLINK)
    
    def check_timeout(self) -> Frame | None:
        """Проверяет таймаут и возвращает фрейм для повторной отправки если нужно."""
        if self.last_activity is None:
            return None
        if time.time() - self.last_activity > self.timeout:
            if self.retry_count >= self.max_retries:
                self.state = ConnectionState.DISCONNECTED
                return None  # Возвращаем None, чтобы указать, что попытки исчерпаны
            self.retry_count += 1
            self.last_activity = time.time()
            if self.state == ConnectionState.CONNECTING:
                return self.create_frame(Frame.TYPE_LINK)
            elif self.state == ConnectionState.DISCONNECTING:
                return self.create_frame(Frame.TYPE_UPLINK)
        return None
    
    def is_connection_timeout(self) -> bool:
        """Проверяет, истек ли таймаут соединения."""
        if self.last_activity is None or self.state != ConnectionState.CONNECTED:
            return False
        return time.time() - self.last_activity > 300
    
    def is_connected(self) -> bool:
        """Проверяет, установлено ли соединение."""
        return self.state == ConnectionState.CONNECTED
    
    def __str__(self) -> str:
        return f"Connection {self.local_nick}↔{self.remote_nick} [{self.state.value}]"