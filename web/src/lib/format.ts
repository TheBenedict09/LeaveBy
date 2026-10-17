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

/** Tomorrow 09:00 in the browser's time zone, in the format a datetime-local field wants. */
export function defaultArriveByLocal(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(9, 0, 0, 0)
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}