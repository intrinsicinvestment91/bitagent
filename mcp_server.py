#!/usr/bin/env python3
"""BitAgent MCP server.

Exposes BitAgent's agents as tools for Claude and any MCP-compatible client.
Runs as a local stdio server and imports the agent modules directly — no HTTP
round-trip and no payment gate, since the caller is the node's own operator.
Each result still carries ``cost_sats`` so spending is visible, read from the
same catalog the paid HTTP routes use.

Written against the mcp 2.x decorator API. The previous version used
``mcp.server.Server`` with ``@server.list_tools()``, which no longer exists —
the module raised AttributeError on import against any current release.
"""

import asyncio
import logging
import os
import sys
from typing import Any

# Allow imports from the project root when run by path (e.g. from .mcp.json).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import MCPServer  # noqa: E402

from src.payments import price_of  # noqa: E402

logging.basicConfig(level=logging.WARNING)

server = MCPServer(
    "bitagent",
    version="1.0.0",
    instructions=(
        "BitAgent tools give you access to live web search, web page fetching, "
        "real-time crypto prices, and text translation. "
        "Each tool reports its cost in sats so you can track spending."
    ),
)


def _priced(service_id: str, result: dict[str, Any]) -> dict[str, Any]:
    result["cost_sats"] = price_of(service_id)
    return result


@server.tool()
async def translate(text: str, target_lang: str, source_lang: str = "auto") -> dict[str, Any]:
    """Translate text into another language. Supports 100+ languages.

    Args:
        text: The text to translate.
        target_lang: Target language code, e.g. "es", "fr", "ja".
        source_lang: Source language code, or "auto" to detect.
    """
    from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent

    result = await PolyglotAgent().handle_translation(
        text=text, source_lang=source_lang, target_lang=target_lang
    )
    return _priced("polyglot.translate", result)


@server.tool()
async def search(query: str, num_results: int = 5) -> dict[str, Any]:
    """Search the web and return titles, URLs, and snippets.

    Args:
        query: The search query.
        num_results: How many results to return (1-20).
    """
    from src.agents.search_agent.search_agent import search as run_search

    result = await run_search(query=query, num_results=min(max(num_results, 1), 20))
    return _priced("search.query", result)


@server.tool()
async def fetch_url(url: str) -> dict[str, Any]:
    """Fetch a public web page and return its cleaned text content.

    Private and internal addresses are refused.

    Args:
        url: The absolute http(s) URL to fetch.
    """
    from src.agents.web_fetch_agent.web_fetch import fetch_url as run_fetch

    result = await run_fetch(url)
    return _priced("fetch.url", result)


@server.tool()
async def get_price(coin: str = "bitcoin") -> dict[str, Any]:
    """Get the current USD price of a cryptocurrency.

    Args:
        coin: Coin id, e.g. "bitcoin", "ethereum", "litecoin".
    """
    from src.agents.price_oracle_agent.price_oracle import get_prices

    coin = coin.lower()
    prices = await get_prices([coin])
    return _priced("oracle.price", {"coin": coin, **prices.get(coin, {"error": "Not found"})})


@server.tool()
async def convert_sats(sats: int) -> dict[str, Any]:
    """Convert a satoshi amount to USD using the live BTC price.

    Args:
        sats: The number of satoshis to convert.
    """
    from src.agents.price_oracle_agent.price_oracle import sats_to_usd

    result = await sats_to_usd(sats)
    return _priced("oracle.convert", result)


async def main() -> None:
    await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
