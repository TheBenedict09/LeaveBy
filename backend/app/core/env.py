"""Read the repo's .env into the process environment (no extra dependency). Values already set win, so tests
and real deployments can override or blank anything. Never logs values."""

import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[3] / ".env"


def load_env(path: Path = DEFAULT_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.split(" #", 1)[0].strip().strip("'\""))
