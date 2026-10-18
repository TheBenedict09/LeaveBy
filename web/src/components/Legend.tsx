import type { ReactNode } from "react"
import { Info } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

export type LegendItem = { swatch: ReactNode; label: string }

/** A row of small swatches with short labels, and the longer explanation in a tooltip. */
export function Legend({ items, detail }: { items: LegendItem[]; detail?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          {it.swatch}
          {it.label}
        </span>
      ))}
      {detail && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label="About this chart"
              className="inline-grid size-5 place-items-center rounded-full hover:text-rain focus-visible:text-rain focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Info className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-72">{detail}</TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export function Dot({ className }: { className: string }) {
  return <span aria-hidden className={`size-2.5 rounded-full ${className}`} />
}

export function Bar({ className }: { className: string }) {
  return <span aria-hidden className={`h-0.5 w-4 rounded-full ${className}`} />
}
