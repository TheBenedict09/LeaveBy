import { Badge } from "@/components/ui/badge"
import type { Traffic } from "@/lib/types"

const BASIS: Record<Traffic["basis"], string> = {
  live: "live traffic, TomTom",
  predicted: "predicted traffic for that time, TomTom",
  "free-flow": "free-flow, no traffic data",
}

/** One honest line about the car's traffic, and incidents only when there are any. */
export function TrafficLine({ traffic }: { traffic: Traffic }) {
  const i = traffic.incidents
  return (
    <div className="flex flex-col gap-1 text-sm text-muted-foreground">
      <p>
        Car: <span className="font-mono text-foreground">{Math.round(traffic.car_min)} min</span> (
        {BASIS[traffic.basis]}
        {traffic.basis !== "free-flow" && `; ${Math.round(traffic.free_flow_min)} min without traffic`})
      </p>
      {i && (
        <p className={`flex flex-wrap items-center gap-2 ${i.simulated ? "text-deadline" : "text-risk"}`}>
          {i.simulated && (
            <Badge variant="outline" className="border-deadline/60 text-deadline">
              Simulated
            </Badge>
          )}
          {i.simulated
            ? `Demo accident on the car route, +${Math.round(i.worst_delay_min)} min. Not real.`
            : `${i.count} ${i.count === 1 ? "incident" : "incidents"} near your route now, worst +${Math.round(i.worst_delay_min)} min${i.description ? `: ${i.description}` : ""}.`}
        </p>
      )}
    </div>
  )
}
