import { useEffect, useRef, useState } from "react"
import maplibregl, { type GeoJSONSource, type LngLatLike } from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import type { Mode, Route, TrainService } from "@/lib/types"

const STYLE = "https://tiles.openfreemap.org/styles/dark"
const RAIN = "#6ea8ff"
const DEADLINE = "#ffc857"

type LatLon = [number, number]
type Lines = { solid: LatLon[]; dotted: LatLon[][]; stations: { name: string; at: LatLon }[] }

/** What to draw for the chosen option. Trains have no track geometry, so the rail leg is a straight, labelled line. */
function linesFor(route: Route, mode: Mode, service: TrainService | null | undefined): Lines {
  if (mode === "train" && service) {
    const a = service.from_coord as LatLon
    const b = service.to_coord as LatLon
    return {
      solid: [a, b],
      dotted: [
        [route.origin as LatLon, a],
        [b, route.destination as LatLon],
      ],
      stations: [
        { name: service.from_station, at: a },
        { name: service.to_station, at: b },
      ],
    }
  }
  if (mode === "drive" && route.car_line) return { solid: route.car_line as LatLon[], dotted: [], stations: [] }
  return { solid: [], dotted: [[route.origin as LatLon, route.destination as LatLon]], stations: [] }
}

const ll = ([lat, lon]: LatLon): [number, number] => [lon, lat]

function lineFeature(points: LatLon[]) {
  return {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "LineString" as const, coordinates: points.map(ll) },
  }
}

function multi(parts: LatLon[][]) {
  return { type: "FeatureCollection" as const, features: parts.filter((p) => p.length > 1).map(lineFeature) }
}

function pin(className: string, label: string): HTMLElement {
  const el = document.createElement("div")
  el.className = className
  el.setAttribute("aria-hidden", "true")
  el.title = label
  return el
}

