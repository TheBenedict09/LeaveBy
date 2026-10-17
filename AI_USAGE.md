# AI usage (DRAFT)

> This is a draft for ABS to check and complete before submission. Items marked `<!-- ABS: confirm -->` can only be answered by ABS.

Placeholders to confirm:

1. How much code ABS wrote or edited by hand, and in which areas.
2. Which AI changes ABS reviewed line by line, and how (diffs, PR review, running the app).
3. Any AI suggestions ABS rejected or rewrote, beyond those listed below.
4. Whether other AI tools were used (for example in the editor), and for what.
5. Whether the Traffic Scotland access claim correction (below) happened as described.
6. Who wrote the original blueprint and the early backend steps (steps 1 to 6).

## Summary

LeaveBy was built by ABS with AI assistance. ABS chose the problem, set the direction, made the product decisions and reviewed, merged and owns every change. Claude (Anthropic) was used in two ways:

- **Planning and coaching:** a Claude project conversation was used to plan steps, discuss ideas (for example the real timetable, live traffic, priorities and the honesty labels), and turn ABS's decisions into concrete briefs.
- **Code changes:** a Claude Code session running on ABS's own machine made code changes in this repository on request: writing and editing code, running tests and the app, and preparing commits, branches and pull requests. ABS directed each step, decided what to merge and merged it.

<!-- ABS: confirm the share of hand-written code and the areas you wrote yourself. -->

## What the AI-assisted work covered

- Web app setup and UI: the composer and place search, the verdict, the raincloud chart and its interactions, the priorities sliders, the trade-off chart, the leave-later scrubber, the sources panel and add to calendar.
- Backend steps from the real rail timetable onwards: the timetable extract and its builder, delay calibration, real CO2e factors, the TomTom adapter, and the related tests and OpenAPI updates.
- Research: finding the GB timetable feed, the DESNZ 2026 conversion factors and the published punctuality figures used for calibration.
- Documentation drafts, including this file.

<!-- ABS: confirm the list above and add anything missing (for example the blueprint and steps 1 to 6). -->

## How the output was verified

- Automated tests on every step (`make test`, 148 backend tests at the time of writing), lint and format checks (`make lint`), and the web lint and production build.
- A contract test that fails if `openapi.yaml` drifts from the API.
- Live checks against the running API and app in a browser for each feature, including before and after numbers for the demo routes.
- One real TomTom call to confirm that departure-time prediction returns different values for different times (it did).
- The TomTom key is read only from the git-ignored `.env`; tests run with a blank key and never call TomTom.

<!-- ABS: confirm how you reviewed the changes yourself. -->

## Where AI output was wrong and was corrected

- **Scenario counts did not match the percentage.** The verdict said "51 of 51" next to 99%, because counts used one noise draw while the percentage used all of them. Fixed so counts cover all 2,040 scenarios.
- **Unrealistic mock trains.** The first rail model suggested a Glasgow to London train leaving at 01:33 and a 03:00 bike ride as a backup. Fixed with a service window, a distance-based speed table and a cycling limit, and later replaced by the real timetable.
- **Wrong Glasgow station.** Using only the nearest station picked Glasgow Central's slow direct trains to Edinburgh; the fast trains leave from Queen Street, 400 m away. Fixed by considering every station within reach.
- **Out-of-date calendar text.** The calendar event still said rail data was mock after the real timetable arrived. Fixed.
- **UI bugs found during checks:** a lower-case import path that broke the build on case-sensitive systems, a place dropdown clipped by its card, and slider handles without accessible names.
- **Traffic Scotland access claim.** An early suggestion about how Traffic Scotland data could be used was corrected. <!-- ABS: confirm what was claimed and how it was corrected. -->

<!-- ABS: add any suggestions you rejected or rewrote. -->

## Data honesty

AI assistance was also used to keep the app honest about its data: every number in the app is labelled Live, Predicted, Static, Modelled, Mock or Simulated, and the "Sources and assumptions" panel lists each source with its credit and licence.
