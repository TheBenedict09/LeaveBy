"""Record the provider responses for the offline demo (`make record-fixtures`).

Needs the network; uses TOMTOM_API_KEY from .env if present. Runs the real pipeline for the demo routes through a
recording HTTP transport and writes the responses to fixtures/demo/ with a manifest. The API key is never written:
it is stripped from every recorded request key, and responses do not contain it. Replay with DEMO_FIXTURES=1.
"""

import asyncio
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api import pipeline  # noqa: E402
from app.api.schemas import RecommendationRequest  # noqa: E402
from app.api.services import Services  # noqa: E402
from app.core.env import load_env  # noqa: E402
from app.core.fixtures import DEFAULT_DIR, RecordingTransport  # noqa: E402

GLC = {"label": "Glasgow Central", "lat": 55.8587, "lon": -4.2575}
ROUTES = {
    "Glasgow Central to Edinburgh Waverley": {"label": "Edinburgh Waverley", "lat": 55.9521, "lon": -3.1895},
    "Glasgow Central to Paisley Gilmour Street": {"label": "Paisley Gilmour Street", "lat": 55.8477, "lon": -4.4243},
}
PLACES = ["Edinburgh", "Paisley", "Glasgow"]


async def main() -> None:
    load_env()
    out = DEFAULT_DIR
    shutil.rmtree(out, ignore_errors=True)
    services = Services.create(client=httpx.AsyncClient(transport=RecordingTransport(out)))
    # the next weekday at 09:00, so the recorded car traffic is a working-day morning (the demo uses a weekday)
    tomorrow_9 = (datetime.now(ZoneInfo("Europe/London")) + timedelta(days=1)).replace(hour=9, minute=0, second=0)
    while tomorrow_9.weekday() >= 5:
        tomorrow_9 += timedelta(days=1)
    soon = datetime.now(UTC) + timedelta(minutes=90)  # a trip leaving now, so live traffic incidents are recorded
    for dest in ROUTES.values():
        for arrive in (soon, tomorrow_9):  # last write wins: keep tomorrow morning's predicted car traffic
            req = RecommendationRequest.model_validate(
                {"origin": GLC, "destination": dest, "arrive_by": arrive.isoformat(), "constraints": {"has_car": True}}
            )
            await pipeline.build(req, services)
    for q in PLACES:
        await services.geocode.fetch(q, 6)
    await services.client.aclose()
    files = len(list(out.glob("*.json")))
    manifest = {"recorded_at": datetime.now(UTC).isoformat(), "routes": list(ROUTES), "places": PLACES, "files": files}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"recorded {files} responses into {out}")


if __name__ == "__main__":
    asyncio.run(main())
