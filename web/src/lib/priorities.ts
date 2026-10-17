import type { Option, Weights } from "@/lib/types"

/** Slider positions (0 to 100) that reproduce the backend's default weights exactly. */
export const DEFAULT_WEIGHTS: Weights = { time: 40, cost: 20, carbon: 20, accessibility: 20 }

/** Slider positions -> weights for the API. The backend divides by the total, so only the ratios matter. */
export function shares(w: Weights): Weights {
  return { time: w.time / 100, cost: w.cost / 100, carbon: w.carbon / 100, accessibility: w.accessibility / 100 }
}

/** Each slider's share of the decision, in percent, as the backend sees it after normalising. */
export function percentOf(w: Weights): Weights {
  const total = w.time + w.cost + w.carbon + w.accessibility || 1
  const p = (x: number) => Math.round((100 * x) / total)
  return { time: p(w.time), cost: p(w.cost), carbon: p(w.carbon), accessibility: p(w.accessibility) }
}

/** kg CO2e and percent saved by the recommended option against driving the same trip; null for the car itself. */
export function savedVsDriving(winner: Option, options: Option[]): { kg: number; pct: number } | null {
  const car = options.find((o) => o.mode === "drive")
  if (!car || winner.mode === "drive" || car.co2e_kg <= winner.co2e_kg) return null
  const kg = car.co2e_kg - winner.co2e_kg
  return { kg, pct: Math.round((100 * kg) / car.co2e_kg) }
}
