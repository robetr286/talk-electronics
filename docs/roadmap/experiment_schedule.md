# Experiment Rollout Schedule

This roadmap coordinates upcoming detector experiments and validation cycles.

## Objectives
1. Establish a baseline detector (NoOp → classic CV pipeline → first ML model).
2. Run controlled A/B tests comparing detectors on identical datasets.
3. Track deployment readiness with clear promotion gates.

## Iteration Plan
| Iteration | Target Dates | Milestones | Exit Criteria |
|-----------|--------------|------------|----------------|
| 0 (current) | 2025-11-05 → 2025-11-12 | Data validation tools (`scripts/validate_annotations.py`), inference benchmark harness, annotation SOP | Scripts executed on sample exports; benchmark produces repeatable timing |
| 1 | 2025-11-13 → 2025-11-27 | Integrate classical detector (template matching) with registry; populate `data/sample_benchmark/` | Precision/recall report on 20 gold-standard sheets ≥ 0.65 F1 |
| 2 | 2025-11-28 → 2025-12-12 | Train first ML detector (YOLOv8-small); automate weight packaging | Model exported to ONNX ≤ 50 MB; passes regression tests |
| 3 | 2025-12-13 → 2025-12-31 | A/B experiment in staging with ML vs classical | Latency within +25% of baseline; diagnostic chat integration verified |

## Governance
- **Experiment Owner**: ML engineer assigned per iteration (update this table as staffing changes).
- **Review Cadence**: weekly sync every Monday; publish notes in `docs/roadmap/notes/<YYYY-MM-DD>.md`.
- **Promotion Gate**: require sign-off from QA + product before deploying to production detectors list.

## Action Items
- Generate initial benchmark dataset (`data/sample_benchmark/`) with curated PNG crops.
- Automate benchmark run in CI once detectors produce meaningful results.
- Define rollback plan for detector regressions (toggle via configuration flag in Flask app).
