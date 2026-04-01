#!/usr/bin/env python3
"""
Конвертер тегов из формата tags.json в конфигурацию MasterOPC для Siemens PLC (.sdv)

Скрипт читает теги из JSON-файла и обновляет указанную группу в SDV-файле,
заменяя существующие теги на новые из JSON.
"""

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from colorama import init, Fore, Style

# Инициализация colorama для кроссплатформенной работы с цветами
init()


def parse_tags_list_groups(filepath: Path) -> dict[str, list[str]]:
    """
    Парсит файл tags_list.txt с группировкой тегов.

    Формат файла:
    Group:group_name:
    tag1
    tag2

    Group:another_group:
    tag3
    tag4

    Args:
        filepath: Путь к файлу tags_list.txt

    Returns:
        Словарь {имя_группы: [список_тегов]}
    """
    groups: dict[str, list[str]] = {}
    current_group: Optional[str] = None

    content = filepath.read_text(encoding='utf-8')

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        # Проверка на заголовок группы
        if line.startswith('Group:'):
            # Извлекаем имя группы (между Group: и последним :)
            group_name = line[6:].rstrip(':')
            current_group = group_name
            if current_group not in groups:
                groups[current_group] = []
        elif current_group:
            # Это тег
            groups[current_group].append(line)

    return groups


def parse_plc_address(plc_input: dict[str, Any]) -> dict[str, Any]:
    """
    Создаёт адрес PLC из словаря PLC.Input.

    Args:
        plc_input: Словарь PLC.Input с ключами Block, Word, Bit

    Returns:
        Словарь с компонентами адреса:
        - area: 'DB'
        - db_number: номер блока данных
        - byte_address: адрес байта
        - bit_address: адрес бита
    """
    plc_block = plc_input.get('Block', 0)
    plc_word = plc_input.get('Word', 0)
    plc_bit = plc_input.get('Bit', 0)
    
    return {
        'area': 'DB',
        'db_number': plc_block,
        'byte_address': plc_word,
        'bit_address': plc_bit
    }


def map_type(yaml_type: str) -> tuple[str, str]:
    """
    Маппинг типа данных из JSON в формат SDV.

    Args:
        yaml_type: Тип данных из JSON (например, 'Float', '16 Bit/Time')

    Returns:
        Кортеж (Type, S7DataType):
        - Type: внутренний тип ('float', 'uint16', 'int32', etc.)
        - S7DataType: тип данных S7 ('REAL', 'WORD', 'INT', etc.)
    """
    yaml_type_lower = yaml_type.lower() if yaml_type else ''

    # Float типы
    if 'float' in yaml_type_lower or 'flt' in yaml_type_lower:
        return ('float', 'REAL')

    # 16-битные типы
    if '16 bit' in yaml_type_lower or '16 Bit/Time' in yaml_type_lower:
        return ('uint16', 'WORD')

    # 32-битные типы
    if '32 bit' in yaml_type_lower:
        return ('int32', 'DINT')

    # # 8-битные типы
    # if '8 bit' in yaml_type_lower or 'byte' in yaml_type_lower:
    #     return ('byte', 'BYTE')

    # 8-битные типы
    if '8 bit' in yaml_type_lower or 'byte' in yaml_type_lower:
        return ('bool', 'BOOL')     

    # Bool типы
    if 'bool' in yaml_type_lower or 'bit' in yaml_type_lower:
        return ('bool', 'BOOL')

    # По умолчанию - 16 бит
    return ('uint16', 'WORD')


def find_group_by_name(node: dict, name: str) -> Optional[dict]:
    """
    Рекурсивный поиск группы по NameInTree в иерархии node.

    Args:
        node: Корневой или дочерний node для поиска
        name: Имя группы для поиска (NameInTree)

    Returns:
        Ссылка на найденный node группы или None
    """
    if not isinstance(node, dict):
        return None

    if node.get('Category') == 'Group' and node.get('NameInTree') == name:
        return node

    # Поиск в дочернем node
    if 'node' in node:
        child = node['node']
        if isinstance(child, list):
            for item in child:
                result = find_group_by_name(item, name)
                if result:
                    return result
        else:
            result = find_group_by_name(child, name)
            if result:
                return result

    return None


