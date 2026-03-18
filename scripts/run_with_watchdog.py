#!/usr/bin/env python
"""Run a command with monitoring (watchdog).

Features:
- overall timeout (kill after N seconds)
- idle timeout (kill if no stdout/stderr activity for M seconds)
- optional max restarts
- captures logs to a file

Usage (simple):
  python scripts/run_with_watchdog.py --cmd "python debug/.../script.py --arg x" --timeout 3600 --idle 300

This is intentionally minimal — pure-Python, cross-platform and easy to call
from CI or other wrapper scripts.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path


def now():
    return datetime.utcnow().isoformat() + "Z"


def monitor_process(cmd, timeout=None, idle_timeout=None, logfile=None, max_restarts=0):
    """Run cmd (list) and monitor stdout/stderr activity.

    Returns exit code. If killed by watchdog, returns non-zero.
    """
    logfile = Path(logfile) if logfile else None

    while True:
        started_at = time.time()
        last_output_at = time.time()

        if logfile:
            f = logfile.open("a", encoding="utf8")
            cmd_display = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
            f.write(f"{now()} RUN START: {cmd_display}\n")
        else:
            f = None

        # Accept both list and string. On Windows Popen with shell=True is more
        # tolerant for full command strings (paths with spaces). On POSIX we prefer
        # to run with a list (no shell) when possible.
        use_shell = False
        if isinstance(cmd, str):
            # On Windows use shell=True for string commands; on POSIX split into a list for safety.
            if os.name == "nt":
                use_shell = True
            else:
                cmd = shlex.split(cmd)

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True, shell=use_shell
        )

        def reader_loop():
            nonlocal last_output_at
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    last_output_at = time.time()
                    if f:
                        f.write(f"{now()} OUT: {line}")
                        f.flush()
                    else:
                        print(line, end="")
            except Exception:
                pass

        t = threading.Thread(target=reader_loop, daemon=True)
        t.start()

        # monitor loop
        while True:
            rc = proc.poll()
            now_time = time.time()
            # check overall timeout
            if timeout and (now_time - started_at) > timeout:
                proc.kill()
                if f:
                    f.write(f"{now()} KILLED: timeout after {timeout}s\n")
                    f.flush()
                return 124  # convention: killed by timeout

            # check idle timeout
            if idle_timeout and (now_time - last_output_at) > idle_timeout:
                proc.kill()
                if f:
                    f.write(f"{now()} KILLED: idle timeout {idle_timeout}s\n")
                    f.flush()
                return 125  # convention: killed due to idle

            if rc is not None:
                # process finished normally
                if f:
                    f.write(f"{now()} RUN END rc={rc}\n")
                    f.flush()
                    f.close()
                return rc

            time.sleep(0.5)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run a command with watchdog (timeouts / idle detection)")
    p.add_argument("--cmd", required=True, help="Command to run (string). Quoted")
    p.add_argument("--timeout", type=int, default=0, help="Overall timeout in seconds (0 = disabled)")
    p.add_argument("--idle", type=int, default=0, help="Idle timeout in seconds (0 = disabled)")
    p.add_argument("--log", default=None, help="Append output to logfile")
    p.add_argument("--max-restarts", type=int, default=0, help="Max automatic restarts on non-zero exit")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    # keep original cmd string where provided; monitor_process will handle it
    cmd = args.cmd
    timeout = args.timeout or None
    idle = args.idle or None
    rc = monitor_process(cmd, timeout=timeout, idle_timeout=idle, logfile=args.log, max_restarts=args.max_restarts)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
