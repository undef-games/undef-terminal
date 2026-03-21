from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Import handler base classes directly from workers — these MUST resolve to the
# real CF runtime classes (not stubs) so Cloudflare's Pyodide validation phase
# detects Default/SessionRuntime as registered event handlers.
_DurableObject: type = object  # type: ignore[assignment]
try:
    from workers import DurableObject as _DurableObject  # type: ignore[import-not-found]
    from workers import (
        Response,  # type: ignore[import-not-found]
        WorkerEntrypoint,  # type: ignore[import-not-found]
    )
except ImportError:
    # Outside CF runtime (tests / local dev): defer to cf_types (loaded below).
    Response = None  # type: ignore[assignment]
    WorkerEntrypoint = None  # type: ignore[assignment]

# Ensure the current directory, its parent, and python_modules are in sys.path
# for Cloudflare runtime.  Pyodide loads modules from /session/metadata/ and
# needs explicit path configuration.
_current_file = Path(__file__).resolve()
_current_dir = str(_current_file.parent)  # .../undef_terminal_cloudflare/
_parent_dir = str(_current_file.parent.parent)  # contains undef_terminal_cloudflare/ as package
_python_modules_dir = str(_current_file.parent.parent.parent / "python_modules")

# In CF runtime, wrangler may flatten src/ so that entry.py is at /session/
# and the package is at /session/undef_terminal_cloudflare/.  Add /session/
# (the grandparent) as well as the typical /session/metadata/ parent.
_import_error: str | None = None

for _path in [_parent_dir, _current_dir, _python_modules_dir]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from undef_terminal_cloudflare.auth.jwt import (
        JwtValidationError,
        decode_jwt,
        extract_bearer_or_cookie,
    )
    from undef_terminal_cloudflare.cf_types import json_response
    from undef_terminal_cloudflare.config import CloudflareConfig
    from undef_terminal_cloudflare.do.session_runtime import SessionRuntime
    from undef_terminal_cloudflare.state.registry import list_kv_sessions
    from undef_terminal_cloudflare.ui.assets import read_asset_text, serve_asset

    if Response is None:  # workers module wasn't available (test env)
        from undef_terminal_cloudflare.cf_types import Response, WorkerEntrypoint  # type: ignore[assignment,no-redef]
except Exception:
    try:
        from auth.jwt import (  # type: ignore[import-not-found]
            JwtValidationError,
            decode_jwt,
            extract_bearer_or_cookie,
        )
        from cf_types import json_response  # type: ignore[import-not-found]
        from config import CloudflareConfig  # type: ignore[import-not-found]
        from do.session_runtime import SessionRuntime  # type: ignore[import-not-found]
        from state.registry import list_kv_sessions  # type: ignore[import-not-found]
        from ui.assets import read_asset_text, serve_asset  # type: ignore[import-not-found]

        if Response is None:  # workers module wasn't available
            from cf_types import Response, WorkerEntrypoint  # type: ignore[assignment,no-redef,import-not-found]
    except Exception:
        # Last resort for Pyodide validation phase — stubs for non-handler imports.
        # WorkerEntrypoint/Response/DurableObject are imported directly from workers
        # above, so handler registration always succeeds.
        _import_error = f"paths={sys.path[:5]}"
        JwtValidationError = Exception  # type: ignore[assignment]

        def decode_jwt(*_a: object, **_k: object) -> None:  # type: ignore[assignment]
            return None

        def extract_bearer_or_cookie(*_a: object, **_k: object) -> None:  # type: ignore[assignment]
            return None

        def json_response(*_a: object, **_k: object) -> None:  # type: ignore[assignment]
            return None

        CloudflareConfig = object  # type: ignore[assignment]

        class SessionRuntime(_DurableObject):  # type: ignore[assignment]  # pragma: no cover
            """Stub DO for validation phase — real impl loaded at runtime."""

            async def fetch(self, _request):  # type: ignore[override]
                return Response.json({"error": "not initialized"}, status=503)  # type: ignore[union-attr]

        def list_kv_sessions(*_a: object, **_k: object) -> None:  # type: ignore[assignment]
            return None

        def read_asset_text(*_a: object, **_k: object) -> None:  # type: ignore[assignment]
            return None

        def serve_asset(*_a: object, **_k: object) -> None:  # type: ignore[assignment]
            return None


