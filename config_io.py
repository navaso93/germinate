"""Read JSON configuration with optional leading // comment lines."""
import json
from pathlib import Path


def load_json(path):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("//") or not line.strip():
            lines[index] = "\n"
        else:
            break
    return json.loads("".join(lines))
