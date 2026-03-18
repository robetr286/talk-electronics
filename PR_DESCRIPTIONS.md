# PR templates for local_patch_repair split

Below are suggested PR titles and descriptions to use when opening the three smaller PRs derived from the recent local_patch_repair work (worker, tests, gating). These branches were created without rewriting history and pushed to remote:

- feature/local-patch-base — common code fixes for `local_patch_repair` (lint, bugfixes)
- feature/local-patch-worker — worker wrapper/script for local_patch_repair
- feature/local-patch-tests — unit tests for `local_patch_repair` internals
- feature/local-patch-gating — gating/regression script that runs the worker and validates results

## PR: feature/local-patch-base
Title: fix(local_patch_repair): base fixes and validation utilities

Description:
- Adds lint fixes and core improvements to `debug/graph_repair_validation/local_patch_repair.py`.
- Includes diagnostic artifacts (local_results.json) and helper scripts used by downstream worker/tests/gating.
- Purpose: provide a stable, testable base for workers/tests/gating without changing other parts of the repo.

## PR: feature/local-patch-worker
Title: feat(worker): add `local_patch_repair` worker wrapper

Description:
- Adds `scripts/local_patch_repair_worker.py` — a lightweight worker wrapper to run local patch repair experiments.
- Designed to be run under `scripts/run_with_watchdog.py` in CI or by developers, and to produce `debug/graph_repair_validation/local_results` artifacts.
- This PR depends on `feature/local-patch-base` (base fixes) — start by reviewing the worker code and CLI behavior.

## PR: feature/local-patch-tests
Title: test(local): add unit tests for `local_patch_repair` internals

Description:
- Adds focused unit tests for Bresenham line drawing, endpoints detection and try_connect logic: `tests/test_local_patch_repair.py`.
- These tests validate core algorithmic behaviors and protect against regressions when tuning repairs.
- This PR depends on `feature/local-patch-base`.

## PR: feature/local-patch-gating
Title: test(gating): add gating/regression runner for `local_patch_repair` results

Description:
- Adds `scripts/local_patch_repair_gate.py` — a gating script that executes the worker and validates `local_results.json` against acceptance thresholds (IoU, endpoints reduction).
- Intended for CI gating so that repair changes must pass the acceptance criteria before being merged into `main`.
- This PR depends on `feature/local-patch-base` and `feature/local-patch-worker`.

---

If you'd like, I can open draft PRs using these branches or create issue templates to share with reviewers.
