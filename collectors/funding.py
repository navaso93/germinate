"""Adapters for public funding data. Never evaluate downloaded JavaScript."""
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from html import unescape
from io import BytesIO
import json
import os
import tempfile
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from collectors.html import extract_links, extract_text


def canonical_url(url):
    p = urlsplit(url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Expected a public HTTP(S) source URL")
    if p.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Local URLs are not funding sources")
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", p.query, ""))


class Fetcher:
    def __init__(self, directory, max_bytes=15000000):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def get(self, url):
        import hashlib
        url = canonical_url(url)
        path = self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".bin")
        if path.exists():
            return path.read_bytes()
        try:
            with urlopen(Request(url, headers={"User-Agent": "GerminateGrantMonitor/0.3"}), timeout=40) as response:
                data = response.read(self.max_bytes + 1)
        except HTTPError:
            raise
        except URLError:
            # Windows Schannel handles some EU hosts that reset OpenSSL handshakes.
            curl = shutil.which("curl.exe")
            if not curl:
                raise
            try:
                result = subprocess.run([curl, "--fail", "--location", "--silent", "--show-error",
                                         "--max-time", "45", "--max-filesize", str(self.max_bytes), url],
                                        capture_output=True, timeout=50, check=True)
                data = result.stdout
            except subprocess.CalledProcessError:
                powershell = shutil.which("powershell.exe")
                if not powershell:
                    raise
                # URL/path are passed as environment data, never interpolated into code.
                with tempfile.TemporaryDirectory() as temporary:
                    target = Path(temporary) / "response.bin"
                    environment = dict(os.environ, GERMINATE_FETCH_URL=url, GERMINATE_FETCH_PATH=str(target))
                    subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command",
                                    "$ErrorActionPreference='Stop'; Invoke-WebRequest -UseBasicParsing -TimeoutSec 45 -Uri $env:GERMINATE_FETCH_URL -OutFile $env:GERMINATE_FETCH_PATH"],
                                   env=environment, capture_output=True, timeout=55, check=True)
                    if target.stat().st_size > self.max_bytes:
                        raise ValueError("Document exceeds configured byte limit")
                    data = target.read_bytes()
        if len(data) > self.max_bytes:
            raise ValueError("Document exceeds configured byte limit")
        path.write_bytes(data)
        return data

    def text(self, url):
        return self.get(url).decode("utf-8-sig", errors="replace")

    def json(self, url):
        return json.loads(self.text(url))


def iso_date(value):
    if not value:
        return ""
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def policy_reason(publication, deadline, status, today, config):
    """Empty means eligible for assessment/export under the date policy."""
    if config.get("exclude_closed", True) and (status == "closed" or (deadline and deadline < today.isoformat())):
        return "closed"
    if publication:
        if publication > today.isoformat():
            return "future_publication"
        if publication < (today - timedelta(days=config["publication_last_days"])).isoformat():
            return "old_publication"
        return ""
    if config.get("missing_publication") == "include_if_open" and status == "open":
        return ""
    return "publication_unverified"


def topic_match(text, terms):
    return any(term.casefold() in text.casefold() for term in terms)


def main_text(html):
    m = re.search(r"<main\b[^>]*>(.*?)</main>", html, re.S | re.I)
    return extract_text(m[1] if m else html)


def embedded_array(html, name):
    match = re.search(r"\b(?:const|let|var)\s+" + re.escape(name) + r"\s*=\s*(\[)", html)
    if not match:
        raise ValueError(f"Expected embedded data array {name} not found")
    data, _ = json.JSONDecoder().raw_decode(html[match.start(1):])
    if not isinstance(data, list):
        raise ValueError("Expected a list of calls")
    return data


def rural_data(bundle, filename):
    mapping = re.search(r'"\./' + re.escape(filename) + r'":(\d+)', bundle)
    if not mapping:
        raise ValueError(f"Toolkit dataset missing: {filename}")
    pattern = mapping[1] + r":function\(\w+\).*?JSON.parse\(('(?:\\.|[^'\\])*')\)"
    match = re.search(pattern, bundle)
    if not match:
        raise ValueError(f"Toolkit dataset format changed: {filename}")
    # Literal-only parsing. No JavaScript execution and no eval().
    return json.loads(ast.literal_eval(match[1]))


def codes(value):
    return {int(n) for n in re.findall(r"\d+", str(value or ""))}


def rural_matches(row, site):
    if site.get("support_code") != 1:
        raise ValueError("Only the toolkit grant support code (1) is implemented")
    if not re.search(r"\bGrant\s*\*\s*1\b", str(row.get("FICHE_TYPEFUND", "")), re.I):
        return False
    return (not site["activity_codes"] or bool(codes(row.get("FILTER_THEMFOCUS_CODE")) & set(site["activity_codes"]))) and (
        not site["applicant_codes"] or bool(codes(row.get("FILTER_WHO_CODE")) & set(site["applicant_codes"])))


