import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Ticker } from "@/components/Reveal"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Meta, Option } from "@/lib/types"

// What each non-live source feeds, in words people understand.
const SOURCE_LABEL: Record<string, string> = {
  "mock-rail": "train times and delays",
  "mock-rail-delays": "train delays (the timetable itself is real)",
  "simulated-incident": "the accident (a demo, not real)",
  "simulated-storm": "the weather (a demo storm, not the forecast)",
  "mock-fares": "fares and running costs",
  "mock-accessibility": "access score",
}

/** Cost, carbon and access for the winning option, with an honest tag when any of it is not live data. */
export function VerdictStats({ option, meta }: { option: Option; meta: Meta }) {
  const kind = new Map(meta.sources.map((s) => [s.id, s.kind]))
  const estimated = option.provenance.filter((id) => {
    const k = kind.get(id) ?? (id.startsWith("mock-") ? "mock" : "live")
    return k === "mock" || k === "estimated"
  })

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
      <Stat label="Cost" value={<Ticker value={option.cost_gbp} format={(v) => `£${v.toFixed(2)}`} />} />
      <Stat label="CO2e" value={<Ticker value={option.co2e_kg} format={(v) => `${v.toFixed(1)} kg`} />} />
      <Stat label="Access score" value={<Ticker value={option.accessibility.score} format={(v) => v.toFixed(2)} />} />
      {estimated.length > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline" className="cursor-help text-deadline" tabIndex={0}>
              Estimated
            </Badge>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">
            Not live yet: {estimated.map((id) => SOURCE_LABEL[id] ?? id).join(", ")}.
            {option.provenance.includes("rdg-timetable") && " Timetable: real, Rail Delivery Group (static file)."}
            {option.provenance.includes("desnz-ghg-2026") && " CO2e: real, UK Government conversion factors 2026."}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="text-muted-foreground">
      {label} <span className="font-mono text-foreground">{value}</span>
    </span>
  )
}
