import type { Option } from "@/lib/types"

const HARD = ["walking limit", "cycling limit", "No car", "No step-free"] // constraints a later departure cannot change

/** Options worth asking "what if I leave at…" about: everything not ruled out by a hard constraint. */
export function scrubbable(options: Option[]): Option[] {
  return options.filter((o) => o.cliff.length && !HARD.some((h) => o.infeasible_reason?.includes(h)))
}

/** P(on time) if you leave home at t (ms): you take the first simulated departure at or after t (the next train,
 * or the next 5-minute car slot). Leaving after the last one simulated means you are too late: 0. */
export function chanceIfLeaving(o: Option, t: number): number {
  const next = o.cliff.find((c) => new Date(c.leave).getTime() >= t)
  return next ? next.p_on_time : 0
}
