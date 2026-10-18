// Arrive-by times are UK time whatever the browser's zone, across clock changes.
// Run: TZ=America/New_York node --experimental-strip-types scripts/check_arrive_by.ts
import assert from "node:assert/strict"
import { arriveByIso } from "../web/src/lib/format.ts"

const at = (s: string) => Date.parse(s)
const cases: [string, number, string, string][] = [
  ["2026-10-18T10:00:00Z", 0, "16:00", "2026-10-18T15:00:00.000Z"], // today, BST
  ["2026-10-18T10:00:00Z", 1, "09:00", "2026-10-19T08:00:00.000Z"],
  ["2026-10-24T10:00:00Z", 1, "09:00", "2026-10-25T09:00:00.000Z"], // clocks go back on the 25th
  ["2026-10-24T23:30:00Z", 0, "09:00", "2026-10-25T09:00:00.000Z"], // already the 25th in the UK
  ["2026-12-31T23:30:00Z", 1, "08:00", "2027-01-01T08:00:00.000Z"], // GMT, over the year end
  ["2026-03-28T12:00:00Z", 1, "09:00", "2026-03-29T08:00:00.000Z"], // clocks go forward on the 29th
]
for (const [now, day, time, want] of cases) assert.equal(arriveByIso(day, time, at(now)), want)
console.log(`arriveByIso: ${cases.length} cases ok`)
