"""Run quick experiments: reduced classes, augmented real, and mixed dataset.

Writes run directories under runs/segment/ with descriptive names.

Usage:
  python scripts/experiments/run_mix_experiments.py --base-weights runs/segment/train14/weights/best.pt
"""

import argparse
import os

from ultralytics import YOLO

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def run(name, data_yaml, weights=None, epochs=10):
    print(f"Starting experiment {name} -> data={data_yaml} weights={weights}")
    model = YOLO(weights or "yolov8n-seg.pt")
    res = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=1,
        imgsz=640,
        patience=5,
        workers=0,
        amp=False,
        device=0,
        save_period=5,
        name=name,
    )
    print("Saved to:", res.save_dir)
    return res.save_dir


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-weights", default=None)
    args = p.parse_args()

    out_dirs = []
    # 1) reduced
    out_dirs.append(
        run("exp_reduced", "data/yolo_dataset/real_batch1_reduced/dataset.yaml", weights=args.base_weights, epochs=10)
    )
    # 2) augmented real
    out_dirs.append(
        run("exp_augmented_real", "data/yolo_dataset/real_aug/dataset.yaml", weights=args.base_weights, epochs=10)
    )
    # 3) mixture
    out_dirs.append(
        run("exp_mix_small", "data/yolo_dataset/mix_small/dataset.yaml", weights=args.base_weights, epochs=10)
    )

    # ensure we print string paths
    print("All experiments finished. Results:\n", "\n".join([str(p) for p in out_dirs]))


if __name__ == "__main__":
    main()
