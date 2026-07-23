"""Production entry point for Syggramma API server.

On Windows, psycopg requires SelectorEventLoop.  This must be set
before any other imports that might create event loops.
"""

import asyncio
import selectors
import sys

# Windows: force SelectorEventLoop before anything else
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "syggramma.api:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info",
    )
