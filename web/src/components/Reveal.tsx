import { useEffect, useRef, useState, type ReactNode } from "react"
import { animate, motion, useReducedMotion } from "motion/react"

/** Fades and lifts its children in once, after `order` steps of a short stagger. Remount (new key) to replay. */
export function Reveal({ order, children }: { order: number; children: ReactNode }) {
  const still = useReducedMotion() ?? false
  return (
    <motion.div
      initial={still ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.12 + order * 0.08, duration: 0.4, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  )
}

/** "07:33" with each digit rolling into place: up from 0 on the first render, then to each new value. */
export function RollingTime({ text }: { text: string }) {
  const still = useReducedMotion() ?? false
  return (
    <span className="inline-flex">
      <span className="sr-only">{text}</span>
      {[...text].map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={i} aria-hidden className="relative inline-block h-[1em] w-[0.62em] overflow-hidden leading-none">
            <motion.span
              className="absolute inset-x-0 top-0 flex flex-col"
              initial={still ? false : { y: "0em" }}
              animate={{ y: `${-Number(ch)}em` }}
              transition={{ duration: still ? 0 : 0.7, delay: still ? 0 : 0.15 + i * 0.07, ease: [0.2, 0.8, 0.2, 1] }}
            >
              {"0123456789".split("").map((d) => (
                <span key={d} className="h-[1em] text-center leading-none">
                  {d}
                </span>
              ))}
            </motion.span>
          </span>
        ) : (
          <span key={i} aria-hidden className="leading-none">
            {ch}
          </span>
        ),
      )}
    </span>
  )
}

/** A number that counts up from 0 when it first appears and tweens to new values after that. */
export function Ticker({ value, format }: { value: number; format: (v: number) => string }) {
  const still = useReducedMotion() ?? false
  const [shown, setShown] = useState(still ? value : 0)
  const from = useRef(still ? value : 0)
  useEffect(() => {
    if (still) {
      from.current = value
      return
    }
    const controls = animate(from.current, value, {
      duration: 0.8,
      ease: "easeOut",
      onUpdate: (v) => {
        from.current = v // an interrupted tween continues from where it is
        setShown(v)
      },
    })
    return () => controls.stop()
  }, [value, still])
  return <span className="tabular-nums">{format(still ? value : shown)}</span>
}
