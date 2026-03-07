# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.2.0] — 2026-03-07

### Added

- **Fleet-wide session registry** — `state/registry.py` provides `update_kv_session` /
  `list_kv_sessions` helpers backed by a `SESSION_REGISTRY` KV binding. The Default Worker
  returns all sessions fleet-wide when KV is configured, with a `X-Sessions-Scope: fleet`
  response header; falls back to `local` (single-DO) scope when KV is absent.
- **KV heartbeat via Durable Object alarm** — `alarm()` reschedules itself every 60 s and
  refreshes the KV entry (300 s TTL safety net), preventing zombie entries when a DO hibernates.
- **`/hijack/{hid}/snapshot` endpoint** — returns the last stored terminal snapshot (in-memory
  or SQLite fallback) for polling-based hijack clients.
- **Contract parity TypedDicts** — `contracts.py` defines TypedDicts for all REST response
  shapes and a `RuntimeProtocol` structural interface to align the DO and test doubles without
  circular imports.
- **`input_mode` persistence** — new `input_mode` SQLite column (idempotent `ALTER TABLE`
  migration), `save_input_mode()` store method, and restore in `_restore_state()` so the mode
  survives hibernation.
- **`min_event_seq` store method** — `store.min_event_seq()` returns the oldest retained event
  sequence number; the events endpoint now includes `min_event_seq` in its response.
- **JWKS key selection by algorithm** — when a JWT has no `kid` header, `auth/jwt.py` filters
  JWKS keys by the `alg` header rather than returning the first key unconditionally.
- **`HijackCoordinator` always generates new UUID** — `acquire()` generates a fresh
  `hijack_id` on every call, preventing replay of stale IDs across hibernation cycles.

### Fixed

- **KV `input_mode` staleness** — `update_kv_session` now accepts and forwards the current
  `input_mode`; called with the live mode on connect and on every alarm heartbeat.
- **`webSocketError` left KV zombie** — the KV entry is now deleted when the worker WebSocket
  closes with an error, matching the behaviour of `webSocketClose`.
- **`_socket_browser_role` was fail-open** — auth modes other than `none`/`dev` now default
  to `"viewer"` instead of `"admin"` when role resolution is unavailable.
- **Blocking JWKS fetch** — `PyJWKClient.get_signing_key_from_jwt()` (synchronous
  `urllib.request`) replaced with an async `js.fetch` path in CF Workers and a `urllib`
  fallback for test environments, keeping the event loop unblocked.
- **`/api/sessions` single-DO scope** — Default Worker reads KV to return all fleet sessions;
  the old implementation only returned the current DO's session.
- **`_run()` masked SQL exceptions** — the dual-calling-convention fallback in
  `SqliteStateStore._run()` now re-raises the original exception rather than swallowing it when
  both invocation styles fail.
- **`ws_key` visibility** — renamed from `_ws_key` to `ws_key` (public method on
  `RuntimeProtocol` and `SessionRuntime`) so WS routes can call it without name-mangling.

### Security

- **Admin-only input mode and disconnect** — `POST /worker/{id}/input_mode` and
  `POST /worker/{id}/disconnect_worker` now return HTTP 403 for non-admin callers.
- **Empty `keys` rejected on send** — `POST /hijack/.../send` returns HTTP 400 when `keys`
  is absent or empty.
- **`owner` default hardened** — `POST /hijack/acquire` defaults `owner` to `"operator"`
  instead of an empty string when the field is omitted.

### Removed

- **`bridge/upstream_ws.py`** — unused file with no importers; deleted to reduce dead surface area.

### Tests

- 55 unit tests (+ 4 E2E skipped by default; run with `-m e2e` or `E2E=1`).
- `test_api_contracts.py` — enforces REST API shape parity against TypedDicts in `contracts.py`.
- `test_security_hardening.py` — JWT validation, query-token policy, lease clamping, and
  admin-only route guards.

---

## [0.1.0] — 2026-03-06

Initial release of the Cloudflare Workers port.

### Added

- **`SessionRuntime` Durable Object** — multiplexes worker and browser WebSocket connections
  for a single `worker_id`; uses the CF Hibernation API (`webSocketOpen` / `webSocketMessage` /
  `webSocketClose` / `webSocketError` / `alarm`) to survive DO restarts with near-zero cost.
- **SQLite-backed state** — `SqliteStateStore` persists hijack leases, the last terminal
  snapshot, and an event ring-buffer (cap 2000) via `ctx.storage.sql.exec`.
- **REST hijack API parity** — acquire / heartbeat / snapshot / events / send / step / release
  endpoints with lease expiry, heartbeat renewal, and lease-bounds clamping (1 s – 3600 s).
- **JWT / JWKS authentication** — `auth/jwt.py` supports symmetric and asymmetric keys with
  configurable clock skew; `dev` and `none` modes for local development.
- **Default Worker** — routes to `SessionRuntime` DO stubs via `idFromName`; serves `/api/sessions`
  and static assets with fallback to the `undef-terminal` frontend package.
- **`HijackCoordinator`** — pure in-memory hijack arbitration with session UUID generation.
- **CLI entry point** — `uterm-cf` for local development and deployment helpers.
