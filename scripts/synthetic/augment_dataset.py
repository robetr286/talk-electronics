#!/usr/bin/env python3
"""
Augmentacja datasetu syntetycznych schematów.

Stosuje transformacje (szum, artefakty, rotacje) do obrazów oraz
aktualizuje odpowiadające im anotacje COCO.

Użycie:
    python augment_dataset.py --input data/synthetic/images_raw/ \
                              --output data/synthetic/images_augmented/ \
                              --annotations data/synthetic/annotations/raw.json

TODO:
- [ ] Zintegrować z albumentations
- [ ] Zdefiniować profile augmentacji (scan artifacts, noise, blur)
- [ ] Implementować transformacje zachowujące bounding boxy
- [ ] Aktualizować anotacje COCO po transformacjach
- [ ] Obsłużyć batch processing
- [ ] Zapisać parametry augmentacji do metadanych
"""

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import albumentations as A
    from albumentations.core.composition import BboxParams

    HAS_ALBUMENTATIONS = True
except ImportError:
    HAS_ALBUMENTATIONS = False
    A = None  # Placeholder dla type hints
    BboxParams = None
    print("⚠️  albumentations nie jest zainstalowany. Zainstaluj: pip install albumentations")

try:
    import numpy as np
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️  Pillow/numpy nie są zainstalowane. Zainstaluj: pip install Pillow numpy")


class AugmentationProfile:
    """Profil transformacji dla datasetu."""

    @staticmethod
    def _build_compose(transforms, *, include_bboxes: bool):
        """Buduje A.Compose i oznacza czy wymaga bboxes."""
        if not HAS_ALBUMENTATIONS:
            raise ImportError("albumentations jest wymagany")

        bbox_params = None
        if include_bboxes:
            bbox_params = BboxParams(format="coco", label_fields=["category_ids"])

        compose = A.Compose(transforms, bbox_params=bbox_params)
        setattr(compose, "requires_bboxes", include_bboxes)
        return compose

    @staticmethod
    def _gauss_noise_from_var_range(var_range: Tuple[float, float], probability: float):
        """Buduje GaussNoise kompatybilny z albumentations 2.x i starszymi."""
        if not HAS_ALBUMENTATIONS:
            raise ImportError("albumentations jest wymagany")

        # Albumentations 2.x oczekuje std_range w [0,1]; wcześniejsze wersje używały var_limit
        min_var, max_var = var_range
        min_std = math.sqrt(max(min_var, 0.0)) / 255.0
        max_std = math.sqrt(max(max_var, 0.0)) / 255.0

        try:
            return A.GaussNoise(std_range=(min_std, max_std), p=probability)
        except TypeError:
            # starsze wersje albumentations – zachowaj poprzednią składnię
            return A.GaussNoise(var_limit=var_range, p=probability)

    @staticmethod
    def _coarse_dropout(
        num_holes_range: Tuple[int, int] = (4, 8),
        hole_size_range_px: Tuple[int, int] = (10, 20),
        fill_value: int = 255,
        probability: float = 0.3,
    ):
        """Tworzy CoarseDropout zgodny z API 2.0+ (ułamki lub piksele)."""
        if not HAS_ALBUMENTATIONS:
            raise ImportError("albumentations jest wymagany")

        height_range = (hole_size_range_px[0], hole_size_range_px[1])
        width_range = (hole_size_range_px[0], hole_size_range_px[1])

        try:
            return A.CoarseDropout(
                num_holes_range=num_holes_range,
                hole_height_range=height_range,
                hole_width_range=width_range,
                fill=fill_value,
                p=probability,
            )
        except TypeError:
            # Fallback dla starszych wersji, zachowuje poprzednią składnię
            return A.CoarseDropout(
                max_holes=num_holes_range[1],
                max_height=hole_size_range_px[1],
                max_width=hole_size_range_px[1],
                fill_value=fill_value,
                p=probability,
            )

    @staticmethod
    def get_light_augmentation():
        """Lekka augmentacja - drobne artefakty."""
        if not HAS_ALBUMENTATIONS:
            raise ImportError("albumentations jest wymagany")

        return AugmentationProfile._build_compose(
            [
                AugmentationProfile._gauss_noise_from_var_range((10.0, 50.0), probability=0.5),
                A.Blur(blur_limit=3, p=0.3),
                A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
            ],
            include_bboxes=False,
        )

    @staticmethod
    def get_scan_artifacts():
        """Augmentacja symulująca artefakty skanowania."""
        if not HAS_ALBUMENTATIONS:
            raise ImportError("albumentations jest wymagany")

        return AugmentationProfile._build_compose(
            [
                AugmentationProfile._gauss_noise_from_var_range((20.0, 100.0), probability=0.7),
                A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.8),
                A.ISONoise(color_shift=(0.01, 0.05), intensity=(0.1, 0.5), p=0.5),
                A.Blur(blur_limit=5, p=0.4),
                A.Sharpen(alpha=(0.2, 0.5), lightness=(0.5, 1.0), p=0.3),
                # Rotacja do ±5 stopni (korekta skanu)
                A.Rotate(limit=5, border_mode=0, p=0.6),
            ],
            include_bboxes=True,
        )

    @staticmethod
    def get_heavy_augmentation():
        """Ciężka augmentacja - maksymalne zróżnicowanie."""
        if not HAS_ALBUMENTATIONS:
            raise ImportError("albumentations jest wymagany")

        return AugmentationProfile._build_compose(
            [
                AugmentationProfile._gauss_noise_from_var_range((30.0, 150.0), probability=0.8),
                A.RandomBrightnessContrast(brightness_limit=0.4, contrast_limit=0.4, p=0.9),
                A.ISONoise(color_shift=(0.01, 0.1), intensity=(0.2, 0.7), p=0.7),
                A.Blur(blur_limit=7, p=0.6),
                A.Sharpen(alpha=(0.2, 0.8), lightness=(0.3, 1.0), p=0.5),
                A.Rotate(limit=10, border_mode=0, p=0.7),
                AugmentationProfile._coarse_dropout(probability=0.3),
            ],
            include_bboxes=True,
        )


