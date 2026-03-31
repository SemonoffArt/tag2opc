#!/usr/bin/env python3
"""
Конвертер тегов из формата tags.yml в конфигурацию MasterOPC для Siemens PLC (.sdv)

Скрипт читает теги из YAML-файла и обновляет указанную группу в SDV-файле,
заменяя существующие теги на новые из YAML.
"""

import csv
import json
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import yaml


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


def parse_plc_address(plc_inp: str) -> dict[str, Any]:
    """
    Парсит адрес PLC_INP в формате %DB4.DBD320 или %DB4.DBB320 и т.д.
    
    Args:
        plc_inp: Строка адреса, например '%DB4.DBD320'
        
    Returns:
        Словарь с компонентами адреса:
        - area: 'DB', 'I', 'Q', 'M', 'T', 'C'
        - db_number: номер блока данных (для DB)
        - byte_address: адрес байта
        - bit_address: адрес бита (всегда 0 для word/dword адресов)
        
    Raises:
        ValueError: Если формат адреса не распознан
    """
    # Паттерн для адресов типа %DB4.DBD320, %DB4.DBB320, %DB4.DBDW320
    pattern_db = r'^%DB(\d+)\.(DB[BDW])(\d+)$'
    # Паттерн для адресов типа %I0.0, %Q0.0, %M0.0
    pattern_simple = r'^%([IQMTC])(\d+)(?:\.(\d+))?$'
    
    match_db = re.match(pattern_db, plc_inp)
    if match_db:
        db_number = int(match_db.group(1))
        byte_address = int(match_db.group(3))
        return {
            'area': 'DB',
            'db_number': db_number,
            'byte_address': byte_address,
            'bit_address': 0
        }
    
    match_simple = re.match(pattern_simple, plc_inp)
    if match_simple:
        area = match_simple.group(1)
        byte_address = int(match_simple.group(2))
        bit_address = int(match_simple.group(3)) if match_simple.group(3) else 0
        return {
            'area': area,
            'db_number': 0,
            'byte_address': byte_address,
            'bit_address': bit_address
        }
    
    raise ValueError(f"Не распознан формат адреса PLC_INP: {plc_inp}")


