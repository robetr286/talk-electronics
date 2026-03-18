import pprint
import sys
from pathlib import Path

import yaml


def load_yaml(path: Path):
    text = path.read_text(encoding="utf-8")
    print(f"length {len(text)}")
    return yaml.safe_load(text)


def main(args):
    target = Path(args[0]) if args else Path(".github/workflows/preflight.yml")
    if not target.exists():
        print(f"Brak pliku: {target}")
        return 1

    try:
        data = load_yaml(target)
        pprint.pprint(data)
        keys = list(data.keys()) if isinstance(data, dict) else type(data)
        print("\nParsed YAML top-level keys:", keys)
    except Exception as exc:
        print("YAML parse error:", exc)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
