# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