def map_type(yaml_type: str) -> tuple[str, str]:
    """
    Маппинг типа данных из YAML в формат SDV.
    
    Args:
        yaml_type: Тип данных из YAML (например, 'Float', '16 Bit/Time')
        
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
    if '16 bit' or '16 Bit/Time' in yaml_type_lower:
        return ('uint16', 'WORD')
    
    # 32-битные типы
    if '32 bit' in yaml_type_lower:
        return ('int32', 'DINT')
    
    # 8-битные типы
    if '8 bit' in yaml_type_lower or 'byte' in yaml_type_lower:
        return ('byte', 'BYTE')
    
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
        tag_data: Данные тега из YAML
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
        "SourceCodeWrite": "BIqWQMvfT6bXR6bwPI0D2Y1cTMvZT6blRY1FRabkQNGeAGqA86LkP0qABIqWP6LfRcbqQM5iQNfb80qA86PrRcDqQMzk84zkGsnlSsKeAGqA86LkP0qABIqWQ65kP6nfRcSW3GeWPdLkOtHfRsuWJsvNScbqPIWf3GeWPMva3G",
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
    Порядок колонок соответствует порядку полей в YAML.

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

    # Сохраняем порядок полей как в первом теге (как в YAML)
    fieldnames = list(flat_tags[0].keys())

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_tags)

    print(f"Создан CSV файл: {output_path} ({len(tags)} тегов)")


def convert_tags_groups_to_sdv(
    tags_list_path: Path,
    yaml_path: Path,
    sdv_path: Path,
    output_path: Path
) -> None:
    """
    Конвертирует теги из YAML в SDV с группировкой по tags_list.txt.
    Каждая группа из tags_list.txt создаёт отдельный узел node_xx1, node_xx2 и т.д.

    Args:
        tags_list_path: Путь к файлу tags_list.txt с группами
        yaml_path: Путь к файлу tags.yaml с данными тегов
        sdv_path: Путь к шаблону .sdv файла
        output_path: Путь для выходного файла
    """
    print(f"Загрузка групп из {tags_list_path}...")
    groups = parse_tags_list_groups(tags_list_path)
    
    if not groups:
        print("⚠ Группы с тегами не найдены")
        return

    total_tags = sum(len(tags) for tags in groups.values())
    print(f"Найдено групп: {len(groups)}, всего тегов: {total_tags}")

    print(f"Загрузка YAML из {yaml_path}...")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        all_yaml_tags = yaml.safe_load(f)
    
    # Создаём словарь для быстрого поиска тегов по имени
    yaml_tags_dict = {tag['Tag']: tag for tag in all_yaml_tags}
    print(f"Загружено {len(all_yaml_tags)} тегов из YAML")

    print(f"Загрузка SDV шаблона из {sdv_path}...")
    sdv_data = load_sdv_file(sdv_path)
    root_node = sdv_data.get('node', {})

    all_converted_tags = 0
    all_converted_tags_list = []
    group_index = 1
    converted_tags_csv = []

    for group_name, tag_names in groups.items():
        print(f"\nОбработка группы '{group_name}' ({len(tag_names)} тегов)...")

        # Создаём новую группу
        group_node = create_group_node(group_name)

        # Конвертируем теги
        converted_tags = []

        skipped_tags = []
        for tag_name in tag_names:
            if tag_name not in yaml_tags_dict:
                skipped_tags.append(f"Тег '{tag_name}' не найден в YAML")
                continue

            tag_data = yaml_tags_dict[tag_name]
            plc_inp = tag_data.get('PLC_INP', '')
            yaml_type = tag_data.get('PLC', {}).get('Input', {}).get('Type', '')

            if not plc_inp:
                skipped_tags.append(f"Тег '{tag_name}': нет PLC_INP")
                continue

            try:
                plc_address = parse_plc_address(plc_inp)
            except ValueError as e:
                skipped_tags.append(f"Тег '{tag_name}': {e}")
                continue

            converted_tags_csv.append(tag_data)
            
            type_info = map_type(yaml_type)
            tag_node = create_tag_node(tag_data, plc_address, type_info)
            converted_tags.append(tag_node)

            print(f"  ✓ {tag_name} -> {plc_inp} ({type_info[0]}/{type_info[1]})")

        # Выводим список пропущенных тегов
        if skipped_tags:
            print(f"\n\033[91mПропущенные теги ({len(skipped_tags)}):\033[0m")
            for skipped in skipped_tags:
                print(f"\033[91m  - {skipped}\033[0m")

        # Добавляем теги в группу
        add_tags_to_group(group_node, converted_tags)
        
        # Добавляем группу в корневой узел с ключом node_xx{index}
        root_node[f'node_xx{group_index}'] = group_node
        group_index += 1
        
        all_converted_tags += len(converted_tags)
        all_converted_tags_list.extend(converted_tags_csv)
        print(f"  Добавлено {len(converted_tags)} тегов в группу '{group_name}'")

    print(f"\nСохранение результата в {output_path}...")
    save_sdv_file(sdv_data, output_path)

    print(f"Нормализация ключей node_xx*...")
    normalize_node_keys(output_path)

    # Выгрузка конвертированных тегов в CSV
    csv_output_path = output_path.with_suffix('.csv')
    create_tags_csv(converted_tags_csv, csv_output_path)

    print(f"\nГотово! Конвертировано тегов: {all_converted_tags} в {len(groups)} группах")


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
    print(f"Нормализация ключей node_xx* завершена для {filepath}")


def main():
    """Точка входа скрипта."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Конвертер тегов из YAML в конфигурацию Siemens PLC (.sdv)'
    )
    parser.add_argument(
        '--yaml', '-y',
        type=Path,
        default=Path('./data/tags.yaml'),
        help='Путь к файлу tags.yml (по умолчанию: data/tags.yaml)'
    )
    parser.add_argument(
        '--sdv', '-s',
        type=Path,
        default=Path('./data/template.sdv'),
        help='Путь к шаблону .sdv файла (по умолчанию: data/template.sdv)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path('siemens_plc_opc_converted.sdv'),
        help='Путь к выходному файлу (по умолчанию: siemens_plc_opc_converted.sdv)'
    )
    parser.add_argument(
        '--group', '-g',
        type=str,
        default='Flot',
        help='Имя группы для заполнения тегами (по умолчанию: Flot)'
    )
    parser.add_argument(
        '--filter', '-f',
        type=Path,
        default=Path('tags_list.txt'),
        help='Путь к файлу со списком тегов для фильтрации (по умолчанию: None)'
    )
    parser.add_argument(
        '--normalize', '-n',
        type=Path,
        default=Path('siemens_plc_opc_converted.sdv'),
        help='Нормализовать ключи node_xx* в указанном файле (без конвертации)'
    )
    parser.add_argument(
        '--tags-list', '-t',
        type=Path,
        default=Path('tags_list.txt'),
        help='Путь к файлу tags_list.txt с группами (режим конвертации с группами)'
    )
    parser.add_argument(
        '--mode', '-m',
        type=str,
        choices=['yaml', 'groups'],
        default='groups',
        help='Режим работы: yaml (обычная конвертация) или groups (с группами из tags_list.txt)'
    )

    args = parser.parse_args()



    # Проверка существования файлов
    if not args.sdv.exists():
        print(f"Ошибка: Файл SDV не найден: {args.sdv}")
        sys.exit(1)

    if args.mode == 'groups':
        # Режим конвертации с группами из tags_list.txt
        if not args.tags_list.exists():
            print(f"Ошибка: Файл tags_list не найден: {args.tags_list}")
            sys.exit(1)
        
        if not args.yaml.exists():
            print(f"Ошибка: Файл YAML не найден: {args.yaml}")
            sys.exit(1)
        
        convert_tags_groups_to_sdv(
            tags_list_path=args.tags_list,
            yaml_path=args.yaml,
            sdv_path=args.sdv,
            output_path=args.output
        )
    else:
        raise ValueError("Обычный режим конвертации удалён. Используйте режим --groups")

    # Если указан только --normalize, выполняем только нормализацию
    if args.normalize:
        if not args.normalize.exists():
            print(f"Ошибка: Файл не найден: {args.normalize}")
            sys.exit(1)
        normalize_node_keys(args.normalize)
        # return


