from dataclasses import dataclass
from typing import Optional
import json
import os

@dataclass
class SerialConfig:
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = 'N'  # N - none, E - even, O - odd
    stopbits: float = 1.0
    timeout: float = 0.1
    
    @classmethod
    def load(cls, filename: str = 'serial_config.json') -> 'SerialConfig':
        """Загружает конфигурацию из JSON файла."""
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return cls(**data)
        return cls()  # Возвращаем конфиг по умолчанию
    
    def save(self, filename: str = 'serial_config.json') -> None:
        """Сохраняет конфигурацию в JSON файл."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, indent=4)
    
    def to_dict(self) -> dict:
        """Преобразует конфигурацию в словарь для serial.Serial."""
        return {
            'baudrate': self.baudrate,
            'bytesize': self.bytesize,
            'parity': self.parity,
            'stopbits': self.stopbits,
            'timeout': self.timeout
        }

def print_serial_config(config: SerialConfig):
    """Выводит текущую конфигурацию в консоль."""
    print("\n=== Настройки COM-порта ===")
    print(f"Скорость обмена: \033[1;36m{config.baudrate}\033[0m бод")
    print(f"Биты данных: \033[1;36m{config.bytesize}\033[0m")
    print(f"Четность: \033[1;36m{config.parity}\033[0m")
    print(f"Стоп-биты: \033[1;36m{config.stopbits}\033[0m")
    print(f"Таймаут: \033[1;36m{config.timeout}\033[0m сек")
    print("=" * 25 + "\n")

def configure_port() -> Optional[SerialConfig]:
    """Интерактивная настройка параметров COM-порта."""
    config = SerialConfig.load()
    print_serial_config(config)
    
    if input("Изменить настройки? (y/N): ").lower() != 'y':
        return config
    
    print("\nВведите новые значения (или Enter для сохранения текущего):")
    
    # Скорость обмена
    baudrates = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
    print("\nДоступные скорости:")
    for i, rate in enumerate(baudrates, 1):
        print(f"{i}: {rate}")
    try:
        choice = input(f"Выберите скорость (1-{len(baudrates)}): ").strip()
        if choice:
            config.baudrate = baudrates[int(choice) - 1]
    except (ValueError, IndexError):
        print("Оставляем текущее значение")
    
    # Биты данных
    try:
        bits = input("Биты данных (5-8): ").strip()
        if bits:
            bits = int(bits)
            if 5 <= bits <= 8:
                config.bytesize = bits
    except ValueError:
        print("Оставляем текущее значение")
    
    # Четность
    print("\nЧетность:")
    print("N: Нет")
    print("E: Четный")
    print("O: Нечетный")
    parity = input("Выберите режим (N/E/O): ").strip().upper()
    if parity in ['N', 'E', 'O']:
        config.parity = parity
    
    # Стоп-биты
    print("\nСтоп-биты:")
    print("1: 1 бит")
    print("2: 2 бита")
    print("1.5: 1.5 бита")
    try:
        stopbits = input("Выберите количество стоп-бит (1/1.5/2): ").strip()
        if stopbits:
            config.stopbits = float(stopbits)
    except ValueError:
        print("Оставляем текущее значение")
    
    # Таймаут
    try:
        timeout = input("Таймаут в секундах (например, 0.1): ").strip()
        if timeout:
            config.timeout = float(timeout)
    except ValueError:
        print("Оставляем текущее значение")
    
    # Сохраняем конфигурацию
    config.save()
    print("\nНовые настройки:")
    print_serial_config(config)
    
    return config 