/** A dark map of the chosen option. Falls back to a schematic SVG if the map tiles cannot load. */
export default function RouteMap({
  route,
  mode,
  service,
  still,
}: {
  route: Route
  mode: Mode
  service?: TrainService | null
  still: boolean
}) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const markers = useRef<maplibregl.Marker[]>([])
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)
  const lines = linesFor(route, mode, service)
  const frame = useRef(0) // the line-drawing animation; kept in a ref so re-renders do not cancel it
  const drawn = useRef("") // what is on the map now, so a rescore that changes nothing does not redraw
  const center = useRef(route.origin as LatLon) // the map is created once per result (the parent keys it)

  useEffect(() => {
    if (!box.current) return
    const m = new maplibregl.Map({
      container: box.current,
      style: STYLE,
      center: ll(center.current),
      zoom: 8,
      attributionControl: false,
      cooperativeGestures: true,
    })
    m.addControl(new maplibregl.AttributionControl({ compact: true })) // the style carries the OpenStreetMap credit
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")
    let loaded = false
    // Only a real failure to load the style (network, blocked host) swaps in the schematic. No timer: a tab in
    // the background pauses rendering, and that must not count as a failure.
    m.on("error", () => {
      if (!loaded) setFailed(true)
    })
    m.on("load", () => {
      loaded = true
      m.addSource("dotted", { type: "geojson", data: multi([]) })
      m.addSource("solid", { type: "geojson", data: multi([]) })
      m.addLayer({
        id: "dotted",
        type: "line",
        source: "dotted",
        paint: { "line-color": RAIN, "line-width": 2, "line-opacity": 0.6, "line-dasharray": [0.5, 2] },
        layout: { "line-cap": "round" },
      })
      m.addLayer({
        id: "solid-glow",
        type: "line",
        source: "solid",
        paint: { "line-color": RAIN, "line-width": 10, "line-opacity": 0.18, "line-blur": 6 },
      })
      m.addLayer({
        id: "solid",
        type: "line",
        source: "solid",
        paint: { "line-color": RAIN, "line-width": 3.5 },
        layout: { "line-cap": "round", "line-join": "round" },
      })
      setReady(true)
    })
    map.current = m
    return () => {
      cancelAnimationFrame(frame.current)
      m.remove()
      map.current = null
    }
  }, [])

  // Draw (and animate in) whenever the chosen option changes.
  useEffect(() => {
    const m = map.current
    const key = JSON.stringify([route.origin, route.destination, lines])
    if (!m || !ready || drawn.current === key) return
    drawn.current = key
    markers.current.forEach((mk) => mk.remove())
    markers.current = []
    const add = (at: LatLon, el: HTMLElement, label?: string, above = false) => {
      // station labels sit above their point, so they never cover the start or destination pin beneath
      const mk = new maplibregl.Marker({
        element: el,
        anchor: above ? "bottom" : "center",
        offset: above ? [0, -8] : [0, 0],
      }).setLngLat(ll(at) as LngLatLike)
      if (label) mk.setPopup(new maplibregl.Popup({ offset: 12, closeButton: false }).setText(label))
      markers.current.push(mk.addTo(m))
      el.tabIndex = -1 // decorative: the map's label already says where the pins are
    }
    add(route.origin as LatLon, pin("lb-pin lb-pin-start", "Start"), "Start")
    add(route.destination as LatLon, pin("lb-pin lb-pin-end", "Destination"), "Destination")
    for (const s of lines.stations) {
      const el = pin("lb-station", s.name)
      el.textContent = s.name
      add(s.at, el, undefined, true)
    }
    ;(m.getSource("dotted") as GeoJSONSource).setData(multi(lines.dotted))
    const all = [route.origin as LatLon, route.destination as LatLon, ...lines.solid]
    const bounds = all.reduce((b, p) => b.extend(ll(p)), new maplibregl.LngLatBounds(ll(all[0]), ll(all[0])))
    m.resize() // the card may have changed size since the map was created
    m.fitBounds(bounds, {
      padding: { top: 48, bottom: 64, left: 72, right: 72 },
      duration: still ? 0 : 800,
      maxZoom: 13,
    })

    const solid = m.getSource("solid") as GeoJSONSource
    if (still || lines.solid.length < 2) {
      solid.setData(multi([lines.solid]))
      return
    }
    // Draw the line in over about 900 ms
    cancelAnimationFrame(frame.current)
    const points = lines.solid
    const start = performance.now()
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / 900)
      solid.setData(multi([points.slice(0, Math.max(2, Math.ceil(k * points.length)))]))
      if (k < 1) frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)
  }, [ready, lines, route, still])

  const label =
    mode === "train" && service
      ? `Map: from your start to ${service.from_station}, train to ${service.to_station}, then to your destination.`
      : mode === "drive"
        ? "Map: the driving route from your start to your destination."
        : "Map: your start and destination."

  if (failed) return <Schematic route={route} lines={lines} label={label} />
  return (
    <div className="relative">
      <div ref={box} role="region" aria-label={label} className="h-72 w-full overflow-hidden rounded-lg sm:h-80" />
      {mode === "train" && service && (
        <p className="mt-2 text-xs text-muted-foreground">
          Rail line shown schematically, not the track. Dotted legs to and from the stations are not routed.
        </p>
      )}
    </div>
  )
}

/** No tiles: the same lines on a plain dark canvas, so the card is never blank. */
function Schematic({ route, lines, label }: { route: Route; lines: Lines; label: string }) {
  const pts = [route.origin, route.destination, ...lines.solid] as LatLon[]
  const lats = pts.map((p) => p[0])
  const lons = pts.map((p) => p[1])
  const [W, H, P] = [600, 280, 30]
  const sx = (lon: number) =>
    P + ((lon - Math.min(...lons)) / (Math.max(...lons) - Math.min(...lons) || 1)) * (W - 2 * P)
  const sy = (lat: number) =>
    H - P - ((lat - Math.min(...lats)) / (Math.max(...lats) - Math.min(...lats) || 1)) * (H - 2 * P)
  const path = (p: LatLon[]) => p.map(([la, lo], i) => `${i ? "L" : "M"}${sx(lo)},${sy(la)}`).join("")
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg bg-secondary/40" role="img" aria-label={label}>
        {lines.dotted.map((d, i) => (
          <path
            key={i}
            d={path(d)}
            fill="none"
            stroke={RAIN}
            strokeOpacity={0.6}
            strokeDasharray="2 6"
            strokeWidth={2}
          />
        ))}
        {lines.solid.length > 1 && <path d={path(lines.solid)} fill="none" stroke={RAIN} strokeWidth={3} />}
        <circle cx={sx(route.origin[1])} cy={sy(route.origin[0])} r={6} fill="none" stroke={RAIN} strokeWidth={3} />
        <circle cx={sx(route.destination[1])} cy={sy(route.destination[0])} r={6} fill={DEADLINE} />
      </svg>
      <p className="mt-2 text-xs text-muted-foreground">Map tiles are unavailable, so this is a schematic view.</p>
    </div>
  )
}
