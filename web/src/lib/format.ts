import type { Mode } from "@/lib/types"

export const MODE_LABEL: Record<Mode, string> = {
  walk: "on foot",
  bike: "by bike",
  drive: "by car",
  train: "by train",
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
}

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`
}

/** The moment you must arrive, as an ISO string, from "N days from today" plus a "HH:MM" time. */
export function arriveByIso(dayOffset: number, time: string): string {
  const [h, m] = time.split(":").map(Number)
  const d = new Date()
  d.setDate(d.getDate() + dayOffset)
  d.setHours(h, m, 0, 0)
  return d.toISOString()
}