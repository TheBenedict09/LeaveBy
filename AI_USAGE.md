# AI usage

**To confirm before submission** (only I can answer these; delete this block when done):

- <!-- ABS: confirm how much of steps 1 to 6 you typed or edited by hand and which AI tool you used locally -->
- <!-- ABS: same question for the first web commits ("built web/src typescript structure", "composer and the new app.tsx added") -->

## Summary

LeaveBy is my solo project for GUTS 2026, BlackRock challenge "One app. One clear decision". I built it with heavy AI assistance. I used Claude in two ways: a planning and coaching chat, and a Claude Code session on my Mac that wrote and changed most of the code at my direction. I chose the idea, made the product decisions, tested the app by hand, reviewed and merged every pull request.

## What I did myself

**The idea.** I chose the challenge and the core idea: instead of an average ETA, give one leave-by time with an explicit confidence level ("leave at 07:33 to be 95% sure"), across walking, cycling, driving and the train.

**Product decisions.**

- Real data over mock. I asked for a real UK rail timetable instead of made-up trains. I created the TomTom developer account and API key and put it in `.env` myself.
- CO2e and priorities (time, cost, carbon, access) as inputs to the decision, not just extra numbers.
- Honesty labels. I asked what in the app was real and what was mock; that became the Live, Predicted, Static, Modelled, Mock and Simulated badges and the "Sources and assumptions" panel.
- Weather first. I said "on time in 1,977 of 2,040 simulated journeys" meant nothing to a user, so the app now leads with the real forecast, the minutes the weather costs, and chances in plain words ("late about 1 morning in 33").
- I cut the "simulate a stormy morning" feature (PR 23 closed) because it was a fake demo switch, not a decision aid.
- After pressing the button the page scrolls to "Your verdict", not to a chart.
- Layout and design feedback from screenshots: empty left side, squashed map, dead space, the confidence slider moved up into the verdict, legends instead of text-heavy blocks, proper weather icons inside the weather card, no header animation, an explainer for the access score.

**Hand testing and bug reports.**

- The place dropdown was clipped by its card.
- Result cards duplicated after repeated clicks and "Add to calendar".
- Layout dead space and a squashed map.
- I questioned the "100%" chance; it was really 99.6% rounded up, and a promise of certainty is wrong for a tool like this.
- I spotted a mistake in `App.tsx` while running the early version and asked for it to be debugged.

**Git, GitHub and deployment.** One branch and one PR per step, running the app and checks before merging, merging the PRs in order, keeping `.env` git-ignored so the API key was never committed, and deploying on Vercel myself.

**Early steps.** Steps 1 to 6 (scaffold, adapters, engine, decision, API) I did locally, following a stepwise plan prepared with the planning chat. <!-- ABS: confirm how much of steps 1 to 6 you typed or edited by hand and which AI tool you used locally -->

## What Claude built while I monitored

From step 7 onwards Claude Code wrote most of the code in this repository. I monitored Claude to build these parts, ran them, and reviewed the behaviour, but I did not write them line by line:

- The Monte Carlo engine and scoring as they stand now (2,040 scenarios, leave-by search, backup plan, flip sentences, rescore).
- Adapters: Open-Meteo weather and geocoding, OSRM routing, TomTom traffic and incidents, with timeouts, retries and caches.
- The rail timetable extract from the national feed, the station matching and the delay calibration.
- The weather story (forecast at departure and arrival, the dry and calm re-run, tips).
- The React and TypeScript UI: composer and place search, verdict, raincloud, map, door-to-door timeline, priorities, trade-off chart, leave-later scrubber, weather card, sources panel, calendar.
- Contract-first OpenAPI tooling, the tests, accessibility fixes, the offline demo mode, the Vercel config, and the docs drafts (including the first draft of this file).

## How AI output was checked, and where it was wrong

**Checks on every step:** 158 backend tests (`make test`), a contract test that fails if `openapi.yaml` drifts from the API, `make lint`, the web lint, TypeScript type-check and production build, an axe accessibility scan (0 issues), a clean-clone script that installs and runs everything from scratch, and a browser script that checks no result card is ever duplicated.

**AI output that was wrong and was corrected:**

| Problem | Who found it | Fix |
|---|---|---|
| Verdict said "51 of 51" next to 99% | Found when I asked what the numbers meant | Counts now cover all 2,040 scenarios |
| "100%" shown for 99.6% | Me | Chances never round up to certainty (">99%", "<1%") |
| Mock rail suggested a 01:33 train to London and a 03:00 bike ride as backup | During testing | Service window and cycling limit, then the real timetable |
| Glasgow to Edinburgh used Glasgow Central's slow trains | During testing of the real timetable | All stations within 3 km are considered (Queen Street wins) |
| Calendar event still said "Rail data is mock" | Claude, in a later check | Text fixed |
| Duplicate result cards (duplicate React keys) | Me, by hand testing | Unique keys and a regression script |
| Clipped place dropdown | Me, from a screenshot | Dropdown rendered above the page |
| Claim that Traffic Scotland data could be accessed and used | The Claude planning chat, in cross-review (not me) | Claim dropped; TomTom used instead |
| Storm visibility setting slowed cars far too much (+105 min) | Claude | Setting eased; the storm feature was later dropped |
| Lower-case import path broke the build; slider handles had no accessible names | Claude's checks | Fixed |

Smaller fixes are in the git history and PR descriptions.

## What is real, modelled and mock

| Real data | Modelled (our assumptions) | Mock or placeholder |
|---|---|---|
| Weather: 51-member ECMWF ensemble (Open-Meteo) | How rain and wind slow each mode (stated factors, our guesses) | Fares and running costs |
| Routes and base times: OSRM | Traffic and walking/cycling variation (random spread, our guess) | Access and effort score |
| Car traffic: TomTom live or predicted (with a key) | Train delays: simulated, calibrated to 86.5% within 5 min (Scottish Government FOI, ORR) | "Simulate an accident" demo switch |
| Train times: GB national timetable extract | Fixed walk to and from the station | |
| CO2e: UK Government 2026 factors (DESNZ) | | |

## Questions I can answer live

- **How is the leave-by time found?** For each option we simulate 51 forecasts × 40 random draws = 2,040 mornings, and pick the latest departure where at least 95% of them arrive on time.
- **Why 95%?** It is the default, not a magic number; you choose it with the slider, and the leave-by time moves.
- **What does "typically arrive" mean?** The middle (median) arrival across those mornings.
- **Why does pinning one morning compare fairly across options?** Every option uses the same random numbers and the same forecast member for that morning, so differences come from the mode, not luck.
- **What if TomTom fails or there is no key?** The car falls back to free-flow OSRM times and the app says traffic is unavailable.
- **What is mock?** Fares and the access score; everything else is real data or a stated model (table above).
- **How is CO2e computed?** Distance × the UK Government 2026 factor: car 0.166 kg per km, rail 0.031 kg per passenger km, walking and cycling 0.
- **How does rescore work?** Moving a slider re-ranks the stored simulation with new weights or confidence; nothing is simulated again.
