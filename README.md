# AVC1WRITER (2020-2021 годов разработки)
Консольная и графическая версии программ для корректной подготовки и записи AVC файла на SD карту
для теста в тестере AVC1READER

Основная идея программы - монтировать/размонтировать и форматировать SD карту с последующей записью
AVC файла на SD карту. Программа также добавляет в конец AVC файла последнюю строку, которая 
интерпретируется AVC1READER как последняя (содержит только символы X и x). 

AVC1WRITER - консольный Bash скрипт, который выполняет вышепреведенные функции

AVC1WRITER_UI - программа с графическим интерфейсом для запуска которой необходим **Python 3** 
с установленной библиотекой **PySide2**

Форматирование SD карты необходимо для восстановления исходного состояния файловой системы FAT32 
(FAT таблицы и прочее). Если просто так удалить AVC файл и записать новый, то тестер AVC1READER
откроет его неправильно, а то и просто в файловой системе на SD карте будет каша.

Форматировать заново SD карту, записывать AVC файл можно и вручную, а добавлять 
последнюю строку можно и в текстовом редакторе. Но использование отдельной программы автоматизирует
этот процесс. К тому же, в AVC1WRITER_UI можно назначать отдельные сигналы из AVC файла на колодку,
изменяя их порядок.
