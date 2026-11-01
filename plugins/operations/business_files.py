"""Bounded streaming CSV/XLSX readers; spreadsheets are data, never executable."""
import csv
from datetime import datetime, timedelta
from io import BytesIO, TextIOWrapper
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def archive(data):
    try:
        book = ZipFile(BytesIO(data))
        if len(book.infolist()) > 2000 or sum(i.file_size for i in book.infolist()) > 200 * 1024 * 1024:
            raise ValueError('Excel 解压后过大')
        # ElementTree never resolves external entities; also reject internal entity declarations.
        for item in book.infolist():
            if item.filename.endswith(('.xml', '.rels')):
                with book.open(item) as stream:
                    tail = b''
                    while chunk := stream.read(65536):
                        block = tail + chunk
                        if b'<!DOCTYPE' in block.upper() or b'<!ENTITY' in block.upper():
                            raise ValueError('不支持含实体声明的 Excel')
                        tail = block[-16:]
        return book
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError('Excel 文件无效') from exc


def sheets(data):
    with archive(data) as book:
        relations = ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in relations if r.attrib.get('TargetMode') != 'External'}
        workbook = ET.fromstring(book.read('xl/workbook.xml'))
        result = {}
        for sheet in workbook.findall(f'{NS}sheets/{NS}sheet'):
            target = targets.get(sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'), '')
            path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
            if not path.startswith('xl/') or path not in book.namelist():
                raise ValueError('Excel 工作表引用无效')
            result[sheet.attrib['name']] = path
        return result


def _date_styles(book):
    if 'xl/styles.xml' not in book.namelist():
        return set()
    root = ET.fromstring(book.read('xl/styles.xml'))
    formats = {int(x.attrib['numFmtId']): x.attrib.get('formatCode', '') for x in root.findall(f'{NS}numFmts/{NS}numFmt')}
    return {index for index, x in enumerate(root.findall(f'{NS}cellXfs/{NS}xf'))
            if int(x.attrib.get('numFmtId', 0)) in range(14, 23) or
            re.search(r'[yd]', re.sub(r'"[^"]*"|\[[^]]*\]', '', formats.get(int(x.attrib.get('numFmtId', 0)), '')).lower())}


def _cell(cell, strings, dates, base):
    value = cell.findtext(NS + 'v')
    if cell.find(NS + 'f') is not None and value is None:
        return '#公式没有缓存值，请转为数值'
    kind = cell.attrib.get('t')
    if kind == 'inlineStr':
        return ''.join(cell.itertext())
    if kind == 's':
        return strings[int(value)] if value is not None else ''
    if kind == 'e':
        return '#Excel 错误：' + str(value)
    if value and int(cell.attrib.get('s', 0)) in dates:
        return (base + timedelta(days=float(value))).date().isoformat()
    return value or ''


def _xlsx_rows(data, sheet):
    choices = sheets(data)
    if sheet not in choices:
        raise ValueError('请选择有效工作表')
    with archive(data) as book:
        strings = []
        if 'xl/sharedStrings.xml' in book.namelist():
            with book.open('xl/sharedStrings.xml') as stream:
                for _, node in ET.iterparse(stream, events=('end',)):
                    if node.tag == NS + 'si':
                        strings.append(''.join(n.text or '' for n in node.iter(NS + 't')))
                        node.clear()
        dates = _date_styles(book)
        root = ET.fromstring(book.read('xl/workbook.xml'))
        props = root.find(NS + 'workbookPr')
        base = datetime(1904, 1, 1) if props is not None and props.attrib.get('date1904') in ('1', 'true') else datetime(1899, 12, 30)
        with book.open(choices[sheet]) as stream:
            for _, node in ET.iterparse(stream, events=('end',)):
                if node.tag != NS + 'row':
                    continue
                cells = {}
                for cell in node.findall(NS + 'c'):
                    column = 0
                    for char in re.sub('[^A-Z]', '', cell.attrib.get('r', '')):
                        column = column * 26 + ord(char) - 64
                    if not 1 <= column <= 100:
                        raise ValueError('表格最多支持 100 列')
                    cells[column - 1] = _cell(cell, strings, dates, base)
                yield [cells.get(i, '') for i in range(max(cells, default=-1) + 1)]
                node.clear()


def rows(data, name, sheet=''):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('文件必须非空且不超过 20 MB')
    if name.lower().endswith('.csv'):
        iterator = csv.reader(TextIOWrapper(BytesIO(data), encoding='utf-8-sig', newline=''))
    elif name.lower().endswith('.xlsx'):
        iterator = _xlsx_rows(data, sheet)
    else:
        raise ValueError('仅支持 UTF-8 CSV 和 XLSX')
    try:
        for index, row in enumerate(iterator):
            if index > MAX_ROWS:
                raise ValueError('数据超过 10 万行')
            if len(row) > 100 or any(len(str(x)) > 10000 for x in row):
                raise ValueError('表格列数或单元格内容过长')
            yield index + 1, row
    except (UnicodeError, csv.Error, ET.ParseError, KeyError, IndexError) as exc:
        raise ValueError('表格无法读取，请检查编码和单元格内容') from exc
