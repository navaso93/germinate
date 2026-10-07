"""Upload CSV snapshots to a configured Google Drive folder."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from config_io import load_json

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'config' / 'drive.json'
# An arbitrary existing folder needs Drive access without a Google Picker flow.
SCOPES = ['https://www.googleapis.com/auth/drive']


def folder_id(value):
    value = str(value).strip()
    if re.fullmatch(r'[A-Za-z0-9_-]+', value):
        return value
    parts = urlsplit(value)
    match = re.fullmatch(r'/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/?', parts.path)
    if parts.scheme == 'https' and parts.hostname == 'drive.google.com' and match:
        return match[1]
    raise ValueError('Set folder to a Google Drive folder URL or ID in config/drive.json.')


def local_path(value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def credentials(config, authorize=False):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError('Install Drive support: python -m pip install -r requirements.txt') from exc
    token = local_path(config.get('token_file', 'secrets/drive-token.json'))
    if authorize:
        client = local_path(config.get('client_secrets_file', 'secrets/drive-client.json'))
        flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
        creds = flow.run_local_server(port=0, timeout_seconds=300, access_type='offline', prompt='consent')
    else:
        if not token.exists():
            raise RuntimeError('Drive is not connected. Run python drive_upload.py --authorize first.')
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise RuntimeError('Drive login expired. Run python drive_upload.py --authorize again.')
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding='utf-8')
    return creds


def upload_with_service(path, destination, service, media_factory, now=None):
    """Check the destination, then create one dated CSV; never overwrite older runs."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Results file not found: {path}')
    files = service.files()
    folder = files.get(fileId=destination, fields='id,mimeType,trashed,capabilities(canAddChildren)',
                       supportsAllDrives=True).execute()
    if folder.get('trashed') or folder.get('mimeType') != 'application/vnd.google-apps.folder':
        raise ValueError('The Drive destination is not an active folder.')
    if not folder.get('capabilities', {}).get('canAddChildren'):
        raise ValueError('Your Google account cannot add files to this folder.')
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S-%fZ')
    name = f'{path.stem}_{stamp}.csv'
    media = media_factory(str(path), mimetype='text/csv', resumable=True)
    result = files.create(body={'name': name, 'parents': [destination], 'mimeType': 'text/csv'},
                          media_body=media, fields='id,name,webViewLink', supportsAllDrives=True).execute()
    if not result.get('id'):
        raise RuntimeError('Drive returned no file ID; upload could not be confirmed.')
    return result.get('webViewLink') or f"https://drive.google.com/file/d/{result['id']}/view"


def upload_csv(path, config):
    destination = folder_id(config.get('folder', ''))
    creds = credentials(config)
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError('Install Drive support: python -m pip install -r requirements.txt') from exc
    with build('drive', 'v3', credentials=creds, cache_discovery=False) as service:
        return upload_with_service(path, destination, service, MediaFileUpload)


def configured_upload(path, config_path=CONFIG_PATH, force=False, demo=False):
    if demo and not force:
        return None
    if not config_path.exists():
        if force:
            raise ValueError('Copy config/drive.example.json to config/drive.json and set your folder.')
        return None
    config = load_json(config_path)
    if not force and not config.get('enabled', False):
        return None
    return upload_csv(path, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    parser.add_argument('--authorize', action='store_true', help='Connect your Google account in a browser')
    parser.add_argument('--file', type=Path, help='Upload an existing CSV without running collection again')
    args = parser.parse_args()
    try:
        if args.authorize:
            config = load_json(args.config)
            folder_id(config.get('folder', ''))
            credentials(config, authorize=True)
            print('Google Drive connected. No results uploaded during authorization.')
        elif args.file:
            print('Uploaded to Google Drive: ' + configured_upload(args.file, args.config, force=True))
        else:
            parser.error('Choose --authorize or --file PATH')
        return 0
    except Exception as exc:
        print(f'Drive: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
