# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: **1114 tests passing**. `undef.terminal.server` at **99% coverage** (config.py, pages.py, ui.py, models.py all 100%). Pre-commit hooks active. `ty check src/undef/` passes clean.
- **CF package (`undef-terminal-cloudflare`)**: **359 unit tests passing** + E2E tests (`-m e2e`). Total: **1473**. Overall: **94% coverage**. All reachable lines at 100%.

---

## Completed in Most Recent Session

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

### Docker Containers ✓ (fully verified)
- `docker/Dockerfile.server` — FastAPI server; xterm.js + addon-fit.js injected (fitaddon_cdn); terminal renders correctly
- `docker/Dockerfile.cf` — pywrangler dev server; copies compiled frontend into `ui/static/`; wrangler.toml `[[rules]]` bundles JS/CSS; hijack demo page renders
- `docker/docker-compose.yml` — brings up both on ports 8780 + 8788
- 12 CF E2E tests pass against containerized CF worker (`REAL_CF_URL=http://localhost:8788 REAL_CF=1`)

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
