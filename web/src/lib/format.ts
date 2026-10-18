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
  return x > 0.99 ? ">99%" : `${Math.round(x * 100)}%`
}

/** The moment you must arrive, as an ISO string, from "N days from today" plus a "HH:MM" time. */
export function arriveByIso(dayOffset: number, time: string): string {
  const [h, m] = time.split(":").map(Number)
  const d = new Date()
  d.setDate(d.getDate() + dayOffset)
  d.setHours(h, m, 0, 0)
  return d.toISOString()
}
