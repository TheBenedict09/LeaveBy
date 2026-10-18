import type { Sky } from "@/components/WeatherScene"
import type { WeatherPoint } from "@/lib/types"

const HOUR = new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Europe/London" })

/** The animated sky's inputs, straight from the forecast at one time (no data, no sky). */
export function skyFrom(p: WeatherPoint): Sky {
  return {
    rainMmH: p.rain_mm_h_median,
    rainShare: p.members_with_rain / p.members,
    gustMph: p.gust_mph_median,
    tempC: p.temp_c_median,
    visibilityM: p.visibility_m_median,
    hour: Number(HOUR.format(new Date(p.at))) % 24,
  }
}
