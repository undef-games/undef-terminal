# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: **1225 tests passing** (excl. Playwright). **100% branch coverage** (4540 stmts, 1262 branches, 0 missing). Pre-commit hooks active.
- **CF package (`undef-terminal-cloudflare`)**: **402 unit tests passing** + 5 skipped + E2E tests (`-m e2e`). Overall: **100% coverage** (1523 stmts, 0 missing).

---

## Completed in Most Recent Session

### VERSION standardization + quality gate parity (plan implemented)

**VERSION files:**
- `undef-terminal/VERSION` → `0.3.0` (new file)
- `undef-terminal/packages/undef-terminal-cloudflare/VERSION` → `0.3.0` (new file; setuptools restricts cross-dir `../../VERSION` refs)
- `undef-telemetry/VERSION` → `0.1.0` (new file)
- All pyproject.toml files now use `dynamic = ["version"]` + `[tool.setuptools.dynamic]`

**CF package: hatchling → setuptools** (`packages/undef-terminal-cloudflare/pyproject.toml`):
- Build backend switched; `[tool.hatch.build.targets.wheel]` removed; `[tool.setuptools.packages.find]` added

**Coverage enforcement added (both packages):**
- addopts: `--cov-branch`, `--cov-report=term-missing`, `--cov-fail-under=100`
- `[tool.coverage.run]` branch = true; `[tool.coverage.report]` fail_under = 100

**100% branch coverage achieved** (was 97.59% for main, 100% stmt but ~99% branch for CF):
- Main package: 4540 stmts, 1262 branches — 0 missing
- CF package: 1536 stmts, 524 branches — 0 missing
- Tests: 1225 (main) + 425 (CF) = 1650 total

**New dev dependencies (undef-terminal):**
- `mutmut>=3.3.1`, `pip-audit>=2.7.0`, `pytest-randomly>=3.15.0`, `vulture>=2.14`, `xenon>=0.9.3`
- `[tool.vulture]`, `[tool.xenon]`, `[tool.mutmut]` sections added

**pytest-randomly:** added `--randomly-dont-reorganize` to addopts (preserves zzz_ Playwright ordering)
Both Playwright test files excluded from default addopts run (`--ignore=tests/test_zzz_*.py`).

**New coverage gap tests (main package):**
- `tests/test_coverage_gaps2.py` — 20+ tests for branch gaps across hub, routes, bridge, ansi, telnet
- Various additions to `test_session_logger.py`, `test_ssh_transport.py`, `test_telnet_transport*.py`, `test_server_connectors.py`
- `# pragma: no branch` annotations in `ownership.py`, `ansi.py`, `telnet.py`

**New coverage gap tests (CF package):**
- `tests/test_branch_coverage.py` — 20 tests for branch gaps across http_routes, auth/jwt, cli, config, session_runtime, ws_helpers, state/registry, ui/assets

---

### Main Package — 100% Branch Coverage (items from previous session)

Filled all remaining branch coverage gaps (10 missing arcs → 0). Changes:

**Pragma annotations** (unreachable/dead branches):
- `src/undef/terminal/ansi.py` line 329: `# pragma: no branch` on `if seq:` inside `_handle_tilde_codes` (all `_TILDE_MAP` entries have valid color chars, so `seq` is always truthy)
- `src/undef/terminal/hijack/routes/websockets.py` line 215: changed to `# pragma: no cover` on body of `if role not in VALID_ROLES:` (dead code — `resolve_role_for_browser` always returns valid role)
- `src/undef/terminal/transports/telnet.py` lines 394, 416: `# pragma: no branch` on final `elif cmd == WONT:` in `_negotiate()` (exhaustive chain — cmd is always one of DO/DONT/WILL/WONT when called)

**New tests** covering previously-missing arcs:
- `tests/test_coverage_gaps2.py::TestAnsiTildeCodeNotInMap` — `_handle_tilde_codes` with unknown code (`~Z`) → `326->333` False branch
- `tests/test_coverage_gaps2.py::TestAnsiTwgsTokenInvalidPolarity` — fixed: `{xR}` (4-char TWGS token) not `{xRG}` → `345->351` False branch
- `tests/test_coverage_gaps2.py::TestBridgeInvalidUriFixed` — fixed: `await bridge.start()` (was called without await) → covers `214-220` (InvalidURI stops reconnect)
- `tests/test_coverage_gaps2.py::TestBridgeSessionUnknownMtypeRecvWins` — fixed: 2nd mock_recv sets `_stop` then returns valid JSON (not raises CancelledError) → covers `runtime.py 233->237`
- `tests/test_server_connectors.py::TestSshSessionConnector::test_stop_with_stdin_none_skips_write_eof` — `164->167` False branch (stdin=None at stop time)
- `tests/test_server_connectors.py::TestSshSessionConnector::test_stop_with_conn_none_skips_close` — `170->exit` False branch (conn=None at stop time)
- `tests/test_ssh_transport.py::TestSSHStreamReaderUnknownType` — line 57 (non-str/bytes return → `b""`)
- `tests/test_ssh_transport.py::TestSSHStreamWriterDoubleClose` — `87->exit` False branch (close when already closed)
- `tests/test_telnet_transport.py::TestTelnetClientCloseWhenNotConnected` — `91->exit` False branch (close when writer=None)
- `tests/test_telnet_transport_branches.py::TestConsumeRxBufferZeroConsumed` — `248->250` False branch (incomplete IAC → consumed=0)

