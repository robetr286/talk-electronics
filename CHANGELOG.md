# CHANGELOG

All notable changes to this project will be documented in this file.

## Unreleased

### Added
- 2026-01-10: Backend accepts images provided as data-URL (`data:image/png;base64,...`) in `/api/segment/lines` and decodes them server-side (OpenCV). This fixes flakiness in ROI-related E2E tests and allows deterministic image injection in tests.
- 2026-01-10: Added unit test `test_segment_with_data_url_image_and_roi` and E2E stabilizations for ROI tests (Playwright smoke now passes locally: 11/11).

### Fixed
- 2026-01-10: Fix intermittent 404 in ROI E2E by supporting inline image data and improving test determinism.

---

(Generated: 2026-01-10)
