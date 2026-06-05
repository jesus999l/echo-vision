#!/usr/bin/env python3
"""
web_search.py — Echo Web Search Module
Place in: ~/vision_assistant/web_search.py

Adds real-time web search to Echo's two-tier AI pipeline.
No API key required for the default DDG backend.

Backends (tried in order):
  1. DuckDuckGo Instant Answer API  — structured, fast, zero-config
  2. DuckDuckGo HTML scrape         — broader results, still zero-config
  3. SearXNG local instance         — full privacy, requires Docker (optional)

Query router automatically decides whether a query needs web search or
can be answered entirely from the local LLM, keeping latency low for
conversational turns that don't need current info.

Usage in Echo's AI pipeline:
    from web_search import WebSearch, needs_web_search

    searcher = WebSearch()                   # once at startup

    if needs_web_search(user_message):
        results = searcher.search(user_message)
        context = results.to_prompt_block()  # ready to inject into system prompt
    else:
        context = ""

Dependencies: requests (already in vision_env via Ollama/pip)
"""

import re
import time
import json
import logging
import hashlib
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus, urljoin

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

logger = logging.getLogger("echo.websearch")


# ============================================================================
# Constants
# ============================================================================

DDG_INSTANT_URL  = "https://api.duckduckgo.com/"
DDG_HTML_URL     = "https://html.duckduckgo.com/html/"
DEFAULT_SEARXNG  = "http://localhost:8081"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Words/patterns that signal a query needs current information
_FRESHNESS_PATTERNS = [
    r"\b(today|tonight|yesterday|this week|this month|this year)\b",
    r"\b(current|currently|right now|at the moment|latest|newest|recent)\b",
    r"\b(news|update|release|announce|happen(ed|ing)|break(ing)?)\b",
    r"\b(price|cost|stock|weather|score|result|winner|winner)\b",
    r"\b(who is|who('s| is) the|what is the (current|new|latest))\b",
    r"\b(when (is|was|did|does)|how (long|far|much|many) (is|are|does))\b",
    r"\b(still|anymore|yet|already)\b",
    r"\b(v\d+[\.\d]*|version \d|release \d)\b",       # version numbers
    r"\b(2024|2025|2026)\b",                           # explicit years near cutoff
]
_FRESHNESS_RE = re.compile("|".join(_FRESHNESS_PATTERNS), re.IGNORECASE)

# Patterns that almost never need web search (LLM handles fine)
_LOCAL_PATTERNS = [
    r"^(what is|explain|define|how do(es)? .* work|tell me about)\b",
    r"^(write|create|draft|generate|code|make me)\b",
    r"^(add|set|remind|schedule|log|track|start|stop|cancel)\b",
    r"^(how do i|how can i|what should i)\b",
]
_LOCAL_RE = re.compile("|".join(_LOCAL_PATTERNS), re.IGNORECASE)


# ============================================================================
# Search result types
# ============================================================================

class SearchResult:
    """Single search result."""

    def __init__(self, title: str, snippet: str, url: str = "",
                 source: str = "ddg"):
        self.title   = title.strip()
        self.snippet = snippet.strip()
        self.url     = url.strip()
        self.source  = source

    def __repr__(self):
        return f"<SearchResult {self.title[:40]!r}>"


class SearchResponse:
    """
    Collection of results from a single search.
    Call .to_prompt_block() to get a string ready to inject into an AI prompt.
    """

    def __init__(self, query: str, results: List[SearchResult],
                 instant_answer: str = "", elapsed_ms: int = 0,
                 backend: str = ""):
        self.query          = query
        self.results        = results
        self.instant_answer = instant_answer.strip()
        self.elapsed_ms     = elapsed_ms
        self.backend        = backend
        self.timestamp      = datetime.now()

    @property
    def has_results(self) -> bool:
        return bool(self.instant_answer or self.results)

    def to_prompt_block(self, max_results: int = 5,
                         max_snippet: int = 200) -> str:
        """
        Returns a formatted string for injection into an AI system prompt.
        Keeps it tight — the model doesn't need the full page, just enough
        to answer accurately.
        """
        if not self.has_results:
            return ""

        lines = [
            f"[Web search: {self.query!r} — {self.timestamp.strftime('%Y-%m-%d %H:%M')}]"
        ]

        if self.instant_answer:
            lines.append(f"Instant answer: {self.instant_answer}")

        for i, r in enumerate(self.results[:max_results], 1):
            snippet = r.snippet[:max_snippet]
            if r.url:
                lines.append(f"{i}. {r.title}\n   {snippet}\n   {r.url}")
            else:
                lines.append(f"{i}. {r.title}\n   {snippet}")

        return "\n".join(lines)

    def __repr__(self):
        return (f"<SearchResponse query={self.query!r} "
                f"results={len(self.results)} "
                f"instant={'yes' if self.instant_answer else 'no'} "
                f"backend={self.backend}>")


