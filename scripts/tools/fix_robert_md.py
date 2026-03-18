from pathlib import Path

p = Path("robert_to_do 09_12_2025.md")
s = p.read_text(encoding="utf-8", errors="replace")
# Show the region after the final '---' separator to inspect duplication and encoding
sep = "---\n\n"
pos = s.rfind(sep)
if pos != -1:
    snippet = s[pos : pos + 800]
    print("Found separator at", pos)
    print("Snippet repr:\n", repr(snippet))
else:
    print("Separator not found")
# Additionally print last 400 chars for manual inspection
print("\n---\nTail repr:\n", repr(s[-400:]))
# As a fallback, keep only lines up to the explicit question line (clean UTF-8 section)
keep_marker = "Chcesz, żebym teraz uruchomił sanity-check"
idx = s.find(keep_marker)
if idx != -1:
    # keep up to the end of the line that contains the marker
    line_end = s.find("\n", idx)
    if line_end == -1:
        line_end = len(s)
    new = s[: line_end + 1]
    p.write_text(new, encoding="utf-8")
    print("Truncated file at marker", keep_marker, "new length", len(new))
else:
    print("Keep marker not found; no truncation performed")
