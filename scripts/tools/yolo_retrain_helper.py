#!/usr/bin/env python3
"""Helper: prepare dataset config and augmentation recipes for YOLO retraining."""
import argparse
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, default=Path("runs/segment/exp_yolo_retrain"))
    return p.parse_args()


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print("Prepare dataset config, augmentation pipeline and training scripts in", args.out_dir)


if __name__ == "__main__":
    main()
