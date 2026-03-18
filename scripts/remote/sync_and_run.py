#!/usr/bin/env python3
"""Sync repo to remote droplet and run a command there.

Simple, practical helper that uses `rsync` and `ssh`. Assumes you have SSH access to the droplet.
"""

import argparse
import subprocess
from pathlib import Path


def run(cmd, **kwargs):
    print("$", " ".join(map(str, cmd)))
    subprocess.check_call(cmd, **kwargs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--remote-path", default="~/work/flask_gpt_codex")
    p.add_argument("--local-path", default=".")
    p.add_argument("--run-cmd", required=True, help="Command to run on remote (quoted)")
    p.add_argument("--fetch-results", action="store_true", help="Rsync the remote runs/<name> back to local")
    p.add_argument("--exclude", action="append", default=[".git", "runs", "data"], help="rsync excludes")
    args = p.parse_args()

    local = Path(args.local_path).resolve()
    remote = args.remote_path
    userhost = f"{args.user}@{args.host}"

    rsync_cmd = [
        "rsync",
        "-avz",
        "--delete",
    ]
    for e in args.exclude:
        rsync_cmd += ["--exclude", e]
    rsync_cmd += [f"{str(local)}/", f"{userhost}:{remote}/"]

    print("Syncing code to remote...")
    run(rsync_cmd)

    # Run command via ssh inside remote path; use nohup to keep it running
    ssh_cmd = [
        "ssh",
        f"{userhost}",
        f"mkdir -p {remote}/debug && cd {remote} && nohup {args.run_cmd} > debug/remote_run.log 2>&1 & echo $!",
    ]
    print("Starting remote job...")
    out = subprocess.check_output(ssh_cmd).decode().strip()
    print("Remote started, PID:", out)

    if args.fetch_results:
        print("Fetching results (runs/) back to local...")
        run(["rsync", "-avz", f"{userhost}:{remote}/runs/", str(local / "runs/")])


if __name__ == "__main__":
    main()
