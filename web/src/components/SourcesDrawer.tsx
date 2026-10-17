import { useState } from "react"
import { BookOpen } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { getAssumptions, getSources, type Assumptions, type SourceInfo } from "@/lib/api"
import { fmtTime } from "@/lib/format"
import type { Meta, RecommendationData, SourceMeta } from "@/lib/types"

/** How much to trust each source, in plain words. Derived only from the source's id and kind in this response. */
function badge(s: SourceMeta): { label: string; tone: string } {
  if (s.id === "tomtom-predicted") return { label: "Predicted", tone: "text-rain border-rain/50" }
  if (s.id === "simulated-incident") return { label: "Simulated", tone: "text-deadline border-deadline/60" }
  if (s.id === "mock-rail-delays") return { label: "Modelled", tone: "text-deadline border-deadline/50" }
  if (s.kind === "live") return { label: "Live", tone: "text-safe border-safe/50" }
  if (s.kind === "cached") return { label: "Live, cached", tone: "text-safe border-safe/40" }
  if (s.kind === "static") return { label: "Static", tone: "text-rain border-rain/50" }
  if (s.kind === "estimated") return { label: "Fallback", tone: "text-risk border-risk/50" }
  return { label: "Mock", tone: "text-muted-foreground" }
}

type Loaded = { registry: Map<string, SourceInfo> } & Assumptions

export function SourcesDrawer({
  meta,
  data,
  confidence,
}: {
  meta: Meta
  data: RecommendationData
  confidence: number
}) {
  const [info, setInfo] = useState<Loaded | null>(null)
  const [failed, setFailed] = useState(false)

  async function load() {
    try {
      const [s, a] = await Promise.all([getSources(), getAssumptions()])
      setInfo({ ...a.data, registry: new Map(s.data.sources.map((x) => [x.id, x])) })
    } catch {
      setFailed(true)
    }
  }

  const total = data.options[0]?.total_scenarios ?? 0
  const draws = info?.model.noise.n_draws
  const rail = info?.model.rail
  const tt = info?.rail_timetable

  return (
    <Sheet onOpenChange={(open) => open && !info && load()}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm" className="self-start px-0 text-muted-foreground hover:text-foreground">
          <BookOpen />
          Sources and assumptions
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Sources and assumptions</SheetTitle>
          <SheetDescription>Everything behind this answer, and how much to trust each part.</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-6 px-4 pb-6 text-sm">
          <section aria-labelledby="src-h" className="flex flex-col gap-3">
            <h3 id="src-h" className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Data used for this result
            </h3>
            <ul className="flex flex-col gap-3">
              {meta.sources.map((s) => {
                const b = badge(s)
                const reg = info?.registry.get(s.id)
                return (
                  <li key={`${s.id}-${s.kind}`} className="flex flex-col gap-1 rounded-lg border border-border/60 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{reg?.role ?? s.id}</span>
                      <Badge variant="outline" className={b.tone}>
                        {b.label}
                      </Badge>
                    </div>
                    {(s.attribution ?? reg?.attribution) && (
                      <span className="text-xs text-muted-foreground">{s.attribution ?? reg?.attribution}</span>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {s.licence}
                      {(s.kind === "live" || s.kind === "cached") &&
                        ` · retrieved ${fmtTime(s.fetched_at)}${s.age_s ? `, ${Math.round(s.age_s / 60)} min old` : ""}`}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>

          <section aria-labelledby="ass-h" className="flex flex-col gap-2">
            <h3 id="ass-h" className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Key assumptions
            </h3>
            {failed && <p className="text-risk">Could not load the assumptions. Try again later.</p>}
            <ul className="flex list-disc flex-col gap-1.5 pl-4 text-muted-foreground">
              <li>
                Confidence you chose: <span className="font-mono text-foreground">{confidence}%</span>
              </li>
              <li>
                <span className="font-mono text-foreground">{total.toLocaleString()}</span> simulated journeys per
                option
                {draws ? ` (${total / draws} weather forecast members × ${draws} traffic and delay draws)` : ""}.
              </li>
              {data.traffic && (
                <li>
                  Car time:{" "}
                  {data.traffic.basis === "free-flow"
                    ? "free-flow routing, no traffic data"
                    : `TomTom ${data.traffic.basis} traffic`}
                  , with random traffic noise on top.
                </li>
              )}
              {rail && (
                <>
                  <li>
                    Real trains are used when both ends are within{" "}
                    <span className="font-mono text-foreground">{rail.station_radius_m / 1000} km</span> of a timetable
                    station; otherwise trains are simulated.
                  </li>
                  <li>
                    Train delays are modelled so that in calm weather{" "}
                    <span className="font-mono text-foreground">
                      {Math.round(rail.calm_within_5min_target * 1000) / 10}%
                    </span>{" "}
                    arrive within 5 minutes, from published punctuality:
                    <ul className="mt-1 list-[circle] pl-4 text-xs">
                      {rail.calm_target_sources.map((x) => (
                        <li key={x}>{x}</li>
                      ))}
                    </ul>
                  </li>
                </>
              )}
              {tt && (
                <li>
                  {tt.source}. Release {tt.release}, valid {tt.valid_from} to {tt.valid_to}.
                </li>
              )}
              {info && <li>CO2e: {info.model.emissions.source}.</li>}
              {meta.sources.some((s) => s.id === "mock-fares" || s.id === "mock-accessibility") && (
                <li>Fares and access scores are placeholders until real data is connected.</li>
              )}
            </ul>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  )
}