Result: **100% branch coverage** (4540 stmts, 1262 branches, 0 missing, 0 failing).

---

### CF Endpoint Parity + 100% Coverage

Added all FastAPI endpoints that were missing from the CF package:

**New CF routes** (`packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes.py`):
- `GET /api/sessions/{id}` — single session status (uses `_session_status_item` DRY helper)
- `GET /api/sessions/{id}/snapshot` — snapshot without hijack lease
- `GET /api/sessions/{id}/events` — event history with `?limit=` and `?after_seq=` params
- `POST /api/sessions/{id}/mode` — set input mode (admin only)
- `POST /api/sessions/{id}/clear` — clear snapshot + request fresh snapshot (operator/admin)
- `POST /api/sessions/{id}/analyze` — trigger analysis + poll result (operator/admin)
- Prompt guards in `/hijack/{hid}/send`: `expect_prompt_id`, `expect_regex`, `timeout_ms`, `poll_interval_ms`
- Fixed hardcoded `limit=100` in `/hijack/{hid}/events` to use `?limit=` query param

**Supporting changes:**
- `ws_routes.py`: analysis frames from worker stored in `runtime.last_analysis`
- `do/session_runtime.py`: added `self.last_analysis: str | None = None`
- `entry.py`: added `/api/sessions/{id}[/sub]` to `_WORKER_ROUTE_PATTERNS`
- `contracts.py`: added `last_analysis` to `RuntimeProtocol` + TypedDicts for new endpoints
- `cf_types.py`: dead-code fallback in `json_response` marked `pragma: no cover`

**Tests (56 new):**
- `test_http_routes_coverage.py`: 43 new tests for all new endpoints + auth branches
- `test_http_routes_coverage2.py`: 9 tests for timeout/fallback paths (`_wait_for_prompt`, `_wait_for_analysis`, bad params)
- `test_ws_routes.py`: 2 tests for analysis frame handling
- `test_cf_cli.py`: 2 tests for `_run()` helper and `__main__` import

Result: 402 tests passing (up from 369), **100% coverage** (up from 99%).

---

### Code Review Fixes + DRY Refactors

**Security:**
- `src/undef/terminal/hijack/routes/websockets.py`: `secrets.compare_digest` for timing-safe worker token check

**Bug fixes:**
- `src/undef/terminal/hijack/hub/core.py`: `min_event_seq` updated AFTER append (not before); added `browser_count()` async method
- `src/undef/terminal/server/registry.py`: `_on_worker_empty` has 5-second grace period before deleting ephemeral sessions; calls `hub.browser_count()`

**DRY:**
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/auth/jwt.py`: added shared `extract_bearer_or_cookie()` function
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/entry.py`: removed local `_extract_bearer_or_cookie`, uses shared one
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/do/session_runtime.py`: `_extract_token` delegates to shared `extract_bearer_or_cookie`
- `packages/undef-terminal-frontend/src/app/api.ts`: removed duplicate local `apiJson`, imports from `server-common.js`
- `packages/undef-terminal-frontend/src/hijack-page.ts`: uses standard `/api/sessions/` routes instead of `/demo/session/` routes

**Input size limit:**
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/api/http_routes.py`: `_MAX_INPUT_CHARS = 10_000`, returns 400 if exceeded

**Hibernation warning:**
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/do/session_runtime.py`: WARNING log when `serializeAttachment` fails
- `packages/undef-terminal-cloudflare/src/undef_terminal_cloudflare/do/ws_helpers.py`: WARNING log when post-hibernation role fallback triggers in jwt mode

**Demo server + tests:**
- `scripts/demo_server.py`: added `/api/sessions/` routes (GET status, POST mode, POST restart) returning `SessionStatus`-compatible format
- `packages/undef-terminal-cloudflare/tests/test_fallback_imports.py`: mock `auth.jwt` modules now include `extract_bearer_or_cookie`
- `packages/undef-terminal-cloudflare/tests/test_http_routes_coverage.py`: `test_send_400_keys_too_long` covering new size check
- `tests/test_server_registry.py`: `_make_hub()` includes `browser_count = AsyncMock(return_value=0)`

---

### Dashboard Expansion (items 1, 2, 3, 5, 6)

**5. Dashboard — session badges, tags, restart button:**
- `packages/undef-terminal-frontend/src/app/api.ts`: added `restartSession()` API call
- `packages/undef-terminal-frontend/src/app/views/dashboard-view.ts`: session cards now show:
  - Recording badge (⏺ rec) / recording-available badge (⏺ saved)
  - Visibility badge for non-public sessions
  - Tag chips in a tag-list
  - Restart button with optimistic UI (disabled + "…" while pending)
- Event delegation on `content` div for `.btn-restart` clicks
- `src/undef/terminal/frontend/server-app-components.css`: added `.session-badges`, `.tag-list`, `.tag`, `.badge`, `.badge-visibility`, `.badge-rec`, `.badge-rec-avail`

**6. terminal-page.css — responsive CSS:**
- `safe-area-inset-*` env() for iOS notch/home-bar
- `user-select: none`, `-webkit-tap-highlight-color: transparent`, `touch-action: none` on `#app`

