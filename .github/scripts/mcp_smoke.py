"""Launch an MCP server package over stdio, as a client would, and list its tools.

Usage (from the package directory, inside its environment):
    python ../../.github/scripts/mcp_smoke.py

The command is the package's first ``[project.scripts]`` entry, so this works
for any server in mcp-servers/ without per-package configuration. It catches
what unit tests miss: a server that cannot start (e.g. an SDK API removed in a
new major version).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def console_script(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8")
    section = re.search(r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not section:
        sys.exit(f"{pyproject}: no [project.scripts] entry to launch")
    m = re.search(r'^\s*"?([A-Za-z0-9_.-]+)"?\s*=', section.group(1), re.M)
    if not m:
        sys.exit(f"{pyproject}: empty [project.scripts]")
    return m.group(1)


async def main() -> None:
    name = console_script(Path("pyproject.toml"))
    exe = shutil.which(name, path=str(Path(sys.executable).parent)) or shutil.which(name)
    if not exe:
        sys.exit(f"console script {name!r} is not installed in this environment")
    params = StdioServerParameters(command=exe, args=[], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=60)
            tools = (await session.list_tools()).tools
    if not tools:
        sys.exit(f"{name}: server started but exposes no tools")
    print(f"{name}: {len(tools)} tools: {', '.join(sorted(t.name for t in tools))}")


if __name__ == "__main__":
    asyncio.run(main())
