"""Read hyperlinks from a public Google Sheet's XLSX export (no dependencies)."""
from io import BytesIO
import posixpath
import re
from urllib.request import urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def read_export(data, tab, column, start_row=3):
    with ZipFile(BytesIO(data)) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheet = next((s for s in workbook.findall('s:sheets/s:sheet', NS) if s.attrib['name'] == tab), None)
        if sheet is None:
            raise ValueError(f'Sheet tab not found: {tab}')
        target = rels[sheet.attrib[RID]]
        path = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
        root = ET.fromstring(archive.read(path))
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(item.itertext()) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        link_path = posixpath.join(posixpath.dirname(path), '_rels', posixpath.basename(path) + '.rels')
        targets = {}
        if link_path in archive.namelist():
            targets = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(archive.read(link_path))
                       if r.attrib.get('Type', '').endswith('/hyperlink')}
        hyperlinks = {h.attrib['ref']: targets.get(h.attrib.get(RID)) for h in root.findall('s:hyperlinks/s:hyperlink', NS)}
        rows, skipped = [], []
        for cell in root.findall('s:sheetData/s:row/s:c', NS):
            ref = cell.attrib['r']
            match = re.fullmatch(r'([A-Z]+)([0-9]+)', ref)
            if not match or match[1] != column.upper() or int(match[2]) < start_row:
                continue
            text = cell.findtext('s:v', '', NS)
            if cell.attrib.get('t') == 's':
                text = strings[int(text)]
            elif cell.attrib.get('t') == 'inlineStr':
                text = ''.join(cell.find('s:is', NS).itertext())
            link = hyperlinks.get(ref)
            formula = cell.findtext('s:f', '', NS)
            formula_link = re.match(r'(?i)HYPERLINK\("([^"]+)"', formula)
            if not link and formula_link:
                link = formula_link[1]
            if not link and text.strip().startswith(('https://', 'http://')):
                link = text.strip()
            if link:
                rows.append([link, text.strip(), ref])
            elif text.strip():
                skipped.append(f'{ref}: {text.strip()} (no URL)')
        return rows, skipped


def fetch_public(config, spreadsheet):
    url = f'https://docs.google.com/spreadsheets/d/{spreadsheet}/export?format=xlsx'
    with urlopen(url, timeout=30) as response:
        data = response.read()
    return read_export(data, config['tab'], config['column'], config.get('start_row', 3))
