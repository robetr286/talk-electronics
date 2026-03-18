# H100 Benchmark Run (DigitalOcean)

This document explains how to run a fair GPU-time benchmark on an H100 droplet and collect comparable metrics for YOLOv8 and Mask R-CNN.

Prerequisites:
- DigitalOcean account with H100 droplet access.
- Docker installed on the droplet (or use the prebuilt NGC PyTorch container).
- SSH access and appropriate keys.

Build the Docker image locally or on the droplet:

```bash
docker build -t talk-electronic:latest .
```

Run the H100 benchmark script inside the container (example 2h budget for each model):

```bash
# on the droplet
docker run --gpus all -it --rm -v /path/to/data:/workspace/data -v /path/to/output:/workspace/runs/benchmarks talk-electronic:latest bash
python scripts/tools/h100_benchmark.py --yolo-data data/yolo_dataset/mix_small/dataset.yaml --coco-json data/synthetic/coco_v2_450.json \
    --yolo-budget 120 --mask-budget 120 --device cuda:0 --imgsz 512 --batch 8 --mask-batch 2 --workers 8 --output-dir runs/benchmarks/h100
```

Notes and adjustments:
- `--yolo-budget`/`--mask-budget` specify minutes of GPU-time to allocate to each model.
- Adjust `--batch` and `--mask-batch` to fit memory of the H100 (H100 supports larger batches than local A2000).
- When using the NGC NVIDIA container, you may omit CUDA toolkit installation.

Cost estimate:
- DigitalOcean H100 pricing varies; verify the provider's rate. Use GPU-time budget to estimate cost: `cost = hourly_rate * total_hours`. Example: 2 hours @ $X/hr -> cost $2X.

Rough runtime estimates (conservative):
- YOLOv8: 5–12× speedup vs local A2000. Example: a 10.4 h local run reduces to ~0.9–2.1 h on H100.
- Mask R-CNN: 5–12× speedup vs local A2000. Example: a 15.2 h local run reduces to ~1.3–3.0 h on H100.

Note: Final speedups will vary depending on batch sizes, IO, and whether AMP/FP16 is used.

After experiment finishes, the results JSON will be in `runs/benchmarks/h100` with timing and saved models/dirs.