def create_group_node(name: str) -> dict:
    """
    Создаёт структуру узла группы в формате SDV.

    Args:
        name: Имя группы (NameInTree)

    Returns:
        Словарь с структурой группы
    """
    return {
        "Category": "Group",
        "NameInTree": name,
        "Comment": name,
        "Level": "3",
        "Enabled": "true",
        "Invisible": "false",
        "Owner": "PLUGIN",
        "TypeDevice": "PLUGIN",
        "SubTypeDevice": "SIEMENSPLC",
        "NameDevice": "siemensplc",
        "en_del": "true",
        "en_copy": "true",
        "en_ren": "true",
        "en_move": "true"
    }


def create_tag_node(tag_data: dict, plc_address: dict, type_info: tuple[str, str]) -> dict:
    """
    Создаёт структуру тега в формате SDV.

    Args:
        tag_data: Данные тега из JSON
        plc_address: Распарсенный адрес PLC
        type_info: Кортеж (Type, S7DataType)

    Returns:
        Словарь с структурой тега в формате SDV
    """
    tag_name = tag_data['Tag']
    desc_eng = tag_data.get('DescEng', '')
    desc_rus = tag_data.get('DescRus', '')
    eng_unit_id = tag_data.get('EngUnitId', '')
    constant1 = tag_data.get('Constant1', '')

    # Извлекаем BlockAlg из вложенной структуры Algorithms
    block_alg = tag_data.get('Algorithms', {}).get('BlockAlg', '')

    comment = f"{desc_eng}" if desc_eng else ""
    if desc_rus:
        comment = f"{desc_eng} | {desc_rus}" if desc_eng else desc_rus

    comment = f"{comment} | значение * {constant1} " if constant1 else comment
    comment = f"{comment} | {eng_unit_id} " if eng_unit_id else comment  # EU - Единицы измерения


    type_internal, s7_data_type = type_info

    # Формирование PluginProperties как JSON-строки
    plugin_props = {
        "tag": {
            "name": "S7Tag",
            "description": "",
            "en_del": "true",
            "en_copy": "true",
            "en_ren": "true",
            "en_move": "true",
            "en_many": "false",
            "properties": {
                "_comment_": {
                    "type": "string",
                    "inival": comment,
                    "minval": "0",
                    "maxval": "0",
                    "comboval": "0",
                    "description": "",
                    "visible": "true",
                    "visibleintable": "false"
                },
                "_type_": {
                    "type": "combo",
                    "inival": type_internal,
                    "minval": "0",
                    "maxval": "0",
                    "comboval": f"{type_internal},",
                    "description": "",
                    "visible": "true",
                    "visibleintable": "false"
                },
                "_access_": {
                    "type": "combo",
                    "inival": "ReadOnly",
                    "minval": "0",
                    "maxval": "0",
                    "comboval": "ReadOnly,ReadWrite,WriteOnly,",
                    "description": "",
                    "visible": "true",
                    "visibleintable": "false"
                },
                "Area": {
                    "type": "combodata",
                    "inival": plc_address['area'],
                    "minval": "0",
                    "maxval": "none$ReadOnly#NumberDB,none$none#NumberDB,none$none#NumberDB,none$none,uint16$none#NumberDB;NumberBit;AmountBytes,uint16$none#NumberDB;NumberBit;AmountBytes",
                    "comboval": "I,Q,M,DB,T,C",
                    "description": "Регион данных",
                    "visible": "true",
                    "_visr_": "true",
                    "_visar_": "false"
                },
                "S7DataType": {
                    "type": "combodata",
                    "inival": s7_data_type,
                    "minval": "0",
                    "maxval": "bool$none#AmountBytes,byte$none#NumberBit;AmountBytes,byte$none#NumberBit;AmountBytes,uint16$none#NumberBit;AmountBytes,sbyte;float$none#NumberBit;AmountBytes,byte;float$none#NumberBit;AmountBytes,uint16;float$none#NumberBit;AmountBytes,int16;float$none#NumberBit;AmountBytes,uint16;float$none#NumberBit;AmountBytes,uint32;float$none#NumberBit;AmountBytes,int32;float$none#NumberBit;AmountBytes,uint32;float$none#NumberBit;AmountBytes,float;int32$none#NumberBit;AmountBytes,double$none#NumberBit;AmountBytes,string;bytestring$none#NumberBit,string;bytestring$none#NumberBit,string;uint16$none#NumberBit;AmountBytes,string;uint32$none#NumberBit;AmountBytes,string;int32$none#NumberBit;AmountBytes,string;datetime$none#NumberBit;AmountBytes,float;string$none#NumberBit;AmountBytes",
                    "comboval": "BOOL,BYTE,CHAR,WCHAR,SINT,USINT,WORD,INT,UINT,DWORD,DINT,UDINT,REAL,LREAL,STRING,WSTRING,DATE,TOD,TIME,DT,S5TIME",
                    "description": "Тип данных",
                    "visible": "true",
                    "_visr_": "true",
                    "_visar_": "false"
                },
                "NumberDB": {
                    "type": "uint32",
                    "inival": str(plc_address['db_number']),
                    "minval": "0",
                    "maxval": "256000",
                    "comboval": "0",
                    "description": "Номер блока",
                    "visible": "true",
                    "_visr_": "false",
                    "_visar_": "true"
                },
                "AddressByte": {
                    "type": "uint32",
                    "inival": str(plc_address['byte_address']),
                    "minval": "0",
                    "maxval": "256000",
                    "comboval": "0",
                    "description": "Адрес байта",
                    "visible": "true",
                    "_visr_": "false",
                    "_visar_": "true"
                },
                "NumberBit": {
                    "type": "uint32",
                    "inival": str(plc_address['bit_address']),
                    "minval": "0",
                    "maxval": "7",
                    "comboval": "0",
                    "description": "Номер бита",
                    "visible": "true",
                    "_visr_": "false",
                    "_visar_": "true"
                },
                "AmountBytes": {
                    "type": "uint32",
                    "inival": "1",
                    "minval": "1",
                    "maxval": "1024",
                    "comboval": "1",
                    "description": "Количество байт",
                    "visible": "true",
                    "_visr_": "false",
                    "_visar_": "false"
                }
            }
        }
    }

    # Сериализация PluginProperties в JSON-строку
    plugin_props_str = json.dumps(plugin_props, ensure_ascii=False, indent='\t')

    tag_node = {
        "Category": "Teg",
        "NameInTree": tag_name,
        "Enabled": "true",
        "Invisible": "false",
        "Owner": "PLUGIN",
        "NameDevice": "siemensplc",
        "PluginProperties": plugin_props_str,
        "Region": "Protocol",
        "AddressInRegion": "Device",
        "Type": type_internal,
        "Access": "ReadOnly",
        "EnableProgramAfterTagRead": "false",
        "SourceCodeRead": "BIqWQMvfT6bXR6bwPI0D2Y1cTMvZT6blRY1FRabkQNGeAGqA86LkP0qABIqWP6LfRcbqQM5iQNfb3GeWPdLkOtHfRsuWJsv3R6zpPIWf3GeWPMva3GejBI1eOMvaR6bkPmqA86PrRcDqQMzk84zkKcLXP2Wf3GeWPMva3G",
        "EnableProgramBeforeTagWrite": "false",
        "SourceCodeWrite": "BIqWQMvfT6bXR6bwPI0D2Y1cTMvZT6blRY1FRabkQNGeAGqA86LkP0qABIqWQ65kP6nfRcSW3GeWPdLkOtHfRsuWJsvNScbqPIWf3GeWPMva3G",
        "Level": "4",
        "IsHDA": "false",
        "HDACountRecords": "1000",
        "HDASaveToFile": "false",
        "HDASaveAutomatic": "false",
        "HDASaveIfChange": "false",
        "en_del": "true",
        "en_copy": "true",
        "en_ren": "true",
        "en_move": "true",
        "IEC104_Connect": "false",
        "IEC104_Address": "1",
        "IEC104_Reason": "true",
        "IEC104_Write": "false",
        "TurnOffEnable": "false",
        "IsBoundMin": "false",
        "BoundMin": "0",
        "IsBoundMax": "false",
        "BoundMax": "100",
        "ReadAfterWrite": "false",
        "IEC104_SendType": "AS_IN_SERVER",
        "_type_": type_internal,
        "Comment": comment
    }

    return tag_node


