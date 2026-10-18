import { CloudRain, Sun, Wind } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { fmtTime, MODE_LABEL } from "@/lib/format"
import type { Mode, WeatherInfo, WeatherPoint } from "@/lib/types"

/** "Rain likely (38 of 51 forecasts)", "Some chance of rain (9 of 51 forecasts)" or "Dry". */
function rainWords(p: WeatherPoint): string {
  const k = p.members_with_rain
  if (k === 0) return "Dry in every forecast"
  return `${k * 2 > p.members ? "Rain likely" : "Some chance of rain"} (${k} of ${p.members} forecasts)`
}

function Row({ label, p }: { label: string; p: WeatherPoint }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-0.5 text-sm">
      <span className="text-muted-foreground">
        {label} <span className="font-mono text-foreground">{fmtTime(p.at)}</span>
      </span>
      <span>
        {rainWords(p)}
        {p.members_with_rain * 2 > p.members ? (
          <span className="text-muted-foreground">
            {" "}
            · typically <span className="font-mono">{p.rain_mm_h_median.toFixed(1)}</span> mm/h, up to{" "}
            <span className="font-mono">{p.rain_mm_h_p90.toFixed(1)}</span> at the wet end
          </span>
        ) : (
          p.members_with_rain > 0 && (
            <span className="text-muted-foreground">
              {" "}
              · up to <span className="font-mono">{p.rain_mm_h_p90.toFixed(1)}</span> mm/h at the wet end
            </span>
          )
        )}
      </span>
      <span />
      <span className="text-muted-foreground">
        Gusts <span className="font-mono text-foreground">{Math.round(p.gust_mph_median)}</span> mph (up to{" "}
        <span className="font-mono">{Math.round(p.gust_mph_p90)}</span>)
        {p.temp_c_median !== null && (
          <>
            {" "}
            · <span className="font-mono text-foreground">{Math.round(p.temp_c_median)}°C</span>
          </>
        )}
      </span>
    </div>
  )
}

/** The real forecast for the trip, what it costs in minutes, and advice that follows from it. */
export function WeatherCard({ weather, winner }: { weather: WeatherInfo; winner?: Mode }) {
  const cost = winner ? weather.extra_min[winner] : undefined
  // the option the weather hurts most, to say so when the recommended one is unaffected
  const [worstMode, worst] = Object.entries(weather.extra_min).reduce<[string, number]>(
    (a, [m, v]) => ((v ?? 0) > a[1] ? [m, v ?? 0] : a),
    ["", 0],
  )
  const [calm, now] = weather.train_late_over_5min ?? [0, 0]
  const wet = weather.departure.members_with_rain * 2 > weather.departure.members
  const Icon = wet ? CloudRain : weather.departure.gust_mph_median >= 30 ? Wind : Sun
  return (
    <div className="flex flex-col gap-4">
      {weather.simulated && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-deadline">
          <Badge variant="outline" className="border-deadline/60 text-deadline">
            Simulated
          </Badge>
          Demo weather, not the real forecast: every forecast was made stormy by fixed amounts (see Sources and
          assumptions).
        </p>
      )}
      <p className="flex items-start gap-2 text-base">
        <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-rain" />
        <span>
          {cost === undefined
            ? "Here is the forecast near your start."
            : cost >= 1
              ? `Because of the weather, leave ${Math.round(cost)} min earlier than on a dry, calm morning.`
              : worst >= 1 && winner
                ? `This weather doesn't change your plan ${MODE_LABEL[winner]}, but ${MODE_LABEL[worstMode as Mode]} you would need to leave ${Math.round(worst)} min earlier.`
                : "The weather barely matters this morning: the same leave time works on a dry, calm day."}
        </span>
      </p>
      <div className="flex flex-col gap-2">
        <Row label="Leave" p={weather.departure} />
        <Row label="Arrive by" p={weather.arrival} />
      </div>
      {Object.keys(weather.extra_min).length > 1 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {Object.entries(weather.extra_min).map(([mode, min]) => (
            <li key={mode}>
              {MODE_LABEL[mode as Mode]}:{" "}
              <span className="font-mono text-foreground">{min >= 1 ? `+${Math.round(min)} min` : "no change"}</span>
            </li>
          ))}
        </ul>
      )}
      {now - calm >= 0.005 && (
        <p className="text-sm text-muted-foreground">
          Gusts raise the chance of a train running over 5 min late from{" "}
          <span className="font-mono">{(calm * 100).toFixed(1)}%</span> to{" "}
          <span className="font-mono text-deadline">{(now * 100).toFixed(1)}%</span>.
        </p>
      )}
      {weather.tips.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
          {weather.tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        Forecast: 51 ECMWF forecasts for your start point and these hours. How rain and wind slow each way of travelling
        is modelled from stated rules, listed in Sources and assumptions.
      </p>
    </div>
  )
}
