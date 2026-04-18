import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { useScrollReveal } from '../hooks/useScrollReveal'
import CashMascotEmbed from './CashMascotEmbed'

const itemFade = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
}

const containerStagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
}

function DemoShell({ children, className = '' }) {
  return (
    <motion.div
      variants={containerStagger}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: '-10% 0px' }}
      className={`rounded-lg border border-white/8 bg-white/[0.03] p-3 ${className}`}
    >
      {children}
    </motion.div>
  )
}

function MemoryDemo() {
  return (
    <DemoShell>
      <motion.div
        variants={itemFade}
        className="flex items-center gap-2 text-[0.62rem] font-display font-semibold uppercase tracking-[0.14em] text-[#7fa9ff]"
      >
        <motion.span
          className="w-1 h-1 rounded-full bg-[#4f8eff]"
          animate={{ opacity: [1, 0.3, 1], scale: [1, 1.6, 1] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        />
        Memory #4,212
      </motion.div>
      <motion.p
        variants={itemFade}
        className="mt-1.5 text-[0.85rem] text-[#f1f3f9] font-medium"
      >
        &ldquo;just one&rdquo; beer
      </motion.p>
      <motion.p
        variants={itemFade}
        className="mt-0.5 text-[0.68rem] text-[#6b7480]"
      >
        logged Mar 12, 7:14 PM · still counting
      </motion.p>
    </DemoShell>
  )
}

function CalendarDemo() {
  const rows = [
    { time: '09:00', title: 'Standup', tag: 'Work', color: '#4f8eff' },
    { time: '11:30', title: '1:1 w/ Alex', tag: 'Personal', color: '#10b981' },
    { time: '14:00', title: 'Dentist', tag: 'Family', color: '#c4b5fd' },
  ]
  return (
    <DemoShell className="space-y-1.5">
      {rows.map((r, i) => (
        <motion.div
          key={r.time}
          variants={itemFade}
          className="flex items-center gap-2 text-[0.75rem]"
        >
          <span className="font-mono text-[0.65rem] text-[#6b7480] w-10 shrink-0">
            {r.time}
          </span>
          <motion.span
            className="w-[3px] h-3.5 rounded-sm shrink-0"
            style={{ background: r.color }}
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{
              duration: 2.4,
              repeat: Infinity,
              delay: i * 0.3,
              ease: 'easeInOut',
            }}
          />
          <span className="text-[#f1f3f9] font-medium flex-1 truncate">
            {r.title}
          </span>
          <span className="text-[0.6rem] text-[#6b7480] uppercase tracking-wider shrink-0">
            {r.tag}
          </span>
        </motion.div>
      ))}
    </DemoShell>
  )
}

function ScheduleDemo() {
  const CYCLE = 4.5
  return (
    <DemoShell>
      <motion.div
        variants={itemFade}
        className="flex items-center gap-1.5 text-[0.62rem] font-display font-semibold uppercase tracking-[0.14em] text-[#7fa9ff]"
      >
        <motion.span
          className="material-symbols-outlined text-[13px]"
          style={{
            fontVariationSettings:
              "'FILL' 1, 'wght' 600, 'GRAD' 0, 'opsz' 20",
          }}
          animate={{ rotate: [0, -12, 12, 0], scale: [1, 1.15, 1.15, 1] }}
          transition={{
            duration: CYCLE,
            repeat: Infinity,
            times: [0, 0.22, 0.28, 0.42],
          }}
          aria-hidden
        >
          bolt
        </motion.span>
        Conflict resolved
      </motion.div>
      <motion.p
        variants={itemFade}
        className="mt-1.5 text-[0.85rem] text-[#f1f3f9] font-medium"
      >
        Gym moved{' '}
        <span className="relative inline-block">
          <span className="text-[#6b7480]">8 PM</span>
          <motion.span
            className="absolute left-0 right-0 top-1/2 h-[1.5px] bg-[#6b7480] origin-left -translate-y-1/2"
            animate={{ scaleX: [0, 0, 1, 1, 0] }}
            transition={{
              duration: CYCLE,
              repeat: Infinity,
              times: [0, 0.22, 0.38, 0.82, 0.95],
              ease: 'easeInOut',
            }}
          />
        </span>
        <motion.span
          className="text-[#7fa9ff] inline-block font-semibold"
          animate={{ opacity: [0, 0, 1, 1, 0], x: [-10, -10, 0, 0, -4] }}
          transition={{
            duration: CYCLE,
            repeat: Infinity,
            times: [0, 0.4, 0.52, 0.82, 0.95],
            ease: 'easeOut',
          }}
        >
          {' → 6 AM'}
        </motion.span>
      </motion.p>
      <motion.p
        variants={itemFade}
        className="mt-0.5 text-[0.68rem] text-[#6b7480]"
      >
        you said you&apos;d go. receipts attached.
      </motion.p>
    </DemoShell>
  )
}

function HabitsDemo() {
  const CYCLE = 5.5
  const BARS = 14
  const [streak, setStreak] = useState(0)

  useEffect(() => {
    const start = Date.now()
    const interval = setInterval(() => {
      const elapsed = (Date.now() - start) % (CYCLE * 1000)
      const t = elapsed / (CYCLE * 1000)
      let next = 0
      if (t < 0.06) next = 0
      else if (t <= 0.56)
        next = Math.min(BARS, Math.floor((t - 0.06) * BARS * 2) + 1)
      else if (t < 0.95) next = BARS
      else next = 0
      setStreak((prev) => (prev !== next ? next : prev))
    }, 90)
    return () => clearInterval(interval)
  }, [])

  return (
    <DemoShell>
      <motion.div
        variants={itemFade}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-1.5 text-[0.78rem] font-medium text-[#f1f3f9]">
          <motion.span
            aria-hidden
            animate={{ rotate: [0, -10, 10, -5, 0] }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              repeatDelay: 3,
              ease: 'easeInOut',
            }}
          >
            🎸
          </motion.span>
          Learn guitar
        </div>
        <motion.span
          className="text-[0.6rem] font-semibold uppercase tracking-wider"
          animate={{
            color: ['#a8b0c0', '#a8b0c0', '#7fa9ff', '#7fa9ff', '#a8b0c0'],
            scale: [1, 1, 1.12, 1.12, 1],
          }}
          transition={{
            duration: CYCLE,
            repeat: Infinity,
            times: [0, 0.55, 0.62, 0.82, 0.95],
          }}
        >
          Day 47
        </motion.span>
      </motion.div>
      <motion.div variants={itemFade} className="mt-2 flex gap-[3px]">
        {Array.from({ length: BARS }).map((_, i) => {
          const fillAt = 0.06 + (i / BARS) * 0.5
          return (
            <motion.span
              key={i}
              className="flex-1 h-1.5 rounded-full"
              initial={{ backgroundColor: 'rgba(255,255,255,0.10)' }}
              animate={{
                backgroundColor: [
                  'rgba(255,255,255,0.10)',
                  'rgba(255,255,255,0.10)',
                  '#4f8eff',
                  '#4f8eff',
                  'rgba(255,255,255,0.10)',
                ],
              }}
              transition={{
                duration: CYCLE,
                repeat: Infinity,
                times: [0, fillAt, fillAt + 0.02, 0.82, 0.95],
                ease: 'linear',
              }}
            />
          )
        })}
      </motion.div>
      <motion.p
        variants={itemFade}
        className="mt-1.5 text-[0.65rem] text-[#6b7480]"
      >
        streak:{' '}
        <span className="tabular-nums font-semibold text-[#7fa9ff]">
          {streak}
        </span>
        /{BARS} · case: still zipped
      </motion.p>
    </DemoShell>
  )
}

function TaskRow({ it, delayFrac }) {
  const CYCLE = 6
  return (
    <motion.div
      variants={itemFade}
      className="flex items-center gap-2 text-[0.75rem]"
    >
      <motion.span
        className="relative w-3.5 h-3.5 rounded-[4px] border shrink-0 flex items-center justify-center overflow-hidden"
        initial={{
          backgroundColor: 'rgba(0,0,0,0)',
          borderColor: 'rgba(255,255,255,0.32)',
        }}
        animate={{
          backgroundColor: [
            'rgba(0,0,0,0)',
            'rgba(0,0,0,0)',
            '#4f8eff',
            '#4f8eff',
            'rgba(0,0,0,0)',
            'rgba(0,0,0,0)',
          ],
          borderColor: [
            'rgba(255,255,255,0.32)',
            'rgba(255,255,255,0.32)',
            '#4f8eff',
            '#4f8eff',
            'rgba(255,255,255,0.32)',
            'rgba(255,255,255,0.32)',
          ],
        }}
        transition={{
          duration: CYCLE,
          repeat: Infinity,
          times: [
            0,
            0.12 + delayFrac,
            0.2 + delayFrac,
            0.42 + delayFrac,
            0.5 + delayFrac,
            1,
          ],
          ease: 'easeOut',
        }}
      >
        <svg
          viewBox="0 0 12 12"
          className="w-[10px] h-[10px]"
          fill="none"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <motion.path
            d="M2.5 6.3 L5 8.4 L9.4 3.8"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{
              pathLength: [0, 0, 1, 1, 1, 1],
              opacity: [0, 0, 1, 1, 0, 0],
            }}
            transition={{
              duration: CYCLE,
              repeat: Infinity,
              times: [
                0,
                0.18 + delayFrac,
                0.28 + delayFrac,
                0.42 + delayFrac,
                0.5 + delayFrac,
                1,
              ],
              ease: 'easeOut',
            }}
          />
        </svg>
      </motion.span>
      <span className="text-[#f1f3f9] flex-1 truncate relative">
        {it.text}
        <motion.span
          className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-[1px] bg-[#6b7480] origin-left"
          animate={{ scaleX: [0, 0, 1, 1, 0, 0] }}
          transition={{
            duration: CYCLE,
            repeat: Infinity,
            times: [
              0,
              0.22 + delayFrac,
              0.3 + delayFrac,
              0.42 + delayFrac,
              0.5 + delayFrac,
              1,
            ],
            ease: 'easeOut',
          }}
        />
      </span>
      <motion.span
        className="text-[0.6rem] font-semibold tabular-nums shrink-0"
        animate={{
          color: ['#7fa9ff', '#7fa9ff', '#6b7480', '#6b7480', '#7fa9ff'],
        }}
        transition={{
          duration: CYCLE,
          repeat: Infinity,
          times: [
            0,
            0.22 + delayFrac,
            0.32 + delayFrac,
            0.5 + delayFrac,
            0.58 + delayFrac,
          ],
        }}
      >
        {it.age}
      </motion.span>
    </motion.div>
  )
}

function TasksDemo() {
  const items = [
    { text: '"Quick" email to Jordan', age: '4d', delayFrac: 0 },
    { text: 'Refactor auth flow', age: '11d', delayFrac: 0.07 },
    { text: 'Call mom', age: '19d', delayFrac: 0.14 },
  ]
  return (
    <DemoShell className="space-y-1.5">
      {items.map((it) => (
        <TaskRow key={it.text} it={it} delayFrac={it.delayFrac} />
      ))}
    </DemoShell>
  )
}

function TypingDots() {
  return (
    <div className="inline-flex items-center gap-[3px]">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-1 h-1 rounded-full bg-[#a8b0c0]"
          animate={{ y: [0, -3, 0], opacity: [0.4, 1, 0.4] }}
          transition={{
            duration: 0.9,
            repeat: Infinity,
            delay: i * 0.15,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  )
}

function ChatDemo() {
  const [phase, setPhase] = useState(0)

  useEffect(() => {
    let active = true
    let timeout
    const run = () => {
      if (!active) return
      setPhase(0)
      timeout = setTimeout(() => {
        if (!active) return
        setPhase(1)
        timeout = setTimeout(() => {
          if (!active) return
          setPhase(2)
          timeout = setTimeout(() => {
            if (!active) return
            setPhase(3)
            timeout = setTimeout(run, 600)
          }, 3200)
        }, 1200)
      }, 500)
    }
    run()
    return () => {
      active = false
      clearTimeout(timeout)
    }
  }, [])

  return (
    <DemoShell className="space-y-1.5">
      <motion.div variants={itemFade} className="flex justify-end">
        <div className="max-w-[80%] rounded-[14px] rounded-br-[4px] bg-[#4f8eff] text-white text-[0.78rem] px-2.5 py-1.5 leading-snug">
          book lunch w/ Ben thu
        </div>
      </motion.div>
      <motion.div variants={itemFade} className="relative">
        <div
          aria-hidden
          className="invisible max-w-[85%] rounded-[14px] rounded-bl-[4px] border border-transparent text-[0.78rem] px-2.5 py-1.5 leading-snug"
        >
          done. Thu 1 PM. judged your calendar on the way.{' '}
          <span className="inline-block w-4 h-3.5 align-middle" />
        </div>
        <AnimatePresence mode="wait">
          {phase === 1 && (
            <motion.div
              key="typing"
              initial={{ opacity: 0, y: 4, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.15 } }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="absolute top-0 left-0 rounded-[14px] rounded-bl-[4px] bg-white/10 border border-white/12 px-2.5 py-1.5 backdrop-blur"
            >
              <TypingDots />
            </motion.div>
          )}
          {phase >= 2 && (
            <motion.div
              key="message"
              initial={{ opacity: 0, y: 8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.2 } }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="absolute top-0 left-0 max-w-[85%] rounded-[14px] rounded-bl-[4px] bg-white/10 border border-white/12 text-[#f1f3f9] text-[0.78rem] px-2.5 py-1.5 leading-snug backdrop-blur"
            >
              done. Thu 1 PM. judged your calendar on the way.{' '}
              <CashMascotEmbed className="inline-block align-middle w-4 h-3.5" />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </DemoShell>
  )
}

const features = [
  {
    icon: 'psychology',
    title: 'Remembers everything',
    desc: "Tell her once. She files it forever. Expect to be reminded on day three of your 'new habit.'",
    Demo: MemoryDemo,
  },
  {
    icon: 'bolt',
    title: 'Smart scheduling',
    desc: 'Auto-resolves conflicts. Rebooks when meetings collide. Guilt-trips you either way.',
    Demo: ScheduleDemo,
  },
  {
    icon: 'calendar_month',
    title: 'Calendar merge',
    desc: 'Google + Outlook + whatever else you juggle — stitched into one screen. With opinions.',
    Demo: CalendarDemo,
  },
  {
    icon: 'interests',
    title: 'Habits & hobbies',
    desc: "Tracks the streaks you break and the hobbies you swore you'd finally start. Gently judgy.",
    Demo: HabitsDemo,
  },
  {
    icon: 'task_alt',
    title: 'Task tracking',
    desc: "Unfinished tasks don't die. They follow you. No delete button, only accountability.",
    Demo: TasksDemo,
  },
  {
    icon: 'chat_bubble',
    title: 'Just ask',
    desc: 'Talk to her like a friend. She understands context, remembers everything, and brings the sass.',
    Demo: ChatDemo,
  },
]

export default function Features() {
  const { ref, isInView } = useScrollReveal()
  const [activeIndex, setActiveIndex] = useState(0)
  const cardRefs = useRef([])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        let best = { ratio: 0, idx: activeIndex }
        entries.forEach((e) => {
          if (e.isIntersecting && e.intersectionRatio > best.ratio) {
            best = {
              ratio: e.intersectionRatio,
              idx: Number(e.target.dataset.idx),
            }
          }
        })
        if (best.ratio > 0) setActiveIndex(best.idx)
      },
      {
        rootMargin: '-35% 0px -35% 0px',
        threshold: [0, 0.25, 0.5, 0.75, 1],
      },
    )
    cardRefs.current.forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [])

  return (
    <section
      id="features"
      ref={ref}
      className="relative py-20 md:py-28 text-[#f1f3f9]"
    >
      <div className="max-w-[1100px] mx-auto px-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16">
          <aside className="md:order-1 md:sticky md:top-24 md:self-start">
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5 }}
            >
              <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#7fa9ff] uppercase tracking-[0.22em] mb-4 inline-flex items-center gap-2">
                <span className="text-[#7fa9ff]" aria-hidden>
                  ⟩
                </span>
                Every pet ships with
              </p>
              <h2 className="font-display font-bold text-3xl sm:text-4xl md:text-5xl tracking-tight leading-[1.05]">
                Standard kitty{' '}
                <span className="hero-title-gradient">toolkit.</span>
              </h2>
              <p className="mt-4 text-[#a8b0c0] text-sm sm:text-base max-w-sm">
                Cash trained her whole litter. Scroll through what your pet
                can do — she&apos;ll wait.
              </p>

              <ul className="mt-8 space-y-2.5 hidden md:block">
                {features.map((f, i) => {
                  const active = i === activeIndex
                  return (
                    <li key={f.title} className="flex items-center gap-3">
                      <span
                        className="relative w-5 h-[2px] rounded-full overflow-hidden"
                        style={{ background: 'rgba(255,255,255,0.14)' }}
                      >
                        <motion.span
                          className="absolute inset-y-0 left-0 rounded-full bg-[#4f8eff]"
                          initial={false}
                          animate={{ width: active ? '100%' : '0%' }}
                          transition={{ duration: 0.4, ease: 'easeOut' }}
                        />
                      </span>
                      <span className="font-mono text-[0.62rem] text-[#7fa9ff]/55 w-5 tabular-nums">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <motion.span
                        className="text-sm"
                        animate={{
                          color: active ? '#f1f3f9' : '#6b7480',
                          fontWeight: active ? 600 : 500,
                        }}
                        transition={{ duration: 0.3 }}
                      >
                        {f.title}
                      </motion.span>
                    </li>
                  )
                })}
              </ul>
            </motion.div>
          </aside>

          <div className="md:order-2 space-y-5 md:space-y-6">
            {features.map((f, i) => {
              const active = i === activeIndex
              return (
                <motion.article
                  key={f.title}
                  ref={(el) => (cardRefs.current[i] = el)}
                  data-idx={i}
                  initial={{ opacity: 0, y: 28 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-10% 0px' }}
                  transition={{ duration: 0.55, ease: [0.25, 0.4, 0.25, 1] }}
                  whileHover={{ y: -4 }}
                  animate={{
                    borderColor: active
                      ? 'rgba(79,142,255,0.55)'
                      : 'rgba(255,255,255,0.10)',
                    boxShadow: active
                      ? '0 24px 60px -18px rgba(79,142,255,0.45)'
                      : '0 8px 24px rgba(0,0,0,0.30)',
                    scale: active ? 1.015 : 1,
                  }}
                  className="group relative rounded-xl border bg-white/[0.04] backdrop-blur-md p-5"
                >
                  <motion.span
                    aria-hidden
                    className="absolute top-4 right-5 font-display font-semibold text-[0.68rem] tracking-[0.15em]"
                    animate={{
                      color: active
                        ? 'rgba(127,169,255,1)'
                        : 'rgba(255,255,255,0.30)',
                    }}
                    transition={{ duration: 0.3 }}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </motion.span>

                  <div className="flex items-center gap-2.5 mb-4">
                    <motion.span
                      className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#4f8eff]/12 border border-[#4f8eff]/25 text-[#7fa9ff]"
                      aria-hidden
                      animate={{ rotate: active ? [0, -6, 6, 0] : 0 }}
                      transition={{ duration: 0.6 }}
                    >
                      <span
                        className="material-symbols-outlined text-[18px]"
                        style={{
                          fontVariationSettings:
                            "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 24",
                        }}
                      >
                        {f.icon}
                      </span>
                    </motion.span>
                    <h3 className="font-sans font-bold text-[0.98rem] tracking-tight text-[#f1f3f9]">
                      {f.title}
                    </h3>
                  </div>

                  <f.Demo />

                  <p className="mt-4 text-[0.85rem] leading-relaxed text-[#a8b0c0]">
                    {f.desc}
                  </p>
                </motion.article>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
