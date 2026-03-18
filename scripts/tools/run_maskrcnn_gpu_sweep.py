"""
Small helper to automate Mask R-CNN GPU sweep on this repo.

Usage example (PowerShell):

    $env:CUDA_LAUNCH_BLOCKING=1;
    C:/Users/DELL/miniconda3/envs/talk_flask/python.exe \
        scripts/tools/run_maskrcnn_gpu_sweep.py \
        --coco-json data/yolo_dataset/mix_small/coco_annotations_small.json \
        --images-dir data/yolo_dataset/mix_small/images \
        --img-sizes 128 256 384 512 \
        --output-dir runs/segment/sweep_results \
        --epochs 2 --batch 1 --workers 0 --device cuda

This script calls `scripts/experiments/run_maskrcnn_poc.py` for each `img-size` and
captures stdout/stderr into per-run logs. It also writes a JSON/CSV summary.

Notes:
- Use `--dry-run` to validate command construction without executing training.
- The script attempts to capture `nvidia-smi` snapshot before & after each run.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_cmd(cmd, log_path, dry_run=False):
    if dry_run:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("DRY_RUN:\n")
            f.write(" ".join(cmd) + "\n")
        return 0, "DRY_RUN", ""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(out)
        if err:
            f.write("\n--- STDERR ---\n")
            f.write(err)
    return proc.returncode, out, err


def capture_nvidia_smi(out_file):
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.free,name",
                "--format=csv",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(proc.stdout)
        return proc.returncode, proc.stdout
    except FileNotFoundError:
        return 1, "nvidia-smi not found"


def main():
    parser = argparse.ArgumentParser(description="Run Mask R-CNN GPU sweep using run_maskrcnn_poc.py")
    parser.add_argument("--coco-json", required=True)
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--img-sizes", nargs="+", required=True, type=int)
    parser.add_argument("--output-dir", default="runs/segment/sweep_results")
    parser.add_argument("--epochs", default=2, type=int)
    parser.add_argument("--batch", default=1, type=int)
    parser.add_argument("--workers", default=0, type=int)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cuda-check", action="store_true", help="Don't try to call nvidia-smi")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    summary_file = output_dir / f"sweep_summary_{timestamp}.json"

    for size in args.img_sizes:
        run_name = f"sweep_{size}"
        run_dir = output_dir / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        weights_dir = run_dir / "weights"
        log_file = run_dir / f"run_{size}.log"
        pre_nvidia = run_dir / "nvidia_pre.txt"
        post_nvidia = run_dir / "nvidia_post.txt"

        if not args.no_cuda_check:
            capture_nvidia_smi(pre_nvidia)

        cmd = [
            args.python_exe,
            "scripts/experiments/run_maskrcnn_poc.py",
            "--coco-json",
            args.coco_json,
            "--images-dir",
            args.images_dir,
            "--output",
            str(run_dir),
            "--epochs",
            str(args.epochs),
            "--batch",
            str(args.batch),
            "--img-size",
            str(size),
            "--device",
            args.device,
            "--workers",
            str(args.workers),
        ]

        start = time.time()
        rc, out, err = run_cmd(cmd, log_file, dry_run=args.dry_run)
        elapsed = time.time() - start

        if not args.no_cuda_check:
            capture_nvidia_smi(post_nvidia)

        weights_saved = False
        if weights_dir.exists():
            if any(weights_dir.iterdir()):
                weights_saved = True

        entry = {
            "img_size": size,
            "run_dir": str(run_dir),
            "start": start,
            "elapsed": elapsed,
            "returncode": rc,
            "weights_saved": weights_saved,
            "log": str(log_file),
        }
        results.append(entry)

        # brief stdout summary
        print(f"Completed: img_size={size}, returncode={rc}, elapsed={elapsed:.1f}s, weights_saved={weights_saved}")

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # optional CSV
    csv_file = output_dir / f"sweep_summary_{timestamp}.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("img_size,returncode,elapsed,weights_saved,run_dir,log\n")
        for r in results:
            f.write(
                f"{r['img_size']},{r['returncode']},{r['elapsed']},{r['weights_saved']},{r['run_dir']},{r['log']}\n"
            )

    print(f"Saved sweep summary: {summary_file}")


if __name__ == "__main__":
    main()
