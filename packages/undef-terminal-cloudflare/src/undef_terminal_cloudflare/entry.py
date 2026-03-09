from __future__ import annotations

import re
from urllib.parse import urlparse

try:
    from undef_terminal_cloudflare.cf_types import Response, WorkerEntrypoint, json_response
    from undef_terminal_cloudflare.config import CloudflareConfig
    from undef_terminal_cloudflare.do.session_runtime import SessionRuntime
    from undef_terminal_cloudflare.state.registry import list_kv_sessions
    from undef_terminal_cloudflare.ui.assets import read_asset_text, serve_asset
except Exception:
    from cf_types import Response, WorkerEntrypoint, json_response  # type: ignore[import-not-found]
    from config import CloudflareConfig  # type: ignore[import-not-found]
    from do.session_runtime import SessionRuntime  # type: ignore[import-not-found]
    from state.registry import list_kv_sessions  # type: ignore[import-not-found]
    from ui.assets import read_asset_text, serve_asset  # type: ignore[import-not-found]

__all__ = ["Default", "SessionRuntime", "UndefTerminalCloudflareWorker"]

_WORKER_ROUTE_PATTERNS = (
    re.compile(r"^/ws/browser/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/term$"),
    re.compile(r"^/ws/worker/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/term$"),
    re.compile(r"^/ws/raw/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/term$"),
    re.compile(r"^/worker/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/hijack(?:/.*)?$"),
    re.compile(r"^/worker/(?P<worker_id>[a-zA-Z0-9_-]{1,64})/(?:input_mode|disconnect_worker)$"),
)
_STATIC_ASSET_PATH = re.compile(r"^/[a-zA-Z0-9._/-]+\.(?:html|css|js)$")


def _extract_bearer_or_cookie(request: object) -> str | None:
    """Return a JWT token from Authorization header or CF_Authorization cookie."""
    try:
        auth_header = str(request.headers.get("Authorization") or "")  # type: ignore[attr-defined]
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return token
    except Exception:  # noqa: S110
        pass
    try:
        cookie_header = str(request.headers.get("Cookie") or "")  # type: ignore[attr-defined]
        for part in cookie_header.split(";"):
            name, _, value = part.strip().partition("=")
            if name.strip() == "CF_Authorization" and value.strip():
                return value.strip()
    except Exception:  # noqa: S110
        pass
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
            # Require JWT auth in jwt mode — fleet-wide session list is sensitive.
            if config.jwt.mode == "jwt":
                token = _extract_bearer_or_cookie(request)
                if not token:
                    return json_response({"error": "authentication required"}, status=401)
                try:
                    from undef_terminal_cloudflare.auth.jwt import JwtValidationError, decode_jwt
                except Exception:
                    from auth.jwt import JwtValidationError, decode_jwt  # type: ignore[import-not-found]
                try:
                    await decode_jwt(token, config.jwt)
                except JwtValidationError as exc:
                    return json_response({"error": "invalid token", "detail": str(exc)}, status=401)
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
            if path in {"/app", "/app/"}:
                body = read_asset_text("terminal.html")
                if body is not None:
                    body = body.replace("<head>", '<head><base href="/assets/">', 1)
                    return Response(body, status=200, headers={"content-type": "text/html; charset=utf-8"})
                return serve_asset("terminal.html")
            if path == "/":
                return serve_asset("hijack.html")
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
