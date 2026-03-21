# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: 3778 tests passing. 100% branch coverage. Pre-commit hooks active.
- **CF package (`undef-terminal-cloudflare`)**: 465 unit tests passing (6 pre-existing failures). Deployed to `https://undef-terminal-cloudflare.neurotic.workers.dev` with JWT auth via Cloudflare Access.
- **Frontend**: 110 vitest tests passing. Biome lint+format clean. TypeScript typecheck clean.

## What Was Done (March 21 2026)

### CF Access JWT Auth
- Cloudflare Access policy (Allow, Everyone) protects worker domain
- JWT verification via Web Crypto API in Pyodide (no `cryptography` C extension)
- Validates exp, nbf, iss, aud; falls back to PyJWT in tests
- wrangler.toml: `AUTH_MODE=jwt`, JWKS URL, issuer, audience (AUD tag), RS256

### Deployment Fix
- `from workers import WorkerEntrypoint/DurableObject/Response` at top of entry.py — Pyodide validation must see real handler classes
- Stub `SessionRuntime(_DurableObject)` in fallback for validation phase
- `_parent_dir` added to sys.path for package imports
- Re-synced vendored `python_modules/`

### Frontend Bug Fixes (hijack.ts)
- Removed local echo (caused double characters when server wraps echo in ANSI)
- Scoped reconnect animation to `_scheduleReconnect()` only
- Remapped status colors: green=active, orange=waking/other-hijack, red=disconnected
- Added `_stopReconnectAnim()` to `dispose()`

### SPA on CF Worker
- Root `/` serves SPA dashboard with bootstrap JSON
- All `/app/*` routes: dashboard, connect, session/{id}, operator/{id}, replay/{id}
- `POST /api/connect` creates sessions in KV
- `DELETE /api/sessions` purges stale KV entries
- Terraform: `cloudflare_workers_custom_domain` with hostname/environment

## Next: Operator View Redesign

### Problem
`operator-view.js` renders a basic debug layout with raw JSON dump instead of structured operator controls. Affects both FastAPI and CF deployments.

### Target Layout (matches FastAPI server's polished version)
- Input Mode toggle (Shared | Exclusive)
- Actions section (Analyze | View replay | Clear runtime)
- Session Info table (Connector, State, Owner, Visibility, Auto-start)
- Tags display
- Restart session button
- Terminal widget filling the right panel

### Key Files
- `src/undef/terminal/frontend/app/views/operator-view.js` — the view to redesign
- `src/undef/terminal/frontend/app/state.js` — `loadOperatorWorkspaceState()` returns data
- `src/undef/terminal/server/routes/pages.py` — FastAPI operator route (reference)
- `src/undef/terminal/server/ui.py` — `session_page_html()` bootstrap structure (reference)
- CSS: `server-app-foundation.css`, `server-app-layout.css`, `server-app-components.css`, `server-app-views.css`

### Checklist
- [ ] Redesign `operator-view.js` with structured sections instead of JSON dump
- [ ] Use existing CSS classes from `server-app-*.css`
- [ ] Map `loadOperatorWorkspaceState()` data to structured HTML
- [ ] Test on both localhost and CF
- [ ] `npm run build:frontend` then `uv run pywrangler deploy`
- [ ] Investigate 6 pre-existing CF test failures
