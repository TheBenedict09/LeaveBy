import { useEffect, useRef, useState } from "react"
import { motion, useInView, useReducedMotion } from "motion/react"
import { scaleLinear, scaleTime } from "d3-scale"
import { area, curveBasis } from "d3-shape"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmtTime, MODE_LABEL, pct } from "@/lib/format"
import type { Option } from "@/lib/types"

const W = 720
const PAD = { top: 16, right: 24, bottom: 32, left: 88 }
const ROW = 96
const FALL = { type: "spring", stiffness: 60, damping: 15 } as const
// Delays in seconds, sized so the last dot lands about 3 s after the rain starts.
const ROW_GAP = 0.25
const SPREAD = 0.9 // random per-dot delay
const SWEEP = 0.15 // extra delay from left to right, so neighbours never land in lockstep
const COLUMN_STAGGER = 0.07 // between dots stacked in the same column, so a stack rains in one by one
const COLUMN_MAX = 0.6
const CLOUD_AT = 1.6 // the cloud and bar fade in once most dots are down

/** Gaussian kernel density of xs (ms) at each point of grid; Silverman bandwidth, at least 1 minute. */
function density(xs: number[], grid: number[]): number[] {
  const n = xs.length
  const mean = xs.reduce((a, b) => a + b, 0) / n
  const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / n)
  const h = Math.max(1.06 * sd * n ** -0.2, 60_000)
  return grid.map((g) => xs.reduce((a, x) => a + Math.exp(-0.5 * ((g - x) / h) ** 2), 0) / (n * h))
}

/** Deterministic 0..1 per (dot, row), so re-renders never reshuffle the rain. */
function hash(i: number, r: number): number {
  const s = Math.sin(i * 12.9898 + r * 78.233) * 43758.5453
  return s - Math.floor(s)
}

// Hard-constraint failures (no car, too far) are left out: their arrivals say nothing about the deadline.
const plotted = (o: Option) => o.feasible || o.infeasible_reason?.startsWith("Cannot reach")

export function RainCloud({ options, deadline, runId }: { options: Option[]; deadline: string; runId: string }) {
  const [asTable, setAsTable] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const still = useReducedMotion() ?? false
  const rows = options.filter(plotted)

  // Bring each new result into view; the rain starts once the chart is on screen.
  useEffect(() => {
    box.current?.scrollIntoView({
      behavior: still ? "auto" : "smooth",
      block: "center",
    })
  }, [runId, still])

  if (!rows.length) return null

  return (
    <div ref={box} className="flex flex-col gap-3">
      <Button
        variant="outline"
        size="sm"
        className="self-end"
        aria-pressed={asTable}
        onClick={() => setAsTable((t) => !t)}
      >
        {asTable ? "Show as chart" : "Show as table"}
      </Button>
      {asTable ? (
        <JourneyTable rows={rows.filter((o) => o.feasible && o.leave_by)} />
      ) : (
        <Chart key={runId} rows={rows} deadline={deadline} still={still} />
      )}
    </div>
  )
}

