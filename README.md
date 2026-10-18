# LeaveBy

**When must I leave to be sure I arrive on time?**

LeaveBy answers that one question with one clear decision: a leave-by time, the way to travel, and how sure it is. You pick where you are going, when you must be there and how confident you want to be (for example 95%). LeaveBy simulates 2,040 possible versions of the journey for each way of travelling, using a real weather forecast ensemble, real train times and traffic, and recommends the latest departure that still gets you there at that confidence. It was built for the BlackRock challenge "One app. One clear decision" and covers multimodal travel: walking, cycling, driving and the train.

## What you see

1. **Plan a trip.** Type any place (or pick a demo route), choose the arrival time and day, and say whether you have a car.
2. **The verdict.** "Leave at 07:33", the real train to catch ("Catch the 07:45 ScotRail from Glasgow Queen Street, arrives Edinburgh at 08:37"), the chance you arrive on time from the forecast for your route ("97% chance, late about 1 morning in 33"), cost, CO2e and access score, the CO2e saved against driving, and the car's traffic basis.
3. **Why.** Plain sentences from the scoring: why this option wins and what would change it ("If easy access counted for 50% instead of 20%, driving would win").
4. **Your priorities.** Time, Cost, Carbon and Access sliders re-rank the options instantly. Only options that meet your confidence are ranked.
5. **How sure do you want to be?** The confidence slider moves the leave-by time live.
6. **What if I leave later?** A slider shows each option's chance of arriving on time if you leave at a different time.
7. **Backup plan.** The alternative least likely to be late on the same mornings as the main plan.
8. **Trade-offs chart.** Every reliable option by leave-by time and CO2e, sized by cost, coloured by how often it is late.
9. **Weather on your trip.** The real forecast when you leave and when you must arrive (rain chance as "38 of 51 forecasts", the wet end, gusts, temperature), how many minutes the weather costs each option compared with a dry, calm morning, the gust effect on train delays, and tips that follow from the forecast.
10. **How the forecast could play out.** Each dot is one of the 51 official forecasts for your start point and morning, against the deadline. Hover a dot to see that forecast's weather and every option's arrival; click to pin it.
11. **Sources and assumptions.** A panel listing every data source behind the answer with an honest trust badge, and the key assumptions.
12. **Add to calendar.** Downloads an event for the leave-by time with a 10 minute alarm, the train to catch and the backup.

## Run it

Requirements: Python 3.12 or later, Node 22.12 or later (Vite 8).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]" pyyaml
cd web && npm install && cd ..
```

Start the API (port 8000) and the web app (port 5173) in two terminals, both from the repo root:

```bash
make dev
```

```bash
cd web && npm run dev
```

Then open http://localhost:5173. The web dev server proxies `/v1` and `/healthz` to the API.

### Settings (`.env`)

Copy `.env.example` to `.env` and fill in what you need. `.env` is git-ignored; never commit real values.

| Variable | Needed? | What it does |
|---|---|---|
| `TOMTOM_API_KEY` | Optional | Car times with TomTom traffic and live incidents. Without it the app works as before and uses free-flow car times from OSRM. |
| `LEAVEBY_USER_AGENT` | Recommended | User-Agent sent to the free OSRM and Open-Meteo services. |
| `LEAVEBY_CORS_ORIGINS` | Optional | Allowed web origins for the API (default `http://localhost:5173`). |
| `DEMO_FIXTURES` | Optional | `1` replays the recordings in `fixtures/demo/` with no network (Glasgow Central to Edinburgh Waverley and to Paisley Gilmour Street). Every source shows as Recorded. Re-record with `make record-fixtures` (needs the network). |

### Tests and checks

```bash
make test        # backend tests (pytest), no network needed
make lint        # ruff check and format check
make fmt         # fix formatting
make openapi     # regenerate openapi.yaml from the API (the contract test fails if it drifts)
cd web && npm run lint && npm run build
```

`node scripts/check_no_duplicate_cards.mjs` (with the API and web dev server running, and Chrome installed) checks that every result card appears once after repeated searches and calendar clicks.

`make rail-data` rebuilds `data/rail_timetable.json` from the national timetable (downloads about 31 MB into the git-ignored `data/cache/`). You only need it to refresh the timetable.

## Data sources

The same badges appear in the app's "Sources and assumptions" panel.

