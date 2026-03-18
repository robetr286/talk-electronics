"""Prosty trening CNN dla patchy skrzyżowań linii.

Uruchomienie:
    python scripts/train_junction_classifier.py \
        --data-root data/sample_benchmark/junction_patches \
        --manifest manifest.csv \
        --output-model models/junction_classifier.onnx

Skrypt zakłada, że struktura katalogów zawiera podfoldery odpowiadające etykietom
(np. dot_present/no_dot/unknown), a plik manifestu posiada kolumny filename, label,
node_id, degree, position_row, position_col, timestamp.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, random_split

DEFAULT_LABELS = ("dot_present", "no_dot", "unknown")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trenuje mały klasyfikator patchy junction.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/sample_benchmark/junction_patches"),
        help="Katalog z podfolderami etykiet oraz plikami PNG",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Ścieżka do manifest.csv (domyślnie data-root/manifest.csv)",
    )
    parser.add_argument(
        "--output-model",
        type=Path,
        default=Path("models/junction_classifier.onnx"),
        help="Ścieżka docelowa dla modelu ONNX",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=Path("models/junction_classifier.metrics.json"),
        help="Plik JSON z metrykami",
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val-split", type=float, default=0.2, help="Procent danych na walidację")
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="Ziarno generatora losowego (pozwala odtwarzać podziały)",
    )
    return parser.parse_args()


@dataclass
class Sample:
    path: Path
    label: int


class JunctionPatchDataset(Dataset):
    def __init__(self, samples: Sequence[Sample]):
        self.samples = list(samples)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        sample = self.samples[idx]
        image = cv2.imread(str(sample.path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"Nie udało się wczytać patcha: {sample.path}")
        array = image.astype(np.float32) / 255.0
        tensor = torch.from_numpy(array).unsqueeze(0)
        label = torch.tensor(sample.label, dtype=torch.long)
        return tensor, label


class SmallJunctionCNN(nn.Module):
    def __init__(self, num_classes: int) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((2, 2)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 2 * 2, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.2),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.features(x)
        return self.classifier(features)


def read_manifest(manifest_path: Path, data_root: Path, labels: Sequence[str]) -> List[Sample]:
    label_to_idx = {label: idx for idx, label in enumerate(labels)}
    samples: List[Sample] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            label = row.get("label", "").strip() or "unknown"
            filename = row.get("filename")
            if not filename:
                continue
            if label not in label_to_idx:
                continue
            candidate = data_root / label / filename
            if not candidate.exists():
                # Spróbuj bezpośrednio w katalogu root jeśli użytkownik przeniósł plik ręcznie.
                fallback = data_root / filename
                if fallback.exists():
                    candidate = fallback
                else:
                    continue
            samples.append(Sample(candidate, label_to_idx[label]))
    if not samples:
        raise ValueError("Manifest nie zawiera żadnych poprawnych wpisów.")
    random.shuffle(samples)
    return samples


def split_dataset(samples: Sequence[Sample], val_split: float) -> Tuple[Dataset, Dataset]:
    dataset = JunctionPatchDataset(samples)
    if val_split <= 0.0 or len(dataset) < 5:
        return dataset, JunctionPatchDataset([])
    val_size = max(1, int(len(dataset) * min(0.9, val_split)))
    train_size = max(1, len(dataset) - val_size)
    return random_split(dataset, [train_size, val_size])


def train(model: nn.Module, loader: DataLoader, criterion, optimizer, device: torch.device) -> Tuple[float, float]:
    model.train()
    total_loss = 0.0
    total_correct = 0
    total_samples = 0
    for inputs, labels in loader:
        inputs = inputs.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * inputs.size(0)
        preds = outputs.argmax(dim=1)
        total_correct += (preds == labels).sum().item()
        total_samples += inputs.size(0)
    avg_loss = total_loss / max(1, total_samples)
    accuracy = total_correct / max(1, total_samples)
    return avg_loss, accuracy


def evaluate(model: nn.Module, loader: DataLoader, criterion, device: torch.device) -> Tuple[float, float]:
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_samples = 0
    with torch.no_grad():
        for inputs, labels in loader:
            inputs = inputs.to(device)
            labels = labels.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            total_loss += loss.item() * inputs.size(0)
            preds = outputs.argmax(dim=1)
            total_correct += (preds == labels).sum().item()
            total_samples += inputs.size(0)
    avg_loss = total_loss / max(1, total_samples)
    accuracy = total_correct / max(1, total_samples)
    return avg_loss, accuracy


def export_model(model: nn.Module, output_path: Path, num_classes: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    dummy_input = torch.randn(1, 1, 32, 32)
    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        input_names=["patch"],
        output_names=["logits"],
        dynamic_axes={"patch": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )


def save_metrics(metrics_output: Path, metrics: Dict[str, float], extra: Dict[str, str]) -> None:
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metrics": metrics,
        "meta": extra,
    }
    metrics_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    manifest = args.manifest or args.data_root / "manifest.csv"
    if not manifest.exists():
        raise FileNotFoundError(f"Nie znaleziono manifestu pod ścieżką {manifest}")

    samples = read_manifest(manifest, args.data_root, DEFAULT_LABELS)
    train_dataset, val_dataset = split_dataset(samples, args.val_split)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SmallJunctionCNN(num_classes=len(DEFAULT_LABELS)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)

    history: List[Dict[str, float]] = []
    best_val_acc = 0.0
    best_state = None

    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = train(model, train_loader, criterion, optimizer, device)
        if len(val_dataset) > 0:
            val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        else:
            val_loss, val_acc = 0.0, 0.0
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "train_acc": train_acc,
                "val_loss": val_loss,
                "val_acc": val_acc,
            }
        )
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            best_state = model.state_dict()
        print(
            f"Epoch {epoch:02d} | train_loss={train_loss:.4f} acc={train_acc:.3f} "
            f"val_loss={val_loss:.4f} acc={val_acc:.3f}"
        )

    if best_state is not None:
        model.load_state_dict(best_state)

    export_model(model, args.output_model, num_classes=len(DEFAULT_LABELS))

    metrics = {
        "train_loss": history[-1]["train_loss"],
        "train_acc": history[-1]["train_acc"],
        "val_loss": history[-1]["val_loss"],
        "val_acc": history[-1]["val_acc"],
        "best_val_acc": best_val_acc,
    }
    meta = {
        "timestamp": datetime.utcnow().isoformat(),
        "device": str(device),
        "epochs": str(args.epochs),
        "samples": str(len(samples)),
    }
    save_metrics(args.metrics_output, metrics, meta)
    print(f"Zapisano model ONNX do {args.output_model}")
    print(f"Zapisano metryki do {args.metrics_output}")


if __name__ == "__main__":
    main()
