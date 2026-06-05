import requests, logging
from datetime import datetime
logger = logging.getLogger("echo.search")
SEARXNG_URL = "http://localhost:8081/search"

def web_search(query, max_results=4):
    try:
        resp = requests.get(SEARXNG_URL, params={"q": query, "format": "json", "engines": "google,bing,duckduckgo", "language": "en"}, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        results = [{"title": r.get("title","").strip(), "url": r.get("url",""), "snippet": r.get("content","").strip()} for r in data.get("results",[])[:max_results]]
        return {"ok": True, "query": query, "results": results}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "SearXNG offline", "query": query}
    except Exception as e:
        return {"ok": False, "error": str(e), "query": query}

def format_results_for_prompt(d):
    if not d.get("ok"): return f"[Search unavailable: {d.get('error')}]"
    if not d["results"]: return f"[No results for: {d['query']}]"
    lines = [f'[Web search: "{d["query"]}"]']
    for i, r in enumerate(d["results"], 1):
        lines.append(f"\n{i}. {r['title']}\n   {r['url']}\n   {r['snippet'][:300]}")
    return "\n".join(lines)

SEARCH_TRIGGERS = ["latest","current","today","this week","recent","news","update","2025","2026","search","look up","find","what is","who is","where is","how much","price of"]
NO_SEARCH = ["remind me","set a timer","add task","journal","habit","calendar","note","open","play","write","summarize"]

def should_search(text):
    t = text.lower()
    if any(p in t for p in NO_SEARCH): return False
    return any(p in t for p in SEARCH_TRIGGERS)

def get_search_context(user_input):
    if not should_search(user_input): return None
    return format_results_for_prompt(web_search(user_input))

if __name__ == "__main__":
    print("Testing SearXNG...\n")
    r = web_search("open source AI 2026")
    print(format_results_for_prompt(r) if r["ok"] else f"FAIL: {r['error']}")