def clear_group_tags(group_node: dict) -> None:
    """
    Очищает существующие теги в группе, оставляя только структуру группы.

    Args:
        group_node: Node группы для очистки
    """
    # Если внутри группы есть дочерние теги (Category: Teg), удаляем их
    if 'node' in group_node:
        child = group_node['node']
        if isinstance(child, dict) and child.get('Category') == 'Teg':
            # Удаляем все теги, рекурсивно проходя по цепочке
            del group_node['node']


def add_tags_to_group(group_node: dict, tags: list[dict]) -> None:
    """
    Добавляет теги в группу, создавая структуру с ключами node_xx0, node_xx1 и т.д.

    В формате SDV теги внутри группы организованы через ключи вида 'node_xx{index}',
    где index начинается с 0 и увеличивается для каждого следующего тега.

    Args:
        group_node: Node группы для добавления тегов
        tags: Список структур тегов для добавления

    Note:
        Перед добавлением тегов группа очищается от старых тегов.
        Каждый тег копируется для предотвращения изменения исходных данных.
    """
    if not tags:
        return

    if not isinstance(group_node, dict):
        raise TypeError("group_node должен быть словарём")

    clear_group_tags(group_node)

    for index, tag_data in enumerate(tags):
        group_node[f'node_xx{index}'] = tag_data.copy()

