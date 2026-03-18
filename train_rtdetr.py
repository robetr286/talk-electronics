#!/usr/bin/env python3
"""
Skrypt do treningu RT-DETR-L na symbolach elektronicznych.

RT-DETR-L (Real-Time DEtection TRansformer) — backbone HGNet + hybrid encoder
+ DETR decoder. Implementacja Ultralytics (PyTorch), ta sama API co YOLO.

Użycie:
    # Domyślny config (syntetyczne 200 obrazów):
    python train_rtdetr.py

    # Z własnym configiem i parametrami:
    python train_rtdetr.py --config configs/rtdetr_symbols.yaml --epochs 100 --batch 8

    # Smoke test (szybka weryfikacja):
    python train_rtdetr.py --epochs 5 --batch 4

    # Na innym datasecie:
    python train_rtdetr.py --data data/yolo_dataset/mix_small/dataset.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

PROJECT_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trening RT-DETR-L na symbolach elektronicznych"
    )
    parser.add_argument(
        "--config", "--data",
        dest="data",
        default="configs/rtdetr_symbols.yaml",
        help="Ścieżka do pliku konfiguracyjnego YAML z danymi (domyślnie: configs/rtdetr_symbols.yaml)",
    )
    parser.add_argument(
        "--weights",
        default="weights/rtdetr-l.pt",
        help="Ścieżka do wag pretrenowanych (domyślnie: weights/rtdetr-l.pt)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Liczba epok (domyślnie: 50)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=4,
        help="Rozmiar batcha (domyślnie: 4 — RTX A2000 ma 6 GB VRAM)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Rozmiar obrazu wejściowego (domyślnie: 640)",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=15,
        help="Early stopping — liczba epok bez poprawy (domyślnie: 15)",
    )
    parser.add_argument(
        "--device",
        default="0",
        help="Urządzenie: 0 (GPU), cpu, auto (domyślnie: 0)",
    )
    parser.add_argument(
        "--project",
        default="runs/detect/rtdetr",
        help="Katalog na wyniki (domyślnie: runs/detect/rtdetr)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Nazwa eksperymentu (domyślnie: auto)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Wznów trening z ostatniego checkpointa",
    )
    parser.add_argument(
        "--save-period",
        type=int,
        default=5,
        help="Co ile epok zapisywać dodatkowy checkpoint epochN.pt (domyślnie: 5)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Liczba workerów DataLoader (domyślnie: 4, Ubuntu)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Walidacja ścieżek
    data_path = PROJECT_ROOT / args.data
    weights_path = PROJECT_ROOT / args.weights

    if not data_path.exists():
        print(f"❌ Nie znaleziono pliku danych: {data_path}")
        sys.exit(1)
    if not weights_path.exists():
        print(f"❌ Nie znaleziono wag: {weights_path}")
        print("   Pobierz: python -c \"from ultralytics import RTDETR; RTDETR('rtdetr-l.pt')\"")
        sys.exit(1)

    print("=" * 60)
    print("  Trening RT-DETR-L — symbole elektroniczne")
    print("=" * 60)
    print(f"  Wagi:      {weights_path}")
    print(f"  Dane:      {data_path}")
    print(f"  Epoki:     {args.epochs}")
    print(f"  Batch:     {args.batch}")
    print(f"  imgsz:     {args.imgsz}")
    print(f"  Patience:  {args.patience}")
    print(f"  Device:    {args.device}")
    print(f"  Workers:   {args.workers}")
    print(f"  SavePeriod:{args.save_period}")
    print(f"  Projekt:   {args.project}")
    print("=" * 60)

    from ultralytics import RTDETR

    model = RTDETR(str(weights_path))

    train_kwargs: dict = dict(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        device=args.device,
        workers=args.workers,
        project=args.project,
        # Augmentacje (umiarkowane — RT-DETR sam ma silny encoder)
        degrees=10.0,
        translate=0.15,
        scale=0.4,
        shear=3.0,
        flipud=0.3,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        mosaic=1.0,
        mixup=0.1,
        close_mosaic=10,
        # Raportowanie
        plots=True,
        val=True,
        save=True,
        save_period=args.save_period,
    )

    if args.name:
        train_kwargs["name"] = args.name
    if args.resume:
        train_kwargs["resume"] = True

    results = model.train(**train_kwargs)

    print("\n" + "=" * 60)
    print("  TRENING ZAKOŃCZONY!")
    print("=" * 60)
    save_dir = getattr(results, "save_dir", args.project)
    print(f"  Wyniki:      {save_dir}")
    print(f"  Najlepsze wagi: {save_dir}/weights/best.pt")
    print()
    print("  Użycie wytrenowanego modelu:")
    print("    from ultralytics import RTDETR")
    print(f"    model = RTDETR('{save_dir}/weights/best.pt')")
    print("    results = model.predict('path/to/schematic.png')")
    print()
    print("  Przełączenie w aplikacji:")
    print(f"    cp {save_dir}/weights/best.pt weights/rtdetr_best.pt")
    print("    export TALK_ELECTRONIC_DETECTOR=rtdetr")


if __name__ == "__main__":
    main()
