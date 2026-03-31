# Project Context: tags2opc

## Project Overview

**tags2opc** — утилита командной строки на Python для конвертации тегов из YAML-формата в конфигурацию Siemens PLC (.sdv) для системы MasterOPC.

### Основное назначение
- Чтение тегов из YAML-файла (`data/tags.yaml`)
- Парсинг групп тегов из текстового файла (`tags_list.txt`)
- Генерация конфигурационного файла `.sdv` в формате JSON с иерархической структурой
- Создание CSV-отчёта с конвертированными тегами

### Технологии
- **Язык:** Python 3.13
- **Менеджер пакетов:** uv
- **Зависимости:** PyYAML >= 6.0
- **Форматы:** YAML, JSON (SDV), CSV

## Структура проекта

```
tag2opc/
├── tags2opc.py              # Основной скрипт конвертера
├── pyproject.toml           # Конфигурация проекта
├── tags_list.txt            # Список тегов с группировкой
├── data/
│   ├── tags.yaml            # Исходные данные тегов
│   └── template.sdv         # Шаблон SDV-файла
├── resources/               # Ресурсы (иконки, изображения)
├── siemens_plc_opc_converted.sdv  # Выходной файл
└── siemens_plc_opc_converted.csv  # CSV-отчёт
```

## Building and Running

### Установка зависимостей
```bash
uv sync
```

### Запуск конвертера

**Режим с группами (по умолчанию):**
```bash
python tags2opc.py --mode groups
```

**Режим одиночной группы:**
```bash
python tags2opc.py --mode yaml --group Flot
```

### Аргументы командной строки

| Аргумент | Короткий | Описание | По умолчанию |
|----------|----------|----------|--------------|
| `--yaml` | `-y` | Путь к файлу tags.yaml | `./data/tags.yaml` |
| `--sdv` | `-s` | Путь к шаблону .sdv | `./data/template.sdv` |
| `--output` | `-o` | Путь выходного файла | `siemens_plc_opc_converted.sdv` |
| `--group` | `-g` | Имя группы для заполнения | `Flot` |
| `--filter` | `-f` | Файл со списком тегов для фильтрации | `tags_list.txt` |
| `--tags-list` | `-t` | Файл tags_list.txt с группами | `tags_list.txt` |
| `--mode` | `-m` | Режим: `yaml` или `groups` | `groups` |
| `--normalize` | `-n` | Нормализовать ключи node_xx* в файле | — |

### Примеры использования

```bash
# Конвертация с группами из tags_list.txt
python tags2opc.py -m groups -t tags_list.txt

# Конвертация в конкретную группу
python tags2opc.py -m yaml -g Flot -y data/tags.yaml

# Нормализация ключей в существующем файле
python tags2opc.py -n siemens_plc_opc_converted.sdv
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

### tags.yaml (структура тега)
```yaml
- Id: 1407
  Tag: _920_OUTDOOR_TEMP
  Groups: 992CD100G04
  DescEng: Outdoor temp
  DescRus: Уличная температура
  PLC:
    PLCNo: '992'
    Input:
      Type: Float
      Block: 9
      Word: 88
  PLC_INP: '%DB9.DBD88'
  EngUnitId: °C
  Constant1: 1.0
```

### SDV-файл
JSON-формат с табуляцией как разделителем, кодировка cp1251. Содержит иерархическую структуру:
- Device (корневой узел)
  - Group (группа тегов)
    - Teg (тег с параметрами)

## Ключевые функции

| Функция | Описание |
|---------|----------|
| `parse_tags_list_groups()` | Парсинг groups из tags_list.txt |
| `parse_plc_address()` | Парсинг адресов типа `%DB4.DBD320` |
| `map_type()` | Маппинг типов данных YAML → S7 |
| `create_tag_node()` | Создание структуры тега для SDV |
| `convert_tags_groups_to_sdv()` | Основная функция конвертации |
| `normalize_node_keys()` | Нормализация ключей node_xx* → node |

## Типы данных (маппинг)

| YAML Type | S7 DataType |
|-----------|-------------|
| Float/Flt | REAL |
| 16 Bit | WORD |
| 32 Bit | DINT |
| 8 Bit/Byte | BYTE |
| Bool/Bit | BOOL |

## Development Practices

- **Стиль кода:** PEP 8, type hints для всех функций
- **Кодировка:** UTF-8 для входных файлов, cp1251 для SDV
- **Обработка ошибок:** ValueError для некорректных адресов PLC
- **Логирование:** print-сообщения с индикацией прогресса

## Примечания

- SDV-файлы используют нестандартный JSON с табуляцией
- Ключи `node_xx*` нормализуются в `node` после сохранения
- Файл `template.sdv` содержит шаблон устройства Siemens PLC
- Поддерживаются адреса: `%DBn.DBD/W/B{addr}`, `%I/Q/M/T/C{addr}.{bit}`