# ============================================================================
# Query router
# ============================================================================

def needs_web_search(query: str, threshold: float = 0.0) -> bool:
    """
    Heuristic: returns True if the query likely needs current web information.

    Rules (in order):
      1. Echo commands (add task, set timer…) → always False
      2. Creative/generative prompts → always False
      3. Freshness signal words/patterns → always True
      4. Short factual questions with no freshness signals → False
      5. Default → False (prefer LLM, avoid unnecessary latency)
    """
    q = query.strip()
    if not q or len(q) < 4:
        return False

    # Hard no — local commands
    if _LOCAL_RE.match(q):
        return False

    # Hard yes — freshness signal
    if _FRESHNESS_RE.search(q):
        return True

    # Questions with "who", "what", "where", "when" about proper nouns
    # e.g. "who won the f1 race" / "what happened to X"
    if re.search(r"\b(who|what|where|when)\b.{0,40}\b[A-Z][a-zA-Z]{2,}\b", q):
        return True

    return False


def search_query_clean(query: str) -> str:
    """Strip conversational filler before sending to search engine."""
    fillers = [
        r"^(hey echo[,\s]+|echo[,\s]+)",
        r"^(can you (look up|search|find|tell me)|please (search|find|look up))\s+",
        r"^(what('s| is) the (latest|current|news about))\s+",
        r"^(search (for|about))\s+",
    ]
    q = query.strip()
    for f in fillers:
        q = re.sub(f, "", q, flags=re.IGNORECASE).strip()
    return q


# ============================================================================
# HTTP session with retry
# ============================================================================

