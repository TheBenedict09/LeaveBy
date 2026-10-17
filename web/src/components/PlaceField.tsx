import { useEffect, useId, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { searchPlaces } from "@/lib/api"
import { PLACES } from "@/lib/places"
import type { Place } from "@/lib/types"

type Status = "idle" | "loading" | "done" | "offline"
type Found = { places: Place[]; fallback: boolean }
type Pos = { left: number; width: number; top?: number; bottom?: number }

const LIST_MAX = 340 // px, about six suggestions plus a note
const GUTTER = 16

const cache = new Map<string, Found>() // per page load, keyed by the lowercased query

/** "Dundee, Scotland, United Kingdom" -> ["Dundee", "Scotland, United Kingdom"] */
function split(label: string): [string, string] {
  const i = label.indexOf(", ")
  return i < 0 ? [label, ""] : [label.slice(0, i), label.slice(i + 2)]
}

/** Inline combobox: type any place, or pick one of the pinned demo stations. */
export function PlaceField({
  label,
  value,
  onChange,
  className,
}: {
  label: string
  value: Place | null
  onChange: (p: Place | null) => void
  className: string
}) {
  const id = useId()
  const [text, setText] = useState(value?.label ?? "")
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [, setLoaded] = useState(0) // bumped when a reply lands in the cache, to re-render
  const [failed, setFailed] = useState<string | null>(null)
  const [pos, setPos] = useState<Pos | null>(null)
  const anchor = useRef<HTMLDivElement>(null)

  // The list lives in a portal on <body>, so no card can clip it. Opens below, or above when there is no room.
  const place = () => {
    const r = anchor.current?.getBoundingClientRect()
    if (!r) return
    const width = Math.min(Math.max(r.width, 288), window.innerWidth - 2 * GUTTER)
    const left = Math.min(Math.max(r.left, GUTTER), window.innerWidth - GUTTER - width)
    const below = window.innerHeight - r.bottom
    setPos(
      below < LIST_MAX && r.top > below
        ? { left, width, bottom: window.innerHeight - r.top + 8 }
        : { left, width, top: r.bottom + 8 },
    )
  }
  const show = () => {
    place()
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    window.addEventListener("scroll", place, true)
    window.addEventListener("resize", place)
    return () => {
      window.removeEventListener("scroll", place, true)
      window.removeEventListener("resize", place)
    }
  })

  const q = text.trim()
  const key = q.toLowerCase()
  const searching = q.length >= 2 && !(value && value.label === text)
  // Everything below is derived from the current query, so a late reply for an older query can never show.
  const found = cache.get(key)
  const status: Status = !searching ? "idle" : found ? "done" : failed === key ? "offline" : "loading"

  useEffect(() => {
    if (!searching || cache.has(key)) return
    const t = setTimeout(async () => {
      try {
        const res = await searchPlaces(q, 6)
        cache.set(key, { places: res.data.places, fallback: res.meta.degraded })
        setLoaded((n) => n + 1)
      } catch {
        setFailed(key)
      }
    }, 250)
    return () => clearTimeout(t)
  }, [q, key, searching])

  // Pinned stations always come along: instantly when the box is empty, and as the fallback after a search.
  const results = found && status === "done" ? found.places : []
  // While a search is in flight only "Searching..." shows, so the stations do not flash up and vanish.
  const items = !searching ? PLACES : status === "loading" ? [] : results.length ? results : PLACES
  const listId = `${id}-list`
  const optId = (i: number) => `${id}-opt-${i}`

  const choose = (p: Place) => {
    const [name] = split(p.label)
    const picked = { ...p, label: name }
    onChange(picked)
    setText(name)
    setOpen(false)
    setActive(-1)
  }

  let note: string | null = null
  if (searching && status === "loading") note = "Searching..."
  else if (searching && status === "offline") note = "Search is offline, pick one of the stations below."
  else if (searching && status === "done" && !results.length) note = "No matches. Try a city or town name."

  return (
    <div ref={anchor} className="relative">
      <input
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? optId(active) : undefined}
        autoComplete="off"
        spellCheck={false}
        className={className}
        value={text}
        placeholder="Type a place"
        onFocus={show}
        onBlur={() => setOpen(false)}
        onChange={(e) => {
          setText(e.target.value)
          show()
          setActive(-1)
          if (value) onChange(null)
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault()
            if (!open) show()
            const step = e.key === "ArrowDown" ? 1 : -1
            setActive((a) => (a + step + items.length) % items.length)
          } else if (e.key === "Enter" && open && active >= 0) {
            e.preventDefault()
            choose(items[active])
          } else if (e.key === "Escape") {
            setOpen(false)
          }
        }}
      />
      <span className="sr-only" aria-live="polite">
        {open ? (note ?? `${items.length} suggestions available`) : ""}
      </span>
      {open &&
        pos &&
        createPortal(
          <ul
            id={listId}
            role="listbox"
            aria-label={`${label} suggestions`}
            style={{ ...pos, maxHeight: LIST_MAX }}
            className="fixed z-50 overflow-y-auto rounded-xl border border-border bg-popover/95 py-1 text-sm shadow-xl shadow-black/40 backdrop-blur"
          >
            {note && <li className="px-3 py-2 text-xs text-muted-foreground">{note}</li>}
            {items.map((p, i) => {
              const [name, sub] = split(p.label)
              const pinned = i >= results.length
              return (
                <li
                  key={`${p.label}-${p.lat}-${p.lon}`}
                  id={optId(i)}
                  role="option"
                  aria-selected={i === active}
                  className={`cursor-pointer px-3 py-2 ${i === active ? "bg-secondary" : "hover:bg-secondary"}`}
                  onMouseDown={(e) => e.preventDefault()} // keep focus so blur does not close before the click lands
                  onClick={() => choose(p)}
                  onMouseEnter={() => setActive(i)}
                >
                  <span className="block font-medium text-foreground">{name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {pinned ? "Demo station" : sub}
                    {!pinned && found?.fallback ? " · offline list" : ""}
                  </span>
                </li>
              )
            })}
          </ul>,
          document.body,
        )}
    </div>
  )
}
