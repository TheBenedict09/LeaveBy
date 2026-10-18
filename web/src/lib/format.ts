import type { Mode } from "@/lib/types"

export const MODE_LABEL: Record<Mode, string> = {
  walk: "on foot",
  bike: "by bike",
  drive: "by car",
  train: "by train",
}

/** The option as a sentence subject: "the train is on time". */
export const MODE_NOUN: Record<Mode, string> = {
  walk: "walking",
  bike: "cycling",
  drive: "the car",
  train: "the train",
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
}

/** A chance as a percentage that never rounds up to certainty: 0.996 is ">99%", only exactly 1 is "100%". */
export function pct(x: number): string {
  if (x >= 1) return "100%"
  if (x > 0 && x < 0.005) return "<1%" // never show a real chance as 0%
  return x > 0.99 ? ">99%" : `${Math.round(x * 100)}%`
}

const LONDON = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London",
  hourCycle: "h23",
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
})

/** London wall-clock time at an instant, written as if it were UTC (so the difference is London's offset). */
function londonWall(t: number): number {
  const p = Object.fromEntries(LONDON.formatToParts(t).map((x) => [x.type, Number(x.value)]))
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute)
}

/** The moment you must arrive, as an ISO string, from "N days from today" (0 = today) plus a "HH:MM" time,
 * both in UK time, whatever the browser's own time zone. */
export function arriveByIso(dayOffset: number, time: string, now = Date.now()): string {
  const [h, m] = time.split(":").map(Number)
  const today = new Date(londonWall(now))
  const wall = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + dayOffset, h, m)
  const offset = (t: number) => londonWall(t) - t // GMT or BST at t (t on a whole minute)
  const guess = wall - offset(wall) // a second pass settles the guess across a clock change
  return new Date(wall - offset(guess)).toISOString()
}
