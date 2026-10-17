import { useEffect, useRef, useState } from "react"
import { CloudRain } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { Composer } from "@/components/Composer"
import { RainCloud } from "@/components/RainCloud"
import { VerdictStats } from "@/components/VerdictStats"
import { ApiFailure, createRecommendation, rescore } from "@/lib/api"
import { arriveByIso, fmtTime, MODE_LABEL, pct } from "@/lib/format"
import type { ComposerValue, Meta, RecommendationData } from "@/lib/types"

type ApiState = "checking" | "up" | "down"

const API_LABEL: Record<ApiState, string> = {
  checking: "Checking API",
  up: "API connected",
  down: "API offline",
}

const API_DOT: Record<ApiState, string> = {
  checking: "bg-muted-foreground",
  up: "bg-safe",
  down: "bg-risk",
}

export default function App() {
  const [api, setApi] = useState<ApiState>("checking")
  const [confidence, setConfidence] = useState([95])
  // runId changes only on a new search, so rescoring never replays the chart intro or scrolls.
  const [result, setResult] = useState<{
    data: RecommendationData
    meta: Meta
    arriveBy: string
    runId: string
    confidence: number
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latest = useRef(0) // request counter: only the newest reply may land
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    fetch("/healthz")
      .then((r) => setApi(r.ok ? "up" : "down"))
      .catch(() => setApi("down"))
  }, [])

  async function run(v: ComposerValue) {
    clearTimeout(timer.current)
    const n = ++latest.current
    setUpdating(false)
    setLoading(true)
    setError(null)
    try {
      const arriveBy = arriveByIso(v.dayOffset, v.time)
      const res = await createRecommendation({
        origin: v.origin,
        destination: v.destination,
        arrive_by: arriveBy,
        confidence: confidence[0] / 100,
        constraints: { step_free: false, max_walk_m: 1200, max_bike_m: 25000, has_luggage: false, has_car: v.hasCar },
      })
      if (n !== latest.current) return
      setResult({ ...res, arriveBy, runId: res.data.recommendation_id, confidence: confidence[0] })
    } catch (e) {
      if (n !== latest.current) return
      setResult(null)
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  // The slider re-decides live from the stored simulation, once it rests for 250 ms.
  function slide(v: number[]) {
    setConfidence(v)
    if (!result) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      const n = ++latest.current
      setUpdating(true)
      try {
        const res = await rescore(result.data.recommendation_id, { confidence: v[0] / 100 })
        if (n !== latest.current) return
        setError(null)
        setResult((r) => r && { ...r, data: res.data, meta: res.meta, confidence: v[0] })
      } catch (e) {
        if (n !== latest.current) return
        setError(
          e instanceof ApiFailure && e.code === "NOT_FOUND"
            ? "This result has expired. Search again to keep adjusting it."
            : e instanceof Error
              ? e.message
              : "Something went wrong",
        )
      } finally {
        if (n === latest.current) setUpdating(false)
      }
    }, 250)
  }

  useEffect(() => () => clearTimeout(timer.current), [])

  const data = result?.data ?? null
  const headline = data?.headline ?? null
  const winner = headline ? data?.options.find((o) => o.mode === headline.mode) : undefined

  return (
    <div className="min-h-screen">
      <header className="border-b border-border/60">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <CloudRain className="size-5 text-rain" aria-hidden />
            <span className="text-lg font-semibold tracking-tight">LeaveBy</span>
          </div>
          <Badge variant="outline" className="gap-2 font-mono text-xs" role="status">
            <span className={`size-2 rounded-full ${API_DOT[api]}`} aria-hidden />
            {API_LABEL[api]}
          </Badge>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[1fr_320px]">
        <section className="flex flex-col gap-6" aria-label="Recommendation">
          <Card>
            <CardContent>
              <Composer onSubmit={run} loading={loading} />
            </CardContent>
          </Card>

          {error && (
            <div role="alert" className="rounded-lg border border-risk/40 bg-risk/10 px-4 py-3 text-sm text-risk">
              {error}
            </div>
          )}

          {result?.meta.degraded && (
            <div className="rounded-lg border border-deadline/40 bg-deadline/10 px-4 py-3 text-sm text-deadline">
              {result.meta.warnings.map((w) => (
                <p key={w.code + w.message}>{w.message}</p>
              ))}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardDescription>Your verdict</CardDescription>
              <CardTitle
                className={`font-mono text-5xl font-semibold tracking-tight transition-opacity ${headline ? "" : "text-muted-foreground"} ${updating ? "opacity-50" : ""}`}
                aria-busy={updating}
                aria-live="polite"
              >
                {loading ? "Working..." : headline ? `Leave at ${fmtTime(headline.leave_at)}` : "--:--"}
              </CardTitle>
              {winner && result && <VerdictStats option={winner} meta={result.meta} />}
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              {headline ? (
                <p>
                  {MODE_LABEL[headline.mode]}. On time in{" "}
                  <span className="font-mono text-safe">
                    {headline.on_time_scenarios.toLocaleString()} of {headline.total_scenarios.toLocaleString()}
                  </span>{" "}
                  simulated journeys ({pct(headline.p_on_time)}).
                </p>
              ) : data ? (
                <p>
                  No option reaches {result?.confidence}% for this journey. Try a lower confidence or a later arrival
                  time.
                </p>
              ) : (
                <p>
                  Tell LeaveBy where you are going and when you must arrive. It will say exactly when to leave, and how
                  sure it is.
                </p>
              )}
            </CardContent>
          </Card>

          {data?.hedge && (
            <Card>
              <CardHeader>
                <CardDescription>Backup plan</CardDescription>
                <CardTitle className="text-xl">
                  Or leave at <span className="font-mono">{fmtTime(data.hedge.leave_at)}</span>{" "}
                  {MODE_LABEL[data.hedge.backup_mode]}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                Both plans fail together in{" "}
                <span className={`font-mono ${data.hedge.both_late_scenarios ? "text-risk" : "text-safe"}`}>
                  {data.hedge.both_late_scenarios.toLocaleString()} of {data.hedge.total_scenarios.toLocaleString()}
                </span>{" "}
                simulated journeys.
              </CardContent>
            </Card>
          )}

          {data && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">All options</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border/60">
                  {data.options.map((o) => (
                    <li key={o.mode} className="flex items-center justify-between gap-4 py-2 text-sm">
                      <span className="font-medium">{MODE_LABEL[o.mode]}</span>
                      <span className="text-right text-muted-foreground">
                        {o.feasible && o.leave_by
                          ? `leave ${fmtTime(o.leave_by)} · ${pct(o.p_on_time)} on time · £${o.cost_gbp.toFixed(2)}`
                          : o.infeasible_reason}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {result ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Every simulated journey</CardTitle>
                <CardDescription>
                  Each dot is one possible morning if you leave at the suggested time. Mint arrives in time, coral is
                  late.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <RainCloud options={result.data.options} deadline={result.arriveBy} runId={result.runId} />
              </CardContent>
            </Card>
          ) : (
            <Card className="border-dashed">
              <CardContent className="flex h-72 items-center justify-center text-sm text-muted-foreground">
                Your simulated journeys will appear here
              </CardContent>
            </Card>
          )}
        </section>

        <aside className="flex flex-col gap-6" aria-label="Controls">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">How sure do you want to be?</CardTitle>
              <CardDescription>Higher means leaving earlier. Your leave-by time moves as you slide.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="font-mono text-3xl text-rain">{confidence[0]}%</div>
              <Slider
                value={confidence}
                onValueChange={slide}
                min={50}
                max={99}
                step={1}
                aria-label="Confidence that you arrive on time"
              />
            </CardContent>
          </Card>
        </aside>
      </main>
    </div>
  )
}