__all__ = ["Default", "SessionRuntime", "UndefTerminalCloudflareWorker"]

_WORKER_ROUTE_PATTERNS = (
    re.compile(r"^/ws/browser/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/term$"),
    re.compile(r"^/ws/worker/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/term$"),
    re.compile(r"^/ws/raw/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/term$"),
    re.compile(r"^/worker/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/hijack(?:/.*)?$"),
    re.compile(r"^/worker/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/(?:input_mode|disconnect_worker)$"),
    re.compile(r"^/api/sessions/(?P<worker_id>[a-zA-Z0-9_-]{1,64})(?:/(?:snapshot|events|mode|clear|analyze))?$"),
)
_STATIC_ASSET_PATH = re.compile(r"^/[a-zA-Z0-9._/-]+\.(?:html|css|js)$")


async def _require_jwt(request: object, config: CloudflareConfig) -> Response | None:
    """Return a 401 Response if JWT auth fails, or ``None`` if auth passes.

    Skipped when auth mode is not ``jwt``.
    """
    if config.jwt.mode != "jwt":
        return None
    token = extract_bearer_or_cookie(request)
    if not token:
        return json_response({"error": "authentication required"}, status=401)
    try:
        await decode_jwt(token, config.jwt)
    except JwtValidationError as exc:
        return json_response({"error": "invalid token", "detail": str(exc)}, status=401)
    return None


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if not hasattr(self, "_config"):
            # `Default` is a stateless Worker (not a Durable Object), so each
            # isolate instance is reused across multiple requests within the same
            # V8 isolate lifetime.  This guard caches config per-isolate to avoid
            # re-reading env vars on every request; it does NOT persist across
            # isolate restarts or across different Workers instances.
            self._config = CloudflareConfig.from_env(self.env)
        config = self._config
        path = urlparse(str(request.url)).path

        if path == "/api/health":
            return json_response(
                {
                    "ok": True,
                    "service": "undef-terminal-cloudflare",
                    "environment": config.environment,
                }
            )

        if path == "/api/sessions":
            auth_error = await _require_jwt(request, config)
            if auth_error is not None:
                return auth_error
            # Fleet-wide list: query KV registry populated by each DO on connect/disconnect.
            # Falls back to empty list when SESSION_REGISTRY KV binding is not configured.
            kv_configured = getattr(self.env, "SESSION_REGISTRY", None) is not None
            sessions = await list_kv_sessions(self.env)
            scope = "fleet" if kv_configured else "local"
            return json_response(sessions, headers={"X-Sessions-Scope": scope})

        if path.startswith("/assets/"):
            return serve_asset(path.removeprefix("/assets/"))
        if _STATIC_ASSET_PATH.match(path):
            return serve_asset(path.removeprefix("/"))

        worker_id = _extract_worker_id(path)
        if worker_id is None:
            if path in {"/app", "/app/", "/"}:
                # HTML page routes require JWT auth when mode=jwt.
                # Static assets (JS/CSS) are public — same as FastAPI's StaticFiles mount.
                auth_error = await _require_jwt(request, config)
                if auth_error is not None:
                    return auth_error
                # All routes serve the SPA terminal app (terminal.html).
                body = read_asset_text("terminal.html")
                if body is not None:
                    body = body.replace("<head>", '<head><base href="/assets/">', 1)
                    return Response(body, status=200, headers={"content-type": "text/html; charset=utf-8"})
                return serve_asset("terminal.html")
            return json_response({"error": "not_found", "path": path}, status=404)

        namespace = getattr(self.env, "SESSION_RUNTIME", None)
        if namespace is None:
            return json_response({"error": "SESSION_RUNTIME binding missing"}, status=500)

        stub_id = namespace.idFromName(worker_id)
        stub = namespace.get(stub_id)
        return await stub.fetch(request)


UndefTerminalCloudflareWorker = Default


def _extract_worker_id(path: str) -> str | None:
    for pattern in _WORKER_ROUTE_PATTERNS:
        match = pattern.match(path)
        if match:
            return str(match.group("worker_id"))
    return None
