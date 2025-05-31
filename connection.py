from enum import Enum
import time
from frame import Frame

class ConnectionState(Enum):
    DISCONNECTED = "DISCONNECTED"   # Нет соединения
    CONNECTING = "CONNECTING"       # Идёт установка соединения
    CONNECTED = "CONNECTED"         # Соединение установлено
    DISCONNECTING = "DISCONNECTING" # Идёт разрыв соединения

class Connection:
    def __init__(self, local_addr: int, remote_addr: int):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.state = ConnectionState.DISCONNECTED
        self.last_activity = None
        self.retry_count = 0
        self.max_retries = 3
        self.timeout = 5.0  # таймаут в секундах
    
    def create_frame(self, frame_type: int, data: bytes = b'') -> Frame:
        """Создает фрейм с учетом адресов отправителя и получателя."""
        return Frame(
            receiver=self.remote_addr,
            sender=self.local_addr,
            frame_type=frame_type,
            data=data
        )
    
    def handle_frame(self, frame: Frame) -> Frame | None:
        """Обрабатывает входящий фрейм и возвращает ответный фрейм если нужен."""
        if frame.sender != self.remote_addr or frame.receiver != self.local_addr:
            return None  # игнорируем фреймы не для этого соединения
            
        self.last_activity = time.time()
        
        if frame.frame_type == Frame.TYPE_LINK:
            # Получен запрос на соединение
            self.state = ConnectionState.CONNECTED
            return self.create_frame(Frame.TYPE_ACK)
            
        elif frame.frame_type == Frame.TYPE_UPLINK:
            # Получен запрос на разрыв соединения
            self.state = ConnectionState.DISCONNECTED
            return self.create_frame(Frame.TYPE_ACK)
            
        elif frame.frame_type == Frame.TYPE_ACK:
            # Получено подтверждение
            if self.state == ConnectionState.CONNECTING:
                self.state = ConnectionState.CONNECTED
            elif self.state == ConnectionState.DISCONNECTING:
                self.state = ConnectionState.DISCONNECTED
                
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
                return None
                
            self.retry_count += 1
            self.last_activity = time.time()
            
            if self.state == ConnectionState.CONNECTING:
                return self.create_frame(Frame.TYPE_LINK)
            elif self.state == ConnectionState.DISCONNECTING:
                return self.create_frame(Frame.TYPE_UPLINK)
                
        return None
    
    def is_connected(self) -> bool:
        """Проверяет, установлено ли соединение."""
        return self.state == ConnectionState.CONNECTED
    
    def __str__(self) -> str:
        return f"Connection {self.local_addr:02X}↔{self.remote_addr:02X} [{self.state.value}]" 