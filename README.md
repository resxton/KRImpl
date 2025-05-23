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

Из него взять номера портов ```/dev/ttysN``` и выбрать при запуске программы, например: 
```shell
(base) > $ python3 sender.py
Доступные порты:
0: /dev/cu.debug-console — n/a
1: /dev/cu.Bluetooth-Incoming-Port — n/a
2: /dev/ttys0 — виртуальный
3: /dev/ttys1 — виртуальный
4: /dev/ttys2 — виртуальный
5: /dev/ttys3 — виртуальный
6: /dev/ttys4 — виртуальный
7: /dev/ttys5 — виртуальный
8: /dev/ttys6 — виртуальный
9: /dev/ttys7 — виртуальный
10: /dev/ttys8 — виртуальный
11: /dev/ttys9 — виртуальный
12: /dev/ttysa — виртуальный
13: /dev/ttysb — виртуальный
14: /dev/ttysc — виртуальный
15: /dev/ttysd — виртуальный
16: /dev/ttyse — виртуальный
17: /dev/ttysf — виртуальный
18: /dev/ttys031 — виртуальный
19: /dev/ttys032 — виртуальный
20: /dev/ttys033 — виртуальный
21: /dev/ttys034 — виртуальный
22: /dev/ttys038 — виртуальный
23: /dev/ttys039 — виртуальный
24: /dev/ttys040 — виртуальный
25: /dev/ttys041 — виртуальный
26: /dev/ttys042 — виртуальный
27: /dev/ttys043 — виртуальный
28: /dev/ttys002 — виртуальный
29: /dev/ttys003 — виртуальный
30: /dev/ttys005 — виртуальный
31: /dev/ttys006 — виртуальный
32: /dev/ttys008 — виртуальный
33: /dev/ttys009 — виртуальный
Вы хотите выбрать порт из списка? (y/n): y
Выберите порт по номеру: 20
```

В ```sender.py``` и ```receiver.py``` порты выбираем спаренные (в примере это 33 и 34)
