# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **CDN configurability** — `xterm_cdn` and `fonts_cdn` fields on `UiConfig` allow operators to
  point the server UI at a self-hosted CDN or omit CDN links entirely for air-gapped deployments.
- **Recording byte cap** — `RecordingConfig.max_bytes` (default 0 = unlimited) caps the on-disk
  size of session recordings. Writes stop silently once the limit is reached.
- **REST rate limiting** — `TermHub` now accepts `rest_acquire_rate_limit_per_sec` (default 5/s)
  and `rest_send_rate_limit_per_sec` (default 20/s). The acquire, send, and step endpoints
  return HTTP 429 when the per-hub token buckets are exhausted.
- **`worker_hello` mode validation** — unknown `input_mode` values in `worker_hello` messages
  are now logged at `WARNING` level instead of silently ignored.
- **`SessionConnector.clear()` abstract** — `clear()` is now abstract on `SessionConnector`;
  concrete implementations in `DemoSessionConnector` (transcript clear),
  `TelnetSessionConnector` (buffer clear), and `SshSessionConnector` (buffer clear).
- **PyPI classifiers** — `pyproject.toml` now declares `Development Status`, `License`,
  `Programming Language`, `Topic`, and `Framework` classifiers.

### Changed

- **Hub public API** — `TermHub` now exposes atomic methods for all lock-guarded operations
  previously accessed via `hub._lock` + `hub._workers` from route handlers. Direct internal
  access from REST and WS route files has been eliminated.
- **`_AUTO_START_DELAY_S` constant** — the auto-start delay in `server/app.py` is now a named
  module-level constant instead of a magic literal.
- **`PATCH /sessions/{id}` documentation** — `connector_config` is now documented as a
  shallow-merge (not replace) in the route handler.

### Security

- **`session_id` path validation** — all server API session routes now enforce `^[\w\-]+$`
  via `Annotated[str, Path(pattern=...)]`, blocking path-traversal characters.
- **Recording download containment** — `GET /sessions/{id}/recording/download` now verifies
  that the resolved file path is within the configured recordings directory before serving,
  preventing symlink-based escapes.
- **`session_id` config validation** — TOML-sourced `session_id` values are now validated
  against `^[\w\-]+$` at config load time.
- **JWT required claims** — reduced from `["sub", "exp", "iat", "nbf"]` to `["sub", "exp"]`
  to be compatible with issuers (Auth0, Google, Azure AD) that omit `iat`/`nbf`.

### Fixed

- **`KeyError` → HTTP 500** — `SessionRegistry` methods now use a `_require_session()` helper
  that raises a descriptive `KeyError` on miss; route handlers map this to HTTP 404.
- **Health endpoint** — `GET /api/health` now returns `{"ready": false}` with HTTP 503 when
  the registry is not yet initialized, instead of always returning `ok: true`.
- **Query parameter bounds** — `limit` and `offset` parameters on `/events` and
  `/recording/entries` now declare proper `ge`/`le` constraints; out-of-range values
  return HTTP 422 instead of being silently clamped.
- **`screen.py` regex safety** — `extract_menu_options`, `extract_numbered_list`, and
  `extract_key_value_pairs` now catch `re.error` from invalid caller-supplied patterns and
  return empty results instead of propagating an unhandled exception.
- **Browser role resolver timeout** — `TermHub` wraps async `resolve_browser_role` calls
  in `asyncio.wait_for(..., timeout=5.0)` to prevent hung WS connections on slow resolvers.
- **`SessionLogger` file handle leak** — an exception during the initial write in `start()`
  now closes the file handle before re-raising.
- **`SessionLogger` duplicate context fields** — `menu` and `action` keys from the event
  context dictionary were previously written twice (once in `ctx`, once at top level).
  The redundant top-level promotion has been removed.
- **Replay `json.JSONDecodeError`** — corrupted or truncated JSONL lines in session
  recordings are now skipped with a `WARNING` log instead of aborting the entire replay.
- **`SessionRegistry` hub decoupling** — `last_snapshot()` and `events()` now call public
  `TermHub` methods instead of accessing `hub._lock` and `hub._workers` directly.

## [0.1.0] — 2026-03-06

Initial public release.

### Added

- **TermHub** — in-memory registry managing worker and browser WebSocket connections,
  hijack leases (REST and dashboard WS), and terminal event history.
- **HijackableMixin** — worker-side mixin enabling pause/resume/step automation control.
- **TermBridge** — worker-side reconnecting WS client that forwards terminal I/O to TermHub.
- **3-tier browser roles** — `viewer` (observe only), `operator` (open-mode input),
  `admin` (input + hijack). Resolved per-connection via optional `resolve_browser_role`
  callback or `?role=` query parameter.
- **REST hijack API** — acquire/heartbeat/snapshot/events/send/step/release endpoints
  with lease expiry, heartbeat renewal, and prompt-guard (`expect_regex` / `expect_prompt_id`).
- **WebSocket hijack control** — dashboard-initiated hijack with auto-expiring lease,
  broadcasted `hijack_state` messages, and owner/other/none distinction per browser.
- **Input modes** — `hijack` (default, exclusive) and `open` (shared, operator+admin).
- **Rate limiting and size limits** — `TokenBucket` per-browser rate limiter; configurable
  `max_ws_message_bytes` and `max_input_chars` with min-clamp safety.
- **Event deque** — per-worker ordered event log (cap 2000) with `seq`, `min_event_seq`,
  and `has_more` pagination signals on the events endpoint.
- **TelnetWsGateway / SshWsGateway** — transparent Telnet and SSH proxies over WebSocket.
- **Terminal ANSI utilities** — `colorize`, `strip_colors`, `strip_ansi`, `normalize_terminal_text`,
  CP437 encode/decode, and screen-content extraction helpers.
- **Replay viewer** — JSONL session log playback with speed control and step mode.
- **Frontend assets** — browser-side `hijack.js` client with configurable role and mode display.
- **CLI entry points** — `undefterm` and `undefterm-server`.
- **100% test coverage** — 690+ tests across unit, integration, property-based (Hypothesis),
  and Playwright UI suites.

### Known Limitations

- REST hijack routes have no built-in authentication. The router must be protected at the
  application layer before exposure to untrusted clients (see module docstring for patterns).
- `TermBridge` requires the `websocket` extra (`pip install 'undef-terminal[websocket]'`).
- Server JWT features require the `server` extra (`pip install 'undef-terminal[server]'`).
