"""
Testy dla pipeline'u syntetycznych danych.

Sprawdza poprawność działania skryptów generowania, eksportu i anotacji.
"""

import json
import sys
from pathlib import Path

import pytest

# Dodaj scripts/synthetic do PYTHONPATH
synthetic_dir = Path(__file__).parent.parent / "scripts" / "synthetic"
sys.path.insert(0, str(synthetic_dir))


class TestSchematicGenerator:
    """Testy dla generate_schematic.py"""

    def test_schematic_config_creation(self):
        """Test tworzenia konfiguracji generatora."""
        from generate_schematic import SchematicConfig

        config = SchematicConfig(seed=42, num_components=10, component_types=["R", "C"])

        assert config.seed == 42
        assert config.num_components == 10
        assert "R" in config.component_types
        assert "C" in config.component_types

    def test_schematic_config_serialization(self):
        """Test serializacji konfiguracji do dict."""
        from generate_schematic import SchematicConfig

        config = SchematicConfig(seed=123, num_components=5)
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict["seed"] == 123
        assert config_dict["num_components"] == 5
        assert "component_types" in config_dict

    def test_generator_creates_components(self):
        """Test generowania komponentów."""
        from generate_schematic import SchematicConfig, SchematicGenerator

        config = SchematicConfig(seed=1, num_components=3)
        generator = SchematicGenerator(config)

        metadata = generator.generate()

        assert "components" in metadata
        assert len(metadata["components"]) == 3

        # Sprawdź strukturę komponentu
        component = metadata["components"][0]
        assert "id" in component
        assert "type" in component
        assert "position" in component
        assert len(component["position"]) == 2

    def test_generator_metadata_save(self, tmp_path):
        """Test zapisywania metadanych do JSON."""
        from generate_schematic import SchematicConfig, SchematicGenerator

        config = SchematicConfig(seed=42, num_components=5)
        generator = SchematicGenerator(config)

        output_path = tmp_path / "test_metadata.json"
        generator.save_metadata(output_path)

        assert output_path.exists()

        # Sprawdź zawartość
        with open(output_path, "r") as f:
            data = json.load(f)

        assert "config" in data
        assert "components" in data
        assert data["config"]["seed"] == 42


class TestPNGExport:
    """Testy dla export_png.py"""

    def test_pdf_to_png_requires_pymupdf(self):
        """Test sprawdzania dostępności PyMuPDF."""
        from export_png import HAS_PYMUPDF

        # Ten test nie wymaga PyMuPDF, tylko sprawdza flagę
        assert isinstance(HAS_PYMUPDF, bool)

    @pytest.mark.skipif(not Path("data/sample_benchmark").exists(), reason="Brak przykładowych plików PDF")
    def test_pdf_to_png_with_sample(self, tmp_path):
        """Test konwersji PDF na PNG (wymaga przykładowego PDF)."""
        try:
            from export_png import HAS_PYMUPDF, pdf_to_png

            if not HAS_PYMUPDF:
                pytest.skip("PyMuPDF nie jest zainstalowany")

            # Znajdź przykładowy PDF
            sample_dir = Path("data/sample_benchmark")
            pdf_files = list(sample_dir.glob("*.pdf"))

            if not pdf_files:
                pytest.skip("Brak przykładowych PDF")

            sample_pdf = pdf_files[0]
            output_png = tmp_path / "test_output.png"

            result = pdf_to_png(sample_pdf, output_png, dpi=150)

            if result:
                assert output_png.exists()

                # Sprawdź czy to poprawny PNG
                from PIL import Image

                img = Image.open(output_png)
                assert img.format == "PNG"

        except ImportError:
            pytest.skip("Brak wymaganych bibliotek")


