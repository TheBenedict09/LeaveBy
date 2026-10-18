import { useState } from "react"
import { CalendarPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { Mode, RecommendationRequest, Weights } from "@/lib/types"

type CalendarBody = { mode: Mode; confidence: number; weights: Weights; original: RecommendationRequest }

/** Downloads the .ics for the recommended departure: an event from leave-by to the deadline, with a 10 min alarm. */
export function CalendarButton({
  id,
  body,
  onError,
}: {
  id: string
  body: CalendarBody // the current settings and the original search, so any server can make the event
  onError: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)

  async function download() {
    setBusy(true)
    try {
      const res = await fetch(`/v1/recommendations/${encodeURIComponent(id)}/calendar.ics`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      })
      if (res.status === 404) return onError("This result has expired. Search again to add it to your calendar.")
      if (!res.ok) return onError(`Could not make the calendar file (${res.status}).`)
      const url = URL.createObjectURL(await res.blob())
      const a = Object.assign(document.createElement("a"), { href: url, download: "leaveby.ics" })
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      onError("Can't reach the LeaveBy API. Is it running?")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button type="button" variant="outline" size="sm" className="self-start" onClick={download} disabled={busy}>
      <CalendarPlus />
      {busy ? "Preparing..." : "Add to calendar"}
    </Button>
  )
}