def document_text(data, config):
    if data.startswith(b"%PDF"):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        count = min(len(reader.pages), config["max_pdf_pages"])
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:count])
        if not text.strip():
            raise ValueError("PDF has no extractable text; OCR not implemented")
        if count < len(reader.pages):
            text += "\n[PDF truncated by configured page limit]"
        return text
    return main_text(data.decode("utf-8", errors="replace"))


def add_documents(item, urls, fetcher, config, report):
    for url in list(dict.fromkeys(urls))[:config["max_linked_documents"]]:
        try:
            data = fetcher.get(url)
            if len(data) > config["max_document_bytes"]:
                raise ValueError("Linked document exceeds configured byte limit")
            text = document_text(data, config)
            item["evidence"] += "\n\nOFFICIAL LINKED DOCUMENT " + url + "\n" + text[:45000]
            item["evidence_urls"].append(url)
            if len(text) > 45000:
                item["notes"].append("Linked document text truncated at 45000 characters.")
        except Exception as exc:
            message = f"{url}: {type(exc).__name__}: {exc}"
            report["errors"].append(message)
            item["notes"].append("Linked document could not be read.")


def candidate(site, title, url, evidence, publication="", deadline="", status="unknown"):
    return dict(source=site["name"], site_id=site["id"], title=unescape(title), url=canonical_url(url),
                evidence=evidence, publication_date=publication, deadline=deadline,
                application_status=status, evidence_urls=[url], notes=[])


def collect_cascade(site, common, today, fetcher, report):
    data = embedded_array(fetcher.text(site["url"]), "dataProposals")
    report["discovered"] = len(data)
    output = []
    for row in data:
        if row["call_type"] != site["call_type"]:
            continue
        matches = True
        for selected, key in (("domains", "domains"), ("technologies", "technologies"), ("beneficiaries", "type_of_beneficiary")):
            allowed = set(site.get(selected, []))
            if allowed and not allowed.intersection(x["value"] for x in row.get(key, [])):
                matches = False
        if not matches:
            report["excluded"]["site_filters"] = report["excluded"].get("site_filters", 0) + 1
            continue
        deadline = iso_date(row.get("closes"))
        # The page explicitly lists OPEN calls. created_time is a database timestamp, not a publication date.
        status = "closed" if deadline and deadline < today.isoformat() else "open"
        if status == "closed":
            report["excluded"]["closed"] = report["excluded"].get("closed", 0) + 1
            continue
        evidence = "Source: current Open Calls / Calls for proposals listing.\n" + json.dumps(
            {k: v for k, v in row.items() if k not in {"icon", "created_time", "id"}}, ensure_ascii=False)
        item = candidate(site, row["title"], row["permalink"], evidence, deadline=deadline, status=status)
        item["notes"].append("Database created_time is not used as publication date.")
        links = row.get("links") or {}
        add_documents(item, [u for u in (links.get("guidelines"), links.get("website")) if u], fetcher, common, report)
        output.append(item)
    return output


def ipyme_publication(detail):
    # Only call announcements; amendments and legal bases are not new calls.
    dates = [iso_date(b.get("FechaPublicacion")) for b in detail.get("Boletines", [])
             if str(b.get("NaturalezaAnuncio", "")).strip().casefold() == "convocatoria"]
    return min((d for d in dates if d), default="")


