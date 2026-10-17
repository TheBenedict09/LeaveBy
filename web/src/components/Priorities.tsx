import { RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { DEFAULT_WEIGHTS, percentOf } from "@/lib/priorities"
import type { Weights } from "@/lib/types"

const ROWS: { key: keyof Weights; label: string; hint: string }[] = [
  { key: "time", label: "Time", hint: "leave as late as possible" },
  { key: "cost", label: "Cost", hint: "spend less" },
  { key: "carbon", label: "Carbon", hint: "emit less CO2e" },
  { key: "accessibility", label: "Access", hint: "an easier journey" },
]

/** Four priority sliders. They only re-rank options that already meet the confidence level. */
export function Priorities({ value, onChange }: { value: Weights; onChange: (w: Weights) => void }) {
  const share = percentOf(value)
  const isDefault = ROWS.every(({ key }) => value[key] === DEFAULT_WEIGHTS[key])
  const allZero = ROWS.every(({ key }) => value[key] === 0)
  return (
    <div className="flex flex-col gap-4">
      {ROWS.map(({ key, label, hint }) => (
        <div key={key} className="grid grid-cols-[5rem_1fr_3rem] items-center gap-3">
          <span className="text-sm">
            {label}
            <span className="block text-xs text-muted-foreground">{hint}</span>
          </span>
          <Slider
            value={[value[key]]}
            onValueChange={([v]) => onChange({ ...value, [key]: v })}
            min={0}
            max={100}
            step={5}
            aria-label={`${label} priority`}
            aria-valuetext={`${label}: ${share[key]}% of the decision`}
          />
          <span className="text-right font-mono text-sm text-rain">{share[key]}%</span>
        </div>
      ))}
      <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>{allZero ? "Move at least one slider above 0." : "Only options you can rely on are ranked."}</span>
        <Button variant="ghost" size="sm" disabled={isDefault} onClick={() => onChange(DEFAULT_WEIGHTS)}>
          <RotateCcw />
          Reset
        </Button>
      </div>
    </div>
  )
}
