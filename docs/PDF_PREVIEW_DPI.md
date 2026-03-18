PDF Preview DPI and Automatic Clamping

Overview
--------
To avoid creating extremely large bitmap previews (which may hang browsers or consume too much memory on the server), the app now applies an automatic pixel-based clamp to preview/export DPI values.

Key points
----------
- A server-side limit controls the maximum allowed pixels on the longer side of a rendered preview image. Default: 10000 pixels.
- The max pixel limit can be overridden via Flask config: `app.config['MAX_PREVIEW_PIXELS']`.
- When a requested DPI would produce an image exceeding this limit, the server reduces the DPI so the resulting width/height stay within the configured bound.
- API changes:
  - `/page/<token>/<page>` now returns `requested_dpi`, `applied_dpi` and `clamped` in the JSON response.
  - `/page/<token>/<page>/export` also returns the same fields and `clamped_dpi` when a clamp occurred.
- Frontend changes:
    - The export UI shows the preview DPI and estimated dimensions before rendering.

Notes for developers
--------------------
- The default maximum preview pixel length is defined as `DEFAULT_MAX_PREVIEW_PX = 10000` in `talk_electronic/routes/pdf_routes.py`.
- Helper functions `_compute_max_dpi_for_pdf` and `_compute_max_dpi_for_image` compute the DPI clamping based on page dimensions.
- Tests were added to `tests/test_pdf_export.py` verifying that extremely large pages are clamped and that upload responses include `requested_dpi`/`applied_dpi`/`clamped`.

If you need different limits for local testing or production, set `app.config['MAX_PREVIEW_PIXELS']` accordingly (e.g., 8000 or 16000).
