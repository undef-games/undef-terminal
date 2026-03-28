# undef-terminal: Handoff

## Current State (2026-03-25)

- **Main package (`undef-terminal`)**: 4043 tests passing. 100% branch coverage. Pre-commit hooks active.
- **CF package (`undef-terminal-cloudflare`)**: 599 unit tests + 14 real_cf E2E tests — all pass.
  100% coverage across all files. Deployed to `https://undef-terminal-cloudflare.neurotic.workers.dev`.
- **Shell package (`undef-shell`)**: 160 tests passing. 100% coverage.
- **Frontend**: TypeScript tests pass (vitest). Biome lint+format clean. TypeScript typecheck clean.
- **Release gate**: All three packages at 100% coverage. Pre-commit clean. Ready for v0.4.0 tag.

## What Was Done

### 2026-03-22: CF Access Service Token + E2E Against Live CF
- Created CF Access service token "e2e-test" (non-expiring) + Service Auth policy
- Worker accepts service token JWTs (`sub=""` → `common_name` fallback, admin role)
- Worker bearer token bypass for CF Access service tokens in DO
- E2E tests pass CF-Access-Client-Id/Secret + Bearer token headers
- WS messages use control stream framing; tests decode with `_decode_control_frames()`
- All 14 real_cf E2E tests pass against live deployment
- 94 new coverage tests (jwt, entry, session_runtime, registry)
- Xenon complexity: entry.py + jwt.py refactored to pass B threshold

### 2026-03-22: uwarp-space Terminal Fixes
- Removed local echo from uwarp-space terminal.js (double character fix)
- Spinner delay 0→500ms (only on actual hibernation wake)
- DO sends `⠋ waking…` ANSI indicator on hibernation rehydration (all transports)
- Deployed to `warp.undef.games`

### 2026-03-21: Operator View Redesign
- Structured sidebar: Input Mode toggle, Actions, Session Info, Tags
- Analyze screen moved behind Advanced disclosure
- Font consistency (Fira Code everywhere)

