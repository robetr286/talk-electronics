from __future__ import annotations

from typing import Callable, Dict, Iterable

from .base import SymbolDetector

DetectorFactory = Callable[[], SymbolDetector]


class DetectorRegistry:
    """Simple in-memory registry for symbol detectors."""

    def __init__(self) -> None:
        self._factories: Dict[str, DetectorFactory] = {}

    def register(self, name: str, factory: DetectorFactory, *, replace: bool = False) -> None:
        key = name.lower()
        if key in self._factories and not replace:
            raise ValueError(f"Detector '{name}' already registered")
        self._factories[key] = factory

    def create(self, name: str) -> SymbolDetector:
        key = name.lower()
        if key not in self._factories:
            raise KeyError(f"Detector '{name}' is not registered")
        detector = self._factories[key]()
        detector.warmup()
        return detector

    def available(self) -> Iterable[str]:
        return tuple(sorted(self._factories.keys()))


_global_registry = DetectorRegistry()


def register_detector(name: str, factory: DetectorFactory, *, replace: bool = False) -> None:
    _global_registry.register(name, factory, replace=replace)


def create_detector(name: str) -> SymbolDetector:
    return _global_registry.create(name)


def available_detectors() -> Iterable[str]:
    return _global_registry.available()
