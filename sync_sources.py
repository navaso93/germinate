"""Preview or merge a Google Sheets URL column into the local sources file."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import sys
from sheet_sources import fetch_public
from config_io import load_json
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def sheet_id(value):
    match = re.fullmatch(r"[A-Za-z0-9_-]+", value)
    if match:
        return value
    parts = urlsplit(value)
    match = re.match(r"/spreadsheets/d/([A-Za-z0-9_-]+)(?:/|$)", parts.path)
    if parts.scheme == "https" and parts.hostname == "docs.google.com" and match:
        return match.group(1)
    raise ValueError("Expected a Google Sheets URL or spreadsheet ID")


def column_range(tab, column, start_row):
    if not isinstance(column, str) or not re.fullmatch(r"[A-Za-z]{1,3}", column):
        raise ValueError("column must be a column letter, such as C or AA")
    if not isinstance(start_row, int) or isinstance(start_row, bool) or start_row < 1:
        raise ValueError("start_row must be a positive integer")
    if not isinstance(tab, str) or not tab:
        raise ValueError("tab is required")
    column = column.upper()
    return "'" + tab.replace("'", "''") + f"'!{column}{start_row}:{column}"


def fetch_values(config):
    spreadsheet = sheet_id(config["spreadsheet"])
    selected_range = column_range(config["tab"], config["column"], config.get("start_row", 2))
    if config.get("access") == "public":
        rows, skipped = fetch_public(config, spreadsheet)
        for message in skipped:
            print(f"Skipped {message}", file=sys.stderr)
        return rows
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError("Install Sheets support: python -m pip install -r requirements.txt") from exc
    credentials, _ = google.auth.default(scopes=[SCOPE])
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet}"
    with AuthorizedSession(credentials) as session:
        response = session.get(url, params={"ranges": selected_range, "includeGridData": "true",
            "fields": "sheets(data(startRow,rowData(values(formattedValue,hyperlink,textFormatRuns(format(link))))))"}, timeout=30)
        response.raise_for_status()
        rows = []
        for sheet in response.json().get("sheets", []):
            for grid in sheet.get("data", []):
                for index, row in enumerate(grid.get("rowData", []), grid.get("startRow", 0) + 1):
                    cells = row.get("values", [])
                    if not cells:
                        continue
                    cell = cells[0]
                    label = cell.get("formattedValue", "")
                    links = {run.get("format", {}).get("link", {}).get("uri")
                             for run in cell.get("textFormatRuns", [])}
                    links.discard(None)
                    if cell.get("hyperlink"):
                        links.add(cell["hyperlink"])
                    if not links and label.strip().startswith(("https://", "http://")):
                        links.add(label.strip())
                    for link in sorted(links):
                        rows.append([link, label, f"{config['column']}{index}"])
                    if not links and label.strip():
                        print(f"Skipped {config['column']}{index}: {label} (no URL)", file=sys.stderr)
        return rows


def clean_url(value):
    if not isinstance(value, str):
        raise ValueError("Expected a plain-text HTTP(S) URL")
    value = value.strip()
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username or parts.password or any(c.isspace() for c in value)):
        raise ValueError("Expected one plain-text HTTP(S) URL without embedded credentials")
    _ = parts.port  # Validate malformed ports before writing anything.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def merge_sources(existing, rows, start_row=2):
    """Append only; preserve hand-configured collectors, keywords, and source names."""
    merged = copy.deepcopy(existing)
    known = {clean_url(url) for source in existing for url in source["start_urls"]}
    additions, invalid = [], []
    for number, row in enumerate(rows, start_row):
        if not row or row[0] is None or (isinstance(row[0], str) and not row[0].strip()):
            continue
        try:
            url = clean_url(row[0])
        except ValueError as exc:
            invalid.append(f"Row {row[2] if len(row) > 2 else number}: {exc}")
            continue
        if url in known:
            continue
        known.add(url)
        source = {"name": row[1] if len(row) > 1 and row[1] else urlsplit(url).hostname + urlsplit(url).path,
                  "collector_type": "html", "max_depth": 2, "max_pages": 30,
                  "start_urls": [url], "notes": "Imported from Google Sheets; review collector type before crawling."}
        merged.append(source)
        additions.append(url)
    if invalid:
        raise ValueError("No changes written. Fix invalid URL cells:\n" + "\n".join(invalid))
    return merged, additions


def write_sources(path, sources):
    """Replace atomically so an interrupted write cannot truncate sources.json."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(sources, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "sheets.json")
    parser.add_argument("--sources", type=Path, default=ROOT / "config" / "sources.json")
    parser.add_argument("--apply", action="store_true", help="Write additions; default only previews")
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        existing = load_json(args.sources)
        rows = fetch_values(config)
        merged, additions = merge_sources(existing, rows, config.get("start_row", 2))
        for url in additions:
            print(f"Add: {url}")
        if args.apply and additions:
            write_sources(args.sources, merged)
        print(f"{'Applied' if args.apply else 'Previewed'} {len(additions)} new sources; existing settings preserved.")
        return 0
    except Exception as exc:
        print(f"Source sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