def load_sdv_file(filepath: Path) -> dict:
    """
    Загружает SDV файл как JSON.

    SDV файл содержит JSON с табуляцией как разделителем ключ-значение.

    Args:
        filepath: Путь к SDV файлу

    Returns:
        Словарь с данными SDV
    """
    # Пробуем несколько кодировок, так как SDV может быть в разных кодировках
    for encoding in ['utf-8', 'cp1251', 'cp1252']:
        try:
            content = filepath.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Не удалось прочитать файл в поддерживаемых кодировках: {filepath}")

    # SDV использует табуляцию как разделитель, что не является стандартным JSON
    # Заменяем табуляцию на пробелы для корректного парсинга
    # Но сохраняем табуляцию внутри строковых значений (PluginProperties)

    # Простой подход: пытаемся распарсить как есть
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Если не получилось, пробуем заменить табуляцию вне строк
        # Это сложная задача, используем простой подход с заменой
        normalized = content.replace('\t', '    ')
        return json.loads(normalized)


def save_sdv_file(data: dict, filepath: Path) -> None:
    """
    Сохраняет данные в SDV файл с форматированием табуляцией.

    Args:
        data: Данные для сохранения
        filepath: Путь к файлу
    """
    # Сериализуем с табуляцией
    content = json.dumps(data, ensure_ascii=False, indent='\t')
    # Сохраняем в cp1251 для совместимости с оригинальным форматом
    filepath.write_text(content, encoding='cp1251')


def load_tags_filter(filter_path: Optional[Path]) -> Optional[set[str]]:
    """
    Загружает список тегов для фильтрации из текстового файла.

    Args:
        filter_path: Путь к файлу со списком тегов (по одному в строке)

    Returns:
        Множество имён тегов или None, если фильтр не указан или файл пустой
    """
    if not filter_path or not filter_path.exists():
        return None

    tags = set()
    content = filter_path.read_text(encoding='utf-8')
    for line in content.splitlines():
        tag_name = line.strip()
        if tag_name:
            tags.add(tag_name)

    # Если файл пустой (нет тегов), возвращаем None — обрабатывать все теги
    return tags if tags else None


