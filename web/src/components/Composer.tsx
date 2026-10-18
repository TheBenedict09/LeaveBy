import { useState } from "react"
import {
  ArrowRight,
  ArrowUpDown,
  CalendarDays,
  Car,
  Clock,
  CloudLightning,
  Loader2,
  MapPin,
  TriangleAlert,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { PlaceField } from "@/components/PlaceField"
import { PLACES } from "@/lib/places"
import type { ComposerValue, Place } from "@/lib/types"

const place =
  "w-full bg-transparent text-lg font-medium text-foreground outline-none placeholder:text-muted-foreground/60"

const DAYS = ["Tomorrow", "In 2 days", "In 3 days"]

const label = "text-xs font-medium tracking-wide text-muted-foreground uppercase"

// Raised pill shared by the time select and the car toggle; brightens and glows on hover and focus.
const pill =
  "h-10 rounded-full border border-border bg-secondary/50 transition-[border-color,box-shadow,background-color] hover:border-rain/50 hover:shadow-[0_0_0_3px_rgb(110_168_255/0.12)] focus-within:border-rain focus-within:shadow-[0_0_0_3px_rgb(110_168_255/0.2)]"

const DUNDEE: Place = { label: "Dundee", lat: 56.4691, lon: -2.9749 }

// Fill the form without submitting, so a demo needs no typing.
const DEMOS: { name: string; from: Place; to: Place; car: boolean }[] = [
  { name: "Glasgow → Edinburgh", from: PLACES[0], to: PLACES[1], car: false },
  { name: "Glasgow → Edinburgh by car", from: PLACES[0], to: PLACES[1], car: true },
  { name: "Glasgow → Paisley", from: PLACES[0], to: PLACES[2], car: false },
  { name: "Glasgow → Dundee", from: PLACES[0], to: DUNDEE, car: false },
]

// 05:00 to 22:30 in half-hour steps
const TIMES = Array.from({ length: 36 }, (_, i) => {
  const mins = 5 * 60 + i * 30
  return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`
})

/** Straight-line distance in metres (haversine). */
function metres(a: Place, b: Place): number {
  const rad = Math.PI / 180
  const h =
    Math.sin(((b.lat - a.lat) * rad) / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h))
}

export function Composer({ onSubmit, loading }: { onSubmit: (v: ComposerValue) => void; loading: boolean }) {
  const [from, setFrom] = useState<Place | null>(PLACES[0])
  const [to, setTo] = useState<Place | null>(PLACES[1])
  const [rev, setRev] = useState(0) // remounts the fields so their text follows a swap or a demo route
  const [day, setDay] = useState(0)
  const [time, setTime] = useState("09:00")
  const [hasCar, setHasCar] = useState(false)
  const [accident, setAccident] = useState(false) // demo only, never on by default
  const [storm, setStorm] = useState(false) // demo only, never on by default
  const same = from !== null && to !== null && metres(from, to) < 300

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault()
        if (from && to && !same)
          onSubmit({
            origin: from,
            destination: to,
            dayOffset: day + 1,
            time,
            hasCar,
            simulateIncident: accident,
            simulateStorm: storm,
          })
      }}
    >
      {/* The route: two stops joined by a line, like a ticket */}
      <div className="relative rounded-xl border border-border bg-secondary/40 transition-colors focus-within:border-rain/50">
        <span
          aria-hidden
          className="absolute top-9 bottom-9 left-6 w-px border-l border-dashed border-muted-foreground/40"
        />
        <div className="flex items-center gap-3 rounded-t-xl px-4 py-3 transition-colors focus-within:bg-secondary">
          <span aria-hidden className="flex w-4 shrink-0 justify-center">
            <span className="size-3 rounded-full border-2 border-rain bg-card" />
          </span>
          <div className="min-w-0 flex-1">
            <p className={label}>From</p>
            <PlaceField key={`from-${rev}`} label="From" value={from} onChange={setFrom} className={place} />
          </div>
        </div>
        <div className="relative mx-4 border-t border-border">
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Swap from and to"
            className="absolute top-1/2 right-0 size-10 -translate-y-1/2 rounded-full bg-card transition-transform hover:border-rain/50 hover:text-rain active:rotate-180"
            onClick={() => {
              setFrom(to)
              setTo(from)
              setRev((n) => n + 1)
            }}
          >
            <ArrowUpDown />
          </Button>
        </div>
        <div className="flex items-center gap-3 rounded-b-xl px-4 py-3 transition-colors focus-within:bg-secondary">
          <MapPin aria-hidden className="size-4 shrink-0 text-deadline" />
          <div className="min-w-0 flex-1">
            <p className={label}>To</p>
            <PlaceField key={`to-${rev}`} label="To" value={to} onChange={setTo} className={place} />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <div className="flex flex-col gap-1.5">
          <span className={label}>Arrive by</span>
          <div className={`relative ${pill}`}>
            <Clock
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-rain"
            />
            <select
              aria-label="Arrival time"
              className="h-full appearance-none rounded-full bg-transparent pr-4 pl-9 font-mono text-base text-rain outline-none"
              value={time}
              onChange={(e) => setTime(e.target.value)}
            >
              {TIMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className={`${label} flex items-center gap-1.5`} id="day-label">
            <CalendarDays aria-hidden className="size-3.5" />
            Day
          </span>
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            aria-labelledby="day-label"
            value={String(day)}
            onValueChange={(v) => v && setDay(Number(v))}
          >
            {DAYS.map((d, i) => (
              <ToggleGroupItem
                key={d}
                value={String(i)}
                className="h-10 px-4 data-[state=on]:border-rain/50 data-[state=on]:bg-rain/15 data-[state=on]:text-rain"
              >
                {d}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        <label
          className={`${pill} flex cursor-pointer items-center gap-2 px-3 text-sm ${hasCar ? "border-rain/50 text-rain" : "text-muted-foreground"}`}
        >
          <Car aria-hidden className="size-4" />I have a car
          <Switch checked={hasCar} onCheckedChange={setHasCar} aria-label="I have a car" />
        </label>
        <label
          className={`${pill} flex cursor-pointer items-center gap-2 border-dashed px-3 text-sm ${accident ? "border-deadline/60 text-deadline" : "text-muted-foreground"}`}
        >
          <TriangleAlert aria-hidden className="size-4" />
          Simulate an accident <span className="text-xs opacity-70">(demo)</span>
          <Switch
            checked={accident}
            onCheckedChange={setAccident}
            aria-label="Simulate an accident on the car route (demo)"
          />
        </label>
        <label
          className={`${pill} flex cursor-pointer items-center gap-2 border-dashed px-3 text-sm ${storm ? "border-deadline/60 text-deadline" : "text-muted-foreground"}`}
        >
          <CloudLightning aria-hidden className="size-4" />
          Simulate a stormy morning <span className="text-xs opacity-70">(demo)</span>
          <Switch
            checked={storm}
            onCheckedChange={setStorm}
            aria-label="Simulate a stormy morning instead of the real forecast (demo)"
          />
        </label>
      </div>

      {same && (
        <p role="status" className="text-sm text-deadline">
          From and to are the same place (within 300 m). Pick a different destination.
        </p>
      )}
      <Button
        type="submit"
        size="lg"
        className="group h-12 w-full rounded-full bg-linear-to-r from-rain to-rain/80 text-base text-background shadow-[0_8px_30px_-8px_rgb(110_168_255/0.6)] transition-[box-shadow,filter] hover:shadow-[0_8px_40px_-6px_rgb(110_168_255/0.8)] hover:brightness-110 disabled:shadow-none"
        disabled={loading || !from || !to || same}
      >
        {loading ? (
          <>
            <Loader2 className="animate-spin" />
            Working...
          </>
        ) : (
          <>
            When should I leave?
            <ArrowRight className="transition-transform group-hover:translate-x-0.5" />
          </>
        )}
      </Button>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Try a route</span>
        {DEMOS.map((d) => (
          <button
            key={d.name}
            type="button"
            className="h-8 rounded-full border border-border bg-secondary/40 px-3 text-xs text-muted-foreground transition-[color,border-color,box-shadow] outline-none hover:border-rain/50 hover:text-foreground hover:shadow-[0_0_12px_-2px_rgb(110_168_255/0.4)] focus-visible:border-rain focus-visible:text-foreground"
            onClick={() => {
              setFrom(d.from)
              setTo(d.to)
              setHasCar(d.car)
              setRev((n) => n + 1)
            }}
          >
            {d.name}
          </button>
        ))}
      </div>
    </form>
  )
}
