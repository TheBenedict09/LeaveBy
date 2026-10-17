import { useEffect, useState } from "react"
import { CloudRain } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"

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

  useEffect(() => {
    fetch("/healthz")
      .then((r) => setApi(r.ok ? "up" : "down"))
      .catch(() => setApi("down"))
  }, [])

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
            <CardHeader>
              <CardDescription>Your verdict</CardDescription>
              <CardTitle className="font-mono text-5xl font-semibold tracking-tight text-muted-foreground">
                --:--
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Tell LeaveBy where you are going and when you must arrive. It will say exactly when to leave, and how sure
              it is.
            </CardContent>
          </Card>

          <Card className="border-dashed">
            <CardContent className="flex h-72 items-center justify-center text-sm text-muted-foreground">
              The raincloud goes here
            </CardContent>
          </Card>
        </section>

        <aside className="flex flex-col gap-6" aria-label="Controls">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">How sure do you want to be?</CardTitle>
              <CardDescription>Higher means leaving earlier.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="font-mono text-3xl text-rain">{confidence[0]}%</div>
              <Slider
                value={confidence}
                onValueChange={setConfidence}
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