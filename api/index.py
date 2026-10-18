"""Vercel entry point: the FastAPI app as one Python function. vercel.json routes /v1/* and /healthz here."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402,F401
