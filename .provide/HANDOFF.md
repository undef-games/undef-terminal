# undef-terminal: Handoff

## Current State (2026-03-21)

- **Main package (`undef-terminal`)**: ~3846 tests collected. 100% branch coverage on all
  Python packages. Pre-commit hooks active and passing.
- **CF package (`undef-terminal-cloudflare`)**: Tests fail collection locally with
  `ModuleNotFoundError: undef_terminal_cloudflare` — package must be installed from its own
  environment (`cd packages/undef-terminal-cloudflare && uv sync`). Deployed to
  `https://undef-terminal-cloudflare.neurotic.workers.dev` with JWT auth via Cloudflare Access.
- **Frontend**: TypeScript tests pass (vitest). Biome lint+format clean. TypeScript typecheck clean.

## What Was Done

### 2026-03-21: Detection pipeline error isolation (e0f6c14, bbsbot 819fc17)
- `saver.py`: hash recorded after write — prevents silent screen loss on I/O error;
  dup-slot exhaustion raises `OSError` instead of silently overwriting
- `engine.py`: each hook wrapped in `try/except` — one failing hook no longer stops others
  or propagates out of `process_screen()`; saver call wrapped similarly
- `models.py`: `PromptDetection.buffer` typed as `ScreenBuffer | None` (was `Any`)
- `detector.py`: documented case-sensitivity asymmetry (negative=IGNORECASE, positive=exact)
  and cursor-flag fingerprint trade-off; blocking I/O note added to `save_screen()` docstring
- `debug_screens.py` (bbsbot): added `.detector` null guard

### 2026-03-21: 100% Python coverage + TS thresholds (e69f06f)
- Achieved 100% coverage across all Python packages
- Added shell package tests (`tests/shell/`)
- Added remaining frontend TS test files

### 2026-03-21: Shell package (939ea22)
- `ushell` package added with CF DO adapter
- Shell tests in `tests/shell/` cover commands, connector, output, REPL, sandbox

### 2026-03-21: Operator view redesign (9008557) — COMPLETE
- Structured sidebar: Input Mode toggle (Shared/Exclusive), Actions, Session Info table,
  tags, restart button, terminal widget in right panel
- Uses `server-app-*.css` classes; works on both FastAPI and CF deployments

### CF Access JWT Auth + SPA
- JWT verification via Web Crypto API in Pyodide (no `cryptography` C extension)
- Validates exp, nbf, iss, aud; falls back to PyJWT in tests
- wrangler.toml: `AUTH_MODE=jwt`, JWKS URL, issuer, audience (AUD tag), RS256
- Root `/` serves SPA dashboard; all `/app/*` routes handled
- `POST /api/connect`, `DELETE /api/sessions` implemented

## Known Issues

- CF tests require the CF package installed separately — not runnable from main dev venv
- `tests/detection/test_rules.py` shows `M` in `git status` despite no content diff —
  likely a git index artifact; harmless

## What's Next

No explicit backlog. Candidates:
- Investigate CF test collection failures in the dev venv
- Any new game/BBS feature work driven by bbsbot session needs