function JourneyTable({ rows }: { rows: Option[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Option</TableHead>
          <TableHead>Leave by</TableHead>
          <TableHead>Typical arrival</TableHead>
          <TableHead>Range 5% to 95%</TableHead>
          <TableHead>On time</TableHead>
          <TableHead>Buffer needed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((o) => (
          <TableRow key={o.mode}>
            <TableCell className="font-medium">{MODE_LABEL[o.mode]}</TableCell>
            <TableCell className="font-mono">{fmtTime(o.leave_by!)}</TableCell>
            <TableCell className="font-mono">{fmtTime(o.arrival.p50)}</TableCell>
            <TableCell className="font-mono">
              {fmtTime(o.arrival.p05)} to {fmtTime(o.arrival.p95)}
            </TableCell>
            <TableCell>
              {pct(o.p_on_time)}{" "}
              <span className="text-muted-foreground">
                ({o.on_time_scenarios.toLocaleString()} of {o.total_scenarios.toLocaleString()})
              </span>
            </TableCell>
            <TableCell>{Math.round(o.journey_at_risk_min)} min</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

type Hover = { row: number; t: number; dot: number | null } // t = time under the pointer or the focused dot

function Chart({ rows, deadline, still }: { rows: Option[]; deadline: string; still: boolean }) {
  const ref = useRef<SVGSVGElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.4 })
  const [fallback, setFallback] = useState(false)
  const [ready, setReady] = useState(still) // hover stays off until the rain has landed
  const [hover, setHover] = useState<Hover | null>(null)
  const [width, setWidth] = useState(W) // rendered px width, to place the card

  const started = still || inView || fallback

  // Start anyway if the observer never fires (for example, a viewport too short to show 40% of the chart).
  useEffect(() => {
    const t = setTimeout(() => setFallback(true), 2500)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (!started || still) return
    const t = setTimeout(() => setReady(true), 3200)
    return () => clearTimeout(t)
  }, [started, still])

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

  const data = rows.map((o, r) => {
    const xs = o.scenario_arrivals.map((t) => new Date(t).getTime())
    const base = PAD.top + r * ROW + ROW * 0.5
    const d = density(xs, grid)
    const y = scaleLinear()
      .domain([0, Math.max(...d)])
      .range([0, ROW * 0.42])
    const cloud = area<number>()
      .x((_, i) => x(grid[i]))
      .y0(base)
      .y1((v) => base - y(v))
      .curve(curveBasis)(d)
    const cys = xs.map((_, i) => base + 20 + ((i * 0.618) % 1) * (ROW * 0.3))
    const order = xs.map((_, i) => i).sort((a, b) => xs[a] - xs[b]) // dot indices in time order, for arrow keys
    return { o, xs, base, cloud, cys, order }
  })

  const summary = data
    .map(
      ({ o, xs }) => `${MODE_LABEL[o.mode]}: ${xs.filter((t) => t > dl).length} of ${xs.length} sampled mornings late`,
    )
    .join("; ")

  // Pointer -> time on the x axis, in chart units.
  const timeAt = (e: React.PointerEvent) => {
    const box = ref.current!.getBoundingClientRect()
    setWidth(box.width)
    return x.invert(((e.clientX - box.left) * W) / box.width).getTime()
  }

  const onKey = (e: React.KeyboardEvent, r: number) => {
    const { order, xs } = data[r]
    if (e.key === "Escape") return setHover(null)
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return
    e.preventDefault()
    setWidth(ref.current!.getBoundingClientRect().width)
    // Functional update, so fast key repeats each step from the latest position.
    setHover((h) => {
      const at = h?.row === r && h.dot !== null ? order.indexOf(h.dot) : -1
      const k = Math.max(
        0,
        Math.min(order.length - 1, e.key === "ArrowRight" ? at + 1 : at < 0 ? order.length - 1 : at - 1),
      )
      return { row: r, dot: order[k], t: xs[order[k]] }
    })
  }

  // The card: placed from chart units, flipped near the edges so it never clips.
  let card = null
  if (hover) {
    const { o, xs, cys, base } = data[hover.row]
    const px = (x(hover.t) / W) * width
    const top = ((hover.dot === null ? base - ROW * 0.42 : cys[hover.dot]) / W) * width
    const shift = px < 110 ? "0%" : px > width - 110 ? "-100%" : "-50%"
    const t = hover.t
    const mins = Math.round(Math.abs(dl - t) / 60_000)
    card = (
      <div
        role="status"
        className="pointer-events-none absolute z-10 w-max max-w-64 rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md"
        style={{ left: px, top, transform: `translate(${shift}, calc(-100% - 10px))` }}
      >
        <p className="font-medium text-foreground">{MODE_LABEL[o.mode]}</p>
        {hover.dot === null ? (
          <p className="text-muted-foreground">
            <span className="font-mono text-rain">{pct(xs.filter((a) => a <= t).length / xs.length)}</span> of mornings
            arrive by <span className="font-mono text-foreground">{fmtTime(new Date(t).toISOString())}</span>
          </p>
        ) : (
          <>
            <p className="text-muted-foreground">
              Arrives <span className="font-mono text-foreground">{fmtTime(new Date(t).toISOString())}</span>
            </p>
            <p className={t <= dl ? "text-safe" : "text-risk"}>
              {t <= dl
                ? mins
                  ? `On time, ${mins} min before the deadline`
                  : "On time, just"
                : `Late by ${mins || "under 1"} min`}
            </p>
            <p className="text-muted-foreground">One of {xs.length} forecast members</p>
          </>
        )}
      </div>
    )
  }

  const ease = still ? undefined : "r 150ms ease-out, opacity 150ms"

  return (
    <div className="relative" onPointerLeave={() => setHover(null)}>
      <motion.svg
        ref={ref}
        initial={still ? false : "hidden"}
        animate={started ? "shown" : "hidden"}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label={`Simulated arrival times against your ${fmtTime(deadline)} deadline. ${summary}. Use "Show as table" for the numbers.`}
      >
        {x.ticks(6).map((t) => (
          <g key={t.getTime()} transform={`translate(${x(t)},0)`}>
            <line y1={PAD.top} y2={H - PAD.bottom} className="stroke-border" strokeDasharray="2 4" />
            <text y={H - 10} textAnchor="middle" className="fill-muted-foreground font-mono text-[11px]">
              {fmtTime(t.toISOString())}
            </text>
          </g>
        ))}

        {data.map(({ o, xs, base, cloud, cys }, r) => {
          const [p05, p50, p95] = [o.arrival.p05, o.arrival.p50, o.arrival.p95].map((t) => x(new Date(t)))
          const focused = hover?.row === r
          const delay = (i: number) =>
            r * ROW_GAP +
            hash(i, r) * SPREAD +
            ((x(xs[i]) - PAD.left) / (W - PAD.left - PAD.right)) * SWEEP +
            Math.min(xs.slice(0, i).filter((u) => Math.abs(x(u) - x(xs[i])) < 3).length * COLUMN_STAGGER, COLUMN_MAX)
          return (
            <g key={o.mode} opacity={hover && !focused ? 0.55 : 1} style={{ transition: ease && "opacity 150ms" }}>
              <text
                x={PAD.left - 12}
                y={base}
                textAnchor="end"
                dominantBaseline="middle"
                className={`text-xs ${focused ? "fill-rain font-medium" : "fill-foreground"}`}
              >
                {MODE_LABEL[o.mode]}
              </text>
              <motion.g
                variants={{
                  hidden: { opacity: 0 },
                  shown: { opacity: 1, transition: { delay: CLOUD_AT + r * ROW_GAP, duration: 0.6 } },
                }}
              >
                <path
                  d={cloud ?? ""}
                  tabIndex={0}
                  aria-label={`${MODE_LABEL[o.mode]} arrival times, ${pct(o.p_on_time)} on time. Use the arrow keys to step through them.`}
                  className={`stroke-rain outline-none ${focused && hover?.dot === null ? "fill-rain/40" : "fill-rain/25"} focus-visible:fill-rain/40`}
                  strokeWidth={focused ? 2.5 : 1.5}
                  style={{ transition: ease && "fill 150ms, stroke-width 150ms" }}
                  onPointerMove={(e) => ready && setHover({ row: r, t: timeAt(e), dot: null })}
                  onKeyDown={(e) => onKey(e, r)}
                  onBlur={() => setHover(null)}
                />
                <line
                  x1={p05}
                  x2={p95}
                  y1={base + 8}
                  y2={base + 8}
                  className="stroke-muted-foreground"
                  strokeWidth={2}
                />
                <line x1={p50} x2={p50} y1={base + 3} y2={base + 13} className="stroke-foreground" strokeWidth={2} />
              </motion.g>
              {xs.map((t, i) => {
                const on = focused && hover?.dot === i
                const late = t > dl
                return (
                  <motion.circle
                    key={i}
                    cx={x(t)}
                    cy={cys[i]}
                    r={on ? 5 : 2.5}
                    className={`${late ? "fill-risk stroke-risk/40" : "fill-safe stroke-safe/40"}`}
                    strokeWidth={on ? 6 : 0}
                    opacity={focused && hover?.dot !== null && !on ? 0.35 : 0.9}
                    style={{ transition: ease, paintOrder: "stroke" }}
                    variants={{
                      hidden: { y: -cys[i], opacity: 0 },
                      shown: {
                        y: 0,
                        opacity: 1,
                        transition: { y: { ...FALL, delay: delay(i) }, opacity: { delay: delay(i), duration: 0.2 } },
                      },
                    }}
                  />
                )
              })}
              {/* Wide invisible hit targets, so the tiny dots are easy to hover */}
              {ready &&
                xs.map((t, i) => (
                  <circle
                    key={`hit-${i}`}
                    cx={x(t)}
                    cy={cys[i]}
                    r={6}
                    fill="transparent"
                    onPointerEnter={(e) => {
                      timeAt(e)
                      setHover({ row: r, t, dot: i })
                    }}
                    onPointerLeave={() => setHover(null)}
                  />
                ))}
            </g>
          )
        })}

        {hover && (
          <line
            x1={x(hover.t)}
            x2={x(hover.t)}
            y1={PAD.top}
            y2={H - PAD.bottom}
            className="pointer-events-none stroke-rain/70"
            strokeDasharray="3 3"
          />
        )}
        <line x1={x(dl)} x2={x(dl)} y1={PAD.top - 8} y2={H - PAD.bottom} className="stroke-deadline" strokeWidth={2} />
        <text x={x(dl) + 6} y={PAD.top} className="fill-deadline font-mono text-[11px]">
          deadline {fmtTime(deadline)}
        </text>
      </motion.svg>
      {card}
    </div>
  )
}