def create_tags_csv(tags: list[dict], output_path: Path) -> None:
    """
    Создаёт CSV файл со всеми полями из тегов.
    Вложенные структуры разворачиваются в отдельные колонки.
    Порядок колонок соответствует порядку полей в JSON.

    Args:
        tags: Список структур тегов
        output_path: Путь для выходного CSV файла
    """
    if not tags:
        return

    def flatten_tag(tag: dict) -> dict:
        """Разворачивает вложенные структуры в плоский словарь."""
        flat = {}
        for key, value in tag.items():
            if isinstance(value, dict):
                # Разворачиваем вложенный словарь
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, dict):
                        # Второй уровень вложенности
                        for subsubkey, subsubvalue in subvalue.items():
                            flat[f"{key}_{subkey}_{subsubkey}"] = subsubvalue
                    else:
                        flat[f"{key}_{subkey}"] = subvalue
            else:
                flat[key] = value
        return flat

    # Плоская структура тегов
    flat_tags = [flatten_tag(tag) for tag in tags]

    # Сохраняем порядок полей как в первом теге (как в JSON)
    fieldnames = list(flat_tags[0].keys())

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_tags)

    print(f"Создан CSV файл: {output_path} ({len(tags)} тегов)")


def convert_tags_groups_to_sdv(
    tags_list_path: Path,
    json_path: Path,
    sdv_path: Path,
    output_path: Path
) -> None:
    """
    Конвертирует теги из JSON в SDV с группировкой по tags_list.txt.
    Каждая группа из tags_list.txt создаёт отдельный узел node_xx1, node_xx2 и т.д.

    Args:
        tags_list_path: Путь к файлу tags_list.txt с группами
        yaml_path: Путь к файлу tags.json с данными тегов
        sdv_path: Путь к шаблону .sdv файла
        output_path: Путь для выходного файла
    """
    print(f"{Fore.CYAN}Загрузка групп из {tags_list_path}...{Style.RESET_ALL}")
    groups = parse_tags_list_groups(tags_list_path)

    if not groups:
        print(f"{Fore.YELLOW}⚠ Группы с тегами не найдены{Style.RESET_ALL}")
        return

    total_tags = sum(len(tags) for tags in groups.values())
    print(f"{Fore.GREEN}Найдено групп: {len(groups)}, всего тегов: {total_tags}{Style.RESET_ALL}")

    print(f"{Fore.CYAN}Загрузка JSON из {json_path}...{Style.RESET_ALL}")
    with open(json_path, 'r', encoding='utf-8') as f:
        all_yaml_tags = json.load(f)

    # Создаём словарь для быстрого поиска тегов по имени
    yaml_tags_dict = {tag['Tag']: tag for tag in all_yaml_tags}
    print(f"{Fore.GREEN}Загружено {len(all_yaml_tags)} тегов из JSON{Style.RESET_ALL}")

    print(f"{Fore.CYAN}Загрузка SDV шаблона из {sdv_path}...{Style.RESET_ALL}")
    sdv_data = load_sdv_file(sdv_path)
    root_node = sdv_data.get('node', {})

    all_converted_tags = 0
    all_converted_tags_list = []
    group_index = 1
    converted_tags_csv = []

    for group_name, tag_names in groups.items():
        print(f"\n{Fore.MAGENTA}Обработка группы '{group_name}' ({len(tag_names)} тегов)...{Style.RESET_ALL}")

        # Создаём новую группу
        group_node = create_group_node(group_name)

        # Конвертируем теги
        converted_tags = []

        skipped_tags = []
        for tag_name in tag_names:
            if tag_name not in yaml_tags_dict:
                skipped_tags.append(f"Тег '{tag_name}' не найден в JSON")
                continue

            tag_data = yaml_tags_dict[tag_name]

            # Извлекаем адрес из PLC.Input
            plc_input = tag_data.get('PLC', {}).get('Input', {})
            yaml_type = plc_input.get('Type', '')

            if not plc_input or plc_input.get('Block') is None or plc_input.get('Word') is None:
                skipped_tags.append(f"Тег '{tag_name}': нет PLC.Input.Block или PLC.Input.Word")
                continue

            try:
                plc_address = parse_plc_address(plc_input)
            except ValueError as e:
                skipped_tags.append(f"Тег '{tag_name}': {e}")
                continue

            converted_tags_csv.append(tag_data)

            type_info = map_type(yaml_type)
            tag_node = create_tag_node(tag_data, plc_address, type_info)
            converted_tags.append(tag_node)

            print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {tag_name} -> {Fore.YELLOW}DB{plc_address['db_number']}.DBD{plc_address['byte_address']}{Style.RESET_ALL} (bit: {plc_address['bit_address']}) ({Fore.CYAN}{type_info[0]}/{type_info[1]}{Style.RESET_ALL})")

        # Выводим список пропущенных тегов
        if skipped_tags:
            print(f"\n{Fore.RED}Пропущенные теги ({len(skipped_tags)}):{Style.RESET_ALL}")
            for skipped in skipped_tags:
                print(f"{Fore.RED}  - {skipped}{Style.RESET_ALL}")

        # Добавляем теги в группу
        add_tags_to_group(group_node, converted_tags)

        # Добавляем группу в корневой узел с ключом node_xx{index}
        root_node[f'node_xx{group_index}'] = group_node
        group_index += 1

        all_converted_tags += len(converted_tags)
        all_converted_tags_list.extend(converted_tags_csv)
        print(f"  {Fore.GREEN}Добавлено {len(converted_tags)} тегов в группу '{group_name}'{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Сохранение результата в {output_path}...{Style.RESET_ALL}")
    save_sdv_file(sdv_data, output_path)

    print(f"{Fore.CYAN}Нормализация ключей node_xx*...{Style.RESET_ALL}")
    normalize_node_keys(output_path)

    # Выгрузка конвертированных тегов в CSV
    csv_output_path = output_path.with_suffix('.csv')
    create_tags_csv(converted_tags_csv, csv_output_path)

    print(f"\n{Fore.GREEN}Готово! Конвертировано тегов: {all_converted_tags} в {len(groups)} группах{Style.RESET_ALL}")


