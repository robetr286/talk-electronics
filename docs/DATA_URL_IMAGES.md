# Data-URL images (inline) for /api/segment/lines

Short note: the segmentation endpoint `/api/segment/lines` accepts images provided inline as a data-URL (for example `data:image/png;base64,...`). The backend decodes the base64 payload and loads the image using OpenCV, so the client does not need to upload a file to `uploads/` first.

Why it matters
- Useful for deterministic E2E tests (Playwright) — tests can inject the exact image bytes without depending on server-side fixture paths.
- Handy for integration scenarios where the client has an image in memory (canvas) and wants to run segmentation without a round-trip upload.

Example payload
```json
{
  "imageUrl": "data:image/png;base64,<BASE64_PAYLOAD>",
  "roi": { "x": 10, "y": 10, "width": 50, "height": 50 },
  "storeHistory": true
}
```

Notes & guidance
- The endpoint accepts the same geometry and ROI fields as when using a file URL; if ROI is provided, the server will crop the image before running detection and attach `metadata.roi` to the response.
- Keep an eye on message size: embedding large high-resolution images as data-URL increases request size — prefer smaller crops for interactive use.

Related docs
- `README.md` (Usage → Wysyłanie obrazów inline)
- `tests/test_segment_routes.py` (unit test demonstrating data-URL usage)

(Generated: 2026-01-10)
