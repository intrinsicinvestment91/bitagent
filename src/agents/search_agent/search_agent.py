import os
import logging
import httpx

logger = logging.getLogger(__name__)


async def _search_brave(query: str, count: int) -> list[dict]:
    api_key = os.getenv("BRAVE_API_KEY")
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": query, "count": min(count, 20)}
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })
        return results


async def _search_searxng(query: str, count: int) -> list[dict]:
    base_url = os.getenv("SEARXNG_URL", "").rstrip("/")
    params = {"q": query, "format": "json", "language": "en"}
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(f"{base_url}/search", params=params)
        r.raise_for_status()
        data = r.json()
        results = []
        for item in data.get("results", [])[:count]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            })
        return results


async def _search_duckduckgo(query: str, count: int) -> list[dict]:
    import asyncio
    from ddgs import DDGS

    def _run():
        return list(DDGS().text(query, max_results=count))

    raw = await asyncio.get_event_loop().run_in_executor(None, _run)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in raw
    ]


async def search(query: str, num_results: int = 10) -> dict:
    num_results = max(1, min(num_results, 20))

    backend = "duckduckgo"
    try:
        if os.getenv("BRAVE_API_KEY"):
            backend = "brave"
            results = await _search_brave(query, num_results)
        elif os.getenv("SEARXNG_URL"):
            backend = "searxng"
            results = await _search_searxng(query, num_results)
        else:
            results = await _search_duckduckgo(query, num_results)
    except Exception as e:
        logger.warning(f"{backend} search failed: {e}, falling back to DuckDuckGo")
        try:
            backend = "duckduckgo"
            results = await _search_duckduckgo(query, num_results)
        except Exception as e2:
            return {"error": f"All search backends failed: {e2}"}

    return {
        "query": query,
        "results": results,
        "result_count": len(results),
        "backend": backend,
    }


class SearchAgent:
    name = "SearchAgent"
    description = "Web search. Returns titles, URLs, and snippets."
    price_sats = 10

    def get_info(self) -> dict:
        backend = "duckduckgo"
        if os.getenv("BRAVE_API_KEY"):
            backend = "brave"
        elif os.getenv("SEARXNG_URL"):
            backend = "searxng"
        return {
            "name": self.name,
            "description": self.description,
            "price_sats": self.price_sats,
            "active_backend": backend,
            "max_results": 20,
        }

    async def search(self, query: str, num_results: int = 10) -> dict:
        return await search(query, num_results)
