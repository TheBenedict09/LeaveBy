import { useMemo, type ReactNode } from "react"
import { CloudRain, Droplets, Eye, Info, Lightbulb, Thermometer, TrainFront, Wind } from "lucide-react"
import { WeatherScene } from "@/components/WeatherScene"
import { skyFrom } from "@/lib/sky"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fmtTime, MODE_LABEL } from "@/lib/format"
import type { Mode, WeatherInfo, WeatherPoint } from "@/lib/types"

/** A short name for the sky, from the numbers only. */
function condition(p: WeatherPoint): string {
  const share = p.members_with_rain / p.members
  const cold = p.temp_c_median !== null && p.temp_c_median <= 1
  let sky = "Dry"
  if (share > 0.5) {
    const kind = cold ? "Snow" : p.rain_mm_h_median >= 2.5 ? "Heavy rain" : "Rain"
    sky = `${kind} likely`
  } else if (share > 0) sky = "Mostly dry"
  const extras = [
    p.gust_mph_median >= 30 && "windy",
    p.visibility_m_median !== null && p.visibility_m_median < 2000 && "murky",
  ]
  return [sky, ...extras.filter(Boolean)].join(", ")
}

function Chip({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-background/50 px-2.5 py-1 text-xs backdrop-blur"
      aria-label={label}
    >
      {icon}
      <span className="font-mono">{children}</span>
    </span>
  )
}

/** The real forecast for the trip as an animated sky, what it costs in minutes, and advice that follows from it. */
export function WeatherCard({ weather, winner }: { weather: WeatherInfo; winner?: Mode }) {
  const dep = weather.departure
  const sky = useMemo(() => skyFrom(dep), [dep])
  const cost = winner ? weather.extra_min[winner] : undefined
  const [worstMode, worst] = Object.entries(weather.extra_min).reduce<[string, number]>(
    (a, [m, v]) => ((v ?? 0) > a[1] ? [m, v ?? 0] : a),
    ["", 0],
  )
  const [calm, now] = weather.train_late_over_5min ?? [0, 0]
  const night = sky.hour < 7 || sky.hour >= 19

  return (
    <div className="flex flex-col gap-4">
      <div
        className={`relative h-40 overflow-hidden rounded-xl border border-border/60 ${night ? "bg-linear-to-b from-[#0b1424] to-[#121826]" : "bg-linear-to-b from-[#1a2a44] to-[#121826]"}`}
      >
        <WeatherScene sky={sky} className="absolute inset-0" />
        <div className="relative flex h-full flex-col justify-between p-4">
          <div>
            <p className="text-xs text-muted-foreground">When you leave, {fmtTime(dep.at)}</p>
            <p className="text-xl font-semibold tracking-tight">{condition(dep)}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Chip icon={<CloudRain className="size-3.5 text-rain" />} label="Forecasts with rain">
              {dep.members_with_rain}/{dep.members}
            </Chip>
            <Chip icon={<Droplets className="size-3.5 text-rain" />} label="Rain at the wet end of the forecast">
              {dep.rain_mm_h_p90.toFixed(1)} mm/h
            </Chip>
            <Chip icon={<Wind className="size-3.5 text-rain" />} label="Typical gusts">
              {Math.round(dep.gust_mph_median)} mph
            </Chip>
            {dep.temp_c_median !== null && (
              <Chip icon={<Thermometer className="size-3.5 text-rain" />} label="Temperature">
                {Math.round(dep.temp_c_median)}°C
              </Chip>
            )}
            {dep.visibility_m_median !== null && (
              <Chip icon={<Eye className="size-3.5 text-rain" />} label="Visibility">
                {(dep.visibility_m_median / 1000).toFixed(1)} km
              </Chip>
            )}
          </div>
        </div>
      </div>

      <p className="text-base">
        {cost === undefined
          ? `By ${fmtTime(weather.arrival.at)}: ${condition(weather.arrival).toLowerCase()}.`
          : cost >= 1
            ? `Because of the weather, leave ${Math.round(cost)} min earlier than on a dry, calm morning.`
            : worst >= 1 && winner
              ? `This weather doesn't change your plan ${MODE_LABEL[winner]}, but ${MODE_LABEL[worstMode as Mode]} you would need to leave ${Math.round(worst)} min earlier.`
              : "The weather barely matters this morning: the same leave time works on a dry, calm day."}
      </p>

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">Extra time for the weather</span>
        {Object.entries(weather.extra_min).map(([mode, min]) => (
          <span key={mode} className="rounded-full border border-border px-2 py-0.5">
            {MODE_LABEL[mode as Mode]}{" "}
            <span className={`font-mono ${(min ?? 0) >= 1 ? "text-deadline" : "text-safe"}`}>
              {(min ?? 0) >= 1 ? `+${Math.round(min ?? 0)} min` : "none"}
            </span>
          </span>
        ))}
        {now - calm >= 0.005 && (
          <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
            <TrainFront aria-hidden className="size-3.5" /> late over 5 min{" "}
            <span className="font-mono">{(calm * 100).toFixed(1)}%</span> →{" "}
            <span className="font-mono text-deadline">{(now * 100).toFixed(1)}%</span>
          </span>
        )}
        <span className="text-muted-foreground">
          · arrive by {fmtTime(weather.arrival.at)}: {condition(weather.arrival).toLowerCase()}
        </span>
      </div>

      {weather.tips.length > 0 && (
        <ul className="flex flex-col gap-1.5 text-sm">
          {weather.tips.map((t) => (
            <li key={t} className="flex items-start gap-2">
              <Lightbulb aria-hidden className="mt-0.5 size-4 shrink-0 text-deadline" />
              {t}
            </li>
          ))}
        </ul>
      )}

      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1 self-start text-xs text-muted-foreground hover:text-foreground"
          >
            <Info aria-hidden className="size-3.5" /> 51 ECMWF forecasts · effects modelled
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-72">
          The sky and numbers come from the 51 forecasts for your start point at this hour (median, and the wet end for
          rain). How rain and wind slow each way of travelling follows stated rules, listed in Sources and assumptions.
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
