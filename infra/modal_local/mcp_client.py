"""A real stdio MCP client for launcher operations and acceptance checks."""

import json
import os
from contextlib import asynccontextmanager
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect():
    parameters = StdioServerParameters(
        command="/usr/local/bin/blender-mcp", env=dict(os.environ)
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=120)
        ) as session:
            await session.initialize()
            yield session


async def call(session, name, **arguments):
    arguments.setdefault("user_prompt", "Validate Blender sandbox tooling")
    result = await session.call_tool(name, arguments)
    text = "\n".join(item.text for item in result.content if item.type == "text")
    if result.isError or text.startswith(("Error", "Failed", "Rejected")):
        raise RuntimeError(f"{name}: {text}")
    return result, text


async def code(session, source):
    _, text = await call(
        session, "execute_blender_code", code="import render\n" + source
    )
    return text


async def evaluate(session, expression):
    text = await code(
        session,
        f"import render, json; print('ASTRA_RESULT=' + json.dumps({expression}))",
    )
    return json.loads(text.split("ASTRA_RESULT=", 1)[1].strip())
