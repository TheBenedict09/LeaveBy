// Regression check: result cards must never duplicate after repeated searches or calendar clicks.
// Needs the API (make dev) and web dev server (npm run dev) running, plus Chrome. Run:
//   node scripts/check_no_duplicate_cards.mjs   (CHROME=/path/to/chrome to override)
import { spawn } from "node:child_process"
import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const URL = process.env.APP_URL || "http://localhost:5173/"
const PORT = 9333
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "lb-chrome-"))}`,
  "--use-angle=swiftshader",
  "--enable-unsafe-swiftshader",
  "about:blank",
])
let ok = false
try {
  await wait(2000)
  const tabs = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
  const ws = new WebSocket(tabs.find((t) => t.type === "page").webSocketDebuggerUrl)
  await new Promise((r) => (ws.onopen = r))
  let id = 0
  const pending = new Map()
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data)
    if (d.id && pending.has(d.id)) (pending.get(d.id)(d), pending.delete(d.id))
  }
  const send = (method, params = {}) =>
    new Promise((r) => {
      const i = ++id
      pending.set(i, r)
      ws.send(JSON.stringify({ id: i, method, params }))
    })
  const run = async (e) =>
    (await send("Runtime.evaluate", { expression: e, awaitPromise: true, returnByValue: true })).result?.result?.value
  await send("Page.navigate", { url: URL })
  await wait(4000)
  const counts = JSON.parse(
    await run(`(async () => {
      const w = (ms) => new Promise((r) => setTimeout(r, ms))
      const titles = ["Your route", "Your priorities", "What if I leave later?", "All options", "Backup plan"]
      const count = () => Object.fromEntries(titles.map((t) => [t, [...document.querySelectorAll('[data-slot=card-title]')].filter((e) => e.textContent.trim().startsWith(t)).length]))
      const btn = (text) => [...document.querySelectorAll("button")].find((b) => b.textContent.includes(text))
      btn("Glasgow → Edinburgh by car").click(); await w(100)
      ;[...document.querySelectorAll("[data-slot=toggle-group-item]")].find((b) => b.textContent === "In 2 days").click(); await w(100)
      const submit = () => document.querySelector("button[type=submit]")
      const steps = {}
      submit().click(); await w(5000); steps.first = count()
      for (let i = 0; i < 4; i++) { submit().click(); await w(150) }
      await w(5000); steps.repeatedSearch = count()
      URL.createObjectURL = () => "blob:x"; HTMLAnchorElement.prototype.click = () => {} // no real downloads
      for (let i = 0; i < 3; i++) { btn("Add to calendar").click(); await w(300) }
      await w(1000); steps.calendarClicks = count()
      const real = window.fetch
      window.fetch = (u, i) => (String(u).includes("calendar.ics") ? Promise.resolve(new Response("", { status: 500 })) : real(u, i))
      btn("Add to calendar").click(); await w(800)
      steps.failedCalendar = count(); steps.banner = document.querySelector("[role=alert]")?.textContent ?? null
      return JSON.stringify(steps)
    })()`),
  )
  console.log(JSON.stringify(counts, null, 1))
  // "Backup plan" only appears when there is a backup, so it may be 0; nothing may ever appear twice
  const cards = ["first", "repeatedSearch", "calendarClicks", "failedCalendar"].flatMap((k) =>
    Object.entries(counts[k]).map(([title, n]) => (title === "Backup plan" ? Math.max(n, 1) : n)),
  )
  ok = cards.every((n) => n === 1) && Boolean(counts.banner)
  ws.close()
} finally {
  chrome.kill()
}
console.log(ok ? "PASS: every result card appears exactly once" : "FAIL: a result card is missing or duplicated")
process.exit(ok ? 0 : 1)
