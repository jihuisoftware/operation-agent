"""Backend root handshake for Desktop clients; no browser application is served."""

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse


def mount_backend_root(application: FastAPI) -> None:
    """Retain the legacy Desktop bootstrap without exposing a token on gated listeners.

    Current local clients use private control tickets. Older remote Desktop clients
    still read the standalone backend token from the root response.
    """
    @application.get("/")
    async def backend_root():
        from hermes_cli.web_deps import _server

        server = _server()
        gated = bool(getattr(application.state, "auth_required", False))
        withheld = gated or bool(getattr(server.app.state, "withhold_session_token", False))
        headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
        if withheld:
            return JSONResponse({"service": "Hermes Desktop backend"}, headers=headers)
        return HTMLResponse(
            "<!doctype html><html><head><script>"
            f"window.__HERMES_SESSION_TOKEN__={json.dumps(server._SESSION_TOKEN)};"
            "window.__HERMES_AUTH_REQUIRED__=false;"
            "</script></head><body>Hermes Desktop backend</body></html>",
            headers=headers,
        )