def collect_ipyme(site, common, today, fetcher, report):
    base = site["api_url"].rstrip("/")
    params = {"texto": site["query"], "enPlazo": str(site["only_open"]).lower()}
    total = int(fetcher.json(base + "/ayudas?" + urlencode(params)))
    report["reported_total"] = total
    listings = {}
    exhausted = False
    for page in range(site["max_listing_pages"]):
        rows = fetcher.json(base + "/ayudas?" + urlencode(dict(params, pagina=page, ventana=site["page_size"])))
        if not isinstance(rows, list):
            raise ValueError("IPYME search response is not a list")
        before = len(listings)
        for row in rows:
            listings[str(row["Id"])] = row
        if len(listings) >= total or not rows:
            exhausted = True
            break
        if len(listings) == before:
            raise ValueError("IPYME pagination repeated a page before all results were collected")
    if not exhausted or len(listings) < total:
        report["errors"].append("IPYME page limit reached; discovery is incomplete.")
    report["discovered"] = len(listings)
    output = []
    def load(row):
        return row, fetcher.json(base + "/detalle/" + str(row["Id"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, detail in pool.map(load, listings.values()):
            aid = detail["Ayuda"]
            if not any(t.casefold() in str(aid.get("TipoAyuda", "")).casefold() for t in site["grant_types"]):
                report["excluded"]["not_grant"] = report["excluded"].get("not_grant", 0) + 1
                continue
            publication = ipyme_publication(detail)
            deadline = iso_date(row.get("FechaSolicitud"))
            status = "open" if row.get("Vigentes") is True else "unknown"
            if aid.get("esVigente") is False and status == "open":
                status = "unknown"
            reason = policy_reason(publication, deadline, status, today, common)
            if reason:
                report["excluded"][reason] = report["excluded"].get(reason, 0) + 1
                continue
            evidence = "IPYME public search record:\n" + json.dumps(row, ensure_ascii=False)
            evidence += "\nIPYME detailed record and official publication references:\n" + json.dumps(detail, ensure_ascii=False)
            if not topic_match(evidence, common["topic_terms"]):
                report["excluded"]["topics"] = report["excluded"].get("topics", 0) + 1
                continue
            item = candidate(site, aid["Titulo"], site["url"] + "?idAyuda=" + str(row["Id"]),
                             evidence, publication, deadline, status)
            if row.get("Vigentes") is True and aid.get("esVigente") is False:
                item["notes"].append("IPYME listing says open but detail flag disagrees; opening is unconfirmed.")
            add_documents(item, [base + "/detalle?" + urlencode({"id": row["Id"], "fichero": ""})], fetcher, common, report)
            output.append(item)
    return output


def collect_rural(site, common, today, fetcher, report):
    html = fetcher.text(site["url"])
    asset = re.search(r'<script[^>]+src=["\']([^"\']*/js/app\.[^"\']+\.js)', html)
    if not asset:
        raise ValueError("Toolkit application bundle link not found")
    bundle = fetcher.text(urljoin(site["url"], asset[1]))
    funds = rural_data(bundle, "ruraltoolkit.json")
    selected = [row for row in funds if rural_matches(row, site)]
    report["catalogue_total"] = len(funds)
    report["programmes_selected"] = len(selected)
    report["programme_links"] = []
    output, visited, emitted = [], set(), set()
    listing_queue = []
    for row in selected:
        urls = re.findall(r"https?://[^\s<>\"*]+", str(row.get("FICHE_CALLSWEB") or ""))
        for url in urls:
            url = site.get("call_url_overrides", {}).get(url, url)
            report["programme_links"].append({"programme": row["FICHE_SHORTTITLE"], "url": url})
            if "/opportunities/portal/" in url:
                report["errors"].append(f"{row['FICHE_SHORTTITLE']}: EU Funding & Tenders SPA requires a separate adapter: {url}")
                continue
            listing_queue.append((url, row["FICHE_SHORTTITLE"], 0))
    while listing_queue:
        url, programme, depth = listing_queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetcher.text(url)
            links = extract_links(html, url)
        except Exception as exc:
            report["errors"].append(f"{url}: {type(exc).__name__}: {exc}")
            continue
        for link in links:
            # Listing pagination, never automatically follow every national portal.
            if depth + 1 < site["max_listing_pages"] and re.search(r"[?&]page=\d+", link.url) and urlsplit(link.url).path == urlsplit(url).path:
                listing_queue.append((link.url, programme, depth + 1))
            path = urlsplit(link.url).path.rstrip("/")
            if urlsplit(url).hostname in {"eit.europa.eu", "www.eit.europa.eu"} and not path.startswith("/our-activities/opportunities/"):
                continue
            if link.url in emitted or link.url == url or len(path.split("/")) < 3:
                continue
            if not re.search(r"call|grant|funding|opportunit|convocatoria", link.title + " " + path, re.I):
                continue
            if re.search(r"privacy|cookie|procurement|vacanc|job|tender|newsletter|/news-events/events", path, re.I):
                continue
            if "/opportunities/portal/" in link.url:
                continue
            # Avoid navigation, generic programmes, and directory/category pages.
            if path.endswith(("/opportunities", "/calls", "/open-calls", "/funding", "/calls-for-projects", "/programmes")):
                continue
            emitted.add(link.url)
            if len(emitted) > site["max_call_pages"]:
                report["errors"].append("Rural toolkit detail-page limit reached; remaining links not assessed.")
                report["discovered"] = len(emitted) - 1
                return output
            try:
                page = fetcher.text(link.url)
                text = main_text(page)
                if len(text) < 200 or "doesn't work without JavaScript" in text:
                    report["errors"].append(f"Dynamic or empty call page: {link.url}")
                    continue
                if not topic_match(text, common["topic_terms"]):
                    continue
                item = candidate(site, link.title, link.url, "Discovered through EU Rural Toolkit programme: " + programme + "\n" + text)
                docs = [l.url for l in extract_links(page, link.url)
                        if ".pdf" in l.url.lower() and re.search(r"guideline|applicant|call|convocatoria|bases", l.title, re.I)]
                add_documents(item, docs, fetcher, common, report)
                output.append(item)
            except Exception as exc:
                report["errors"].append(f"{link.url}: {type(exc).__name__}: {exc}")
    report["discovered"] = len(emitted)
    return output


COLLECTORS = {"cascade": collect_cascade, "ipyme": collect_ipyme, "rural_toolkit": collect_rural}


def collect(site, common, today, fetcher):
    report = {"source": site["name"], "errors": [], "excluded": {}}
    rows = COLLECTORS[site["id"]](site, common, today, fetcher, report)
    report["candidates"] = len(rows)
    return rows, report