class DatasetAugmenter:
    """Augmentacja datasetu z anotacjami COCO."""

    def __init__(self, input_dir: Path, output_dir: Path, annotations_path: Path, profile: str = "scan"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.annotations_path = annotations_path
        self.profile = profile

        self.coco_data = None
        self.augmented_images = []
        self.augmented_annotations = []

        # Wczytaj anotacje
        self._load_annotations()

        # Wybierz profil augmentacji
        self.transform = self._get_transform(profile)
        self.requires_bboxes = getattr(self.transform, "requires_bboxes", True)

    def _load_annotations(self):
        """Wczytuje anotacje COCO z pliku."""
        if self.annotations_path.exists():
            with open(self.annotations_path, "r", encoding="utf-8") as f:
                self.coco_data = json.load(f)
            print(f"✓ Wczytano anotacje: {len(self.coco_data.get('images', []))} obrazów")
        else:
            print(f"⚠️  Brak pliku anotacji: {self.annotations_path}")
            self.coco_data = {"images": [], "annotations": [], "categories": []}

    def _get_transform(self, profile: str):
        """Zwraca transform odpowiedni do profilu."""
        profiles = {
            "light": AugmentationProfile.get_light_augmentation,
            "scan": AugmentationProfile.get_scan_artifacts,
            "heavy": AugmentationProfile.get_heavy_augmentation,
        }

        if profile not in profiles:
            print(f"⚠️  Nieznany profil: {profile}, używam 'scan'")
            profile = "scan"

        return profiles[profile]()

    def augment_image(self, image_info: Dict, annotations: List[Dict]) -> Tuple[Path, List[Dict]]:
        """
        Augmentuje pojedynczy obraz wraz z anotacjami.

        Args:
            image_info: Słownik z metadanymi obrazu (COCO format).
            annotations: Lista anotacji dla tego obrazu.

        Returns:
            Tuple (ścieżka do augmentowanego obrazu, zaktualizowane anotacje).
        """
        if not HAS_PIL:
            raise ImportError("Pillow jest wymagany do augmentacji")

        # Wczytaj obraz
        image_path = self.input_dir / image_info["file_name"]

        if not image_path.exists():
            print(f"⚠️  Brak obrazu: {image_path}")
            return None, []

        image = Image.open(image_path)
        image_np = np.array(image)

        # Przygotuj bounding boxy
        bboxes = [ann["bbox"] for ann in annotations]
        category_ids = [ann["category_id"] for ann in annotations]

        # Zastosuj augmentację
        try:
            transform_kwargs = {"image": image_np}
            if self.requires_bboxes:
                transform_kwargs.update({"bboxes": bboxes, "category_ids": category_ids})

            transformed = self.transform(**transform_kwargs)

            augmented_image = Image.fromarray(transformed["image"])
            augmented_bboxes = transformed.get("bboxes", bboxes)

            if not self.requires_bboxes:
                augmented_bboxes = bboxes

            # Zapisz augmentowany obraz
            output_path = self.output_dir / image_info["file_name"]
            augmented_image.save(output_path)

            # Zaktualizuj anotacje
            updated_annotations = []
            for i, bbox in enumerate(augmented_bboxes):
                ann = annotations[i].copy()
                ann["bbox"] = list(bbox)
                ann["area"] = bbox[2] * bbox[3]
                updated_annotations.append(ann)

            return output_path, updated_annotations

        except Exception as e:
            print(f"❌ Błąd augmentacji {image_path}: {e}")
            return None, []

    def process_dataset(self) -> Path:
        """
        Przetwarza cały dataset.

        Returns:
            Ścieżka do pliku z augmentowanymi anotacjami.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        images = self.coco_data.get("images", [])
        all_annotations = self.coco_data.get("annotations", [])

        # Grupuj anotacje po image_id
        annotations_by_image = {}
        for ann in all_annotations:
            image_id = ann["image_id"]
            if image_id not in annotations_by_image:
                annotations_by_image[image_id] = []
            annotations_by_image[image_id].append(ann)

        # Przetwórz każdy obraz
        for image_info in images:
            image_id = image_info["id"]
            annotations = annotations_by_image.get(image_id, [])

            output_path, updated_annotations = self.augment_image(image_info, annotations)

            if output_path:
                self.augmented_images.append(image_info)
                self.augmented_annotations.extend(updated_annotations)
                print(f"✓ Augmentowano: {image_info['file_name']}")

        # Zapisz zaktualizowane anotacje
        output_annotations_path = self.output_dir / "annotations.json"
        self._save_annotations(output_annotations_path)

        return output_annotations_path

    def _save_annotations(self, output_path: Path):
        """Zapisuje augmentowane anotacje COCO."""
        augmented_coco = {
            "info": self.coco_data.get("info", {}),
            "licenses": self.coco_data.get("licenses", []),
            "images": self.augmented_images,
            "annotations": self.augmented_annotations,
            "categories": self.coco_data.get("categories", []),
        }

        # Dodaj informację o profilu augmentacji
        augmented_coco["info"]["augmentation_profile"] = self.profile

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(augmented_coco, f, indent=2)

        print(f"✓ Zapisano augmentowane anotacje: {output_path}")


def main():
    """Główna funkcja skryptu."""
    parser = argparse.ArgumentParser(description="Augmentacja datasetu schematów z anotacjami COCO")
    parser.add_argument("--input", type=Path, required=True, help="Katalog z obrazami wejściowymi")
    parser.add_argument("--output", type=Path, required=True, help="Katalog wyjściowy dla augmentowanych obrazów")
    parser.add_argument("--annotations", type=Path, required=True, help="Plik COCO JSON z anotacjami")
    parser.add_argument("--profile", choices=["light", "scan", "heavy"], default="scan", help="Profil augmentacji")

    args = parser.parse_args()

    if not HAS_ALBUMENTATIONS:
        print("❌ Brak wymaganych bibliotek. Zainstaluj: pip install albumentations")
        return

    # Utwórz augmenter
    augmenter = DatasetAugmenter(
        input_dir=args.input, output_dir=args.output, annotations_path=args.annotations, profile=args.profile
    )

    # Przetwórz dataset
    output_annotations = augmenter.process_dataset()

    print("\n✓ Augmentacja zakończona")
    print(f"  - Obrazy: {args.output}")
    print(f"  - Anotacje: {output_annotations}")


if __name__ == "__main__":
    main()
