"""
Skrypt do treningu YOLOv8 na danych z real_batch1.
Utworzony dla rozwiązania problemu z multiprocessing na Windows.
"""

import os

from ultralytics import YOLO

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


if __name__ == "__main__":
    # Załaduj model
    model = YOLO("yolov8n-seg.pt")

    # Trenuj model z minimalną konfiguracją dla stabilności na Windows
    results = model.train(
        data="data/yolo_dataset/real_batch1/dataset.yaml",
        epochs=50,
        imgsz=640,
        batch=1,
        patience=10,
        save_period=5,
        amp=False,  # Wyłączone AMP dla stabilności
        workers=0,  # Wyłączone multiprocessing dla Windows
        plots=False,  # Wyłączone generowanie wykresów podczas treningu
        val=True,  # Walidacja po każdej epoce
        device=0,  # Użyj GPU 0
    )

    print("\n" + "=" * 60)
    print("TRENING ZAKOŃCZONY!")
    print("=" * 60)
    print(f"Wyniki zapisane w: {results.save_dir}")
