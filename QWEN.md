# Project Context: tag2opc

## Project Overview

**tag2opc** — утилита командной строки, автоматизирующая настройку MasterOPC. Инструмент преобразует список тегов из SCADA FLS ECS7 в готовый файл конфигурации (.sdv) для OPC сервера.

### Основное назначение
- Чтение тегов из JSON-файла (`data/tags.json`)
- Парсинг групп тегов из текстового файла (`tags_list.txt`)
- Генерация конфигурационного файла `.sdv` в формате JSON с иерархической структурой
- Создание CSV-отчёта с конвертированными тегами

### Технологии
- **Язык:** Python 3.10+
- **Менеджер пакетов:** uv
- **Зависимости:** 
  - PyYAML >= 6.0
  - colorama >= 0.4.6
- **Форматы:** JSON (вход), JSON (SDV), CSV

## Структура проекта

```
tag2opc/
├── tag2opc.py               # Основной скрипт конвертера
├── pyproject.toml           # Конфигурация проекта
├── tags_list.txt            # Список тегов с группировкой
├── data/
│   ├── tags.json            # Исходные данные тегов
│   └── template.sdv         # Шаблон SDV-файла
├── resources/               # Ресурсы (иконки, изображения)
├── siemens_plc_opc.sdv  # Выходной файл
└── siemens_plc_opc.csv  # CSV-отчёт
```

## Building and Running

### Установка зависимостей
```bash
uv sync
```

### Запуск конвертера

```bash
# Запуск с параметрами по умолчанию
python tag2opc.py

# Запуск с указанием входного и выходного файлов
python tag2opc.py tags_list.txt siemens_plc_opc_converted

# Показать справку
python tag2opc.py --help
python tag2opc.py -h
python tag2opc.py -?
```

### Аргументы командной строки

| Аргумент | Короткий | Описание | По умолчанию |
|----------|----------|----------|--------------|
| `input` | — | Путь к файлу со списком тегов | `./tags_list.txt` |
| `output` | — | Путь к выходному файлу | `siemens_plc_opc_converted.sdv` |
| `--help` | `-h`, `-?` | Показать справку | — |

### Примеры использования

```bash
# Конвертация с параметрами по умолчанию
python tag2opc.py

# Конвертация с указанием файлов
python tag2opc.py tags_list.txt siemens_plc_opc_converted

# Показать справку
python tag2opc.py -h
```

## Форматы данных

### tags_list.txt
```
Group:имя_группы:
tag1
tag2

Group:другая_группа:
tag3
tag4
```

### tags.json (структура тега)
```json
{
    "Id": 1407,
    "Tag": "_920_OUTDOOR_TEMP",
    "Groups": "992CD100G04",
    "DescEng": "Outdoor temp",
    "DescRus": "Уличная температура",
    "PLC": {
        "PLCNo": "992",
        "Input": {
            "Type": "Float",
            "Block": 9,
            "Word": 88
        }
    },
    "PLC_INP": "%DB9.DBD88",
    "EngUnitId": "°C",
    "Constant1": 1.0
}
```

### SDV-файл
JSON-формат с табуляцией как разделителем, кодировка cp1251. Содержит иерархическую структуру:
- Device (корневой узел)
  - Group (группа тегов)
    - Teg (тег с параметрами)

## Ключевые функции

| Функция | Описание |
|---------|----------|
| `parse_tags_list_groups()` | Парсинг групп из tags_list.txt |
| `parse_plc_address()` | Парсинг адресов типа `%DB4.DBD320` |
| `map_type()` | Маппинг типов данных JSON → S7 |
| `create_tag_node()` | Создание структуры тега для SDV |
| `convert_tags_groups_to_sdv()` | Основная функция конвертации |
| `normalize_node_keys()` | Нормализация ключей node_xx* → node |

## Типы данных (маппинг)

| JSON Type | S7 DataType |
|-----------|-------------|
| Float/Flt | REAL |
| 16 Bit | WORD |
| 32 Bit | DINT |
| 8 Bit/Byte | BOOL |
| Bool/Bit | BOOL |

## Development Practices

- **Стиль кода:** PEP 8, type hints для всех функций
- **Кодировка:** UTF-8 для входных файлов, cp1251 для SDV
- **Обработка ошибок:** ValueError для некорректных адресов PLC
- **Вывод:** Цветные сообщения с использованием colorama

## Цветовой вывод

| Цвет | Элемент |
|------|---------|
| CYAN (голубой) | Заголовки этапов загрузки/сохранения |
| GREEN (зелёный) | Успешные операции, количество тегов, галочки ✓ |
| MAGENTA (пурпурный) | Заголовки групп |
| YELLOW (жёлтый) | Адреса PLC (DB-блоки) |
| RED (красный) | Ошибки и пропущенные теги |

## Примечания

- SDV-файлы используют нестандартный JSON с табуляцией
- Ключи `node_xx*` нормализуются в `node` после сохранения
- Файл `template.sdv` содержит шаблон устройства Siemens PLC

