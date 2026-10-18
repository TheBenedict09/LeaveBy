import { useEffect, useRef } from "react"
import { useReducedMotion } from "motion/react"

export type Sky = {
  rainMmH: number // forecast median at departure
  rainShare: number // share of forecasts with rain, 0 to 1 (more forecasts wet = more cloud)
  gustMph: number
  tempC: number | null
  visibilityM: number | null
  hour: number // local hour of departure, for day or night
}

type Drop = { x: number; y: number; v: number; len: number }
type Streak = { x: number; y: number; v: number; len: number }
type Cloud = { x: number; y: number; r: number; v: number }

const RAIN = "110, 168, 255"

/** What to draw, straight from the forecast numbers. Nothing here is invented: no rain means no drops. */
function plan(s: Sky) {
  const snow = s.tempC !== null && s.tempC <= 1 && s.rainMmH >= 0.2
  return {
    drops: s.rainMmH >= 0.1 ? Math.min(180, Math.round(20 + s.rainMmH * 45)) : 0,
    snow,
    slant: Math.min(0.6, Math.max(0, (s.gustMph - 8) / 60)), // rain leans with the wind
    streaks: Math.min(36, Math.max(0, Math.round((s.gustMph - 15) * 1.5))),
    clouds: Math.round(1 + s.rainShare * 5),
    haze: s.visibilityM !== null && s.visibilityM < 4000 ? Math.min(0.55, (4000 - s.visibilityM) / 6000) : 0,
    night: s.hour < 7 || s.hour >= 19,
  }
}

/** An animated sky for the trip's departure hour (canvas, no dependencies). Still frame under reduced motion. */
export function WeatherScene({ sky, className = "" }: { sky: Sky; className?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const still = useReducedMotion() ?? false

  useEffect(() => {
    const c = canvas.current
    const ctx = c?.getContext("2d")
    if (!c || !ctx) return
    const p = plan(sky)
    let w = 0
    let h = 0
    let drops: Drop[] = []
    let streaks: Streak[] = []
    let clouds: Cloud[] = []
    const rnd = (a: number, b: number) => a + Math.random() * (b - a)

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = c.clientWidth
      h = c.clientHeight
      c.width = Math.round(w * dpr)
      c.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      drops = Array.from({ length: p.drops }, () => ({ x: rnd(-40, w), y: rnd(0, h), v: rnd(4, 8), len: rnd(7, 14) }))
      streaks = Array.from({ length: p.streaks }, () => ({
        x: rnd(0, w),
        y: rnd(0, h * 0.8),
        v: rnd(3, 6),
        len: rnd(30, 70),
      }))
      clouds = Array.from({ length: p.clouds }, (_, i) => ({
        x: rnd(0, w),
        y: rnd(10, h * 0.45),
        r: rnd(26, 46) + i * 2,
        v: rnd(0.05, 0.18) + p.slant * 0.4,
      }))
    }

    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      // the light: sun glow by day, a moon and stars by night, both dimmed when most forecasts are wet
      const light = 1 - sky.rainShare * 0.8
      if (p.night) {
        ctx.fillStyle = `rgba(230, 234, 242, ${0.5 * light})`
        for (let i = 0; i < 24; i++) ctx.fillRect((i * 97) % w, (i * 53) % (h * 0.6), 1.2, 1.2)
        ctx.beginPath()
        ctx.arc(w * 0.82, h * 0.28, 11, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(230, 234, 242, ${0.75 * light})`
        ctx.fill()
      } else {
        const g = ctx.createRadialGradient(w * 0.82, h * 0.25, 4, w * 0.82, h * 0.25, h * 0.9)
        g.addColorStop(0, `rgba(255, 200, 87, ${0.55 * light})`)
        g.addColorStop(1, "rgba(255, 200, 87, 0)")
        ctx.fillStyle = g
        ctx.fillRect(0, 0, w, h)
      }
      for (const cl of clouds) {
        ctx.fillStyle = `rgba(154, 166, 189, ${0.1 + sky.rainShare * 0.14})`
        for (const [dx, dy, k] of [
          [0, 0, 1],
          [cl.r * 0.8, 6, 0.75],
          [-cl.r * 0.75, 8, 0.7],
        ]) {
          ctx.beginPath()
          ctx.arc(cl.x + dx, cl.y + dy, cl.r * k, 0, Math.PI * 2)
          ctx.fill()
        }
      }
      ctx.strokeStyle = `rgba(${RAIN}, 0.55)`
      ctx.fillStyle = "rgba(230, 234, 242, 0.85)"
      ctx.lineWidth = 1.2
      for (const d of drops) {
        if (p.snow) {
          ctx.beginPath()
          ctx.arc(d.x, d.y, 1.6, 0, Math.PI * 2)
          ctx.fill()
        } else {
          ctx.beginPath()
          ctx.moveTo(d.x, d.y)
          ctx.lineTo(d.x + d.len * p.slant, d.y + d.len)
          ctx.stroke()
        }
      }
      ctx.strokeStyle = "rgba(230, 234, 242, 0.18)"
      for (const s of streaks) {
        ctx.beginPath()
        ctx.moveTo(s.x, s.y)
        ctx.lineTo(s.x + s.len, s.y + 2)
        ctx.stroke()
      }
      if (p.haze) {
        const g = ctx.createLinearGradient(0, h, 0, 0)
        g.addColorStop(0, `rgba(154, 166, 189, ${p.haze})`)
        g.addColorStop(1, `rgba(154, 166, 189, ${p.haze * 0.3})`)
        ctx.fillStyle = g
        ctx.fillRect(0, 0, w, h)
      }
    }

    const step = () => {
      const fall = p.snow ? 0.25 : 1
      for (const d of drops) {
        d.y += d.v * fall
        d.x += d.v * fall * p.slant + (p.snow ? Math.sin(d.y / 12) * 0.3 : 0)
        if (d.y > h) {
          d.y = -d.len
          d.x = rnd(-40, w)
        }
      }
      for (const s of streaks) {
        s.x += s.v
        if (s.x > w) {
          s.x = -s.len
          s.y = rnd(0, h * 0.8)
        }
      }
      for (const cl of clouds) {
        cl.x += cl.v
        if (cl.x - cl.r * 2 > w) cl.x = -cl.r * 2
      }
    }

    size()
    draw()
    if (still) return
    let frame = 0
    let visible = true
    const loop = () => {
      step()
      draw()
      frame = requestAnimationFrame(loop)
    }
    const run = () => {
      cancelAnimationFrame(frame)
      if (visible && !document.hidden) frame = requestAnimationFrame(loop)
    }
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting // no work while the card is off screen
      run()
    })
    const ro = new ResizeObserver(() => {
      size()
      draw()
    })
    io.observe(c)
    ro.observe(c)
    document.addEventListener("visibilitychange", run)
    run()
    return () => {
      cancelAnimationFrame(frame)
      io.disconnect()
      ro.disconnect()
      document.removeEventListener("visibilitychange", run)
    }
  }, [sky, still])

  return <canvas ref={canvas} aria-hidden className={`block h-full w-full ${className}`} />
}
