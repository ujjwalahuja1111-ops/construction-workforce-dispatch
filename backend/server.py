"""
FastAPI reverse proxy — this file exists only because Emergent's supervisor
hardcodes `uvicorn server:app` on port 8001. It:

  1. Spawns the real Node/Express dispatch backend (port 8002) as a child
     subprocess on startup and keeps it alive.
  2. Forwards every /api/* request to that backend.

In a proper local deployment (VS Code, docker-compose, etc.), you do NOT
need this file — you run the Node backend directly (`cd backend && npm run dev`)
and point the client at http://localhost:8002.

Keep this thin. No business logic here.
"""
import os
import signal
import subprocess
import sys
import atexit
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

NODE_BACKEND_DIR = Path("/app/dispatch-platform/backend")
NODE_BACKEND_URL = os.environ.get("NODE_BACKEND_URL", "http://localhost:8002")
TIMEOUT = float(os.environ.get("PROXY_TIMEOUT_SECONDS", "30"))

app = FastAPI(title="dispatch-proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = httpx.AsyncClient(timeout=TIMEOUT)
_node_proc: subprocess.Popen | None = None


def _start_node_backend() -> None:
    global _node_proc
    if _node_proc and _node_proc.poll() is None:
        return
    log = open("/var/log/supervisor/dispatch-backend.log", "ab", buffering=0)
    _node_proc = subprocess.Popen(
        ["/usr/bin/npx", "tsx", "watch", "src/server.ts"],
        cwd=str(NODE_BACKEND_DIR),
        stdout=log,
        stderr=log,
        preexec_fn=os.setsid,
        env={**os.environ, "NODE_ENV": "development"},
    )
    print(
        f"[dispatch-proxy] spawned node backend pid={_node_proc.pid} "
        f"cwd={NODE_BACKEND_DIR}"
    )


def _stop_node_backend() -> None:
    global _node_proc
    if _node_proc and _node_proc.poll() is None:
        try:
            os.killpg(os.getpgid(_node_proc.pid), signal.SIGTERM)
        except Exception:
            pass
    _node_proc = None


@app.on_event("startup")
async def _startup():
    _start_node_backend()


@app.on_event("shutdown")
async def _shutdown():
    await _client.aclose()
    _stop_node_backend()


atexit.register(_stop_node_backend)


@app.get("/")
async def root():
    alive = _node_proc is not None and _node_proc.poll() is None
    return {
        "service": "dispatch-proxy",
        "forwards_to": NODE_BACKEND_URL,
        "node_backend_alive": alive,
        "node_pid": _node_proc.pid if _node_proc else None,
        "note": "Real backend is /app/dispatch-platform/backend (Node/Express).",
    }


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy(path: str, request: Request):
    # Auto-restart node if it died
    if _node_proc is None or _node_proc.poll() is not None:
        _start_node_backend()

    url = f"{NODE_BACKEND_URL}/api/{path}"
    body = await request.body()

    fwd_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP and k.lower() != "host"
    }

    try:
        upstream = await _client.request(
            method=request.method,
            url=url,
            content=body,
            params=dict(request.query_params),
            headers=fwd_headers,
        )
    except httpx.ConnectError:
        return Response(
            content=b'{"error":{"code":"BACKEND_DOWN","message":"Node backend unreachable on port 8002 (starting up?)"}}',
            status_code=502,
            media_type="application/json",
        )
    except httpx.ReadTimeout:
        return Response(
            content=b'{"error":{"code":"UPSTREAM_TIMEOUT","message":"Node backend timed out"}}',
            status_code=504,
            media_type="application/json",
        )

    resp_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )
