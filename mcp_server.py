#!/usr/bin/env python3
"""
BitAgent MCP Server
Exposes BitAgent agents as tools for Claude and any MCP-compatible client.
Runs locally as a stdio server — import the agent modules directly,
no HTTP round-trip, no payment gate (cost is reported in each result).
"""

import asyncio
import json
import logging
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

logging.basicConfig(level=logging.WARNING)

server = Server("bitagent", version="1.0.0", instructions=(
    "BitAgent tools give you access to live web search, web page fetching, "
    "real-time crypto prices, and text translation. "
    "Each tool reports its cost in sats so you can track spending."
))


# ── Tool definitions ─────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="translate",
            description=(
                "Translate text into another language. "
                "Supports 100+ languages. Cost: 100 sats."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to translate",
                    },
                    "target_lang": {
                        "type": "string",
                        "description": "Target language code (e.g. 'es', 'fr', 'de', 'zh')",
                    },
                    "source_lang": {
                        "type": "string",
                        "description": "Source language code, defaults to 'auto'",
                        "default": "auto",
                    },
                },
                "required": ["text", "target_lang"],
            },
        ),
        types.Tool(
            name="search",
            description=(
                "Search the web and return titles, URLs, and snippets. "
                "Cost: 10 sats."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (1-20, default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="fetch_url",
            description=(
                "Fetch a public web page and return its clean text content. "
                "Does not work on private/internal URLs. Cost: 25 sats."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch (must be public https:// or http://)",
                    },
                },
                "required": ["url"],
            },
        ),
        types.Tool(
            name="get_price",
            description=(
                "Get the current USD price of a cryptocurrency. "
                "Supported: bitcoin, ethereum, litecoin, dogecoin, monero. "
                "Cost: 2 sats."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "coin": {
                        "type": "string",
                        "description": "Coin name (e.g. 'bitcoin', 'ethereum')",
                        "default": "bitcoin",
                    },
                },
                "required": ["coin"],
            },
        ),
        types.Tool(
            name="convert_sats",
            description=(
                "Convert a satoshi amount to USD using the live BTC price. "
                "Cost: 1 sat."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sats": {
                        "type": "integer",
                        "description": "Number of satoshis to convert",
                    },
                },
                "required": ["sats"],
            },
        ),
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "translate":
        from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent
        agent = PolyglotAgent()
        result = await agent.handle_translation(
            text=arguments["text"],
            source_lang=arguments.get("source_lang", "auto"),
            target_lang=arguments["target_lang"],
        )
        result["cost_sats"] = 100
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    if name == "search":
        from src.agents.search_agent.search_agent import search
        result = await search(
            query=arguments["query"],
            num_results=arguments.get("num_results", 5),
        )
        result["cost_sats"] = 10
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    if name == "fetch_url":
        from src.agents.web_fetch_agent.web_fetch import fetch_url
        result = await fetch_url(arguments["url"])
        result["cost_sats"] = 25
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    if name == "get_price":
        from src.agents.price_oracle_agent.price_oracle import get_prices
        coin = arguments.get("coin", "bitcoin").lower()
        prices = await get_prices([coin])
        result = {"coin": coin, **prices.get(coin, {"error": "Not found"}), "cost_sats": 2}
        return [types.TextContent(type="text", text=json.dumps(result))]

    if name == "convert_sats":
        from src.agents.price_oracle_agent.price_oracle import sats_to_usd
        result = await sats_to_usd(arguments["sats"])
        result["cost_sats"] = 1
        return [types.TextContent(type="text", text=json.dumps(result))]

    return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
