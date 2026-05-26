"""
FastMCP server for Policy Atlas.

Exposes a configured `mcp` FastMCP instance and two transport runners
(`run_stdio`, `run_sse`). Designed for REPL-friendly debugging:

    # Interactive: inspect the server, then launch when ready
    $ uv run python -i -m app.mcp.server
    >>> mcp.list_tools()           # see registered tools
    >>> run_stdio()                # blocks; Ctrl-C to exit

    # Or from another module / script:
    from app.mcp.server import mcp, run_sse
    run_sse(port=8001)

Tools register against `mcp` via @mcp.tool() decorators (see app/mcp/tools.py).
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


mcp = FastMCP(
    name="policy-atlas",
    instructions=(
        "Policy Atlas exposes search and synthesis tools for policy "
        "research. Use suggest_pico_options to frame a question, then "
        "search_evidence to find papers."
    ),
)


# ---------------------------------------------------------------------------
# API-key auth (SSE only)
# ---------------------------------------------------------------------------

API_KEY_HEADER = "x-mcp-api-key"


async def _require_api_key(request: Request) -> JSONResponse | None:
    """Reject SSE requests that don't present a valid API key.

    Returns a 401 JSONResponse on failure, or None to allow through.
    Stdio bypasses this entirely (local-trusted).
    """
    expected = settings.MCP_API_KEY
    if not expected:
        return JSONResponse(
            {"error": "MCP_API_KEY not configured on server"},
            status_code=503,
        )
    provided = request.headers.get(API_KEY_HEADER)
    if provided != expected:
        return JSONResponse(
            {"error": "invalid or missing api key"},
            status_code=401,
        )
    return None


# ---------------------------------------------------------------------------
# Transport runners
# ---------------------------------------------------------------------------


def run_stdio() -> None:
    """Launch the server on stdio (Claude Desktop, mcp-inspector).

    Routes logs to stderr — stdio uses stdout for the JSON-RPC protocol,
    so any log line on stdout would corrupt the message stream.
    """
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    logger.info("Starting MCP server on stdio")
    mcp.run(transport="stdio")


def run_sse(port: int = 8001, host: str = "0.0.0.0") -> None:
    """Launch the server on SSE (remote / production).

    Fails fast if MCP_API_KEY is not set, and rejects requests that don't
    present a matching x-mcp-api-key header.
    """
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    if not settings.MCP_API_KEY:
        raise RuntimeError("MCP_API_KEY must be set when running SSE transport")

    sse_app = mcp.sse_app()

    @sse_app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        rejection = await _require_api_key(request)
        if rejection is not None:
            return rejection
        return await call_next(request)

    import uvicorn

    logger.info("Starting MCP server on SSE %s:%d", host, port)
    uvicorn.run(sse_app, host=host, port=port)


# Import-for-side-effect: loading this module triggers @mcp.tool() decorators
# in tools.py, registering them on the `mcp` instance. Must come *after* the
# `mcp` instance is created above — otherwise tools.py can't import it.
from app.mcp import tools as _tools  # noqa: E402, F401
