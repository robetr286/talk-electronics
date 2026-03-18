# Process monitoring and watchdog policy 🔧

This document describes the official project policy and how-to guidance for running long-running worker scripts, validation pipelines and automated jobs safely using the provided watchdog wrapper (`scripts/run_with_watchdog.py`). The goal is to prevent hung jobs, capture logs, and keep CI / developer machines predictable.

## Why we use a watchdog

- Some processing scripts (image processing, thinning, repair algorithms) can hang or run much longer than expected depending on inputs.
- To avoid blocking CI, wasting resources, or leaving long-running processes in developer machines, we wrap those scripts with the watchdog that enforces a total runtime limit and an idle (no-output) timeout.

## Default policy

- All long-running workers and experimental pipelines should be run through `scripts/run_with_watchdog.py` by default.
- Default timeouts used across worker/gate scripts are:
  - overall timeout: 30 minutes (1800 seconds)
  - idle timeout: 10 minutes (600 seconds)

These defaults are conservative and chosen to balance safety and expected runtime for our validation experiments. They are configurable per script invocation.

## Where to use the watchdog

- Worker wrappers (e.g. `scripts/local_patch_repair_worker.py`) — should run via watchdog by default.
- Gate / CI runner scripts that execute experiments (e.g. `scripts/local_patch_repair_gate.py`) — run guarded by watchdog to prevent stuck pre-merge checks.
- Any new ad-hoc experiments, batch processors or scheduled jobs — add one-line invocation through the watchdog for safety.

## How to run a command through the watchdog

Example: run the local patch repair worker with default timeouts (recommended)

Windows / PowerShell (project uses this by default):

```powershell
# Runs worker with default overall=1800s and idle=600s
python scripts/run_with_watchdog.py -- python scripts/local_patch_repair_worker.py --arg1 v
```

Explicitly set timeouts (example: 1 hour overall, 20 minutes idle)

```powershell
python scripts/run_with_watchdog.py --overall-timeout 3600 --idle-timeout 1200 -- python scripts/local_patch_repair_worker.py --arg1 v
```

Notes:
- On Windows, `run_with_watchdog.py` uses shell=True to run the child command string; pass the command after a `--` separator.
- The watchdog captures stdout/stderr to the console and can optionally write a logfile with `--logfile <path>`.

## CI integration guidance

- Use the watchdog as a wrapper for any CI step that runs long-running scripts.
- Make sure test/validation runners invoked by CI exit with non-zero status when the watchdog kills them; CI jobs should fail visibly.
- Example GitHub Actions step (pseudo):

```yaml
- name: Run local patch repair gate
  run: |
    python scripts/run_with_watchdog.py --overall-timeout 1800 --idle-timeout 600 -- python scripts/local_patch_repair_gate.py --run
```

## Troubleshooting

- If a job is getting killed by the watchdog frequently, inspect logs to find the cause and either:
  1. Fix the code so it doesn't hang or produce excessive idle periods, or
  2. Increase the watchdog timeout for that particular job only (but prefer to make jobs faster/robust when possible).

## Developer notes

- When adding a new worker or pipeline script to the repo, please add a short section to its docstring or docs/ explaining the recommended watchdog settings for that script.
- Please also add unit tests for anything that could cause long blocking operations where feasible.

---

If you have suggestions for improved default timeouts or additional features (e.g., heartbeat files, better logging formats), add them to the backlog and propose a PR to iterate on the policy.
