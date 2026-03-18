from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from flask import Flask

from .pdf_store import PdfStore
from .services.diagnostic_chat import DiagnosticChatStore
from .services.edge_connector_store import EdgeConnectorStore
from .services.ignore_store import IgnoreRegionStore
from .services.processing_history import ProcessingHistoryStore
from .services.retouch_buffer import RetouchBuffer
from .services.symbol_detection import YoloV8SegDetector, available_detectors, register_detector
from .services.symbol_detection.noop import NoOpSymbolDetector
from .services.symbol_detection.rtdetr import RTDETRDetector
from .services.symbol_detection.simple import SimpleThresholdDetector
from .services.symbol_detection.template_matching import TemplateMatchingDetector
from .services.temp_files import cleanup_temp_files


def create_app(test_config: Mapping[str, Any] | None = None) -> Flask:
    """Application factory used by the WSGI entry point and tests."""
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent

    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )

    # Base configuration shared across environments.
    default_config: dict[str, Any] = {
        "UPLOAD_FOLDER": Path("uploads").resolve(),
        "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,  # 16MB
        "AUTO_CLEAN_TEMP_ON_START": True,
    }

    app.config.from_mapping(default_config)

    if test_config:
        # Ensure any externally provided upload path is converted to an absolute Path.
        override_config = dict(test_config)
        if "UPLOAD_FOLDER" in override_config:
            override_config["UPLOAD_FOLDER"] = Path(override_config["UPLOAD_FOLDER"]).resolve()
        app.config.update(override_config)

    upload_folder: Path = Path(app.config["UPLOAD_FOLDER"]).resolve()
    upload_folder.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder

    processed_folder = upload_folder / "processed"
    processed_folder.mkdir(parents=True, exist_ok=True)
    app.config["PROCESSED_FOLDER"] = processed_folder

    retouch_folder = upload_folder / "retouch"
    retouch_folder.mkdir(parents=True, exist_ok=True)
    app.config["RETOUCH_FOLDER"] = retouch_folder

    history_store = ProcessingHistoryStore(upload_folder / "processing-history.json")
    retouch_buffer = RetouchBuffer(retouch_folder / "retouch-buffer.json")
    chat_store = DiagnosticChatStore(upload_folder / "diagnostic-chat.json")
    ignore_store = IgnoreRegionStore(upload_folder / "ignore-regions")
    edge_connector_store = EdgeConnectorStore(upload_folder / "edge-connectors")

    pdf_store = PdfStore()
    app.extensions["pdf_store"] = pdf_store
    app.extensions["processing_history"] = history_store
    app.extensions["retouch_buffer"] = retouch_buffer
    app.extensions["diagnostic_chat"] = chat_store
    app.extensions["ignore_store"] = ignore_store
    app.extensions["edge_connector_store"] = edge_connector_store

    try:
        if NoOpSymbolDetector.name not in available_detectors():
            register_detector(NoOpSymbolDetector.name, NoOpSymbolDetector)
        if SimpleThresholdDetector.name not in available_detectors():
            register_detector(SimpleThresholdDetector.name, SimpleThresholdDetector)
        if TemplateMatchingDetector.name not in available_detectors():
            register_detector(TemplateMatchingDetector.name, TemplateMatchingDetector)
        if YoloV8SegDetector.name not in available_detectors():
            register_detector(YoloV8SegDetector.name, YoloV8SegDetector)
        if RTDETRDetector.name not in available_detectors():
            register_detector(RTDETRDetector.name, RTDETRDetector)
    except Exception:  # pragma: no cover - defensive guard
        app.logger.exception("Failed to register builtin symbol detectors")

    from .routes.core import core_bp
    from .routes.crop_routes import crop_bp
    from .routes.diagnostic_chat import diagnostic_chat_bp
    from .routes.diagnostics import diagnostics_bp
    from .routes.edge_connectors import edge_connectors_bp
    from .routes.ignore_regions import ignore_bp
    from .routes.maintenance import maintenance_bp
    from .routes.pdf_routes import pdf_bp
    from .routes.processing import processing_bp
    from .routes.segment import segment_bp
    from .routes.symbol_detection import symbol_detection_bp
    from .routes.textract import textract_bp
    from .routes.paddleocr_route import paddleocr_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(pdf_bp)
    app.register_blueprint(crop_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(processing_bp)
    app.register_blueprint(segment_bp)
    app.register_blueprint(diagnostic_chat_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(symbol_detection_bp)
    app.register_blueprint(ignore_bp)
    app.register_blueprint(edge_connectors_bp)
    app.register_blueprint(textract_bp)
    app.register_blueprint(paddleocr_bp)

    line_config_path = project_root / "configs" / "line_detection.defaults.json"
    if line_config_path.exists():
        try:
            data = json.loads(line_config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config_data = dict(data)
                color_presets = config_data.pop("color_presets", None)
                app.config["LINE_DETECTION_DEFAULTS"] = config_data
                if isinstance(color_presets, dict):
                    app.config["LINE_DETECTION_COLOR_PRESETS"] = color_presets
        except Exception:  # pragma: no cover - best effort
            app.logger.warning("Nie udało się wczytać %s", line_config_path, exc_info=True)

    if app.config.get("AUTO_CLEAN_TEMP_ON_START", True):
        preserved = history_store.get_referenced_filenames()
        preserved.update(retouch_buffer.get_preserved_filenames())
        removed_count, freed_space = cleanup_temp_files(upload_folder, pdf_store, preserved)
        freed_mb = freed_space / (1024 * 1024)
        app.logger.info(
            "Removed %s temporary file(s) at startup (%.2f MB)",
            removed_count,
            freed_mb,
        )

    return app
