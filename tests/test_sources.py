import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import germinate
from collectors.search import search_urls
from collectors.html import extract_search_links
from sheet_sources import read_export
from sync_sources import column_range, merge_sources, sheet_id, write_sources


class SourceTests(unittest.TestCase):
    def test_search_encoding_filters_and_unique_queries(self):
        source = {'search': {'url': 'https://x.org/search?q=old&type=old', 'query_parameter': 'q',
                            'keywords': ['agua & suelo', 'agua & suelo'], 'parameters': {'type': ['grant', 'call']}}}
        self.assertEqual(search_urls(source), ['https://x.org/search?type=grant&type=call&q=agua+%26+suelo'])

    def test_filter_only_search_removes_existing_keyword(self):
        source = {'search': {'url': 'https://x.org/search?title=old&keep=yes',
                            'query_parameter': 'title', 'keywords': [],
                            'parameters': {'region': '21', 'year': '2026', 'mechanism': '0'}}}
        self.assertEqual(search_urls(source), ['https://x.org/search?keep=yes&region=21&year=2026&mechanism=0'])

    def test_blank_keyword_is_not_silently_a_filter_only_search(self):
        with self.assertRaises(ValueError):
            search_urls({'search': {'url': 'https://x.org/search', 'query_parameter': 'q', 'keywords': [' ']}})

    def test_red_pac_filters_match_reference_and_all_keywords(self):
        from urllib.parse import parse_qs, urlsplit
        source = next(s for s in germinate.load_json('config/sources.json') if s['name'] == 'RED PAC')
        websites = germinate.load_json('config/website-filters.json')['websites']
        reference = next(w['filters'] for w in websites if w['source_name'] == source['name'])
        for key, value in source['search']['parameters'].items():
            if 'options' in reference[key]:
                self.assertIn(value, reference[key]['options'])
        urls = search_urls(source)
        self.assertEqual(len(urls), len(source['search']['keywords']))
        for url in urls:
            query = parse_qs(urlsplit(url).query, keep_blank_values=True)
            for key, value in source['search']['parameters'].items():
                self.assertEqual(query[key], [value])

    def test_bad_search_config(self):
        with self.assertRaises(ValueError):
            search_urls({'search': {'url': 'https://x.org'}})

    def test_empty_results_exclude_navigation(self):
        html = '<a href="/grant">Grant</a><div class="results"><p>0 results</p></div>'
        self.assertEqual(extract_search_links(html, 'https://x.org', 'results'), [])
        with self.assertRaises(ValueError):
            extract_search_links(html, 'https://x.org', 'missing')

    def test_search_follows_generic_result_titles_and_shares_budget(self):
        source = {'name': 'Test', 'collector_type': 'html_search', 'max_depth': 1, 'max_pages': 3,
                  'search': {'url': 'https://x.org/search', 'query_parameter': 'q', 'keywords': ['one', 'two'],
                             'result_container_class': 'results'}}
        pages = {'https://x.org/search?q=one': '<a href="/nav-grant">grant</a><div class="results"><a href="/123">Read more</a></div>',
                 'https://x.org/123': 'ecosystem restoration grant',
                 'https://x.org/search?q=two': '<div class="results"><a href="/123">Read more</a></div>'}
        rules = germinate.load_json(Path('config/rules.json'))
        visited = set(); found = []
        for url in search_urls(source):
            results, errors = germinate.crawl_start_url(url, source, rules, 'today', pages.__getitem__, visited)
            self.assertFalse(errors); found.extend(results)
        self.assertEqual(len(visited), 3)
        self.assertEqual([r.url for r in found], ['https://x.org/123'])

    def test_merge_preserves_settings_and_is_idempotent(self):
        original = [{'name': 'Existing', 'collector_type': 'interactive_search', 'start_urls': ['https://x.org/']}]
        rows = [['https://x.org/#a'], ['https://y.org/Path', 'Useful name'], ['https://y.org/Path']]
        merged, added = merge_sources(original, rows)
        self.assertEqual(len(added), 1)
        self.assertEqual(merged[0], original[0])
        self.assertEqual(merged[1]['name'], 'Useful name')
        self.assertEqual(merge_sources(merged, rows)[1], [])
        self.assertEqual(len(original), 1)

    def test_invalid_cell_aborts(self):
        with self.assertRaisesRegex(ValueError, 'Row 3'):
            merge_sources([], [['https://x.org/'], ['not a URL']])

    def test_range_and_id_validation(self):
        self.assertEqual(column_range("John's tab", 'aa', 3), "'John''s tab'!AA3:AA")
        self.assertEqual(sheet_id('https://docs.google.com/spreadsheets/d/abc/edit'), 'abc')
        with self.assertRaises(ValueError):
            sheet_id('https://evil.org/spreadsheets/d/abc/edit')

    def test_hyperlink_extraction_uses_selected_column_and_tab(self):
        data = BytesIO()
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        with ZipFile(data, 'w') as z:
            z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="Sources" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}" xmlns:r="{rel}"><sheetData><row><c r="A3" t="inlineStr"><is><t>Fund</t></is></c><c r="B3" t="inlineStr"><is><t>https://ignore.org</t></is></c><c r="A4" t="inlineStr"><is><t>Heading</t></is></c></row></sheetData><hyperlinks><hyperlink ref="A3" r:id="h1"/></hyperlinks></worksheet>')
            z.writestr('xl/worksheets/_rels/sheet1.xml.rels', f'<Relationships><Relationship Id="h1" Type="{rel}/hyperlink" Target="https://fund.org"/></Relationships>')
        rows, skipped = read_export(data.getvalue(), 'Sources', 'A', 3)
        self.assertEqual(rows, [['https://fund.org', 'Fund', 'A3']])
        self.assertEqual(len(skipped), 1)
        with self.assertRaises(ValueError):
            read_export(data.getvalue(), 'Wrong', 'A', 3)

    def test_failed_atomic_replace_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sources.json'; path.write_text('[]')
            with patch('sync_sources.os.replace', side_effect=OSError('blocked')):
                with self.assertRaises(OSError):
                    write_sources(path, [{'name': 'new'}])
            self.assertEqual(path.read_text(), '[]')
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
