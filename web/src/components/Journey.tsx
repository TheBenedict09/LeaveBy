import { fmtTime, MODE_LABEL } from "@/lib/format"
import type { Hedge, Option, Traffic } from "@/lib/types"

type Step = { at: string; text: string; note?: string; tone?: string }

/** The legs the engine actually models, with times from the response. */
function steps(o: Option, deadline: string, traffic: Traffic | null | undefined): Step[] {
  if (!o.leave_by) return []
  const out: Step[] = [{ at: o.leave_by, text: "Leave" }]
  const s = o.service
  if (o.mode === "train" && s) {
    const access = Math.round((new Date(s.depart_at).getTime() - new Date(o.leave_by).getTime()) / 60_000)
    out.push({
      at: s.depart_at,
      text: `${s.operator} from ${s.from_station}`,
      note: `${access} min allowance to get to the platform (not routed)`,
    })
    out.push({ at: s.arrive_at, text: `Arrive ${s.to_station}`, note: "then the allowance to your door" })
  } else if (o.mode === "drive" && traffic) {
    out.push({
      at: o.leave_by,
      text: `Drive, about ${Math.round(traffic.car_min)} min`,
      note: traffic.basis === "free-flow" ? "free-flow, no traffic data" : `${traffic.basis} traffic, TomTom`,
    })
  }
  out.push({ at: o.arrival.p50, text: "Typically arrive", note: `9 in 10 by ${fmtTime(o.arrival.p95)}` })
  const buffer = Math.round((new Date(deadline).getTime() - new Date(o.arrival.p50).getTime()) / 60_000)
  out.push({
    at: deadline,
    text: "Deadline",
    note: `${buffer} min to spare on a typical morning`,
    tone: "text-deadline",
  })
  return out
}

export function Journey({
  option,
  backup,
  backupOption,
  deadline,
  traffic,
}: {
  option: Option
  backup: Hedge | null
  backupOption?: Option
  deadline: string
  traffic?: Traffic | null
}) {
  return (
    <div className="flex flex-col gap-3">
      <ol
        className="relative flex flex-col gap-3 border-l border-border pl-5"
        aria-label={`Door to door ${MODE_LABEL[option.mode]}`}
      >
        {steps(option, deadline, option.mode === "drive" ? traffic : null).map((s, i) => (
          <li key={i} className="relative">
            <span
              aria-hidden
              className={`absolute top-1.5 -left-[25px] size-2.5 rounded-full ${s.tone ? "bg-deadline" : i === 0 ? "bg-rain" : "bg-muted-foreground"}`}
            />
            <div className="flex flex-wrap items-baseline gap-x-3">
              <span className={`font-mono text-sm ${s.tone ?? "text-foreground"}`}>{fmtTime(s.at)}</span>
              <span className="text-sm">{s.text}</span>
            </div>
            {s.note && <p className="text-xs text-muted-foreground">{s.note}</p>}
          </li>
        ))}
      </ol>
      {backup && backupOption?.leave_by && (
        <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
          Backup: leave <span className="font-mono">{fmtTime(backup.leave_at)}</span> {MODE_LABEL[backup.backup_mode]},
          typically arrive <span className="font-mono">{fmtTime(backupOption.arrival.p50)}</span>.
        </p>
      )}
    </div>
  )
}
