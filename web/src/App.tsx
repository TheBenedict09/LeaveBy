import { lazy, Suspense, useEffect, useRef, useState } from "react"
import { Cloud, Leaf } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { CalendarButton } from "@/components/CalendarButton"
import { Journey } from "@/components/Journey"
import { Bar, Dot, Legend } from "@/components/Legend"
import { WeatherCard } from "@/components/WeatherCard"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Reveal, RollingTime } from "@/components/Reveal"
import { Composer } from "@/components/Composer"
import { RainCloud } from "@/components/RainCloud"
import { TradeOff } from "@/components/TradeOff"
import { SourcesDrawer } from "@/components/SourcesDrawer"
import { TrafficLine } from "@/components/TrafficLine"
import { VerdictStats } from "@/components/VerdictStats"
import { LeaveLater } from "@/components/LeaveLater"
import { Priorities } from "@/components/Priorities"
import { DEFAULT_WEIGHTS, savedVsDriving, shares } from "@/lib/priorities"
import { ApiFailure, createRecommendation, rescore } from "@/lib/api"
import { arriveByIso, fmtTime, MODE_LABEL, pct } from "@/lib/format"
import type { ComposerValue, Meta, Mode, RecommendationData, Weights } from "@/lib/types"

const RouteMap = lazy(() => import("@/components/RouteMap")) // maplibre is large: load it only with a result

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
  const [demo, setDemo] = useState(false) // the API is replaying recorded responses (DEMO_FIXTURES=1)
  const [confidence, setConfidence] = useState([95])
  const [weights, setWeights] = useState<Weights>(DEFAULT_WEIGHTS)
  const [picked, setPicked] = useState<Mode | null>(null) // option shown on the map; null = the recommendation
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
  const busy = useRef(false) // a search is in flight (a ref, so two clicks in the same tick both see it)
  const [last, setLast] = useState<ComposerValue | null>(null) // the last search, for "Try again"
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    fetch("/healthz")
      .then(async (r) => {
        setApi(r.ok ? "up" : "down")
        setDemo(Boolean((await r.json().catch(() => null))?.demo))
      })
      .catch(() => setApi("down"))
  }, [])

  async function run(v: ComposerValue) {
    if (busy.current) return // a second submit while the first is still running is ignored
    busy.current = true
    setLast(v)
    clearTimeout(timer.current)
    const n = ++latest.current
    setPicked(null)
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
        weights: shares(weights),
        constraints: { step_free: false, max_walk_m: 1200, max_bike_m: 25000, has_luggage: false, has_car: v.hasCar },
        options: { simulate_incident: v.simulateIncident },
      })
      if (n !== latest.current) return
      setResult({ ...res, arriveBy, runId: res.data.recommendation_id, confidence: confidence[0] })
      // Bring the answer into view and move focus to it, for keyboard and screen reader users too
      requestAnimationFrame(() => {
        const verdict = document.getElementById("verdict")
        verdict?.focus({ preventScroll: true })
        verdict?.scrollIntoView({
          behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        })
      })
    } catch (e) {
      if (n !== latest.current) return
      setResult(null)
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  // Sliders re-decide live from the stored simulation (no new forecast or routing), once they rest briefly.
  function refine(c: number, w: Weights, wait: number) {
    if (!result) return
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      const n = ++latest.current
      setUpdating(true)
      try {
        const res = await rescore(result.data.recommendation_id, { confidence: c / 100, weights: shares(w) })
        if (n !== latest.current) return
        setError(null)
        setResult((r) => r && { ...r, data: res.data, meta: res.meta, confidence: c })
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
    }, wait)
  }

  function slide(v: number[]) {
    setConfidence(v)
    refine(v[0], weights, 250)
  }

  function prioritise(w: Weights) {
    setWeights(w)
    if (Object.values(w).some((x) => x > 0)) refine(confidence[0], w, 120)
  }

  useEffect(() => () => clearTimeout(timer.current), [])

  const data = result?.data ?? null
  const headline = data?.headline ?? null
  const winner = headline ? data?.options.find((o) => o.mode === headline.mode) : undefined
  const saved = winner && data ? savedVsDriving(winner, data.options) : null
  const ranked = data ? data.options.filter((o) => o.rank !== null).length : 0
  const still = useReducedMotion() ?? false
  const pickedOption = data?.options.find((o) => o.mode === picked && o.feasible)
  const shown = pickedOption ?? winner
  const backupOption = data?.hedge ? data.options.find((o) => o.mode === data.hedge?.backup_mode) : undefined

  return (
    <div className="min-h-screen">
      <a
        href="#verdict"
        className="sr-only z-50 rounded-md bg-rain px-3 py-2 text-background focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to your verdict
      </a>
      <header className="border-b border-border/60">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="lb-logo relative inline-flex size-7 items-start justify-center" aria-hidden>
              <Cloud className="size-6 text-rain" />
              <span className="lb-drop" style={{ left: "30%", animationDelay: "0s" }} />
              <span className="lb-drop" style={{ left: "52%", animationDelay: "0.45s" }} />
              <span className="lb-drop" style={{ left: "74%", animationDelay: "0.9s" }} />
            </span>
            <h1 className="text-lg font-semibold tracking-tight">LeaveBy</h1>
            <span className="hidden text-sm text-muted-foreground sm:inline">One app. One clear decision.</span>
          </div>
          <div className="flex items-center gap-2">
            {demo && (
              <Badge
                variant="outline"
                className="border-deadline/60 text-xs text-deadline"
                title="Every provider answer is a recording; nothing is live"
              >
                Offline demo mode
              </Badge>
            )}
            <Badge variant="outline" className="gap-2 font-mono text-xs" role="status">
              <span className={`size-2 rounded-full ${API_DOT[api]}`} aria-hidden />
              {API_LABEL[api]}
            </Badge>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6">
        {/* Two independent columns per band (no stretched rows, so no dead space). On phones the "contents"
            wrappers dissolve and the order classes give one column: search, verdict, priorities, route, ... */}
        {/* 1. Ask, answer and tune: the trip and its weather; the verdict with its confidence slider, then priorities */}
        <div className="contents lg:grid lg:grid-cols-12 lg:items-start lg:gap-6">
          <div className="contents lg:col-span-5 lg:flex lg:min-w-0 lg:flex-col lg:gap-6">
            <div className="order-1 empty:hidden lg:order-none">
              <Card className="hero-card overflow-visible bg-card/70 backdrop-blur">
                <CardContent>
                  <Composer onSubmit={run} loading={loading} />
                </CardContent>
              </Card>
            </div>
            <div className="order-6 empty:hidden lg:order-none">
              {data?.weather && result && (
                <Reveal key={`weather-${result.runId}`} order={0}>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Weather on your trip</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <WeatherCard weather={data.weather} winner={headline?.mode} />
                    </CardContent>
                  </Card>
                </Reveal>
              )}
            </div>
          </div>
          <div className="contents lg:col-span-7 lg:flex lg:min-w-0 lg:flex-col lg:gap-6">
            <div className="order-2 empty:hidden lg:order-none">
              {error && (
                <div
                  role="alert"
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-risk/40 bg-risk/10 px-4 py-3 text-sm text-risk"
                >
                  <span>{error}</span>
                  {last && !loading && (
                    <Button variant="outline" size="sm" onClick={() => run(last)}>
                      Try again
                    </Button>
                  )}
                </div>
              )}
            </div>
            <div className="order-2 empty:hidden lg:order-none">
              {result?.meta.degraded && (
                <div className="rounded-lg border border-deadline/40 bg-deadline/10 px-4 py-3 text-sm text-deadline">
                  {result.meta.warnings.map((w) => (
                    <p key={w.code + w.message}>{w.message}</p>
                  ))}
                </div>
              )}
            </div>
            <div className="order-3 empty:hidden lg:order-none">
              <Card
                id="verdict"
                tabIndex={-1}
                className="scroll-mt-6 bg-linear-to-br from-card via-card to-rain/[0.06] outline-none"
              >
                <CardHeader>
                  <CardDescription>Your verdict</CardDescription>
                  <CardTitle
                    className={`font-mono text-5xl font-semibold tracking-tight transition-opacity ${headline ? "" : "text-muted-foreground"} ${updating ? "opacity-50" : ""}`}
                    aria-busy={updating}
                    aria-live="polite"
                  >
                    {loading ? (
                      "Working..."
                    ) : headline ? (
                      <>
                        Leave at <RollingTime key={result?.runId} text={fmtTime(headline.leave_at)} />
                      </>
                    ) : (
                      "--:--"
                    )}
                  </CardTitle>
                  {winner?.service && (
                    <p className="text-sm text-muted-foreground">
                      Catch the <span className="font-mono text-foreground">{fmtTime(winner.service.depart_at)}</span>{" "}
                      {winner.service.operator} from {winner.service.from_station}, arrives {winner.service.to_station}{" "}
                      at <span className="font-mono text-foreground">{fmtTime(winner.service.arrive_at)}</span>.
                    </p>
                  )}
                  {winner && result && <VerdictStats key={result.runId} option={winner} meta={result.meta} />}
                  {saved && (
                    <p className="flex items-center gap-1.5 text-sm text-safe">
                      <Leaf aria-hidden className="size-4" />
                      Saves <span className="font-mono">{saved.kg.toFixed(1)} kg</span> CO2e ({saved.pct}%) vs driving
                    </p>
                  )}
                  {data?.traffic && <TrafficLine traffic={data.traffic} />}
                  <div className="flex flex-wrap items-center gap-3">
                    {headline && result && (
                      <CalendarButton id={result.data.recommendation_id} mode={headline.mode} onError={setError} />
                    )}
                    {data && result && <SourcesDrawer meta={result.meta} data={data} confidence={result.confidence} />}
                  </div>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border/60 bg-secondary/30 px-3 py-2">
                    <span className="text-xs text-muted-foreground">How sure do you want to be?</span>
                    <span className="w-12 font-mono text-lg text-rain">{confidence[0]}%</span>
                    <Slider
                      className="min-w-40 flex-1"
                      value={confidence}
                      onValueChange={slide}
                      min={50}
                      max={99}
                      step={1}
                      aria-label="Confidence that you arrive on time"
                      aria-valuetext={`${confidence[0]}%`}
                    />
                  </div>
                  {loading && !data ? (
                    <div className="flex flex-col gap-2" aria-hidden>
                      <Skeleton className="h-4 w-2/3" />
                      <Skeleton className="h-4 w-1/2" />
                    </div>
                  ) : headline ? (
                    <p className="flex flex-wrap items-center gap-x-1.5">
                      <span>
                        <span className="font-mono text-safe">{pct(headline.p_on_time)}</span> chance you arrive on
                        time, based on the forecast for your route
                        {headline.p_on_time < 1 &&
                          `: late about 1 morning in ${Math.round(1 / (1 - headline.p_on_time))}`}
                        .
                      </span>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button type="button" className="text-xs text-rain underline-offset-2 hover:underline">
                            How is this calculated?
                          </button>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-72">
                          The weather service gives 51 versions of the forecast for your start point and these hours.
                          For each, LeaveBy adds 40 draws of everyday variation (traffic, train delays), plays your trip
                          out leaving at {fmtTime(headline.leave_at)}, and counts the arrivals in time:{" "}
                          {headline.on_time_scenarios.toLocaleString()} of {headline.total_scenarios.toLocaleString()}.
                        </TooltipContent>
                      </Tooltip>
                    </p>
                  ) : data ? (
                    <p>
                      No option reaches {result?.confidence}% for this journey. Try a lower confidence or a later
                      arrival time.
                    </p>
                  ) : (
                    <p>
                      Tell LeaveBy where you are going and when you must arrive. It will say exactly when to leave, and
                      how sure it is.
                    </p>
                  )}
                  {headline && data && (
                    <div className="mt-3 flex flex-col gap-1 border-t border-border/60 pt-3" aria-live="polite">
                      {data.explanation.because.map((s) => (
                        <p key={s}>{s}</p>
                      ))}
                      {data.explanation.flip_points.length
                        ? data.explanation.flip_points.map((s) => (
                            <p key={s} className="text-rain">
                              {s}
                            </p>
                          ))
                        : ranked > 1 && <p className="text-rain">This choice holds whatever you prioritise.</p>}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
            <div className="order-4 empty:hidden lg:order-none">
              {data && (
                <Reveal key={`priorities-${result?.runId}`} order={2}>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Your priorities</CardTitle>
                      <CardDescription>Re-rank the options instantly. Defaults match the verdict.</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Priorities value={weights} onChange={prioritise} />
                    </CardContent>
                  </Card>
                </Reveal>
              )}
            </div>
          </div>
        </div>
        {/* 2. The route, full width */}
        <div className="order-5 empty:hidden lg:order-none">
          {data?.route && shown && result && (
            <Reveal key={`route-${result?.runId}`} order={1}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Your route{" "}
                    {shown !== winner && <span className="text-muted-foreground">({MODE_LABEL[shown.mode]})</span>}
                  </CardTitle>
                  <CardDescription>
                    {shown === winner
                      ? "The recommended option, door to door. Pick another option below to compare."
                      : "Showing the option you picked. "}
                    {shown !== winner && (
                      <button
                        type="button"
                        className="text-rain underline-offset-2 hover:underline"
                        onClick={() => setPicked(null)}
                      >
                        Back to the recommendation
                      </button>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
                  <Suspense fallback={<div className="h-80 animate-pulse rounded-lg bg-secondary/40 lg:h-[440px]" />}>
                    <RouteMap
                      key={result.runId}
                      route={data.route}
                      mode={shown.mode}
                      service={shown.service}
                      still={still}
                    />
                  </Suspense>
                  <Journey
                    option={shown}
                    backup={shown === winner ? data.hedge : null}
                    backupOption={backupOption}
                    deadline={result.arriveBy}
                    traffic={data.traffic}
                  />
                </CardContent>
              </Card>
            </Reveal>
          )}
        </div>
        {/* 3. Compare the options */}
        <div className="contents lg:grid lg:grid-cols-12 lg:items-start lg:gap-6">
          <div className="contents lg:col-span-5 lg:flex lg:min-w-0 lg:flex-col lg:gap-6">
            <div className="order-7 empty:hidden lg:order-none">
              {data && (
                <Reveal key={`options-${result?.runId}`} order={5}>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">All options</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-4">
                      <ul className="divide-y divide-border/60">
                        {data.options.map((o) => (
                          <motion.li
                            key={o.mode}
                            layout={!still}
                            transition={{ type: "spring", stiffness: 400, damping: 35 }}
                            className="flex items-center justify-between gap-4 py-2 text-sm"
                          >
                            <button
                              type="button"
                              disabled={!o.feasible}
                              aria-pressed={shown?.mode === o.mode}
                              title={o.feasible ? "Show on the map" : undefined}
                              onClick={() => setPicked(o.mode)}
                              className={`flex items-center gap-2 rounded-md px-1 font-medium ${o.feasible ? "hover:text-rain" : "cursor-default"} ${shown?.mode === o.mode ? "text-rain" : ""}`}
                            >
                              <span
                                className={`grid size-5 place-items-center rounded-full font-mono text-xs ${o.rank === 1 ? "bg-rain text-background" : "bg-secondary text-muted-foreground"}`}
                              >
                                {o.rank ?? "–"}
                              </span>
                              {MODE_LABEL[o.mode]}
                            </button>
                            <span className="text-right text-muted-foreground">
                              {o.feasible && o.leave_by
                                ? `leave ${fmtTime(o.leave_by)} · ${pct(o.p_on_time)} on time · £${o.cost_gbp.toFixed(2)}`
                                : o.infeasible_reason}
                            </span>
                          </motion.li>
                        ))}
                      </ul>
                      <TradeOff options={data.options} confidence={(result?.confidence ?? 95) / 100} />
                    </CardContent>
                  </Card>
                </Reveal>
              )}
            </div>
          </div>
          <div className="contents lg:col-span-7 lg:flex lg:min-w-0 lg:flex-col lg:gap-6">
            <div className="order-8 empty:hidden lg:order-none">
              {data && headline && result && (
                <Reveal key={`leave-later-${result?.runId}`} order={3}>
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">What if I leave later?</CardTitle>
                      <CardDescription>
                        Slide to see how your chances change. Uses the same simulated mornings.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <LeaveLater
                        key={`${result.runId}-${headline.leave_at}`}
                        options={data.options}
                        leaveAt={headline.leave_at}
                        confidence={result.confidence / 100}
                      />
                    </CardContent>
                  </Card>
                </Reveal>
              )}
            </div>
            <div className="order-9 empty:hidden lg:order-none">
              {data?.hedge && (
                <Reveal key={`backup-${result?.runId}`} order={4}>
                  <Card>
                    <CardHeader>
                      <CardDescription>Backup plan</CardDescription>
                      <CardTitle className="text-xl">
                        Or leave at <span className="font-mono">{fmtTime(data.hedge.leave_at)}</span>{" "}
                        {MODE_LABEL[data.hedge.backup_mode]}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      {data.hedge.both_late_scenarios === 0 ? (
                        <>In no forecast are both plans late on the same morning.</>
                      ) : (
                        <>
                          Both plans are late on the same morning{" "}
                          <span className="font-mono text-risk">
                            {pct(data.hedge.both_late_scenarios / data.hedge.total_scenarios)}
                          </span>{" "}
                          of the time.
                        </>
                      )}
                    </CardContent>
                  </Card>
                </Reveal>
              )}
            </div>
          </div>
        </div>
        {/* 4. The evidence */}
        <div className="order-10 empty:hidden lg:order-none">
          {result ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">How the forecast could play out</CardTitle>
                <Legend
                  items={[
                    { swatch: <Dot className="bg-safe" />, label: "in time" },
                    { swatch: <Dot className="bg-risk" />, label: "late" },
                    { swatch: <Bar className="bg-deadline" />, label: "deadline" },
                    { swatch: <Bar className="bg-muted-foreground" />, label: "9 in 10 arrive" },
                  ]}
                  detail="Each dot is one of the 51 official forecasts (ECMWF) for your start point and morning, if you leave at the suggested time. The blue cloud shows where arrivals bunch up."
                />
              </CardHeader>
              <CardContent className="mx-auto w-full max-w-4xl">
                <RainCloud
                  options={result.data.options}
                  deadline={result.arriveBy}
                  runId={result.runId}
                  weather={result.data.weather?.members_at_departure}
                />
              </CardContent>
            </Card>
          ) : (
            <Card className="border-dashed">
              <CardContent className="flex h-72 items-center justify-center text-sm text-muted-foreground">
                How the forecast could play out will appear here
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  )
}
