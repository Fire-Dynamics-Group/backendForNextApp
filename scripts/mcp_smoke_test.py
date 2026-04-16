"""
Smoke test the mounted MCP server using the official Python MCP client.
Run: python scripts/mcp_smoke_test.py  (backend must be up on :8001)
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8001/mcp/")
TOKEN = os.environ.get("MCP_BEARER_TOKEN")
FLOOR_ID = os.environ.get("MCP_TEST_FLOOR_ID")  # optional


async def main() -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with streamablehttp_client(URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"server: {init.serverInfo.name} v{init.serverInfo.version}")

            tools = await session.list_tools()
            print(f"\ntools ({len(tools.tools)}):")
            for t in tools.tools:
                d = (t.description or "").splitlines()[0] if t.description else ""
                print(f"  - {t.name}: {d}")

            def parse(result):
                """FastMCP splits list returns into one TextContent per item."""
                items = [json.loads(b.text) for b in result.content if getattr(b, "text", None)]
                return items if len(items) != 1 else items[0]

            print("\n=== list_projects ===")
            projects = parse(await session.call_tool("list_projects", {}))
            if isinstance(projects, dict):
                projects = [projects]
            print(f"got {len(projects)} projects; first = {projects[0]['name']}")

            floor_id = FLOOR_ID
            if not floor_id and projects:
                pid = projects[0]["id"]
                print(f"\n=== get_project({pid}) ===")
                pdata = parse(await session.call_tool("get_project", {"project_id": pid}))
                print(f"{len(pdata['floors'])} floors")
                if pdata["floors"]:
                    floor_id = pdata["floors"][0]["id"]

            if floor_id:
                print(f"\n=== get_floor({floor_id}) ===")
                fdata = parse(await session.call_tool("get_floor", {"floor_id": floor_id}))
                types = {}
                for e in fdata.get("elements", []):
                    types[e["type"]] = types.get(e["type"], 0) + 1
                print(f"{len(fdata.get('elements', []))} elements; types = {types}")


if __name__ == "__main__":
    if not TOKEN:
        print("MCP_BEARER_TOKEN env var required", file=sys.stderr)
        sys.exit(2)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"FAIL: {e!r}", file=sys.stderr)
        sys.exit(1)