class TestCOCOAnnotations:
    """Testy dla emit_annotations.py"""

    def test_component_categories_defined(self):
        """Test sprawdzania definicji kategorii komponentów."""
        from emit_annotations import COMPONENT_CATEGORIES

        assert isinstance(COMPONENT_CATEGORIES, dict)
        assert "R" in COMPONENT_CATEGORIES  # Rezystor
        assert "C" in COMPONENT_CATEGORIES  # Kondensator

        # Sprawdź strukturę kategorii
        resistor = COMPONENT_CATEGORIES["R"]
        assert "id" in resistor
        assert "name" in resistor
        assert "supercategory" in resistor

    def test_coco_builder_initialization(self):
        """Test inicjalizacji buildera COCO."""
        from emit_annotations import COCOAnnotationBuilder

        builder = COCOAnnotationBuilder()

        assert len(builder.images) == 0
        assert len(builder.annotations) == 0
        assert len(builder.categories) > 0  # Powinny być domyślne kategorie

    def test_coco_builder_add_image(self):
        """Test dodawania obrazu do datasetu."""
        from emit_annotations import COCOAnnotationBuilder

        builder = COCOAnnotationBuilder()
        builder.add_image(image_id=1, file_name="test.png", width=1000, height=800)

        assert len(builder.images) == 1
        assert builder.images[0]["id"] == 1
        assert builder.images[0]["file_name"] == "test.png"

    def test_coco_builder_add_annotation(self):
        """Test dodawania anotacji."""
        from emit_annotations import COCOAnnotationBuilder

        builder = COCOAnnotationBuilder()

        ann_id = builder.add_annotation(image_id=1, category_id=1, bbox=[100, 100, 50, 30])

        assert len(builder.annotations) == 1
        assert builder.annotations[0]["id"] == ann_id
        assert builder.annotations[0]["bbox"] == [100, 100, 50, 30]
        assert builder.annotations[0]["area"] == 1500

    def test_coco_builder_serialization(self):
        """Test serializacji do formatu COCO."""
        from emit_annotations import COCOAnnotationBuilder

        builder = COCOAnnotationBuilder()
        builder.add_image(1, "test.png", 800, 600)
        builder.add_annotation(1, 1, [10, 10, 20, 20])

        coco_data = builder.to_dict()

        assert "info" in coco_data
        assert "images" in coco_data
        assert "annotations" in coco_data
        assert "categories" in coco_data

        assert len(coco_data["images"]) == 1
        assert len(coco_data["annotations"]) == 1

    def test_coco_builder_save(self, tmp_path):
        """Test zapisywania COCO do pliku."""
        from emit_annotations import COCOAnnotationBuilder

        builder = COCOAnnotationBuilder()
        builder.add_image(1, "test.png", 800, 600)
        builder.add_annotation(1, 1, [10, 10, 20, 20])

        output_path = tmp_path / "test_coco.json"
        builder.save(output_path)

        assert output_path.exists()

        # Waliduj JSON
        with open(output_path, "r") as f:
            data = json.load(f)

        assert "images" in data
        assert len(data["images"]) == 1

    def test_estimate_component_bbox(self):
        """Test szacowania bounding boxu dla komponentu."""
        from emit_annotations import estimate_component_bbox

        component = {"type": "R", "position": [500, 400], "rotation": 0}

        bbox = estimate_component_bbox(component)

        assert len(bbox) == 4  # [x, y, width, height]
        assert bbox[2] > 0  # width > 0
        assert bbox[3] > 0  # height > 0

    def test_estimate_bbox_with_rotation(self):
        """Test bounding boxu z rotacją."""
        from emit_annotations import estimate_component_bbox

        component = {"type": "R", "position": [500, 400], "rotation": 90}

        bbox_90 = estimate_component_bbox(component)

        component["rotation"] = 0
        bbox_0 = estimate_component_bbox(component)

        # Dla rotacji 90° szerokość i wysokość powinny się zamienić
        assert bbox_90[2] == bbox_0[3]
        assert bbox_90[3] == bbox_0[2]


class TestAugmentation:
    """Testy dla augment_dataset.py"""

    def test_augmentation_profiles_exist(self):
        """Test sprawdzania dostępności profili augmentacji."""
        try:
            from augment_dataset import HAS_ALBUMENTATIONS, AugmentationProfile

            if not HAS_ALBUMENTATIONS:
                pytest.skip("albumentations nie jest zainstalowany")

            # Sprawdź czy profile można utworzyć
            light = AugmentationProfile.get_light_augmentation()
            scan = AugmentationProfile.get_scan_artifacts()
            heavy = AugmentationProfile.get_heavy_augmentation()

            assert light is not None
            assert scan is not None
            assert heavy is not None

        except ImportError:
            pytest.skip("albumentations nie jest zainstalowany")

    def test_augmenter_initialization(self, tmp_path):
        """Test inicjalizacji augmentera."""
        try:
            from augment_dataset import DatasetAugmenter

            input_dir = tmp_path / "input"
            output_dir = tmp_path / "output"
            annotations = tmp_path / "annotations.json"

            input_dir.mkdir()

            # Utwórz pusty plik anotacji
            with open(annotations, "w") as f:
                json.dump({"images": [], "annotations": [], "categories": []}, f)

            augmenter = DatasetAugmenter(
                input_dir=input_dir, output_dir=output_dir, annotations_path=annotations, profile="light"
            )

            assert augmenter.input_dir == input_dir
            assert augmenter.output_dir == output_dir
            assert augmenter.profile == "light"

        except ImportError:
            pytest.skip("Brak wymaganych bibliotek")


class TestIntegration:
    """Testy integracyjne pipeline'u."""

    def test_end_to_end_metadata_flow(self, tmp_path):
        """Test przepływu: generowanie → metadane → anotacje."""
        from emit_annotations import COCOAnnotationBuilder, estimate_component_bbox
        from generate_schematic import SchematicConfig, SchematicGenerator

        # 1. Generuj schemat
        config = SchematicConfig(seed=42, num_components=5)
        generator = SchematicGenerator(config)
        metadata = generator.generate()

        # 2. Utwórz anotacje COCO
        builder = COCOAnnotationBuilder()
        builder.add_image(1, "test.png", 1000, 800)

        for i, component in enumerate(metadata["components"]):
            bbox = estimate_component_bbox(component)
            builder.add_annotation(image_id=1, category_id=1, bbox=bbox)  # Przykładowa kategoria

        # 3. Zapisz i zwaliduj
        output_path = tmp_path / "integration_test.json"
        builder.save(output_path)

        assert output_path.exists()

        with open(output_path, "r") as f:
            coco_data = json.load(f)

        assert len(coco_data["annotations"]) == len(metadata["components"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
