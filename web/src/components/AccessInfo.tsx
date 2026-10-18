import { Info } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

/** The (i) next to "Access": what the access score is today, honestly, and what a real one would use. */
export function AccessInfo() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="How we score access"
          className="inline-grid size-5 place-items-center rounded-full text-muted-foreground transition-colors hover:text-rain focus-visible:text-rain focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Info className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="flex max-w-72 flex-col gap-1.5 text-left">
        <span className="flex items-center gap-2 font-medium">
          How we score access
          <Badge variant="outline" className="text-[10px]">
            Estimated
          </Badge>
        </span>
        <span>
          0 to 100, higher means an easier journey. Each way of travelling has one fixed rating from a placeholder table
          (step-free access and physical effort); carrying luggage lowers it by a fixed factor.
        </span>
        <span>
          It is not measured yet. A real score would use station step-free data, changes and walking distance.
        </span>
      </TooltipContent>
    </Tooltip>
  )
}
