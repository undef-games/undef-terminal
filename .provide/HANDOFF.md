# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: **1096 tests passing**. `undef.terminal.server` at **99% coverage**. Pre-commit hooks active. `ty check src/undef/` passes clean.
- **CF package (`undef-terminal-cloudflare`)**: **346 unit tests passing** + E2E tests (`-m e2e`). Total: **1442**. Overall: **94% coverage**. All reachable lines at 100%: `session_runtime.py`, `entry.py`, `ui/assets.py`, `ws_helpers.py`, `contracts.py`, `config.py`, `state/store.py`, `state/registry.py`, `bridge/hijack.py`.

---

## Completed in Most Recent Sessions

### Main Package — Server Coverage Push (98% → 99%)

Added 5 new test files covering `undef.terminal.server`:

| File | What it covers | Coverage gain |
|---|---|---|
| `tests/test_server_auth.py` | `auth.py`: JWT decode, bearer extraction, cookie handling, JWKS cache | 77% → 99% |
| `tests/test_server_runtime.py` | `runtime.py`: `_bridge_session` branches, `_run` error paths, backoff | 86% → 99% |
| `tests/test_server_authorization.py` | `authorization.py`: capability checks, visibility rules, browser role | 90% → 99% |
| `tests/test_server_registry.py` | `registry.py`: `_require_session`, `list_sessions`, recording entries | 88% → 99% |
| `tests/test_server_coverage2.py` | `routes/api.py`: 403/404/409/422 paths; `app.py`: CORS, 5xx metric | 88% → 99% |

Remaining 20 lines (1%) are legitimate integration-only paths:
- `runtime.py`: WS reconnect backoff reset requires a live WS connection
- `auth.py`: JWKS cache edge case (triggered only at cache capacity + concurrent access)
- `registry.py`: Recording file blank-line branches (covered in tail/offset modes)
- `routes/api.py`: Race-condition KeyError paths on PATCH and quick-connect

### CF Package — Coverage Improvements

New file `tests/test_coverage2.py`:
- `bridge/hijack.py`: **93% → 100%** (heartbeat/release edge cases, `can_send_input` when none)
- `state/registry.py`: **78% → 100%** (KV delete/put/list/get failure paths, empty key_name skip)
- `auth/jwt.py`: **60% → 78%** (empty sub, string roles, non-iterable roles, JWKS no-match)
- `state/store.py`: **67% → 74%** (`clear_lease`, `save_input_mode`, `min_event_seq`)

Remaining gaps in `do/session_runtime.py` (23%) and `entry.py` (38%) require the actual Cloudflare runtime — covered by E2E tests only.

### CF Package — Full-Stack E2E Tests (`test_e2e_full_stack.py`)

Tests `HostedSessionRuntime` (Python) → CF DO (WS) → Browser WS proxy chain:

| Test | Markers | What it verifies |
|---|---|---|
| `test_hosted_runtime_connects_and_appears_in_sessions` | `@e2e` | Runtime connects, status().connected == True, appears in /api/sessions |
| `test_hosted_runtime_snapshot_reaches_browser` | `@e2e` | Browser WS receives snapshot from shell connector |
| `test_hosted_runtime_hijack_cycle` | `@e2e` | Acquire hijack, GET snapshot, release while runtime live |
| `test_two_browsers_receive_same_snapshot` | `@e2e @real_cf` | Two browsers both receive worker snapshot broadcast |
| `test_state_persists_after_do_hibernation` | `@real_cf @slow` | SQLite snapshot survives ~40s DO hibernation cycle |

Run:
```bash
E2E=1 uv run pytest tests/test_e2e_full_stack.py -v
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev uv run pytest tests/test_e2e_full_stack.py -v
```

### Shell Connector + Quick-Connect (earlier sessions)
- `demo` → `shell` rename: `ShellSessionConnector` in `connectors/shell.py`
- Quick-connect: `GET /connect` page + `POST /api/connect` for ephemeral sessions
- `SessionDefinition.ephemeral` field; auto-deleted on last browser disconnect

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
uv run pytest tests/ --ignore=tests/test_e2e_*.py --ignore=tests/test_e2e_playwright_proxy.py -q

# CF E2E (pywrangler dev, ~90s startup)
E2E=1 uv run pytest tests/ -m e2e -v

# CF E2E (real CF deployment)
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev uv run pytest tests/ -m e2e -v

# CF hibernation test (slow, real CF only)
REAL_CF=1 SLOW=1 REAL_CF_URL=https://... uv run pytest tests/test_e2e_full_stack.py::test_state_persists_after_do_hibernation -v -s
```

---

## Next Steps

### 1. Frontend TS Source
- Moved to `packages/undef-terminal-frontend/src/` (npm workspace package).
- Root `package.json` is now workspace root (`undef-terminal-root`); delegates via `--workspace=`.
- Run `npm run build:frontend` from repo root to compile to `src/undef/terminal/frontend/`.
- `biome.json` and `.pre-commit-config.yaml` updated to new paths.

### 2. Docker Containers ✓ (verified working)
- `docker/Dockerfile.server` — FastAPI reference server; builds and passes health/sessions/dashboard checks
- `docker/Dockerfile.cf` — pywrangler dev server (Node 20 + Python 3.11); fixed: `ca-certificates`, `wrangler@latest`, `uv sync --extra dev`
- `docker/docker-compose.yml` — brings up both on ports 8780 + 8788
- `docker/server.toml` — default dev config (shell session, no JWT)
- 12 CF E2E tests pass against the containerized CF worker (`REAL_CF_URL=http://localhost:8788 REAL_CF=1`)

### 3. CF Access JWT — Groups-Based Role Mapping
Config already supports this — no code changes needed.
1. Configure SCIM / CF Access identity groups in Zero Trust dashboard
2. Add a custom claim (e.g. `"groups"`) to the CF Access application
3. Set `JWT_ROLES_CLAIM=groups` so the worker reads roles from that claim

### 4. Publish to PyPI
Both packages at version `0.3.0`, metadata complete. Run `uv publish` from repo root.
