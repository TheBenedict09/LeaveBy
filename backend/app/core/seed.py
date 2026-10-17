import hashlib
import json
from typing import Any


def seed_from(obj: Any) -> int:
    """Stable 32-bit seed from any JSON-able object (key order does not matter)."""
    blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()
    return int.from_bytes(hashlib.sha256(blob).digest()[:4], "big")
