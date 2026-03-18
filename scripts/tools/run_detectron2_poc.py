"""Quick PoC runner for Detectron2 Mask R-CNN (1-epoch, low-budget) on a COCO dataset.

This script registers the COCO dataset with Detectron2 if available, configures a Mask R-CNN R50-FPN
trainer, and runs a short quick PoC training (default 1 epoch). It writes a small JSON report with
timings and writes logs to `runs/benchmarks`.

If Detectron2 is not installed, the script tries to install it with a pip command (best-effort).
On Windows this may fail and the script will provide instructions.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def try_install_detectron2():
    print("Detectron2 not installed: attempting pip install (this may fail on Windows).")
    cmd = [sys.executable, "-m", "pip", "install", "git+https://github.com/facebookresearch/detectron2.git"]
    rc = subprocess.call(cmd)
    return rc == 0


def run_poc(coco_json: str, images_dir: str, output_dir: str, epochs: int, batch: int, device: str):
    try:
        import detectron2
        from detectron2.config import get_cfg
        from detectron2.data.datasets import register_coco_instances
        from detectron2.engine import DefaultTrainer
        from detectron2.utils.logger import setup_logger
    except Exception as e:
        print("Detectron2 import failed:", e)
        ok = try_install_detectron2()
        if not ok:
            print(
                "Automatic install failed. Please install detectron2 following https://detectron2.readthedocs.io and retry."
            )
            return False, str(e)
        # try import again
        import detectron2
        from detectron2.config import get_cfg
        from detectron2.data.datasets import register_coco_instances
        from detectron2.engine import DefaultTrainer
        from detectron2.utils.logger import setup_logger

    setup_logger()
    NAME = f"detectron2_poc_{int(time.time())}"
    outdir = Path(output_dir) / NAME
    outdir.mkdir(parents=True, exist_ok=True)

    # Register dataset
    ds_name = f"poc_{NAME}_train"
    try:
        register_coco_instances(ds_name, {}, coco_json, images_dir)
    except Exception as e:
        print("Failed to register COCO dataset:", e)
        return False, str(e)

    cfg = get_cfg()
    # Use COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x as base
    cfg.merge_from_file(
        str(
            Path(detectron2.__file__).parents[1]
            / "configs"
            / "COCO-InstanceSegmentation"
            / "mask_rcnn_R_50_FPN_3x.yaml"
        )
    )
    cfg.DATASETS.TRAIN = (ds_name,)
    cfg.DATASETS.TEST = ()
    cfg.DATALOADER.NUM_WORKERS = 0
    cfg.SOLVERIMS_PER_BATCH = batch
    cfg.SOLVER.MAX_ITER = max(1, int(epochs * 100))  # this is just a small number for PoC; override below
    # Estimate iterations: use len dataset * epochs
    try:
        import detectron2.data.detection_utils as du
        from detectron2.data import DatasetCatalog

        dataset_len = len(DatasetCatalog.get(ds_name))
    except Exception:
        dataset_len = 1
    steps_per_epoch = max(1, dataset_len // max(1, batch))
    cfg.SOLVER.MAX_ITER = steps_per_epoch * epochs
    cfg.SOLVER.BASE_LR = 0.00025
    cfg.SOLVER.WEIGHT_DECAY = 0.0001
    cfg.MODEL.ROI_HEADS.BATCH_SIZE_PER_IMAGE = 64
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 17  # repo default
    cfg.OUTPUT_DIR = str(outdir)
    cfg.MODEL.DEVICE = device

    # minimal trainer
    class PoCTrainer(DefaultTrainer):
        @classmethod
        def build_evaluator(cls, cfg, dataset_name, output_folder=None):
            from detectron2.evaluation import COCOEvaluator

            output_folder = output_folder or os.path.join(cfg.OUTPUT_DIR, "eval")
            return COCOEvaluator(dataset_name, cfg, True, output_folder)

    start = time.monotonic()
    trainer = PoCTrainer(cfg)
    trainer.resume_or_load(resume=False)
    try:
        trainer.train()
        success = True
    except Exception as e:
        print("Detectron2 training failed:", e)
        success = False
    elapsed = time.monotonic() - start

    # Save simple report
    report = {
        "timestamp": int(time.time()),
        "model": "detectron2_maskrcnn_r50_fpn",
        "success": success,
        "save_dir": str(outdir),
        "time_sec": elapsed,
        "dataset_len": dataset_len,
        "epochs": epochs,
        "batch": batch,
    }
    with open(outdir / "detectron2_poc_report.json", "w", encoding="utf8") as f:
        json.dump(report, f, indent=2)

    print("Detectron2 PoC complete. Report saved to:", outdir / "detectron2_poc_report.json")
    return success, report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--coco-json", required=True)
    p.add_argument("--images-dir", required=True)
    p.add_argument("--output-dir", default="runs/benchmarks")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()

    ok, info = run_poc(args.coco_json, args.images_dir, args.output_dir, args.epochs, args.batch, args.device)
    if not ok:
        print("PoC failed or detectron2 not available:", info)
        sys.exit(1)
    # Append to a central benchmark report
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary_file = outdir / "detectron2_poc_summary.json"
    if summary_file.exists():
        try:
            data = json.loads(summary_file.read_text(encoding="utf8"))
        except Exception:
            data = []
    else:
        data = []
    data.append(info)
    with open(summary_file, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2)
    print("Summary appended to:", summary_file)


if __name__ == "__main__":
    main()
