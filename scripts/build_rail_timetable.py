"""Build data/rail_timetable.json, the small real-timetable extract the engine uses (`make rail-data`).

Downloads the GB national rail GTFS feed published by planarnetwork/gb-transit (built weekly from the Rail
Delivery Group DTD timetable) into data/cache/ (git-ignored, ~31 MB), then keeps only direct trips between the
stations below, for one reference date per day type (Mon-Thu, Fri, Sat, Sun). Bank holidays are not modelled:
a date uses its day type's reference timetable.

    python scripts/build_rail_timetable.py [--refresh]
"""

import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.gtfs_extract import extract  # noqa: E402

RELEASE_API = "https://api.github.com/repos/planarnetwork/gb-transit/releases/latest"
ASSET = "gtfs-national-rail-only.zip"
CACHE = ROOT / "data" / "cache" / ASSET
OUT = ROOT / "data" / "rail_timetable.json"
ATTRIBUTION = "Timetable data: Rail Delivery Group (DTD feed), via planarnetwork/gb-transit"

# CRS code -> the stop_id, stop_code or exact stop_name to look for in the feed.
STATIONS = {
    "GLC": "Glasgow Central",
    "GLQ": "Glasgow Queen Street",
    "EDB": "Edinburgh",
    "PYG": "Paisley Gilmour Street",
    "FKK": "Falkirk High",
    "STG": "Stirling",
    "PTH": "Perth",
    "DEE": "Dundee",
    "ABD": "Aberdeen",
    "INV": "Inverness",
    "CAR": "Carlisle",
    "NCL": "Newcastle",
    "MAN": "Manchester Piccadilly",
    "EUS": "London Euston",
    "KGX": "London Kings Cross",
}


def main() -> None:
    release = json.load(urllib.request.urlopen(RELEASE_API))
    if "--refresh" in sys.argv or not CACHE.exists():
        url = next(a["browser_download_url"] for a in release["assets"] if a["name"] == ASSET)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, CACHE)
    with zipfile.ZipFile(CACHE) as z:
        # Match on CRS code first (stop_code), then on name, so the extract survives either id scheme.
        stops = {r for r in z.read("stops.txt").decode("utf-8-sig").splitlines()[1:]}
        wanted = {crs: (crs if any(f",{crs}," in s for s in stops) else name) for crs, name in STATIONS.items()}
        data = extract(z, wanted)
    missing = sorted(set(STATIONS) - set(data["stations"]))
    out = {"source": ATTRIBUTION, "release": release["tag_name"], **data}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    n = sum(len(rows) for by_type in data["pairs"].values() for rows in by_type.values())
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB): {len(data['pairs'])} pairs, {n} trains")
    if missing:
        print(f"not found in the feed: {', '.join(missing)}")


if __name__ == "__main__":
    main()
