import { useState } from "react"
import { Slider } from "@/components/ui/slider"
import { fmtTime, MODE_LABEL, MODE_NOUN, pct } from "@/lib/format"
import { chanceIfLeaving, scrubbable } from "@/lib/leaveLater"
import type { Option } from "@/lib/types"

const STEP = 60_000 // one minute

/** "What if I leave at…": reads each option's on-time curve, already in the response, so it needs no request. */
export function LeaveLater({
  options,
  leaveAt,
  confidence,
}: {
  options: Option[]
  leaveAt: string
  confidence: number
}) {
  const rows = scrubbable(options)
  const times = rows.flatMap((o) => o.cliff.map((c) => new Date(c.leave).getTime()))
  const start = new Date(leaveAt).getTime()
  const [t, setT] = useState(start)
  if (!rows.length) return null

  const lo = Math.min(...times, start)
  const hi = Math.max(...times, start)
  const at = fmtTime(new Date(t).toISOString())
  const chances = rows.map((o) => ({ o, p: chanceIfLeaving(o, t) })).sort((a, b) => b.p - a.p)
  const best = chances[0]
  const lateIn = best.p >= 1 ? 0 : Math.round(1 / Math.max(1 - best.p, 1e-9))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-muted-foreground">If I leave at</span>
        <span className="font-mono text-2xl text-rain">{at}</span>
      </div>
      <Slider
        value={[t]}
        onValueChange={([v]) => setT(v)}
        min={Math.floor(lo / STEP) * STEP}
        max={Math.ceil(hi / STEP) * STEP}
        step={STEP}
        aria-label="Leave home at"
        aria-valuetext={at}
      />
      <p className="text-sm" aria-live="polite">
        {best.p > 0 ? (
          <>
            Leave at <span className="font-mono">{at}</span> and {MODE_NOUN[best.o.mode]} is on time{" "}
            <span className={`font-mono ${best.p >= confidence ? "text-safe" : "text-risk"}`}>{pct(best.p)}</span> of
            the time
            {lateIn > 1 && best.p < confidence ? `: late about 1 morning in ${lateIn}.` : "."}
          </>
        ) : (
          <>Leave at {at} and nothing gets you there in time.</>
        )}
      </p>
      <ul className="flex flex-col gap-2">
        {chances.map(({ o, p }) => (
          <li key={o.mode} className="grid grid-cols-[5.5rem_1fr_3rem] items-center gap-3 text-sm">
            <span className="text-muted-foreground">{MODE_LABEL[o.mode]}</span>
            <span className="h-1.5 overflow-hidden rounded-full bg-secondary">
              <span
                className={`block h-full rounded-full transition-[width] duration-200 ${p >= confidence ? "bg-safe" : p >= 2 * confidence - 1 ? "bg-deadline" : "bg-risk"}`}
                style={{ width: `${p * 100}%` }}
              />
            </span>
            <span className="text-right font-mono">{pct(p)}</span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="self-start text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        onClick={() => setT(start)}
      >
        Back to the recommended {fmtTime(leaveAt)}
      </button>
    </div>
  )
}