def _make_session(timeout: int = 8) -> "requests.Session":
    session = requests.Session()
    retry   = Retry(total=2, backoff_factor=0.3,
                    status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


# ============================================================================
# DuckDuckGo Instant Answer backend
# ============================================================================

def _ddg_instant(query: str, session: "requests.Session",
                 timeout: int = 6) -> SearchResponse:
    """
    DuckDuckGo Instant Answer API.
    Returns a structured answer and up to ~5 related results.
    No API key. Rate-limited by DDG (be reasonable — Echo caches).
    """
    t0 = time.monotonic()
    params = {
        "q":              query,
        "format":         "json",
        "no_html":        "1",
        "skip_disambig":  "1",
        "no_redirect":    "1",
    }
    try:
        r = session.get(DDG_INSTANT_URL, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.debug(f"DDG instant failed: {e}")
        return SearchResponse(query, [], backend="ddg_instant_fail")

    elapsed = int((time.monotonic() - t0) * 1000)

    # Instant answer text
    instant = (
        data.get("Answer")
        or data.get("AbstractText")
        or data.get("Definition")
        or ""
    )

    results: List[SearchResult] = []

    # RelatedTopics → results
    for topic in data.get("RelatedTopics", [])[:8]:
        if isinstance(topic, dict) and "Text" in topic:
            url  = topic.get("FirstURL", "")
            text = topic["Text"]
            # Text format is usually "Title - Snippet"
            if " - " in text:
                title, _, snippet = text.partition(" - ")
            else:
                title   = text[:60]
                snippet = text
            results.append(SearchResult(title, snippet, url, "ddg_instant"))

    # Results array (some queries return this directly)
    for item in data.get("Results", [])[:5]:
        if isinstance(item, dict):
            results.append(SearchResult(
                item.get("Text", "")[:80],
                item.get("Text", ""),
                item.get("FirstURL", ""),
                "ddg_instant",
            ))

    return SearchResponse(query, results, instant, elapsed, "ddg_instant")


# ============================================================================
# DuckDuckGo HTML scrape backend  (fallback for richer results)
# ============================================================================

def _ddg_html(query: str, session: "requests.Session",
              timeout: int = 8) -> SearchResponse:
    """
    Scrapes DDG's lite HTML results page.
    No JS required, no API key. Works when the JSON API returns nothing useful.
    """
    t0 = time.monotonic()
    try:
        r = session.post(
            DDG_HTML_URL,
            data={"q": query, "b": "", "kl": ""},
            timeout=timeout,
        )
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.debug(f"DDG HTML failed: {e}")
        return SearchResponse(query, [], backend="ddg_html_fail")

    elapsed = int((time.monotonic() - t0) * 1000)

    # Minimal HTML parser — no BeautifulSoup dependency
    results: List[SearchResult] = []

    # Result blocks look like:
    #   <a class="result__a" href="...">Title</a>
    #   <a class="result__snippet">Snippet</a>
    title_re   = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_re = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    titles   = title_re.findall(html)
    snippets = [m for m in snippet_re.findall(html)]

    def _clean(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s)
        s = s.replace("&amp;", "&").replace("&lt;", "<").replace(
            "&gt;", ">").replace("&quot;", '"').replace("&#x27;", "'")
        return re.sub(r"\s+", " ", s).strip()

    for i, (url, raw_title) in enumerate(titles[:8]):
        title   = _clean(raw_title)
        snippet = _clean(snippets[i]) if i < len(snippets) else ""
        if title and snippet:
            results.append(SearchResult(title, snippet, url, "ddg_html"))

    return SearchResponse(query, results, "", elapsed, "ddg_html")


# ============================================================================
# SearXNG backend  (local self-hosted, optional)
# ============================================================================

def _searxng(query: str, session: "requests.Session",
             base_url: str = DEFAULT_SEARXNG, timeout: int = 6) -> SearchResponse:
    """
    Queries a local SearXNG instance.
    Run SearXNG with:
      docker run -d -p 8888:8080 --name searxng searxng/searxng
    Then set searxng_url in websearch_config.json.
    """
    t0 = time.monotonic()
    try:
        r = session.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "categories": "general"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.debug(f"SearXNG failed: {e}")
        return SearchResponse(query, [], backend="searxng_fail")

    elapsed = int((time.monotonic() - t0) * 1000)
    results: List[SearchResult] = []

    for item in data.get("results", [])[:8]:
        results.append(SearchResult(
            item.get("title", ""),
            item.get("content", ""),
            item.get("url", ""),
            "searxng",
        ))

    return SearchResponse(query, results, "", elapsed, "searxng")


# ============================================================================
# Simple LRU-ish cache
# ============================================================================

class _SearchCache:
    """
    Thread-safe in-memory cache. Results expire after `ttl` seconds.
    Keeps Echo from hammering DDG on repeated queries within a session.
    """

    def __init__(self, max_size: int = 64, ttl: int = 300):
        self._store: Dict[str, tuple] = {}   # key → (response, expires_at)
        self._lock  = threading.Lock()
        self._max   = max_size
        self._ttl   = ttl

    def _key(self, query: str) -> str:
        return hashlib.md5(query.lower().strip().encode()).hexdigest()

    def get(self, query: str) -> Optional[SearchResponse]:
        k = self._key(query)
        with self._lock:
            entry = self._store.get(k)
        if entry and time.monotonic() < entry[1]:
            return entry[0]
        return None

    def set(self, query: str, response: SearchResponse):
        k = self._key(query)
        expires = time.monotonic() + self._ttl
        with self._lock:
            if len(self._store) >= self._max:
                # Evict oldest
                oldest = min(self._store, key=lambda x: self._store[x][1])
                del self._store[oldest]
            self._store[k] = (response, expires)

    def clear(self):
        with self._lock:
            self._store.clear()


# ============================================================================
# Main WebSearch class
# ============================================================================

class WebSearch:
    """
    Echo's web search interface.

    Initialise once at Echo startup:
        searcher = WebSearch(config_path="websearch_config.json")

    Then call from the AI pipeline:
        if needs_web_search(user_message):
            result = searcher.search(user_message)
            context_block = result.to_prompt_block()

    Backends tried in order:
        ddg_instant → ddg_html → searxng (if configured)
    """

    def __init__(self, config_path: str = "websearch_config.json"):
        self.config     = _load_ws_config(config_path)
        self._session   = _make_session() if REQUESTS_OK else None
        self._cache     = _SearchCache(
            max_size = self.config.get("cache_max_size", 64),
            ttl      = self.config.get("cache_ttl_seconds", 300),
        )
        self._lock      = threading.Lock()
        self._last_call = 0.0
        self._min_gap   = self.config.get("rate_limit_seconds", 1.5)

        if not REQUESTS_OK:
            logger.error("requests not installed — web search disabled. "
                         "pip install requests --break-system-packages")

    # ------------------------------------------------------------------
    def search(self, query: str,
               force_backend: str = "") -> SearchResponse:
        """
        Main search entry point. Cleans the query, checks cache,
        tries backends in order, caches and returns the result.
        """
        if not REQUESTS_OK:
            return SearchResponse(query, [], backend="no_requests")

        clean_q = search_query_clean(query)

        # Cache hit
        cached = self._cache.get(clean_q)
        if cached:
            logger.debug(f"Search cache hit: {clean_q!r}")
            return cached

        # Rate limit
        self._rate_limit()

        backends_order = self._backends_order(force_backend)
        timeout = self.config.get("timeout_seconds", 7)

        response = SearchResponse(clean_q, [], backend="none")

        for backend in backends_order:
            try:
                if backend == "ddg_instant":
                    response = _ddg_instant(clean_q, self._session, timeout)
                elif backend == "ddg_html":
                    response = _ddg_html(clean_q, self._session, timeout)
                elif backend == "searxng":
                    url = self.config.get("searxng_url", DEFAULT_SEARXNG)
                    response = _searxng(clean_q, self._session, url, timeout)

                if response.has_results:
                    logger.info(
                        f"Search [{backend}] {clean_q!r} → "
                        f"{len(response.results)} results "
                        f"({response.elapsed_ms}ms)"
                    )
                    break
                else:
                    logger.debug(f"Backend {backend} returned no results, trying next.")
            except Exception as e:
                logger.warning(f"Backend {backend} error: {e}")
                continue

        if response.has_results:
            self._cache.set(clean_q, response)

        return response

    # ------------------------------------------------------------------
    def search_for_briefing(self, topics: List[str]) -> Dict[str, SearchResponse]:
        """
        Fetch results for multiple topics (used in morning briefing).
        Returns dict of topic → SearchResponse.
        """
        results = {}
        for topic in topics:
            results[topic] = self.search(topic)
            time.sleep(self._min_gap)   # polite pacing
        return results

    # ------------------------------------------------------------------
    def _rate_limit(self):
        with self._lock:
            since = time.monotonic() - self._last_call
            if since < self._min_gap:
                time.sleep(self._min_gap - since)
            self._last_call = time.monotonic()

    def _backends_order(self, force: str = "") -> List[str]:
        if force and force in ("ddg_instant", "ddg_html", "searxng"):
            return [force]
        order = list(self.config.get("backend_order",
                                     ["ddg_instant", "ddg_html"]))
        searxng_url = self.config.get("searxng_url", "")
        if searxng_url and "searxng" not in order:
            order.append("searxng")
        return order

    def clear_cache(self):
        self._cache.clear()

    @property
    def ready(self) -> bool:
        return REQUESTS_OK and self._session is not None


# ============================================================================
# Config
# ============================================================================

_WS_DEFAULTS: Dict[str, Any] = {
    "backend_order":       ["ddg_instant", "ddg_html"],
    "searxng_url":         "",
    "timeout_seconds":     7,
    "rate_limit_seconds":  1.5,
    "cache_max_size":      64,
    "cache_ttl_seconds":   300,
    "max_results_in_prompt": 5,
    "auto_search_in_pipeline": True,
}


def _load_ws_config(path: str) -> Dict[str, Any]:
    import os
    fp = path if os.path.isabs(path) else os.path.join(
        os.path.dirname(__file__) or ".", path
    )
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                return {**_WS_DEFAULTS, **json.load(f)}
        except Exception as e:
            logger.warning(f"Could not load {fp}: {e}")
    return dict(_WS_DEFAULTS)


# ============================================================================
# Convenience wrapper — the single function Echo's AI pipeline calls
# ============================================================================

_global_searcher: Optional[WebSearch] = None
_global_lock = threading.Lock()


def get_searcher(config_path: str = "websearch_config.json") -> WebSearch:
    """Return the module-level singleton WebSearch instance."""
    global _global_searcher
    if _global_searcher is None:
        with _global_lock:
            if _global_searcher is None:
                _global_searcher = WebSearch(config_path)
    return _global_searcher


def search_if_needed(query: str,
                     config_path: str = "websearch_config.json") -> str:
    """
    One-liner for Echo's AI pipeline.
    Returns a prompt-ready string or "" if search not needed / no results.

        context = search_if_needed(user_message)
        system  = base_prompt + ("\\n\\n" + context if context else "")
    """
    if not needs_web_search(query):
        return ""
    searcher = get_searcher(config_path)
    response = searcher.search(query)
    return response.to_prompt_block()


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-22s  %(levelname)s  %(message)s",
    )

    test_queries = [
        "what is the capital of France",              # should NOT search (stable fact)
        "latest news in AI today",                    # SHOULD search
        "add a task to clean the kitchen",            # should NOT search (echo command)
        "what is the current price of Bitcoin",       # SHOULD search
        "who won the NBA finals this year",           # SHOULD search
        "explain how transformers work",              # should NOT search
    ]

    print("=== Query router ===")
    for q in test_queries:
        flag = needs_web_search(q)
        print(f"  {'SEARCH' if flag else 'local ':6}  {q}")

    print("\n=== Live search (2 queries) ===")
    searcher = WebSearch()
    for q in ["latest AI news today", "current weather in San Antonio Texas"]:
        print(f"\nQuery: {q!r}")
        r = searcher.search(q)
        print(r.to_prompt_block(max_results=3) or "  (no results)")

    print("\nDone.")
