"""Run YOLO retraining with configurable augmentation args.

Usage example:
  python scripts/experiments/run_retrain_with_args.py \
    --weights runs/segment/train14/weights/best.pt \
    --data data/yolo_dataset/mix_small/dataset.yaml \
    --name exp_retrain --epochs 50 --degrees 15 --copy_paste 0.5 --mixup 0.35
"""

import argparse

from ultralytics import YOLO


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--weights", default="runs/segment/train14/weights/best.pt")
    p.add_argument("--data", default="data/yolo_dataset/mix_small/dataset.yaml")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--name", default="exp_mix_small_retrain")
    p.add_argument("--device", default=0)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--degrees", type=float)
    p.add_argument("--shear", type=float)
    p.add_argument("--copy_paste", type=float)
    p.add_argument("--mixup", type=float)
    return p.parse_args()


def main():
    args = parse_args()
    model = YOLO(args.weights)
    train_kwargs = {}
    if args.degrees is not None:
        train_kwargs["degrees"] = args.degrees
    if args.shear is not None:
        train_kwargs["shear"] = args.shear
    if args.copy_paste is not None:
        train_kwargs["copy_paste"] = args.copy_paste
    if args.mixup is not None:
        train_kwargs["mixup"] = args.mixup

    res = model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=640,
        patience=10,
        workers=0,
        amp=False,
        device=args.device,
        save_period=5,
        name=args.name,
        **train_kwargs,
    )
    print("Training finished. Saved to:", res.save_dir)


if __name__ == "__main__":
    main()
