#!/usr/bin/env python3
"""
Skrypt do kontynuacji treningu RT-DETR-L z best.pt.

Zamiast resume=True (które wymusza oryginalne parametry z checkpointa),
rozpoczyna NOWY trening z wagami z best.pt. Tracimy info o epoce,
ale model startuje z dobrymi wagami i stabilnymi parametrami.

Zabezpieczenia:
  - workers=0 — zapobiega ConnectionResetError w DataLoader
  - save_period=5 — checkpoint co 5 epok
  - nohup — odporny na utratę terminala

Użycie:
    conda activate Talk_flask
    nohup python resume_training.py > runs/detect/rtdetr/training_resume.log 2>&1 &
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

PROJECT_ROOT = Path(__file__).resolve().parent

# Konfiguracja
BEST_PT = PROJECT_ROOT / "runs/detect/rtdetr/merged_opamp_rtdetr/weights/best.pt"
DATA_YAML = PROJECT_ROOT / "configs/rtdetr_merged_opamp.yaml"
EPOCHS = 60           # Nowy trening: 60 epok od best.pt (≈ epoka 16)
BATCH = 4
IMGSZ = 640
PATIENCE = 20
SAVE_PERIOD = 5       # Checkpoint co 5 epok
WORKERS = 0           # Single-thread — brak ConnectionResetError

for path, label in [(BEST_PT, "wagi"), (DATA_YAML, "config danych")]:
    if not path.exists():
        print(f"❌ Brak pliku: {path} ({label})")
        sys.exit(1)

print("=" * 60)
print("  KONTYNUACJA treningu RT-DETR-L (nowy run od best.pt)")
print("=" * 60)
print(f"  Wagi start:  {BEST_PT}")
print(f"  Dane:        {DATA_YAML}")
print(f"  Epoki:       {EPOCHS}")
print(f"  Batch:       {BATCH}")
print(f"  imgsz:       {IMGSZ}")
print(f"  Patience:    {PATIENCE}")
print(f"  Workers:     {WORKERS} (single-thread, stabilne)")
print(f"  SavePeriod:  {SAVE_PERIOD}")
print("=" * 60)

from ultralytics import RTDETR

model = RTDETR(str(BEST_PT))

results = model.train(
    data=str(DATA_YAML),
    epochs=EPOCHS,
    imgsz=IMGSZ,
    batch=BATCH,
    patience=PATIENCE,
    device="0",
    workers=WORKERS,
    project="runs/detect/rtdetr",
    name="merged_opamp_rtdetr_v2",
    exist_ok=False,
    # Augmentacje
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
    save_period=SAVE_PERIOD,
)

print("\n" + "=" * 60)
print("  TRENING ZAKOŃCZONY!")
print("=" * 60)
save_dir = getattr(results, "save_dir", "runs/detect/rtdetr/merged_opamp_rtdetr_v2")
print(f"  Wyniki:         {save_dir}")
print(f"  Najlepsze wagi: {save_dir}/weights/best.pt")
