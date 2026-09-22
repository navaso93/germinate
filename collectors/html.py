"""Collector for ordinary server-rendered HTML pages."""
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen

@dataclass
class Link:
    title: str
    url: str

class Parser(HTMLParser):
    def __init__(self, base_url: str, text_only: bool = False):
        super().__init__(convert_charrefs=True); self.base_url=base_url; self.text_only=text_only
        self.links=[]; self.text=[]; self._href=None; self._anchor=[]; self._ignored=0
    def handle_starttag(self, tag, attrs):
        if tag in {"script","style","noscript","svg"}: self._ignored += 1
        elif tag=="a" and not self._ignored: self._href=dict(attrs).get("href"); self._anchor=[]
    def handle_data(self, data):
        if not self._ignored and data.strip():
            self.text.append(data.strip())
            if self._href: self._anchor.append(data)
    def handle_endtag(self, tag):
        if tag in {"script","style","noscript","svg"} and self._ignored: self._ignored -= 1
        elif tag=="a" and self._href:
            title, href=" ".join(" ".join(self._anchor).split()), self._href.strip()
            if title and href and not href.startswith(("#","mailto:","javascript:")): self.links.append(Link(title,urljoin(self.base_url,href)))
            self._href=None; self._anchor=[]

def fetch_html(url: str, timeout: int = 25) -> str:
    request=Request(url,headers={"User-Agent":"GerminateGrantMonitor/0.2","Accept":"text/html,application/xhtml+xml"})
    with urlopen(request,timeout=timeout) as response:
        if response.headers.get_content_type() not in {"text/html","application/xhtml+xml"}: raise ValueError("unsupported content type")
        return response.read().decode(response.headers.get_content_charset() or "utf-8",errors="replace")

def extract_links(html: str, base_url: str) -> list[Link]:
    parser=Parser(base_url); parser.feed(html)
    return list({link.url:link for link in parser.links}.values())

def extract_text(html: str) -> str:
    parser=Parser(""); parser.feed(html); return "\n".join(parser.text)

class ScopedParser(Parser):
    """Extract links only inside a configured search-results container."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, base_url, container_class):
        super().__init__(base_url)
        self.container_class = container_class
        self.scope_depth = 0
        self.matched = False

    def handle_starttag(self, tag, attrs):
        if not self.scope_depth:
            if self.container_class not in dict(attrs).get('class', '').split():
                return
            self.matched = True
            self.scope_depth = 1
        elif tag not in self.VOID:
            self.scope_depth += 1
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.scope_depth:
            super().handle_endtag(tag)
            if tag not in self.VOID:
                self.scope_depth -= 1

    def handle_data(self, data):
        if self.scope_depth:
            super().handle_data(data)


def extract_search_links(html, base_url, container_class):
    parser = ScopedParser(base_url, container_class)
    parser.feed(html)
    if not parser.matched:
        raise ValueError(f'Search result container not found: {container_class}')
    return list({link.url: link for link in parser.links}.values())
