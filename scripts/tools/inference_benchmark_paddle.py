#!/usr/bin/env python
"""Benchmark inferencji RT-DETR-L vs YOLOv8 na RTX A2000.

Porównuje czas inferencji (warmup + N powtórzeń) obu modeli
na przykładowym obrazie ze zbioru schematów elektronicznych.

Użycie:
    python scripts/tools/inference_benchmark_paddle.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_DIR = PROJECT_ROOT / "weights"

RTDETR_WEIGHTS = WEIGHTS_DIR / "rtdetr-l.pt"
YOLO_WEIGHTS_CANDIDATES = [
    WEIGHTS_DIR / "train6_best.pt",
    WEIGHTS_DIR / "best.pt",
    WEIGHTS_DIR / "yolo11n.pt",
]

# Obraz testowy (pierwszy znaleziony w data/)
TEST_IMAGE_CANDIDATES = list(
    (PROJECT_ROOT / "data" / "annotations" / "coco_seg" / "splits_2025-12-19" / "val" / "images").glob("*.png")
) + list(
    (PROJECT_ROOT / "data" / "sample_benchmark").glob("*.png")
)

N_WARMUP = 3
N_REPEATS = 10
IMGSZ = 640
CONF = 0.35


def find_test_image() -> Path:
    for p in TEST_IMAGE_CANDIDATES:
        if p.exists():
            return p
    # Fallback: wygeneruj sztuczny obraz
    dummy = PROJECT_ROOT / "data" / "_benchmark_dummy.png"
    img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    cv2.imwrite(str(dummy), img)
    return dummy


def benchmark_model(model, image_path: Path, model_name: str) -> dict:
    """Uruchamia warmup + N inferencji i zwraca statystyki."""
    print(f"\n{'='*60}")
    print(f"  Model: {model_name}")
    print(f"  Wagi:  {getattr(model, 'ckpt_path', 'N/A')}")
    print(f"{'='*60}")

    # Warmup
    print(f"  Warmup ({N_WARMUP}x)...", end=" ", flush=True)
    for _ in range(N_WARMUP):
        model.predict(str(image_path), imgsz=IMGSZ, conf=CONF, verbose=False)
    print("OK")

    # Benchmark
    times = []
    det_counts = []
    for i in range(N_REPEATS):
        t0 = time.perf_counter()
        results = model.predict(str(image_path), imgsz=IMGSZ, conf=CONF, verbose=False)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        times.append(elapsed_ms)
        n_det = len(results[0].boxes) if results and results[0].boxes is not None else 0
        det_counts.append(n_det)

    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    median = sorted(times)[len(times) // 2]

    stats = {
        "model": model_name,
        "avg_ms": round(avg, 1),
        "min_ms": round(mn, 1),
        "max_ms": round(mx, 1),
        "median_ms": round(median, 1),
        "detections": det_counts[0],
        "imgsz": IMGSZ,
    }

    print(f"  Wyniki ({N_REPEATS} powtórzeń):")
    print(f"    Średnia:  {stats['avg_ms']:>8.1f} ms")
    print(f"    Mediana:  {stats['median_ms']:>8.1f} ms")
    print(f"    Min:      {stats['min_ms']:>8.1f} ms")
    print(f"    Max:      {stats['max_ms']:>8.1f} ms")
    print(f"    Detekcje: {stats['detections']}")

    return stats


def main():
    import torch
    print("=" * 60)
    print("  Benchmark inferencji: RT-DETR-L vs YOLOv8")
    print("=" * 60)
    print(f"  PyTorch:     {torch.__version__}")
    print(f"  CUDA:        {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU:         {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"  VRAM:        {vram:.1f} GB")
    print(f"  imgsz:       {IMGSZ}")
    print(f"  conf:        {CONF}")
    print(f"  warmup:      {N_WARMUP}")
    print(f"  repeats:     {N_REPEATS}")

    image_path = find_test_image()
    print(f"  Obraz:       {image_path.name}")
    img = cv2.imread(str(image_path))
    if img is not None:
        print(f"  Rozdzielczość: {img.shape[1]}x{img.shape[0]}")

    results = []

    # --- RT-DETR-L ---
    if RTDETR_WEIGHTS.exists():
        from ultralytics import RTDETR
        model_rtdetr = RTDETR(str(RTDETR_WEIGHTS))
        stats = benchmark_model(model_rtdetr, image_path, "RT-DETR-L (Ultralytics)")
        results.append(stats)
        del model_rtdetr
        torch.cuda.empty_cache()
    else:
        print(f"\n⚠ Brak wag RT-DETR-L: {RTDETR_WEIGHTS}")

    # --- YOLOv8 ---
    yolo_weights = None
    for candidate in YOLO_WEIGHTS_CANDIDATES:
        if candidate.exists():
            yolo_weights = candidate
            break

    if yolo_weights:
        from ultralytics import YOLO
        model_yolo = YOLO(str(yolo_weights))
        stats = benchmark_model(model_yolo, image_path, f"YOLOv8 ({yolo_weights.name})")
        results.append(stats)
        del model_yolo
        torch.cuda.empty_cache()
    else:
        print(f"\n⚠ Brak wag YOLO — pomijam benchmark")

    # --- Podsumowanie ---
    if results:
        print(f"\n{'='*60}")
        print("  PODSUMOWANIE")
        print(f"{'='*60}")
        print(f"  {'Model':<30} {'Avg(ms)':>8} {'Med(ms)':>8} {'Det':>5}")
        print(f"  {'-'*53}")
        for r in results:
            print(f"  {r['model']:<30} {r['avg_ms']:>8.1f} {r['median_ms']:>8.1f} {r['detections']:>5}")

    return results


if __name__ == "__main__":
    main()
