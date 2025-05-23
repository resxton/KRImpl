## Подготовка
1. Установите утилиту для создания виртуальных портов
```shell
brew install socat
```
2. Создайте 2 виртуальных порта
```shell
socat -d -d pty,raw,echo=0 pty,raw,echo=0
```
3. Примерный вывод команды:
```shell
2025/05/20 16:34:04 socat[61078] N PTY is /dev/ttys033
2025/05/20 16:34:04 socat[61078] N PTY is /dev/ttys034
2025/05/20 16:34:04 socat[61078] N starting data transfer loop with FDs [5,5] and [7,7]
```

Из него взять номера портов ```/dev/ttysN``` и вставить в соответствующие места в коде, например: 
```python
port = '/dev/ttys033'  # Ваш порт
```

В ```sender.py``` и ```receiver.py``` порты разные для создания пары.
