"""Run a longer training for exp_mix_small.

This script can be used to run a longer training (e.g. 50 or 100 epochs)
and is suitable for scheduling at system startup.
"""

import argparse

from ultralytics import YOLO


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/yolo_dataset/mix_small/dataset.yaml")
    p.add_argument("--weights", default="runs/segment/train14/weights/best.pt")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--name", default="exp_mix_small_50")
    p.add_argument("--device", default=0)
    p.add_argument("--batch", type=int, default=1)
    args = p.parse_args()

    model = YOLO(args.weights)
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
    )
    print("Training finished. Saved to:", res.save_dir)


if __name__ == "__main__":
    main()
