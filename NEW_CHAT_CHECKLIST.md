# New LLM Chat: Full Mission Brief + Execution Checklist

## 1) What this work is trying to solve

This repo has already had a set of security and correctness fixes applied for hosted terminal server behavior. The next LLM should **not re-design the system**. Its job is to:

- Preserve the existing hardening fixes.
- Improve engineering quality by eliminating current `ty` static type diagnostics in targeted batches.
- Keep strict lint/type gates (`ruff`, `ty`) strong.
- Avoid regressions in runtime/auth/frontend behavior.

The practical point is to move this codebase toward a clean, strict CI-quality state without destabilizing recent security changes.

## 2) Current state (important context)

The following hardening changes are already in place and should be treated as baseline behavior:

- Auth dependency enforcement on hub/API routes for non-`none/dev` modes.
- Role policy no longer trusts client role hints outside permissive local modes.
- Replay page uses configured app mount path instead of hardcoded `/app` assumptions.
- Frontend dashboard/operator views escape dynamic HTML interpolations.
- Runtime loop now cancels and awaits pending tasks to avoid cancellation leaks.
- Regression coverage exists in `tests/test_server_security_regressions.py` for those areas.

Targeted verification for those areas already passed previously:

- `npm run build:frontend`
- `uv run pytest -q tests/test_server_security_regressions.py tests/test_server_config.py tests/test_server_app.py`
- `uv run ruff check` on touched files

Known remaining problem:

- `uv run ty check` still reports many diagnostics across other files (pre-existing backlog outside the five hardened fixes).

## 3) Absolute rules for the new LLM

- Work in: `/Users/tim/code/gh/undef-games/undef-terminal`
- Read and follow `AGENTS.md`.
- Do not revert unrelated changes in the worktree.
- Do not use destructive git operations unless explicitly asked.
- Do not weaken lint/type strictness globally to make warnings disappear.
- Do not alter core auth/role/runtime behavior unless a failing test proves a real bug.
- Keep TypeScript source and compiled frontend JS aligned when frontend files are changed.

## 4) Files that represent the existing hardening baseline

Do not accidentally undo intent in these:

- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/server/app.py`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/server/policy.py`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/server/runtime.py`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/server/ui.py`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/server/routes/pages.py`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/frontend-src/app/views/dashboard-view.ts`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/frontend-src/app/views/operator-view.ts`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/frontend/app/views/dashboard-view.js`
- `/Users/tim/code/gh/undef-games/undef-terminal/src/undef/terminal/frontend/app/views/operator-view.js`
- `/Users/tim/code/gh/undef-games/undef-terminal/tests/test_server_security_regressions.py`

## 5) Ignore this unrelated worktree noise

Do not spend time “fixing” these unless explicitly asked:

- `.uterm-recordings/scratch.jsonl`
- `test-results/**` (playwright artifacts/video churn)

## 6) Primary objective for this new chat

Drive down and resolve the `ty` backlog in safe, incremental batches, starting with smallest-scope test files, while keeping current behavior stable.

## 7) Recommended work order

Start with these files first:

1. `/Users/tim/code/gh/undef-games/undef-terminal/tests/test_ssh_transport.py`
2. `/Users/tim/code/gh/undef-games/undef-terminal/tests/test_cli.py`

Then continue with:

3. `/Users/tim/code/gh/undef-games/undef-terminal/tests/test_e2e_ssh_gateway.py`
4. `/Users/tim/code/gh/undef-games/undef-terminal/tests/test_websocket_transport.py`

Then repeat for additional reported `ty` files until clean.

## 8) Exact execution loop (do this per batch)

1. Capture baseline:
   - `git status --short`
   - `uv run ty check`
2. Pick one or two files from the priority list.
3. Apply minimal type-safe fixes with no behavioral changes.
4. Run targeted tests for touched area.
5. Run:
   - `uv run ruff check <touched files>`
   - `uv run ty check`
6. If frontend touched, also run:
   - `npm run build:frontend`
7. Commit only intentional changes for that batch.
8. Repeat.

## 9) Fix strategy guidance for ty errors

Prefer these patterns:

- Add precise annotations or helper Protocols for mocks/fakes used in tests.
- Use narrow `cast(...)` where runtime behavior is already safe and obvious.
- Replace invalid fake object shapes with typed test doubles matching method contracts.
- Remove stale `# type: ignore` only when unnecessary.

Avoid these patterns:

- Broad `Any` spread through production code.
- Global config changes to suppress diagnostics.
- Rewriting large modules to satisfy one warning.

## 10) Definition of done

The work is done when all are true:

- `uv run ruff check src tests` passes.
- `uv run ty check` passes (or remaining diagnostics are explicitly documented and intentionally deferred).
- Relevant `pytest` tests pass for all touched modules.
- `npm run build:frontend` passes if frontend changed.
- `git status --short` shows only intentional modifications.
- Commit message clearly states batch scope and risk.

## 11) Starter prompt to paste into a new chat

Use this verbatim:

"Work in `/Users/tim/code/gh/undef-games/undef-terminal`. Continue from the current worktree without reverting unrelated files. Your goal is to eliminate `ty` diagnostics incrementally while preserving existing security hardening and behavior. Start with `tests/test_ssh_transport.py` and `tests/test_cli.py`, make minimal safe fixes, run targeted tests plus `ruff` and `ty` after each batch, keep frontend TS/compiled JS in sync if touched, and commit in small scoped batches."
