import type { WeatherPoint } from "@/lib/types"

export type IconName =
  | "clear-day"
  | "clear-night"
  | "partly-cloudy-day"
  | "partly-cloudy-night"
  | "overcast"
  | "drizzle"
  | "rain"
  | "snow"
  | "fog"
  | "wind"
  | "not-available"

const HOUR = new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Europe/London" })

/** Night before 07:00 or from 19:00 UK time (good enough for a morning commute icon). */
export function isNight(at: string): boolean {
  const h = Number(HOUR.format(new Date(at))) % 24
  return h < 7 || h >= 19
}

/** The icon for the forecast at one time, from the numbers only: no forecast, no weather picture. */
export function iconFor(p: WeatherPoint | null | undefined): IconName {
  if (!p || !p.members) return "not-available"
  const share = p.members_with_rain / p.members
  const night = isNight(p.at)
  const cold = p.temp_c_median !== null && p.temp_c_median <= 1
  if (share > 0.5) {
    if (cold) return "snow"
    return p.rain_mm_h_median < 0.5 ? "drizzle" : "rain"
  }
  if (p.visibility_m_median !== null && p.visibility_m_median < 2000) return "fog"
  if (share > 0.2) return "overcast"
  if (share > 0) return night ? "partly-cloudy-night" : "partly-cloudy-day"
  return night ? "clear-night" : "clear-day"
}
