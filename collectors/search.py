"""Build server-rendered GET searches without an AI request per keyword."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def search_urls(source):
    search = source.get("search", {})
    endpoint = search.get("url", "")
    parts = urlsplit(endpoint)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise ValueError("search.url must be an absolute HTTP(S) URL")
    parameter = search.get("query_parameter")
    keywords = search.get("keywords")
    if not isinstance(parameter, str) or not parameter.strip():
        raise ValueError("search.query_parameter is required")
    if not isinstance(keywords, list) or any(
        not isinstance(word, str) or not word.strip() for word in keywords
    ):
        raise ValueError("search.keywords must be a list of nonempty search phrases; use [] for no keyword filter")
    filters = search.get("parameters", {})
    if not isinstance(filters, dict):
        raise ValueError("search.parameters must be an object")
    pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k != parameter and k not in filters]
    pairs += [(k, item) for k, value in filters.items() if k != parameter
              for item in (value if isinstance(value, list) else [value])]
    if not keywords:
        return [urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))]
    return list(dict.fromkeys(
        urlunsplit((parts.scheme, parts.netloc, parts.path,
                    urlencode(pairs + [(parameter, word.strip())]), ""))
        for word in keywords
    ))
