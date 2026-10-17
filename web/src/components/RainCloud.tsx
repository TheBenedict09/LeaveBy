import { scaleLinear, scaleTime } from "d3-scale"
import { area, curveBasis } from "d3-shape"
import { fmtTime, MODE_LABEL } from "@/lib/format"
import type { Option } from "@/lib/types"

const W = 720
const PAD = { top: 16, right: 24, bottom: 32, left: 88 }
const ROW = 96

/** Gaussian kernel density of xs (ms) at each point of grid; Silverman bandwidth, at least 1 minute. */
function density(xs: number[], grid: number[]): number[] {
  const n = xs.length
  const mean = xs.reduce((a, b) => a + b, 0) / n
  const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / n)
  const h = Math.max(1.06 * sd * n ** -0.2, 60_000)
  return grid.map((g) => xs.reduce((a, x) => a + Math.exp(-0.5 * ((g - x) / h) ** 2), 0) / (n * h))
}

// Hard-constraint failures (no car, too far) are left out: their arrivals say nothing about the deadline.
const plotted = (o: Option) => o.feasible || o.infeasible_reason?.startsWith("Cannot reach")

export function RainCloud({ options, deadline }: { options: Option[]; deadline: string }) {
  const rows = options.filter(plotted)
  if (!rows.length) return null

  const dl = new Date(deadline).getTime()
  const all = rows.flatMap((o) => o.scenario_arrivals.map((t) => new Date(t).getTime()))
  const lo = Math.min(dl, ...all)
  const hi = Math.max(dl, ...all)
  const pad = Math.max((hi - lo) * 0.08, 5 * 60_000)
  const x = scaleTime()
    .domain([lo - pad, hi + pad])
    .range([PAD.left, W - PAD.right])
  const H = PAD.top + rows.length * ROW + PAD.bottom
  const grid = Array.from({ length: 80 }, (_, i) => lo - pad + ((hi - lo + 2 * pad) * i) / 79)

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label={`Simulated arrival times against your ${fmtTime(deadline)} deadline`}
    >
      {x.ticks(6).map((t) => (
        <g key={t.getTime()} transform={`translate(${x(t)},0)`}>
          <line y1={PAD.top} y2={H - PAD.bottom} className="stroke-border" strokeDasharray="2 4" />
          <text y={H - 10} textAnchor="middle" className="fill-muted-foreground font-mono text-[11px]">
            {fmtTime(t.toISOString())}
          </text>
        </g>
      ))}

      {rows.map((o, r) => {
        const xs = o.scenario_arrivals.map((t) => new Date(t).getTime())
        const d = density(xs, grid)
        const base = PAD.top + r * ROW + ROW * 0.5
        const y = scaleLinear()
          .domain([0, Math.max(...d)])
          .range([0, ROW * 0.42])
        const cloud = area<number>()
          .x((_, i) => x(grid[i]))
          .y0(base)
          .y1((v) => base - y(v))
          .curve(curveBasis)(d)
        const [p05, p50, p95] = [o.arrival.p05, o.arrival.p50, o.arrival.p95].map((t) => x(new Date(t)))
        return (
          <g key={o.mode}>
            <text x={PAD.left - 12} y={base} textAnchor="end" dominantBaseline="middle" className="fill-foreground text-xs">
              {MODE_LABEL[o.mode]}
            </text>
            <path d={cloud ?? ""} className="fill-rain/25 stroke-rain" strokeWidth={1.5} />
            <line x1={p05} x2={p95} y1={base + 8} y2={base + 8} className="stroke-muted-foreground" strokeWidth={2} />
            <line x1={p50} x2={p50} y1={base + 3} y2={base + 13} className="stroke-foreground" strokeWidth={2} />
            {xs.map((t, i) => (
              <circle
                key={i}
                cx={x(t)}
                cy={base + 20 + ((i * 0.618) % 1) * (ROW * 0.3)}
                r={2.5}
                className={t <= dl ? "fill-safe/80" : "fill-risk"}
              >
                <title>{`${fmtTime(new Date(t).toISOString())}${t <= dl ? "" : " (late)"}`}</title>
              </circle>
            ))}
          </g>
        )
      })}

      <line x1={x(dl)} x2={x(dl)} y1={PAD.top - 8} y2={H - PAD.bottom} className="stroke-deadline" strokeWidth={2} />
      <text x={x(dl) + 6} y={PAD.top} className="fill-deadline font-mono text-[11px]">
        deadline {fmtTime(deadline)}
      </text>
    </svg>
  )
}
