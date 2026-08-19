import json
import threading
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class WikipediaResult:
    title: str
    extract: str
    url: str


class WikipediaService:
    """Consulta Wikipedia en espanol con cache y limites de red razonables."""

    def __init__(self, language="es", timeout=6, cache_ttl=900):
        self.base_url = f"https://{language}.wikipedia.org"
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_lock = threading.Lock()

    def answer(self, query):
        search_term = self._normalize(query)
        if not search_term:
            raise ValueError("La busqueda de Wikipedia no puede estar vacia.")

        cached = self._get_cached(search_term)
        if cached is not None:
            return self._format(cached, cached=True)

        title = self._search_title(search_term)
        if title is None:
            return "No encontre una entrada relacionada en Wikipedia."

        result = self._get_summary(title)
        self._set_cached(search_term, result)
        return self._format(result)

    @staticmethod
    def _normalize(query):
        return " ".join(str(query).strip().split())[:180]

    def _search_title(self, query):
        params = urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 1,
            "format": "json",
            "utf8": 1,
        })
        data = self._get_json(f"{self.base_url}/w/api.php?{params}")
        results = data.get("query", {}).get("search", [])
        return results[0].get("title") if results else None

    def _get_summary(self, title):
        path = quote(title.replace(" ", "_"), safe="()_-")
        data = self._get_json(f"{self.base_url}/api/rest_v1/page/summary/{path}")
        extract = data.get("extract", "").strip()
        if not extract:
            raise RuntimeError("La entrada de Wikipedia no tiene un resumen disponible.")
        return WikipediaResult(
            title=data.get("title", title),
            extract=extract,
            url=data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        )

    def _get_json(self, url):
        request = Request(url, headers={"User-Agent": "AW1-BIOS/1.0"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError("Wikipedia no esta disponible en este momento.") from error

    def _get_cached(self, key):
        with self._cache_lock:
            item = self._cache.get(key)
            if item and time.monotonic() - item[0] < self.cache_ttl:
                return item[1]
            self._cache.pop(key, None)
        return None

    def _set_cached(self, key, value):
        with self._cache_lock:
            self._cache[key] = (time.monotonic(), value)

    @staticmethod
    def _format(result, cached=False):
        suffix = " (cache local)" if cached else ""
        source = f"\nFuente: {result.url}" if result.url else ""
        return f"{result.title}{suffix}\n\n{result.extract}{source}"
