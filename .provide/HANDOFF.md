# undef-terminal: Handoff

## Current State

- **Main package (`undef-terminal`)**: **1931 tests passing** (excl. Playwright). **100% branch coverage** (5121 stmts, 1394 branches, 0 missing). Pre-commit hooks active.
- **CF package (`undef-terminal-cloudflare`)**: **449 unit tests passing** + 20 skipped. **100% branch coverage** (1536 stmts, 524 branches, 0 missing).
- **Playwright**: **35 tests passing** (9 example/proxy/coverage + 6 server pages + 20 hijack).
- **CF E2E**: 14/14 passing against live worker.
- **Mutation score**: 67.3% (5972 killed, 2777 survived across 8877 mutants). Survivors concentrated in connectors, CLI, UI, bridge.
- **Both packages at version 0.3.0**
- **Dependency**: `undef-telemetry>=0.3` (structured logging via structlog)

---

## Completed in This Session

### LLM Review Implementation (Plan B/C)

- **JWKS `time.monotonic()`**: Replaced `time.time()` with `time.monotonic()` in CF auth/jwt.py cache TTL (2 sites). Consistent with http_routes.py.
- **Inline styles round 2**: Extracted 15 CSS utility classes (`.select-sm`, `.filter-input`, `.status-dot`, `.card`, `.page-shell`, `.pre-block`, `.preset-card`, `.nav-btn`, `.btn-sm`, `.metric-grid`, etc.) across 13 component files.

### Replay Improvements

- **ANSI color rendering**: Added `ansiToHtml.ts` utility (SGR parser: 16/256/truecolor, bold/dim/italic/underline/inverse). `ScreenPreview` now defaults to "Rendered" mode with Raw/Rendered toggle.
- **Playback timer**: Fixed play button (was no-op). Uses real-time deltas between event timestamps, scaled by speed selector (0.5x/1x/2x/4x). Gaps clamped to 2s max.

### undef-telemetry Integration

- **Replaced all stdlib logging**: 22 source files migrated from `import logging` / `logging.getLogger(__name__)` to `from undef.telemetry import get_logger` / `get_logger(__name__)`. Zero `import logging` remaining.
- **Namespace package fix**: Removed `src/undef/__init__.py` so `undef.terminal` and `undef.telemetry` coexist as implicit namespace packages.
- **pytest11 plugin**: Added entry point to undef-telemetry so caplog auto-works when installed. Removed manual structlog conftest config from undef-terminal.
- **Pre-commit hooks**: Added `undef-telemetry` + `structlog` to mypy/ty additional_dependencies.
- **Coverage scoping**: Changed `--cov=undef` to `--cov=undef.terminal` so coverage doesn't measure telemetry code.
- **Default fix in undef-telemetry**: `strict_event_name` default changed from `True` to `False` (opt-in, not opt-out).

### Security & Deployment

- **Production auth**: `AUTH_MODE=jwt` in wrangler.toml (was `dev`). Local dev uses `.dev.vars` with `AUTH_MODE=dev`.
- **CF Access**: Worker rejects unauthenticated requests. CF Access Application needs manual setup in Zero Trust dashboard for login redirect.
- **Deployed**: `https://undef-terminal-cloudflare.neurotic.workers.dev` with JWT auth.

### Build & Tooling

- **pywrangler dev loop fix**: Set `watch_dir = "../../src/undef/terminal/frontend"` to prevent infinite rebuild (cp target was inside watched dir).
- **SPDX headers**: Added to all 56 TS/TSX/JS source files in both frontend packages.
- **Playwright tests**: Updated for new React app UI (breadcrumbs, comboboxes, split operator/replay tests).
- **Stale assets**: Cleaned old frontend build artifacts.
- **Hypothesis fix**: Suppressed `HealthCheck.differing_executors` for async hypothesis tests.
- **Mutmut config**: Excluded e2e tests (macOS CPython segfault in proxy_bypass under forked processes).
- **Dead code**: Removed redundant `if output != "raw"` guard in `_clean_snapshot`.

---

## Test Commands

```bash
# Main package (100% coverage)
uv run pytest tests/ --ignore=tests/playwright -q

# CF package (100% coverage)
cd packages/undef-terminal-cloudflare && uv run pytest tests/ --no-cov -q

# Playwright (all 35)
uv run pytest tests/playwright/ -v --headed --no-cov -p no:randomly
uv run pytest tests/playwright/test_server.py tests/playwright/test_hijack.py -v --headed --no-cov -p no:randomly

# CF E2E (production)
REAL_CF=1 REAL_CF_URL=https://undef-terminal-cloudflare.neurotic.workers.dev \
  uv run pytest packages/undef-terminal-cloudflare/tests/test_e2e_wrangler.py \
  packages/undef-terminal-cloudflare/tests/test_e2e_ws.py -v -p no:randomly -p no:xdist --no-cov

# Mutation testing
uv run mutmut run
```

---

## Remaining for Release

- [ ] `git push` (12 commits ahead of origin)
- [ ] CF Access Application in Zero Trust dashboard (browser login redirect)
- [ ] Mutation score improvement (67.3% → target TBD; 2777 survivors across 43 files)
- [ ] PyPI publish (`uv build && uv publish`)
- [ ] CHANGELOG.md (optional — info is here)