| Data | Source | Status |
|---|---|---|
| Weather (rain, wind, gusts, visibility, temperature) | Open-Meteo ensemble API, ECMWF IFS 0.25, 51 members | Live |
| Routes and base times for walk, bike, car | FOSSGIS OSRM on OpenStreetMap | Live |
| Car traffic for trips leaving within 2 hours, and incidents near the route | TomTom Routing and Traffic Incidents (only with a key) | Live |
| Car traffic for later trips | TomTom predicted traffic for that departure time (only with a key) | Predicted |
| Place search | Open-Meteo geocoding, with a built-in UK list as fallback | Live (Fallback when offline) |
| Train timetable | GB national timetable extract, 15 stations, 115 station pairs | Static |
| Carbon per km | UK Government GHG conversion factors 2026 (DESNZ) | Static |
| Train delays | Simulated, calibrated to published punctuality | Modelled |
| Traffic and walking/cycling variation | Seeded random noise on top of the base times | Modelled |
| Fares and running costs | Placeholder values | Mock |
| Step-free access and effort score | Placeholder values | Mock |
| "Simulate an accident" | Demo switch, off by default | Simulated |

Credits and licences:

- **Rail timetable:** Timetable data: Rail Delivery Group (DTD feed), via planarnetwork/gb-transit. The feed lists the Rail Settlement Plan data licence for the RDG data; keep this credit visible. Release `feed-2026-10-17`, valid 17 October 2026 to 17 January 2027. Bank holidays are not modelled.
- **CO2e:** UK Government greenhouse gas conversion factors for company reporting 2026 (DESNZ), Open Government Licence v3.0. Average car (unknown fuel) 0.16590 kg CO2e per km, national rail 0.03092 kg per passenger km.
- **Train delay calibration:** in calm weather 86.5% of trains arrive within 5 minutes, the mean Edinburgh to Glasgow PPM for the years to March 2017 to 2020 (Scottish Government FOI 202100260453); the ORR data portal reports 85.0% within 3 minutes nationally for April to June 2026.
- **Weather icons:** Meteocons by Bas Milius (MIT licence), bundled locally (`@bybas/weather-icons`).
- **Weather and geocoding:** Open-Meteo.com, non-commercial use. **Routing:** OSRM, map data (c) OpenStreetMap contributors (ODbL). **Traffic:** TomTom.

## Known limitations

- Fares and the access score are placeholders, not real data.
- Train delays are simulated (weather-linked and calibrated), not live. Real-time train running data is not connected.
- The timetable uses one typical day for each of Monday to Thursday, Friday, Saturday and Sunday. Bank holidays and engineering works are not modelled.
- The walk to and from the station is a fixed allowance (12 minutes to the platform, 8 minutes from it), not routed.
- Train cost and CO2e use the road distance as a stand-in for the rail distance.
- Incidents are only fetched for trips leaving within 2 hours, and not for very long trips (the search area is too large for one request).
- The offline demo mode only covers the two recorded routes.
- Recommendations are kept in memory, so a restart of the API expires them (the app then asks you to search again).

## 3-minute demo script

Use the next weekday ("In 2 days" on a Saturday) so the real weekday timetable applies.

1. **(30 s) The question.** "Google tells you the average. LeaveBy tells you when to leave to be 95% sure." Click the **Glasgow → Edinburgh by car** chip, pick a weekday, press **When should I leave?**
2. **(30 s) The verdict.** Read "Leave at 07:33", the real 07:45 ScotRail from Queen Street, the chance of arriving on time, the "Weather on your trip" card (how many minutes the weather costs), and "Saves 10.6 kg CO2e vs driving". Point at the car line: predicted traffic makes the car 83 minutes, so the train wins.
3. **(30 s) Uncertainty you can see.** Scroll to the raincloud: each dot is one possible morning. Hover a dot to show the same morning for train and car; click to pin it.
4. **(30 s) Your priorities.** Push **Access** up: the car takes over, and the "why" line explains the flip. Press **Reset**. Move the **confidence** slider from 95% to 80% and watch the leave-by time move later.
5. **(30 s) What if I'm late?** In "What if I leave later?", drag to 07:45: the train drops to 0% because the 07:45 is gone, the car to about 19%.
6. **(20 s) Honesty.** Turn on **Simulate an accident (demo)** and search again: the car gets +15 minutes and a "Simulated" badge. Open **Sources and assumptions** to show what is live, static, modelled and mock.
7. **(10 s) Done.** Press **Add to calendar**.

Good backup routes: Glasgow → Paisley (short trip, the bike and train compete). Glasgow → London Euston or Aberdeen show "No train runs early enough" at 95% for a 09:00 arrival, which is a good honesty example but not a headline demo.