def normalize_node_keys(filepath: Path) -> None:
    """
    Нормализует ключи в SDV файле: заменяет 'node_xx0', 'node_xx1' и т.д. на 'node'.

    Args:
        filepath: Путь к SDV файлу
    """
    content = filepath.read_text(encoding='cp1251')

    # Паттерн для поиска ключей вида "node_xx0", "node_xx1" и т.д.
    pattern = r'"node_xx\d+"'

    # Заменяем все вхождения на "node"
    normalized_content = re.sub(pattern, '"node"', content)

    filepath.write_text(normalized_content, encoding='cp1251')
    print(f"{Fore.GREEN}Нормализация ключей node_xx* завершена для {filepath}{Style.RESET_ALL}")


def main():
    """Точка входа скрипта."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Конвертер тегов ECS7 в конфигурацию устройства MasterOPC (.sdv)',
        add_help=False
    )
    parser.add_argument(
        'input',
        type=Path,
        nargs='?',
        default=Path('tags_list.txt'),
        help='Путь к файлу c тегами для конвертации (по умолчанию: tags_list.txt)'
    )
    parser.add_argument(
        'output',
        type=Path,
        nargs='?',
        default=Path('siemens_plc_opc.sdv'),
        help='Путь к выходному файлу (по умолчанию: siemens_plc_opc.sdv)'
    )
    parser.add_argument(
        '-h', '-?', '--help', '--h', '--?',
        action='help',
        help='Показать справку'
    )

    args = parser.parse_args()

    # Проверка существования файлов
    sdv_path = Path('./data/template.sdv')
    if not sdv_path.exists():
        print(f"{Fore.RED}Ошибка: Файл SDV не найден: {sdv_path}{Style.RESET_ALL}")
        sys.exit(1)

    json_path = Path('./data/tags.json')
    if not json_path.exists():
        print(f"{Fore.RED}Ошибка: Файл с базой тегов ECS не найден: {json_path}{Style.RESET_ALL}")
        sys.exit(1)

    # Режим конвертации с группами из tags_list.txt
    if not args.input.exists():
        print(f"{Fore.RED}Ошибка: Файл c тегами для конвертации не найден: {args.input}{Style.RESET_ALL}")
        sys.exit(1)

    # Добавляем расширение .sdv к выходному файлу, если его нет
    output_path = args.output if args.output.suffix == '.sdv' else args.output.with_suffix('.sdv')

    convert_tags_groups_to_sdv(
        tags_list_path=args.input,
        json_path=json_path,
        sdv_path=sdv_path,
        output_path=output_path
    )


if __name__ == '__main__':
    main()