### 2026-03-21: CF Auth + SPA + Deployment Fix
- JWT via Web Crypto API (Pyodide); validates exp, nbf, iss, aud
- Fixed Pyodide deployment ("no registered event handlers")
- SPA dashboard at root; all /app/* routes; /api/connect; KV cleanup
- Terraform: cloudflare_workers_custom_domain for uterm.neurotic.org

### 2026-03-21: Frontend Bug Fixes (hijack.ts)
- Removed local echo (double rendering fix)
- Scoped reconnect animation to _scheduleReconnect() only
- Remapped status colors: green=active, orange=waking, red=disconnected
- Stopped reconnect animation in dispose() (resource leak)

### 2026-03-21: Detection + Shell + Coverage
- Detection pipeline error isolation
- 100% Python coverage achieved
- ushell package + CF DO adapter

### 2026-03-22: Release prep (0.4.0)
- `src/undef/shell` symlink committed (enables monorepo-root `from undef.shell import ...`)
- CF `python_modules/` new files + `uv.lock` committed
- Root `.gitignore`: added `mutation-score.json`
- `undef-terminal` + `undef-terminal-cloudflare` bumped to **0.4.0**; CF `pyproject.toml` dep updated
- `README.md`: test count 2000→4000; connector list adds `websocket`, `ushell`; ushell docs added
- `packages/undef-shell/README.md`: expanded from stub to full usage doc
- Mutation testing: 95.7% score (134/140 killed); 6 equivalent mutants (unkillable by design)
- `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` added to pymutant MCP server env in `~/.claude.json`
  to fix macOS fork-safety SIGSEGV in mutmut

## Known Issues

- CF overall package coverage at 96.5% (pre-existing gaps in http_routes.py, contracts.py, ws_routes.py)
- 13 xenon blocks above B in pre-existing files (http_routes.py at F, config.py at D)
- `undef-shell` 0.1.0 not yet on PyPI (blocked on non-publishing decision; undef-terminal 0.4.0 also not yet published)

### 2026-03-22: Codebase Hygiene (current session)
- Split `detection/detector.py` (501→437 lines): extracted `auto_detect_input_type` to `detection/input_type.py`
- Split `api/http_routes.py` (504 lines): converted to `api/http_routes/` module dir (`_shared`, `_hijack`, `_session`, `_dispatch`)
- Connector self-registration: replaced hardcoded `KNOWN_CONNECTOR_TYPES` frozenset + if/elif factory with `server/connectors/registry.py`; each connector registers itself at import time
- Removed compiled frontend from git: build artifacts in `.gitignore`; `npm run build:frontend` step added to CI `quality` and `release-readiness` jobs
- Vendored `undef.shell` into CF `python_modules/`; added guard test + CI check
- Pre-commit config: `tsconfig.json` + `vite.config.ts` `outDir` fixed (was writing to stale repo-root path)

## Known Issues

- `tests/detection/test_extractor.py` is 540 lines — pre-existing LOC violation not in scope of hygiene pass; needs split
- CF overall package coverage at 96.5% (pre-existing gaps in contracts.py, ws_routes.py)
- 13 xenon blocks above B in pre-existing files (config.py at D)
- `undef-shell` 0.1.0 not yet on PyPI (blocked on non-publishing decision; undef-terminal 0.4.0 also not yet published)

### 2026-03-22: _bridge_session recv bug fix
- **Bug**: `ShellSessionConnector.poll_messages()` returns `[]` instantly, so `poll_task` always
  beat `recv_task` in `asyncio.wait(FIRST_COMPLETED)`. The old code then called `_cancel_and_wait(pending)`
  which always cancelled `recv_task`, preventing the runtime from ever reading inbound browser messages.
  Symptom: typing in the operator view produced "Worker connection lost." or no response.
- **Fix** (`server/runtime.py`): persist `recv_task` across loop iterations; only cancel `poll_task`
  each cycle. Added `CancelledError` guard on `recv_task.result()` for clean `stop()` shutdown.
  Added `finally` block to cancel `recv_task` on exit.
- **Coverage**: added `test_cancel_and_wait_empty_set_is_noop` and updated
  `test_backoff_reset_after_clean_session` to directly mock `_bridge_session`; 100% branch coverage restored.
- **E2E verified**: Playwright browser at `http://127.0.0.1:8780/app/operator/undef-shell` shows
  "Connected (shared)" and responds to `/status` with full session info.

## Backlog

- **Session state unification**: `TermHub` (in-memory, hosted server) and `state/registry.py` (KV-backed, CF) are separate session state stores with divergent models. A future task should unify these under a shared contract/protocol so session lifecycle, visibility, and metadata are consistent between the two deployment targets.

### 2026-03-28: Tunnel Sharing System (tmate/ngrok-style)
- **Tunnel protocol** (`tunnel/protocol.py`): binary multiplexed frames `[channel][flags][payload]` over WebSocket
- **PTY capture** (`tunnel/pty_capture.py`): spawn PTY or attach to current TTY
- **Tunnel client** (`tunnel/client.py`): async WS client with reconnect + backoff
- **CLI** (`cli/share.py`): `uterm share --server URL [cmd]` shares local terminal
- **FastAPI routes** (`tunnel/fastapi_routes.py`): `/tunnel/{id}` WS endpoint, bridges to TermHub
- **CF routes** (`api/tunnel_routes.py`, `api/_tunnel_api.py`): binary frame handler in DO, `POST /api/tunnels`, share URL auth
- **Share URLs**: `/app/session/{id}?token=...` (viewer), `/app/operator/{id}?token=...` (operator), `/s/{id}?token=...` (CF short URL)
- **Frontend**: `setShareToken()` / `withShareToken()` propagates token to all API + WS calls
- **Tests**: 161 tunnel + 28 CF tunnel + 54 API + 469 frontend = all passing

### 2026-03-28: Tunnel Token Hardening
- **TTL**: default 1 hour, configurable per-server and per-tunnel via `TunnelConfig`
- **Revocation**: `DELETE /api/tunnels/{id}/tokens`
- **Rotation**: `POST /api/tunnels/{id}/tokens/rotate`
- **Timing attack fix**: CF `resolve_share_context()` uses `secrets.compare_digest()` (was `==`)
- **Enumeration fix**: share routes return 404 for both "not found" and "invalid token"
- **Cookie transport**: `_resolve_tunnel_share_principal()` checks `uterm_tunnel_{id}` cookie alongside query param
- **IP binding**: optional (`TunnelConfig.ip_binding`), stores `issued_ip` at creation
- **Audit logging**: structured logs on all token create/validate/expire/revoke/rotate
- **Shared types**: `TunnelTokenState` + `TunnelCreateResponse` TypedDicts in `tunnel/types.py`
- **Config model**: `TunnelConfig` added to `ServerConfig` (token_ttl_s, token_transport, cookie_secure, cookie_samesite, ip_binding)

## Known Issues

- CF overall package coverage at 96.5% (pre-existing gaps in contracts.py, ws_routes.py)
- 13 xenon blocks above B in pre-existing files (config.py at D)
- `undef-shell` 0.1.0 not yet on PyPI
- FastAPI tunnel tokens are in-memory only — server restart loses active share links (CF side has KV persistence)
- Frontend share token propagation uses query params by default; cookie mode available but not default

## What's Next

- **Phase 2**: `uterm tunnel <port>` — TCP port forwarding through the tunnel primitive (channel multiplexing already supports it)
- **Phase 3**: HTTP-aware tunneling with inspection UI (MITM features)
- Ready to publish 0.4.0 when desired.
