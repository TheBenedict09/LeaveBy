import { useState } from "react"
import { motion, useReducedMotion } from "motion/react"
import { scaleLinear, scaleSqrt, scaleTime } from "d3-scale"
import { Dot, Legend } from "@/components/Legend"
import { fmtTime, MODE_LABEL, pct } from "@/lib/format"
import type { Option } from "@/lib/types"

const W = 720
const H = 240
const PAD = { top: 20, right: 28, bottom: 34, left: 52 }

/** Green means late no more often than the user said they accept (1 - confidence); amber up to twice that. */
function risk(p: number, confidence: number): { label: string; fill: string } {
  const late = 1 - p
  const ok = 1 - confidence + 1e-9
  if (late <= ok) return { label: "within your tolerance", fill: "fill-safe" }
  if (late <= 2 * ok) return { label: "medium", fill: "fill-deadline" }
  return { label: "high", fill: "fill-risk" }
}

/** Every option you can rely on: when you must leave (x) against CO2e (y), sized by cost, coloured by risk. */
export function TradeOff({ options, confidence }: { options: Option[]; confidence: number }) {
  const still = useReducedMotion() ?? false
  const [active, setActive] = useState<string | null>(null)
  const rows = options.filter((o) => o.feasible && o.leave_by)
  if (!rows.length) return null

  const t = rows.map((o) => new Date(o.leave_by!).getTime())
  const lo = Math.min(...t)
  const hi = Math.max(...t)
  const pad = Math.max((hi - lo) * 0.15, 10 * 60_000)
  const x = scaleTime()
    .domain([lo - pad, hi + pad])
    .range([PAD.left, W - PAD.right])
  const y = scaleLinear()
    .domain([0, Math.max(...rows.map((o) => o.co2e_kg), 1) * 1.2])
    .range([H - PAD.bottom, PAD.top])
    .nice()
  const r = scaleSqrt()
    .domain([0, Math.max(...rows.map((o) => o.cost_gbp), 1)])
    .range([7, 24])
  const spring = still ? { duration: 0 } : { type: "spring" as const, stiffness: 120, damping: 18 }
  const shown = rows.find((o) => o.mode === active)

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="group"
        aria-label={`Trade-offs: ${rows
          .map(
            (o) =>
              `${MODE_LABEL[o.mode]}, leave ${fmtTime(o.leave_by!)}, ${o.co2e_kg.toFixed(1)} kg CO2e, £${o.cost_gbp.toFixed(2)}`,
          )
          .join("; ")}.`}
      >
        {y.ticks(4).map((v) => (
          <g key={v} transform={`translate(0,${y(v)})`}>
            <line x1={PAD.left} x2={W - PAD.right} className="stroke-border" strokeDasharray="2 4" />
            <text
              x={PAD.left - 8}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-muted-foreground font-mono text-[11px]"
            >
              {v}
            </text>
          </g>
        ))}
        <text x={PAD.left - 8} y={PAD.top - 8} textAnchor="end" className="fill-muted-foreground text-[11px]">
          kg CO2e
        </text>
        {x.ticks(5).map((d) => (
          <text
            key={d.getTime()}
            x={x(d)}
            y={H - 10}
            textAnchor="middle"
            className="fill-muted-foreground font-mono text-[11px]"
          >
            {fmtTime(d.toISOString())}
          </text>
        ))}
        <text x={W - PAD.right} y={H - 22} textAnchor="end" className="fill-muted-foreground text-[11px]">
          leave by → later is better
        </text>

        {rows.map((o) => {
          const cx = x(new Date(o.leave_by!))
          const cy = y(o.co2e_kg)
          const rad = r(o.cost_gbp)
          const best = o.rank === 1
          return (
            <g
              key={o.mode}
              tabIndex={0}
              role="button"
              aria-label={`${MODE_LABEL[o.mode].replace(/^by |^on /, "")}${best ? " · recommended" : ""}: leave ${fmtTime(o.leave_by!)}, ${pct(o.p_on_time)} on time, £${o.cost_gbp.toFixed(2)}, ${o.co2e_kg.toFixed(1)} kg CO2e`}
              className="cursor-pointer outline-none focus-visible:[&>circle:first-child]:stroke-ring"
              onPointerEnter={() => setActive(o.mode)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(o.mode)}
              onBlur={() => setActive(null)}
            >
              <motion.circle
                initial={false}
                animate={{ cx, cy, r: rad + (best ? 5 : 0) }}
                transition={spring}
                className={best ? "fill-none stroke-rain" : "fill-none stroke-transparent"}
                strokeWidth={2}
              />
              <motion.circle
                initial={false}
                animate={{ cx, cy, r: rad }}
                transition={spring}
                className={`${risk(o.p_on_time, confidence).fill} ${active && active !== o.mode ? "opacity-40" : "opacity-85"}`}
              />
              <motion.text
                initial={false}
                animate={{ x: cx, y: cy - rad - (best ? 10 : 6) }}
                transition={spring}
                textAnchor="middle"
                className={`text-xs ${best ? "fill-rain font-medium" : "fill-foreground"}`}
              >
                {MODE_LABEL[o.mode].replace(/^by |^on /, "")}
                {best ? " · recommended" : ""}
              </motion.text>
            </g>
          )
        })}
      </svg>
      {shown && (
        <div
          role="status"
          className="pointer-events-none absolute top-2 right-2 w-max rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md"
        >
          <p className="font-medium text-foreground">{MODE_LABEL[shown.mode]}</p>
          <p className="text-muted-foreground">
            Leave by <span className="font-mono text-foreground">{fmtTime(shown.leave_by!)}</span> ·{" "}
            {pct(shown.p_on_time)} on time (risk: {risk(shown.p_on_time, confidence).label})
          </p>
          <p className="text-muted-foreground">
            £{shown.cost_gbp.toFixed(2)} · {shown.co2e_kg.toFixed(1)} kg CO2e · access{" "}
            {Math.round(shown.accessibility.score * 100)}/100
          </p>
        </div>
      )}
      <div className="mt-1">
        <Legend
          items={[
            { swatch: <Dot className="bg-safe" />, label: `late ≤ ${Math.round((1 - confidence) * 100)}%` },
            { swatch: <Dot className="bg-deadline" />, label: `≤ ${Math.round((1 - confidence) * 200)}%` },
            { swatch: <Dot className="bg-risk" />, label: "more" },
            {
              swatch: <span aria-hidden className="size-3 rounded-full border border-muted-foreground" />,
              label: "size = cost",
            },
          ]}
          detail="Each bubble is an option you can rely on: how late you can leave (right is later) against its CO2e. Colour is how often it is late compared with the confidence you chose. Options that cannot meet your confidence are left out."
        />
      </div>
    </div>
  )
}
