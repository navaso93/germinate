from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import json
import sys

import drive_upload
import germinate


class DriveTests(unittest.TestCase):
    def test_folder_urls_and_ids(self):
        self.assertEqual(drive_upload.folder_id('https://drive.google.com/drive/folders/abc-123?usp=sharing'), 'abc-123')
        self.assertEqual(drive_upload.folder_id('https://drive.google.com/drive/u/0/folders/abc'), 'abc')
        for bad in ['', 'https://evil.org/drive/folders/abc', 'https://docs.google.com/spreadsheets/d/abc']:
            with self.assertRaises(ValueError):
                drive_upload.folder_id(bad)

    def test_upload_uses_exact_folder_and_dated_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'opportunities.csv'; path.write_text('title\nGrant\n')
            service = Mock(); files = service.files.return_value
            files.get.return_value.execute.return_value = {'mimeType': 'application/vnd.google-apps.folder', 'capabilities': {'canAddChildren': True}}
            files.create.return_value.execute.return_value = {'id': 'new-file'}
            media = Mock()
            result = drive_upload.upload_with_service(path, 'target-folder', service, media,
                                                     datetime(2026, 9, 19, 10, 30, tzinfo=timezone.utc))
            self.assertIn('new-file', result)
            body = files.create.call_args.kwargs['body']
            self.assertEqual(body['parents'], ['target-folder'])
            self.assertEqual(body['name'], 'opportunities_2026-09-19_10-30-00-000000Z.csv')
            self.assertEqual(body['mimeType'], 'text/csv')
            self.assertTrue(files.create.call_args.kwargs['supportsAllDrives'])
            files.update.assert_not_called()

    def test_unwritable_or_invalid_folder_does_not_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'out.csv'; path.write_text('x')
            for folder in [{'mimeType': 'text/csv'}, {'mimeType': 'application/vnd.google-apps.folder', 'trashed': True},
                           {'mimeType': 'application/vnd.google-apps.folder', 'capabilities': {'canAddChildren': False}}]:
                service = Mock(); service.files.return_value.get.return_value.execute.return_value = folder
                with self.assertRaises(ValueError):
                    drive_upload.upload_with_service(path, 'folder', service, Mock())
                service.files.return_value.create.assert_not_called()

    def test_optional_upload_and_demo_do_not_require_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'drive.json'
            self.assertIsNone(drive_upload.configured_upload(Path('missing.csv'), config))
            with self.assertRaises(ValueError):
                drive_upload.configured_upload(Path('missing.csv'), config, force=True)
            config.write_text(json.dumps({'enabled': True, 'folder': 'abc'}))
            with patch('drive_upload.upload_csv', return_value='https://drive.google.com/file/d/abc/view') as upload:
                self.assertIsNone(drive_upload.configured_upload(Path('missing.csv'), config, demo=True))
                upload.assert_not_called()
                self.assertIsNotNone(drive_upload.configured_upload(Path('out.csv'), config))
                upload.assert_called_once()

    def test_pipeline_keeps_csv_and_reports_upload_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'out.csv'
            with patch.object(sys, 'argv', ['germinate.py', '--demo', '--drive', '--output', str(path)]), \
                 patch('germinate.configured_upload', side_effect=RuntimeError('offline')), \
                 patch('germinate.enrich', return_value=[]):
                self.assertEqual(germinate.main(), 2)
            self.assertTrue(path.exists())
            self.assertIn('title', path.read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
