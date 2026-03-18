#!/usr/bin/env python3
import re
from datetime import datetime
from pathlib import Path

PATH = Path("qa_log.md")
text = PATH.read_text(encoding="utf-8")

# split preamble before first dated heading
pattern = re.compile(r"(^#{2,3}\s*(\d{4}-\d{2}-\d{2})\b.*)", re.MULTILINE)
m = pattern.search(text)
if not m:
    print("No dated sections found; no changes made.")
    exit(0)

preamble = text[: m.start()].rstrip() + "\n\n"
rest = text[m.start() :]

# split into sections by headings starting with ## or ### and date
sections = re.split(r"(?=(?:^#{2,3}\s*\d{4}-\d{2}-\d{2}\b))", rest, flags=re.MULTILINE)

entries = []
for sec in sections:
    if not sec.strip():
        continue
    # find date
    h = re.match(r"^(#{2,3})\s*(\d{4}-\d{2}-\d{2})\b", sec)
    if h:
        date = datetime.strptime(h.group(2), "%Y-%m-%d")
        entries.append((date, sec))
    else:
        # put into preamble if no date
        preamble += sec

# sort by date ascending
entries.sort(key=lambda x: x[0])

new_text = preamble + "\n".join(sec for _, sec in entries).rstrip() + "\n"
PATH.write_text(new_text, encoding="utf-8")
print("qa_log.md sorted; sections:", len(entries))
