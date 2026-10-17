import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { PLACES } from "@/lib/places"
import type { ComposerValue } from "@/lib/types"

const field =
  "rounded-md border border-input bg-secondary px-2 py-1 font-medium text-rain outline-none focus-visible:ring-2 focus-visible:ring-ring"

const DAYS = ["tomorrow", "in 2 days", "in 3 days"]

// 05:00 to 22:30 in half-hour steps
const TIMES = Array.from({ length: 36 }, (_, i) => {
  const mins = 5 * 60 + i * 30
  return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`
})

export function Composer({ onSubmit, loading }: { onSubmit: (v: ComposerValue) => void; loading: boolean }) {
  const [from, setFrom] = useState(0)
  const [to, setTo] = useState(1)
  const [day, setDay] = useState(0)
  const [time, setTime] = useState("09:00")
  const [hasCar, setHasCar] = useState(false)

  return (
    <form
      className="flex flex-wrap items-center gap-x-2 gap-y-3 text-lg"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({ origin: PLACES[from], destination: PLACES[to], dayOffset: day + 1, time, hasCar })
      }}
    >
      <span>I'm travelling from</span>
      <select aria-label="From" className={field} value={from} onChange={(e) => setFrom(Number(e.target.value))}>
        {PLACES.map((p, i) => (
          <option key={p.label} value={i}>
            {p.label}
          </option>
        ))}
      </select>
      <span>to</span>
      <select aria-label="To" className={field} value={to} onChange={(e) => setTo(Number(e.target.value))}>
        {PLACES.map((p, i) => (
          <option key={p.label} value={i}>
            {p.label}
          </option>
        ))}
      </select>
      <span>and must arrive by</span>
      <select
        aria-label="Arrival time"
        className={`${field} font-mono`}
        value={time}
        onChange={(e) => setTime(e.target.value)}
      >
        {TIMES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <select aria-label="Arrival day" className={field} value={day} onChange={(e) => setDay(Number(e.target.value))}>
        {DAYS.map((d, i) => (
          <option key={d} value={i}>
            {d}
          </option>
        ))}
      </select>
      <label className="flex items-center gap-2 text-base text-muted-foreground">
        <Switch checked={hasCar} onCheckedChange={setHasCar} aria-label="I have a car" />I have a car
      </label>
      <Button type="submit" disabled={loading || from === to}>
        {loading ? "Working it out..." : "When should I leave?"}
      </Button>
    </form>
  )
}