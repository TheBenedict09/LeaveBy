from pathlib import Path

import yaml

from app.main import app

SPEC = Path(__file__).resolve().parents[3] / "openapi.yaml"


def test_committed_openapi_matches_app():
    """Fails if someone changes a model/route without re-running `make openapi`."""
    committed = yaml.safe_load(SPEC.read_text())
    generated = yaml.safe_load(yaml.safe_dump(app.openapi(), sort_keys=True))
    assert committed == generated
