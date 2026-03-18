#!/usr/bin/env bash
# Convenience wrapper for sync_and_run.py
if [ "$#" -lt 3 ]; then
  echo "Usage: submit_to_gpu.sh <user> <host> <run_cmd>"
  echo "Example: ./submit_to_gpu.sh root 1.2.3.4 \"python scripts/experiments/run_retrain_with_args.py --name remote_run --epochs 50 --device 0\""
  exit 1
fi

USER=$1
HOST=$2
shift 2
RUN_CMD="$@"

python scripts/remote/sync_and_run.py --user "$USER" --host "$HOST" --run-cmd "$RUN_CMD"
