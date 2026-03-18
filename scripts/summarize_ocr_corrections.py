"""Command‑line utility to print a human‑readable summary of OCR corrections.

Designed to be run periodically by cron or a task scheduler.  It uses the
functions from ``talk_electronic.ocr_corrections`` to scan the corrections
directory and emit a simple report to stdout.

Usage:
    python scripts/summarize_ocr_corrections.py
"""

from __future__ import annotations

import pprint
from pathlib import Path

from talk_electronic import ocr_corrections


def main():
    directory = Path("reports/textract/corrections")
    summary = ocr_corrections.summarize_corrections(directory=directory)
    print("OCR Corrections summary:")
    pprint.pprint(summary)
    # optionally write a log file or send to monitoring


if __name__ == "__main__":
    main()
