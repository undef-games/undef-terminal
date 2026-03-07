# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (sixth review)

- **`HostedSessionRuntime` stops on permanent HTTP errors** — `_run()` now exits the retry
  loop immediately when the TermHub WebSocket endpoint returns HTTP 401, 403, or 404 (same
  fix applied to `TermBridge` in the fifth review but missed in `runtime.py`).
- **`WebSocketException` no longer swallowed in `_resolve_role_for_browser`** — unauthorized
  browser connections (raised as `WebSocketException` with code 1008) were previously caught
  by the bare `except Exception` handler and re-raised as `BrowserRoleResolutionError`,
  causing the client to receive code 1011 ("internal error") instead of 1008 ("policy
  violation"). `WebSocketException` is now re-raised directly.
- **`browser_handlers.py` error messages** — three `"No worker connected for this worker."`
  strings corrected to `"for this session."`, completing the fix started in the fifth review
  (which only updated `rest.py`).
- **`CHANGELOG` `connector_config` wording** — prior entry incorrectly said "shallow-merge";
  corrected to "full replacement" to match the actual implementation.

### Tests (sixth review)

- **Sixth-review regression suite** — 2 new tests: `browser_handlers.py` has no "for this
  worker" strings, and `HostedSessionRuntime` task exits immediately on HTTP 401.

---

### Added (fifth review)

- **`connector_type` validated at TOML config load time** — `config_from_mapping` now validates
  `connector_type` against `KNOWN_CONNECTOR_TYPES` for each `[[sessions]]` entry, raising
  `ValueError` with a descriptive message at startup rather than surfacing the error later via
  `lifecycle_state == "error"`.
- **SSH `connect_timeout=30`** — `SshSessionConnector.start()` now passes `connect_timeout=30`
  to `asyncssh.connect()`, preventing indefinite hangs when connecting to unreachable SSH hosts.

### Changed

- **SSH input encoding** — `SshSessionConnector.handle_input()` now encodes keystrokes as UTF-8
  instead of latin-1, allowing non-ASCII input (e.g. accented characters, euro sign) to reach
  the remote shell correctly.
- **`TermBridge` stops on permanent HTTP errors** — the reconnect loop in `TermBridge._run()` now
  exits immediately when the server returns HTTP 401, 403, or 404, rather than backing off and
  retrying indefinitely. These status codes indicate misconfiguration that will not resolve itself.
- **Page routes reuse authenticated principal** — all four page handlers in `pages.py` now read
  `request.state.uterm_principal` (set by `_require_authenticated`) instead of calling
  `resolve_http_principal()` again, eliminating a redundant JWT decode / JWKS fetch per page load.
- **Fire-and-forget `_resume_task` done callbacks** — the two `asyncio.create_task()` resume calls
  in `ws_browser_term`'s finally block now have done callbacks that log any failures, matching the
  pattern already used by the worker-disconnect broadcast tasks.

### Fixed

- **Hijack REST error messages** — three `"No worker connected for this worker."` strings in
  `rest.py` corrected to `"No worker connected for this session."` (grammatically accurate and
  consistent with the surrounding context).

### Tests

- **Fifth-review regression suite** — 7 new tests added to
  `tests/test_server_security_regressions.py`: SSH `connect_timeout=30` forwarded to asyncssh,
  SSH handle_input encodes as UTF-8, `config_from_mapping` rejects unknown `connector_type`,
  `TermBridge` self-stops on permanent HTTP 401/403/404, hijack acquire error message says
  "session" not "worker", and page routes do not call `resolve_http_principal` a second time
  when `request.state.uterm_principal` is already set.

---

### Added (prior — fourth review)

- **`connector_type` validated at session-creation time** — `POST /api/sessions` now returns
  HTTP 422 immediately when `connector_type` is not one of the built-in types (`demo`,
  `telnet`, `ssh`), rather than returning 200 and only surfacing the error later via
  `lifecycle_state == "error"`.
- **`TelnetClient` connect timeout** — `TelnetClient.__init__` now accepts a
  `connect_timeout` keyword argument (default 30 s). `connect()` wraps
  `asyncio.open_connection` in `asyncio.wait_for`, preventing indefinite hangs when
  connecting to unreachable hosts.
- **`replay_log` speed upper bound** — `speed` is now clamped to `[0.01, 100.0]`, preventing
  arbitrarily large multipliers from being passed silently.

### Changed

- **`POST /sessions/{id}/mode` returns 422 for invalid `input_mode`** — previously returned
  HTTP 400; changed to 422 to be consistent with all other validation failures in the API.
- **Recording download is fail-closed when config is absent** — the path-containment guard in
  `GET /api/sessions/{id}/recording/download` now returns 404 if `uterm_config` is absent from
  app state (previously skipped the check silently).

### Removed

- **`SessionDefinition.last_active_at` field removed** — the field was set on create/update
  but never read by any eviction policy, metrics counter, or log field. Removed to keep the
  model honest.
- **Dead methods `allow_rest_acquire()` / `allow_rest_send()`** — two unreachable methods in
  `_ConnectionMixin` that were not in `TermHubProtocol` and not called from any route handler
  (only the `allow_rest_acquire_for(client_id)` / `allow_rest_send_for(client_id)` variants
  are used). Deleted to remove confusing surface area.

### Tests

- **Fourth-review regression suite** — 7 new tests added to
  `tests/test_server_security_regressions.py`: unknown `connector_type` → 422,
  `TelnetClient` timeout parameter accepted, `POST /mode` invalid value → 422, recording
  download denied when config absent → 404, `replay_log` speed upper-clamp, and
  `SessionDefinition` has no `last_active_at` field.

### Added (continued — prior releases)

- **Permanent-failure detection** — `HostedSessionRuntime` now distinguishes
  `ValueError` (e.g. unsupported `connector_type`, missing SSH `known_hosts`) as a
  permanent configuration error; the retry loop stops immediately and sets
  `lifecycle_state = "error"` instead of retrying every 5 seconds forever.

### Security

- **XSS fix in `session_page_html`** — `assets_path` inside the `<script>` tag for
  `hijack.js` was the only unescaped dynamic value in `ui.py`; it is now passed through
  `html.escape()` like every other path reference in that file.
- **JWKS cache thread safety** — `_JWKS_CLIENT_CACHE` is now guarded by a
  `threading.Lock` so concurrent `asyncio.to_thread` JWT validations cannot race on
  the shared dict.
- **SSH `known_hosts` default-deny** — `SshSessionConnector` now raises `ValueError`
  when `known_hosts` is not configured, preventing silent MITM exposure. Set
  `insecure_no_host_check = true` in `connector_config` to opt in to the old
  warning-only behaviour.

### Fixed

- **`RecordingConfig.max_bytes` rejects negative values** — `config_from_mapping` now
  raises `ValueError` when `recording.max_bytes < 0` instead of silently treating it
  as unlimited.

### Tests

- **Third-review regression suite** — 11 new tests added to
  `tests/test_server_security_regressions.py` covering: `session_id` path-pattern 422,
  query-param bound 422, health 503 without registry, `PATCH` 422 on invalid
  `input_mode`, idempotent `DELETE`, `"none"` algorithm rejection, page-route 403 for
  private sessions, negative `max_bytes` config rejection, JWT without optional
  `iat`/`nbf` claims, recording-download path-containment 404, and SSH connector
  `known_hosts` enforcement.

### Added (continued — prior release)

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
  full replacement (callers must send the complete desired config, not just changed keys).

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
- **CLI entry points** — `uterm` and `uterm-server`.
- **Test coverage** — 690+ tests across unit, integration, property-based (Hypothesis),
  and Playwright UI suites.

### Known Limitations

- REST hijack routes have no built-in authentication. The router must be protected at the
  application layer before exposure to untrusted clients (see module docstring for patterns).
- `TermBridge` requires the `websocket` extra (`pip install 'undef-terminal[websocket]'`).
- Server JWT features require the `server` extra (`pip install 'undef-terminal[server]'`).
