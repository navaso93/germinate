"""Small, transparent prototype for discovering possible grant opportunities."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent


@dataclass
class Link:
    title: str
    url: str


@dataclass
class Result:
    source: str
    collector_type: str
    title: str
    url: str
    decision: str
    score: int
    matched_grant_terms: str
    matched_topics: str
    rejection_terms: str
    checked_at: str
    note: str


class LinkParser(HTMLParser):
    """Extract visible anchor text and URLs from ordinary HTML."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[Link] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if tag == "a" and self._ignored_depth == 0:
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href and self._ignored_depth == 0:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag == "a" and self._href:
            title = " ".join(" ".join(self._text).split())
            href = self._href.strip()
            if title and href and not href.startswith(("#", "mailto:", "javascript:")):
                self.links.append(Link(title=title, url=urljoin(self.base_url, href)))
            self._href = None
            self._text = []


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_html(url: str, timeout: int = 25) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "GerminateGrantMonitor/0.1 (+manual prototype)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"unsupported content type: {content_type}")
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def find_terms(text: str, terms: Iterable[str]) -> list[str]:
    lowered = text.casefold()
    return sorted({term for term in terms if term.casefold() in lowered})


def classify(link: Link, source: dict, rules: dict, checked_at: str) -> Result | None:
    searchable = f"{link.title} {link.url}"
    grants = find_terms(searchable, rules["grant_terms"])
    topics = find_terms(searchable, rules["topic_terms"])
    rejected = find_terms(searchable, rules["rejection_terms"])
    if not grants and not topics and not rejected:
        return None

    score = len(grants) * 2 + len(topics) - len(rejected) * 4
    if rejected:
        decision = "rejected"
        note = "Contains an excluded financing or procurement term."
    elif grants and topics and score >= rules["minimum_score"]:
        decision = "candidate"
        note = "Looks relevant; human verification is still required."
    else:
        decision = "review"
        note = "Grant type or thematic fit is incomplete."

    if source["collector_type"] == "interactive_search":
        decision = "needs_specialized_collector"
        note = "Interactive search cannot be enumerated reliably by this simple HTML version."

    return Result(
        source=source["name"], collector_type=source["collector_type"],
        title=link.title, url=link.url, decision=decision, score=score,
        matched_grant_terms="; ".join(grants), matched_topics="; ".join(topics),
        rejection_terms="; ".join(rejected), checked_at=checked_at, note=note,
    )


def inspect_html(html: str, base_url: str, source: dict, rules: dict, checked_at: str) -> list[Result]:
    parser = LinkParser(base_url)
    parser.feed(html)
    unique: dict[str, Link] = {}
    for link in parser.links:
        unique.setdefault(link.url, link)
    return [result for link in unique.values()
            if (result := classify(link, source, rules, checked_at)) is not None]


def run_demo(rules: dict, checked_at: str) -> list[Result]:
    source = {"name": "Demo Environmental Fund", "collector_type": "html"}
    url = "https://example.org/funding/"
    html = (ROOT / "demo" / "sample_source.html").read_text(encoding="utf-8")
    return inspect_html(html, url, source, rules, checked_at)


def run_live(sources: list[dict], rules: dict, checked_at: str) -> tuple[list[Result], list[str]]:
    results: list[Result] = []
    errors: list[str] = []
    for source in sources:
        print(f"Checking {source['name']}...", flush=True)
        if source["collector_type"] == "interactive_search":
            results.append(Result(
                source=source["name"], collector_type=source["collector_type"],
                title="Specialized collector required", url=source["start_urls"][0],
                decision="needs_specialized_collector", score=0,
                matched_grant_terms="", matched_topics="", rejection_terms="",
                checked_at=checked_at,
                note="This interactive portal needs browser automation or a public API in the next version.",
            ))
            continue
        for url in source["start_urls"]:
            try:
                results.extend(inspect_html(fetch_html(url), url, source, rules, checked_at))
            except (HTTPError, URLError, TimeoutError, ValueError) as exc:
                errors.append(f"{source['name']} | {url} | {exc}")
    return results, errors


def deduplicate(results: list[Result]) -> list[Result]:
    """Keep one record per source and destination URL."""
    unique: dict[tuple[str, str], Result] = {}
    for result in results:
        key = (result.source.casefold(), result.url.casefold())
        existing = unique.get(key)
        if existing is None or result.score > existing.score:
            unique[key] = result
    return list(unique.values())


def write_csv(results: list[Result], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(Result.__dataclass_fields__)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Find possible Germinate grant opportunities.")
    parser.add_argument("--demo", action="store_true", help="Use sample HTML; no internet required.")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "opportunities.csv")
    args = parser.parse_args()
    rules = load_json(ROOT / "config" / "rules.json")
    sources = load_json(ROOT / "config" / "sources.json")
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results, errors = (run_demo(rules, checked_at), []) if args.demo else run_live(sources, rules, checked_at)
    results = deduplicate(results)
    write_csv(results, args.output)

    print(f"\nSaved {len(results)} records to {args.output}")
    counts: dict[str, int] = {}
    for result in results:
        counts[result.decision] = counts.get(result.decision, 0) + 1
    for decision, count in sorted(counts.items()):
        print(f"  {decision}: {count}")
    if errors:
        print("\nSources with errors:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
