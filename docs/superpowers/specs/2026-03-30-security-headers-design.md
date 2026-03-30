# Security Headers — Configurable with Dev/Strict Modes

## Goal

Add configurable security response headers to both FastAPI and CF Worker backends. Production defaults are strict (CSP, HSTS, X-Frame-Options, etc.). Dev mode disables them for frictionless local development. Every header is individually overridable.

## Scope

- **Both backends** — FastAPI and CF Worker at parity
- **Frontend SRI** — Subresource Integrity hashes for all CDN-loaded scripts/styles
- **Configurable** — top-level `security.mode` with per-header overrides

## Config Model

### FastAPI (`ServerConfig`)

```python
@dataclass
class SecurityConfig:
    mode: Literal["strict", "dev"] = "strict"
    csp: str | None = None
    hsts: str | None = None
    x_frame_options: str | None = None
    x_content_type_options: str | None = None
    referrer_policy: str | None = None
    permissions_policy: str | None = None
```

Added to `ServerConfig` as `security: SecurityConfig`.

### CF Worker (`CloudflareConfig`)

```python
security_mode: str = "strict"
security_csp: str | None = None
security_hsts: str | None = None
security_x_frame_options: str | None = None
security_x_content_type_options: str | None = None
security_referrer_policy: str | None = None
security_permissions_policy: str | None = None
```

Read from environment variables, same pattern as existing `auth_mode`, `tunnel_token_ttl_s`, etc.

## Header Defaults

### Strict Mode

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; font-src fonts.gstatic.com; connect-src 'self' ws: wss:; img-src 'self' data:` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |

### Dev Mode

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | Not set |
| `Strict-Transport-Security` | Not set |
| `X-Frame-Options` | Not set |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | Not set |
| `Permissions-Policy` | Not set |

`X-Content-Type-Options: nosniff` is always set in both modes — there is no valid reason to disable it.

### Override Behavior

When a per-header field is set (not None), it takes precedence over the mode default. This allows fine-tuning without switching modes entirely:

```python
SecurityConfig(mode="strict", csp="default-src 'self' *.mycdn.com")
```

To explicitly suppress a header that strict mode would set, use an empty string:

```python
SecurityConfig(mode="strict", hsts="")  # HSTS disabled despite strict mode
```

## Architecture

### FastAPI — Middleware

New file: `packages/undef-terminal/src/undef/terminal/server/security.py`

```python
class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, config: SecurityConfig) -> None: ...
    async def __call__(self, scope, receive, send) -> None: ...
```

Registered in `create_server_app()` after CORS middleware. Applies headers to every HTTP response. WebSocket upgrade responses are excluded (they don't carry response headers in the same way).

The middleware resolves each header value:
1. If per-header override is set and non-None → use it (empty string = skip)
2. If mode is "strict" → use production default
3. If mode is "dev" → skip (except X-Content-Type-Options)

### CF Worker — Response wrapper

In `packages/undef-terminal-cloudflare/src/undef/terminal/cloudflare/entry.py`, add a `_apply_security_headers(response, config)` function called before returning any HTTP response (not WebSocket upgrades). Same resolution logic as FastAPI.

### Frontend SRI

Pre-computed SRI hashes for xterm.js 6.0.0 CDN assets. Stored as constants in the template generators (not computed at runtime).

**Files affected:**
- `packages/undef-terminal/src/undef/terminal/frontend/terminal.html`
- `packages/undef-terminal/src/undef/terminal/frontend/hijack.html`
- Any test pages that load from CDN (playwright conftest color test page)

Each `<script src="cdn...">` gets `integrity="sha384-..." crossorigin="anonymous"`.
Each `<link href="cdn..." rel="stylesheet">` gets `integrity="sha384-..." crossorigin="anonymous"`.

SRI hashes are computed once by downloading the CDN files and running `openssl dgst -sha384 -binary | openssl base64 -A`.

## Error Handling

- Invalid `security.mode` value → startup error with clear message
- Empty string override → header not set (valid, intentional suppression)
- None override → falls through to mode default

## Testing

### FastAPI Tests

- Strict mode: all 6 headers present with correct values
- Dev mode: only X-Content-Type-Options present
- Per-header override: custom CSP replaces default
- Empty string override: header suppressed
- WebSocket upgrade: no security headers on 101 response
- Config validation: invalid mode raises error

### CF Worker Tests

- Same matrix as FastAPI (strict, dev, overrides, suppression)
- Headers present on HTML responses
- Headers present on JSON API responses
- No headers on WebSocket upgrade

### Frontend SRI Tests

- `integrity` attribute present on all CDN script tags
- `crossorigin="anonymous"` present on all CDN tags
- SRI hashes match actual CDN content (download + verify)

## Files Changed

| File | Action |
|------|--------|
| `packages/undef-terminal/src/undef/terminal/server/security.py` | **Create** — SecurityHeadersMiddleware |
| `packages/undef-terminal/src/undef/terminal/server/models.py` | **Modify** — add SecurityConfig dataclass |
| `packages/undef-terminal/src/undef/terminal/server/app.py` | **Modify** — register middleware, pass config |
| `packages/undef-terminal-cloudflare/src/undef/terminal/cloudflare/config.py` | **Modify** — add security_* fields |
| `packages/undef-terminal-cloudflare/src/undef/terminal/cloudflare/entry.py` | **Modify** — add _apply_security_headers |
| `packages/undef-terminal/src/undef/terminal/frontend/terminal.html` | **Modify** — add SRI hashes |
| `packages/undef-terminal/src/undef/terminal/frontend/hijack.html` | **Modify** — add SRI hashes |
| `packages/undef-terminal/tests/server/test_security_headers.py` | **Create** — FastAPI header tests |
| `packages/undef-terminal-cloudflare/tests/test_security_headers.py` | **Create** — CF Worker header tests |
| `packages/undef-terminal/tests/test_frontend_sri.py` | **Create** — SRI verification tests |
