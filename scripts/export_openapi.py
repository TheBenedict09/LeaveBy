"""Write the generated OpenAPI spec to openapi.yaml.  Run: make openapi"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.main import app  # noqa: E402

out = Path(__file__).resolve().parents[1] / "openapi.yaml"
out.write_text(yaml.safe_dump(app.openapi(), sort_keys=True, allow_unicode=True))
print(f"wrote {out}")