**1. terminal.html — asset path fix:**
- Reverted to relative paths (`terminal.js`, `terminal-page.css`, etc.) — works for both FastAPI `mount_terminal_ui` and `create_server_app` static mounts
- CF `entry.py` now injects `<base href="/assets/">` when serving `terminal.html` so relative refs resolve to `/assets/` in the CF context

**2. test_server_app.py — fitaddon assertions:**
- Added `assert "addon-fit.js" in r.text` to dashboard, session, operator, replay page tests

**3. CF coverage fixes:**
- `pragma: no cover` on CF-runtime-only import paths in `__init__.py`, `__main__.py`, `api/http_routes.py`, `api/ws_routes.py`, `auth/jwt.py`
- `entry.py`: imports `Response` at module level (alongside `WorkerEntrypoint`, `json_response`)
- `tests/test_cf_cli.py`: 13 new tests for `cli.py` and `assets.py` Path fallback / OSError branches
- `tests/test_fallback_imports.py`: adds `Response` to entry fallback mock

**tsconfig.json outDir fix:**
- `packages/undef-terminal-frontend/tsconfig.json`: corrected `outDir` from `../../../` (wrong — resolves to `undef-games/src/`) to `../../src/undef/terminal/frontend` (correct — resolves to `undef-terminal/src/`)
- Rebuilt all frontend JS: `api.js` (+restartSession), `dashboard-view.js` (+badges/tags/restart)

---

## Completed in Earlier Sessions

### Main Package — Server Coverage Push (98% → 99%)

Added 5 new test files covering `undef.terminal.server`:

| File | What it covers | Coverage gain |
|---|---|---|
| `tests/test_server_auth.py` | `auth.py`: JWT decode, bearer extraction, cookie handling, JWKS cache | 77% → 99% |
| `tests/test_server_runtime.py` | `runtime.py`: `_bridge_session` branches, `_run` error paths, backoff | 86% → 99% |
| `tests/test_server_authorization.py` | `authorization.py`: capability checks, visibility rules, browser role | 90% → 99% |
| `tests/test_server_registry.py` | `registry.py`: `_require_session`, `list_sessions`, recording entries | 88% → 99% |
| `tests/test_server_coverage2.py` | `routes/api.py`: 403/404/409/422 paths; `app.py`: CORS, 5xx metric | 88% → 99% |

### Docker Containers ✓ (fully verified, ports updated)
- `docker/Dockerfile.server` — FastAPI server; xterm.js + addon-fit.js injected; terminal renders correctly
- `docker/Dockerfile.cf` — pywrangler dev server; copies compiled frontend into `ui/static/`; wrangler.toml `[[rules]]` bundles JS/CSS; hijack demo page renders
- `docker/docker-compose.yml` — brings up both: FastAPI on **:27780**, CF worker on **:27788** (project-unique ports)
- 15 CF E2E tests pass against containerized CF worker (`REAL_CF_URL=http://localhost:27788 REAL_CF=1 -p no:xdist`)
- 15 CF E2E tests pass against production (`REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev REAL_CF=1 -p no:xdist`)
- 25 Playwright tests pass (hijack + terminal proxy + frontend coverage)
- Note: run e2e_ws + full_stack with `-p no:xdist` — xdist causes asyncio loop conflicts

### CF Package — All Items Complete (earlier sessions)
- Item 1 (Fleet KV), Item 2 (E2E), Item 3 (CF Access JWT), Item 4 (Alarm expiry), Item 5 (Snapshot endpoint)
- All hibernation bugs fixed in `do/session_runtime.py`

---

## Test Commands

```bash
# Main package (all non-playwright, non-e2e) — coverage enforced via addopts
uv run pytest tests/ --ignore=tests/test_e2e_live_hub_ws.py --ignore=tests/test_e2e_ssh_gateway.py --ignore=tests/test_e2e_telnet_gateway.py -q

# CF package unit tests — coverage enforced via addopts
cd packages/undef-terminal-cloudflare
uv run pytest tests/ --ignore=tests/test_e2e_ws.py --ignore=tests/test_e2e_full_stack.py -q

# Skip coverage for quick runs
uv run pytest tests/ --no-cov -q

# CF E2E (pywrangler dev, ~90s startup)
E2E=1 uv run pytest tests/ -m e2e -v

# CF E2E (real CF deployment)
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev uv run pytest tests/ -m e2e -v

# Mutation testing (slow, run pre-release)
uv run mutmut run

# Dead code / complexity / CVE scan
uv run vulture src/
uv run xenon --max-absolute C --max-modules B --average A src/
uv run pip-audit

# Build frontend JS
npm run build:frontend   # from repo root
```

---

## Next Steps

### 1. Publish to PyPI
Both packages at version `0.3.0`, metadata complete. Both at 100% coverage. Run `uv publish` from repo root.
