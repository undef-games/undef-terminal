# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: **1134 tests passing** (all Playwright included). Pre-commit hooks active. `ty check src/undef/` passes clean.
- **CF package (`undef-terminal-cloudflare`)**: **369 unit tests passing** + 5 skipped + E2E tests (`-m e2e`). Overall: **99% coverage** (all reachable lines at 100%).

---

## Completed in Most Recent Session

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
# Main package (all non-playwright)
uv run pytest tests/ --ignore=tests/test_zzz_playwright_hijack.py -q

# Main package coverage
uv run pytest tests/ --ignore=tests/test_zzz_playwright_hijack.py --cov=undef.terminal.server --cov-report=term-missing -q

# CF package unit tests
cd packages/undef-terminal-cloudflare
uv run pytest tests/ --ignore=tests/test_e2e_ws.py --ignore=tests/test_e2e_full_stack.py -q

# CF E2E (pywrangler dev, ~90s startup)
E2E=1 uv run pytest tests/ -m e2e -v

# CF E2E (real CF deployment)
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev uv run pytest tests/ -m e2e -v

# Build frontend JS
npm run build:frontend   # from repo root
```

---

## Next Steps

### 1. Frontend TS Source ✓ (complete)
- Source: `packages/undef-terminal-frontend/src/`
- Output: `src/undef/terminal/frontend/` (Python package-data)
- `tsconfig.json` outDir: `../../src/undef/terminal/frontend` (2 levels up from package dir)
- Run `npm run build:frontend` from repo root

### 2. Publish to PyPI
Both packages at version `0.3.0`, metadata complete. Run `uv publish` from repo root.

### 3. CF Access JWT — Groups-Based Role Mapping
Config already supports this — no code changes needed.
1. Configure SCIM / CF Access identity groups in Zero Trust dashboard
2. Add a custom claim (e.g. `"groups"`) to the CF Access application
3. Set `JWT_ROLES_CLAIM=groups` so the worker reads roles from that claim
