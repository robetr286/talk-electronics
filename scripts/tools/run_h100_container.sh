#!/usr/bin/env bash
# Usage: ./scripts/tools/run_h100_container.sh --yolo-budget 120 --mask-budget 120

set -e

YOLO_BUDGET=""
MASK_BUDGET=""
ARGS=()
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --yolo-budget)
      YOLO_BUDGET="$2"; shift; shift; ;;
    --mask-budget)
      MASK_BUDGET="$2"; shift; shift; ;;
    *)
      ARGS+=("$1"); shift; ;;
  esac
done

if [ -z "${YOLO_BUDGET}" ]; then YOLO_BUDGET=60; fi
if [ -z "${MASK_BUDGET}" ]; then MASK_BUDGET=90; fi

DATA_MOUNT=${DATA_MOUNT:-/workspace/data}
OUT_MOUNT=${OUT_MOUNT:-/workspace/runs/benchmarks/h100}

docker run --gpus all -it --rm -v $(pwd)/data:${DATA_MOUNT} -v $(pwd)/runs/benchmarks/h100:${OUT_MOUNT} talk-electronic:latest bash -lc "python scripts/tools/h100_benchmark.py --yolo-budget ${YOLO_BUDGET} --mask-budget ${MASK_BUDGET} --device cuda:0 --output-dir ${OUT_MOUNT}"
