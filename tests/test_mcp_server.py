"""MCP server registration.

The module previously used ``mcp.server.Server`` with ``@server.list_tools()``,
an API that no longer exists — importing it raised AttributeError against any
current release of the library, so the MCP integration was silently dead. This
test fails if that happens again.
"""

import mcp_server
from src.payments import price_of

EXPECTED_TOOLS = {"translate", "search", "fetch_url", "get_price", "convert_sats"}


async def test_all_tools_are_registered():
    tools = await mcp_server.server.list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


async def test_every_tool_documents_itself():
    for tool in await mcp_server.server.list_tools():
        assert tool.description, f"{tool.name} has no description"
        assert tool.input_schema.get("properties"), f"{tool.name} has no input schema"


def test_costs_come_from_the_catalog():
    """Prices were hardcoded here as a fourth source of truth."""
    assert mcp_server._priced("search.query", {})["cost_sats"] == price_of("search.query")
    assert mcp_server._priced("fetch.url", {})["cost_sats"] == price_of("fetch.url")
