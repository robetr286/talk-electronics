#!/usr/bin/env python3
"""
Skrypt do treningu YOLOv8 na syntetycznych danych.
Wersja z agresywną augmentacją dla maksymalnej różnorodności.
"""

import os

from ultralytics import YOLO

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


if __name__ == "__main__":
    print("🚀 Rozpoczynam trening YOLOv8 na syntetycznych danych...")
    print("📊 Dataset: 500 obrazów, ~13800 komponentów")
    print("🎯 4 kategorie: resistor, capacitor, inductor, diode\n")

    # Załaduj model
    model = YOLO("yolov8n-seg.pt")

    # Trenuj model z AGRESYWNĄ augmentacją dla maksymalnej różnorodności
    results = model.train(
        data="data/synthetic_batch/dataset.yaml",
        epochs=100,  # Więcej epok dla syntetycznych danych
        imgsz=640,
        batch=8,  # Większy batch (mamy więcej danych)
        patience=20,  # Więcej cierpliwości
        save_period=10,  # Zapisuj co 10 epok
        amp=False,  # Wyłączone AMP dla stabilności
        workers=0,  # Wyłączone multiprocessing dla Windows
        device=0,  # Użyj GPU 0
        # ============================================
        # AGRESYWNA AUGMENTACJA - maksymalna różnorodność
        # ============================================
        # Transformacje geometryczne
        degrees=15.0,  # Rotacja ±15° (schematy mogą być odwrócone)
        translate=0.2,  # Przesunięcie 20% (elementy w różnych miejscach)
        scale=0.5,  # Skalowanie 50-150% (różne wielkości)
        shear=5.0,  # Skrzywienie ±5° (perspektywa)
        perspective=0.001,  # Delikatna perspektywa
        flipud=0.5,  # Odbicie w pionie 50%
        fliplr=0.5,  # Odbicie poziome 50%
        # Transformacje kolorystyczne
        hsv_h=0.015,  # Odcień (niewielkie zmiany dla mono schematów)
        hsv_s=0.7,  # Saturacja
        hsv_v=0.4,  # Jasność/wartość (ważne - symuluje różne warunki oświetlenia)
        # Zaawansowane augmentacje
        mosaic=1.0,  # Mosaic mixing (łączy 4 obrazy) - super dla małych obiektów!
        mixup=0.15,  # Mieszanie 2 obrazów (15% szans)
        copy_paste=0.1,  # Copy-paste augmentation (10% szans)
        # Augmentacje specyficzne dla schematów
        auto_augment="randaugment",  # Automatyczna augmentacja
        erasing=0.2,  # Random erasing (symuluje zasłonięte fragmenty)
        # Optymalizacja
        close_mosaic=20,  # Wyłącz mosaic w ostatnich 20 epokach (fine-tuning)
        # Raporty i checkpointy
        plots=True,  # Generuj wykresy (loss curves, confusion matrix)
        val=True,  # Walidacja po każdej epoce
        save=True,  # Zapisz najlepszy model
    )

    print("\n" + "=" * 60)
    print("TRENING ZAKOŃCZONY!")
    print("=" * 60)
    print(f"Wyniki zapisane w: {results.save_dir}")
    print(f"Najlepszy model: {results.save_dir}/weights/best.pt")
    print("\n💡 Użycie modelu:")
    print("   from ultralytics import YOLO")
    print(f"   model = YOLO('{results.save_dir}/weights/best.pt')")
    print("   results = model.predict('path/to/schematic.png')")
