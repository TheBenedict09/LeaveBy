import { useMemo } from "react"
import { useReducedMotion } from "motion/react"
import clearDay from "@bybas/weather-icons/production/fill/all/clear-day.svg?raw"
import clearNight from "@bybas/weather-icons/production/fill/all/clear-night.svg?raw"
import drizzle from "@bybas/weather-icons/production/fill/all/drizzle.svg?raw"
import fog from "@bybas/weather-icons/production/fill/all/fog.svg?raw"
import notAvailable from "@bybas/weather-icons/production/fill/all/not-available.svg?raw"
import overcast from "@bybas/weather-icons/production/fill/all/overcast.svg?raw"
import partlyDay from "@bybas/weather-icons/production/fill/all/partly-cloudy-day.svg?raw"
import partlyNight from "@bybas/weather-icons/production/fill/all/partly-cloudy-night.svg?raw"
import rain from "@bybas/weather-icons/production/fill/all/rain.svg?raw"
import snow from "@bybas/weather-icons/production/fill/all/snow.svg?raw"
import wind from "@bybas/weather-icons/production/fill/all/wind.svg?raw"
import type { IconName } from "@/lib/weatherIcon"

// Meteocons by Bas Milius (MIT), bundled locally so they work offline. Animated with SVG <animate> elements.
const SVG: Record<IconName, string> = {
  "clear-day": clearDay,
  "clear-night": clearNight,
  "partly-cloudy-day": partlyDay,
  "partly-cloudy-night": partlyNight,
  overcast,
  drizzle,
  rain,
  snow,
  fog,
  wind,
  "not-available": notAvailable,
}

/** An animated weather icon; under reduced motion its animation elements are stripped, leaving the first frame. */
export function WeatherIcon({ name, label, className }: { name: IconName; label: string; className?: string }) {
  const still = useReducedMotion() ?? false
  const src = useMemo(() => {
    const raw = still
      ? SVG[name].replace(/<animate[A-Za-z]*\b[^>]*?(\/>|>[\s\S]*?<\/animate[A-Za-z]*>)/g, "")
      : SVG[name]
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(raw)}` // an <img>, so icon ids never clash
  }, [name, still])
  return <img src={src} alt={label} className={className} draggable={false} />
}
