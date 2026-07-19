# Flaky Tests — Known Issues & Recovery Plan

## Current State (2026-07)

4 tests fail sporadically (~30-50% of random-seed runs). Root cause: 84 core modules use module-level singleton pattern. Conftest-based resets cover 76 of 84, but 4 have deep ordering dependencies that require per-module ContextVar migration.

## Affected Tests

| Test | Failure Rate | Root Cause |
|------|-------------|------------|
| test_tool_router.py (2 tests) | ~60% | `_internal_tools` dict pollution across test classes |
| test_background.py::test_reset | ~50% | `BackgroundManager` singleton reset race |
| test_phase11_failure_learning.py::test_stats_through_layer | ~30% | `ValidationLayer.__init__` cross-module state |

## Current Mitigation

- CI runs with `-m "not flaky"` for quick gate
- CI retries each failing job once via `continue-on-error: true`
- Marked with `@pytest.mark.flaky(reason="...")` for documentation

## Recovery Plan

When pipeline_tools or background modules undergo significant refactoring:

1. Replace `_x = None` singletons with `ContextVar` pattern
2. Remove `@pytest.mark.flaky` markers
3. Verify with 10 consecutive random-seed full-suite runs

Estimated effort: 2-3 days. Not prioritized because impact is internal quality only — no user-facing effect.