class TagsConverterGUI:
    """Графический интерфейс для конвертера тегов."""

    def __init__(self, root):
        self.root = root
        self.root.title("Tags2SDV - Конвертер тегов Siemens PLC")
        self.root.geometry("900x700")

        # Текущий файл
        self.current_file = None
        self.modified = False

        # Пути по умолчанию
        self.default_tags_file = Path("tags_list.txt")
        self.default_yaml_file = Path("./data/tags.yaml")
        self.default_sdv_template = Path("./data/template.sdv")
        self.default_output = Path("siemens_plc_opc_converted.sdv")

        self._create_menu()
        self._create_toolbar()
        self._create_text_area()
        self._create_log_area()
        self._create_status_bar()

        # Загрузка файла по умолчанию
        self._load_file(self.default_tags_file)

        # Обработчик закрытия
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_menu(self):
        """Создание меню."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Открыть...", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Сохранить", command=self._save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Сохранить как...", command=self._save_as_file, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_closing)

        # Конвертация
        convert_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Конвертация", menu=convert_menu)
        convert_menu.add_command(label="Создать .sdv файл", command=self._convert, accelerator="F5")

        # Привязка клавиш
        self.root.bind("<Control-o>", lambda e: self._open_file())
        self.root.bind("<Control-s>", lambda e: self._save_file())
        self.root.bind("<Control-Shift-S>", lambda e: self._save_as_file())
        self.root.bind("<F5>", lambda e: self._convert())

    def _create_toolbar(self):
        """Создание панели инструментов."""
        toolbar = tk.Frame(self.root, pady=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_open = tk.Button(toolbar, text="📁 Открыть", command=self._open_file)
        btn_open.pack(side=tk.LEFT, padx=5)

        btn_save = tk.Button(toolbar, text="💾 Сохранить", command=self._save_file)
        btn_save.pack(side=tk.LEFT, padx=5)

        btn_convert = tk.Button(toolbar, text="▶ Конвертировать", command=self._convert, bg="#4CAF50", fg="white")
        btn_convert.pack(side=tk.LEFT, padx=5)

    def _create_text_area(self):
        """Создание текстовой области."""
        text_frame = tk.Frame(self.root)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.text_area = tk.Text(text_frame, wrap=tk.NONE, undo=True, autoseparators=True)
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(text_frame, command=self.text_area.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_area.config(yscrollcommand=scrollbar.set)

        # Настройка тега для жирного шрифта (заголовки групп)
        self.text_area.tag_configure("group_header", font=("Consolas", 18, "bold"))

        # Отслеживание изменений
        self.text_area.bind("<KeyRelease>", self._on_text_change)

        # Контекстное меню (копирование/вставка)
        self._create_context_menu()

    def _highlight_group_headers(self):
        """Подсветка заголовков групп (строки, начинающиеся с 'Group')."""
        # Удаляем старое выделение
        self.text_area.tag_remove("group_header", "1.0", tk.END)

        # Поиск и выделение строк, начинающихся с 'Group'
        content = self.text_area.get("1.0", tk.END)
        for line_num, line in enumerate(content.splitlines(), start=1):
            if line.strip().startswith("Group"):
                start = f"{line_num}.0"
                end = f"{line_num}.end"
                self.text_area.tag_add("group_header", start, end)

    def _create_context_menu(self):
        """Создание контекстного меню для текстовой области."""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Копировать", command=self._copy_text, accelerator="Ctrl+C")
        self.context_menu.add_command(label="Вставить", command=self._paste_text, accelerator="Ctrl+V")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Выделить всё", command=self._select_all_text, accelerator="Ctrl+A")

        # Привязка контекстного меню к правой кнопке мыши
        self.text_area.bind("<Button-3>", self._show_context_menu)

        # Горячие клавиши через виртуальные события (работают при любой раскладке)
        self.text_area.bind("<<Copy>>", lambda e: self._copy_text())
        self.text_area.bind("<<Paste>>", lambda e: self._paste_text())
        self.text_area.bind("<<SelectAll>>", lambda e: self._select_all_text())

    def _show_context_menu(self, event):
        """Показ контекстного меню."""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _copy_text(self):
        """Копирование выделенного текста."""
        try:
            text = self.text_area.selection_get()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass  # Нет выделения
        return 'break'

    def _paste_text(self):
        """Вставка текста из буфера обмена."""
        try:
            text = self.root.clipboard_get()
            self.text_area.insert(tk.INSERT, text)
            self._on_text_change()
        except tk.TclError:
            pass  # Буфер пуст
        return 'break'

    def _select_all_text(self):
        """Выделение всего текста."""
        self.text_area.tag_add(tk.SEL, "1.0", tk.END)
        self.text_area.mark_set(tk.INSERT, "1.0")
        self.text_area.see(tk.INSERT)
        return 'break'

    def _create_log_area(self):
        """Создание области лога."""
        log_frame = tk.Frame(self.root)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False)

        log_label = tk.Label(log_frame, text="Лог:", anchor=tk.W)
        log_label.pack(side=tk.TOP, fill=tk.X)

        self.log_area = tk.Text(log_frame, wrap=tk.WORD, height=10, state=tk.DISABLED)
        self.log_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scrollbar = tk.Scrollbar(log_frame, command=self.log_area.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_area.config(yscrollcommand=log_scrollbar.set)

    def _log(self, message: str):
        """Добавление сообщения в лог."""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    def _clear_log(self):
        """Очистка лога."""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)

    def _create_status_bar(self):
        """Создание строки состояния."""
        self.status_var = tk.StringVar()
        self.status_var.set("Готов")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _on_text_change(self, event=None):
        """Обработчик изменения текста."""
        self.modified = True
        self._update_title()
        self._highlight_group_headers()

    def _update_title(self):
        """Обновление заголовка окна."""
        title = "Tags2SDV"
        if self.current_file:
            title += f" - {self.current_file.name}"
        if self.modified:
            title += " *"
        self.root.title(title)

    def _load_file(self, filepath: Path):
        """Загрузка файла в текстовую область."""
        if not filepath.exists():
            self.status_var.set(f"Файл не найден: {filepath}")
            return

        try:
            content = filepath.read_text(encoding='utf-8')
            self.text_area.delete(1.0, tk.END)
            self.text_area.insert(1.0, content)
            self.current_file = filepath
            self.modified = False
            self._update_title()
            self._highlight_group_headers()
            self.status_var.set(f"Загружен: {filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{e}")

    def _open_file(self):
        """Открытие файла через диалог."""
        filepath = filedialog.askopenfilename(
            title="Открыть файл",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")],
            initialdir=Path.cwd()
        )
        if filepath:
            self._load_file(Path(filepath))

    def _save_file(self):
        """Сохранение файла."""
        if not self.current_file:
            self._save_as_file()
            return

        self._save_to_path(self.current_file)

    def _save_as_file(self):
        """Сохранение файла как."""
        filepath = filedialog.asksaveasfilename(
            title="Сохранить как",
            defaultextension=".txt",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")],
            initialdir=Path.cwd()
        )
        if filepath:
            self._save_to_path(Path(filepath))

    def _save_to_path(self, filepath: Path):
        """Сохранение в указанный путь."""
        try:
            content = self.text_area.get(1.0, tk.END)
            filepath.write_text(content, encoding='utf-8')
            self.current_file = filepath
            self.modified = False
            self._update_title()
            self.status_var.set(f"Сохранен: {filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")

    def _on_closing(self):
        """Обработчик закрытия окна."""
        if self.modified:
            response = messagebox.askyesnocancel(
                "Сохранение",
                "Файл был изменен. Сохранить?"
            )
            if response is None:
                return
            if response:
                self._save_file()
        self.root.destroy()

    def _convert(self):
        """Конвертация тегов в .sdv файл."""
        # Очищаем лог
        self._clear_log()
        
        # Получаем текст из редактора
        tags_content = self.text_area.get(1.0, tk.END).strip()

        # Сохраняем во временный файл
        temp_tags = Path("tags_list_temp.txt")
        temp_tags.write_text(tags_content, encoding='utf-8')
        
        self._log(f"Загрузка групп из {temp_tags}...")

        # Проверяем существование необходимых файлов
        if not self.default_yaml_file.exists():
            self._log(f"Ошибка: YAML файл не найден: {self.default_yaml_file}")
            messagebox.showerror("Ошибка", f"YAML файл не найден:\n{self.default_yaml_file}")
            self.status_var.set("Ошибка: YAML файл не найден")
            return

        if not self.default_sdv_template.exists():
            self._log(f"Ошибка: SDV шаблон не найден: {self.default_sdv_template}")
            messagebox.showerror("Ошибка", f"SDV шаблон не найден:\n{self.default_sdv_template}")
            self.status_var.set("Ошибка: SDV шаблон не найден")
            return

        self._log(f"Загрузка YAML из {self.default_yaml_file}...")
        self._log(f"Загрузка SDV шаблона из {self.default_sdv_template}...")
        
        self.status_var.set("Конвертация...")
        self.root.config(cursor="watch")
        self.root.update()

        try:
            # Перехватываем вывод print для логирования
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            
            # Выполняем конвертацию
            convert_tags_groups_to_sdv(
                tags_list_path=temp_tags,
                yaml_path=self.default_yaml_file,
                sdv_path=self.default_sdv_template,
                output_path=self.default_output
            )
            
            # Получаем вывод и записываем в лог
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
            
            for line in output.splitlines():
                self._log(line)

            self._log(f"\nГотово! Создан файл: {self.default_output}")
            self.status_var.set(f"Готово! Создан: {self.default_output}")
            messagebox.showinfo("Успех", f"Конвертация завершена!\nСоздан файл:\n{self.default_output}")

            # Удаляем временный файл
            if temp_tags.exists():
                temp_tags.unlink()

        except Exception as e:
            self._log(f"Ошибка: {e}")
            self.status_var.set(f"Ошибка: {e}")
            messagebox.showerror("Ошибка конвертации", str(e))

            # Удаляем временный файл
            if temp_tags.exists():
                temp_tags.unlink()

        finally:
            self.root.config(cursor="")


def run_gui():
    """Запуск GUI приложения."""
    root = tk.Tk()
    app = TagsConverterGUI(root)
    root.mainloop()


if __name__ == '__main__':
    # Если запущен без аргументов - запускаем GUI
    if len(sys.argv) == 0:
        run_gui()
    else:
        main()
