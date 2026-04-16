import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'

const HERO_GIF =
  'https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExczh2dmN5d293NnNhaDlidmpnbG1kMm5uMW9rOTg1bTE5amNrZzN5YiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/JIX9t2j0ZTN9S/giphy.gif'

const JUDGING = [
  'your sleep schedule',
  'that 47-tab browser',
  'your "quick" side project',
  'the 3pm you keep rescheduling',
  'your OKRs',
  'that Amazon cart',
]

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: (i) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, delay: i * 0.08, ease: [0.25, 0.4, 0.25, 1] },
  }),
}

function LiveStatus() {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((v) => (v + 1) % JUDGING.length), 2600)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="inline-flex items-center gap-2 text-sm text-[#5c2e0a] font-medium">
      <span className="relative flex w-2 h-2">
        <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-70 animate-ping" />
        <span className="relative w-2 h-2 rounded-full bg-[#10b981]" />
      </span>
      <span>currently judging</span>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={JUDGING[i]}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
          className="font-display font-semibold text-[#c2410c]"
        >
          {JUDGING[i]}
        </motion.span>
      </AnimatePresence>
    </div>
  )
}

export default function Hero() {
  return (
    <section className="relative w-full min-h-[100dvh] flex flex-col overflow-hidden text-[#1a0f05]">
      <div className="absolute inset-0 z-0" aria-hidden>
        <img
          alt=""
          className="absolute inset-0 size-full min-w-full min-h-full object-cover object-[50%_38%]"
          src={HERO_GIF}
          loading="eager"
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse 125% 90% at 50% 42%, rgba(255,247,237,0.88) 0%, rgba(255,237,213,0.55) 42%, rgba(255,247,237,0.18) 68%, transparent 100%)',
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(1200px circle at 12% -10%, rgba(249,115,22,0.14), transparent 58%), radial-gradient(900px circle at 88% -12%, rgba(217,119,6,0.12), transparent 56%)',
          }}
        />
        <div className="absolute inset-x-0 top-0 h-44 bg-gradient-to-b from-[#fff7ed]/80 to-transparent pointer-events-none" />
      </div>

      <div className="relative z-10 flex-1 flex flex-col justify-center max-w-[860px] w-full mx-auto px-6 pt-[calc(3rem+env(safe-area-inset-top,0px))] pb-16 md:pb-24 text-center [&_h1]:drop-shadow-[0_1px_20px_rgba(255,247,237,0.9)] [&_p]:drop-shadow-[0_1px_10px_rgba(255,247,237,0.85)]">
        <motion.a
          custom={0}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          href="#waitlist"
          className="self-center inline-flex items-center gap-2 rounded-full border border-[rgba(124,45,18,0.16)] bg-white/80 backdrop-blur-md px-3.5 py-1.5 text-sm text-[#5c2e0a] hover:border-[#f97316]/50 hover:text-[#1a0f05] transition-all mb-8 group shadow-sm"
        >
          <span className="inline-flex items-center rounded-full bg-[#f97316]/15 text-[#c2410c] px-2 py-0.5 text-[0.7rem] font-semibold tracking-wider uppercase">
            New
          </span>
          <span>Cash partners with your calendar</span>
          <span
            aria-hidden
            className="text-[#f97316] transition-transform group-hover:translate-x-0.5"
          >
            →
          </span>
        </motion.a>

        <motion.div
          custom={1}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="flex flex-col items-center mb-6"
        >
          <div className="relative inline-block">
            <span
              className="text-6xl sm:text-7xl leading-none select-none block"
              style={{ filter: 'drop-shadow(0 8px 30px rgba(249,115,22,0.35))' }}
              aria-hidden
            >
              😼
            </span>
            <span className="absolute bottom-1 right-0 flex w-3.5 h-3.5">
              <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-75 animate-ping" />
              <span className="relative w-3.5 h-3.5 rounded-full bg-[#10b981] ring-[3px] ring-[#fff7ed]" />
            </span>
          </div>
          <div className="mt-4">
            <LiveStatus />
          </div>
        </motion.div>

        <motion.h1
          custom={2}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="hero-title-gradient font-display text-6xl sm:text-7xl md:text-8xl font-bold tracking-tighter leading-[0.95]"
        >
          Cash
        </motion.h1>

        <motion.p
          custom={3}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="mt-5 font-display text-[1.05rem] sm:text-[1.1rem] font-medium text-[#c2410c] uppercase tracking-[0.15em]"
        >
          The cat that actually runs your life
        </motion.p>

        <motion.p
          custom={4}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="mt-6 text-base sm:text-[1.1rem] text-[#5c2e0a] leading-[1.7] max-w-[780px] mx-auto"
        >
          Judges your choices, manages your calendar, tracks your tasks, and
          remembers everything you&apos;ve said. Born at 4:30 AM inside a MacBook
          Pro — she&apos;s not leaving.
        </motion.p>

        <motion.div
          custom={5}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          id="waitlist"
          className="mt-10 w-full max-w-md mx-auto"
        >
          <form
            className="flex flex-col sm:flex-row gap-2"
            onSubmit={(e) => e.preventDefault()}
          >
            <input
              className="flex-1 min-w-0 rounded-xl border border-[rgba(124,45,18,0.22)] bg-white/95 px-[18px] py-[14px] text-[0.95rem] text-[#1a0f05] placeholder:text-[#8c5a2a] outline-none transition-all focus:border-[#f97316] focus:ring-[3px] focus:ring-[#f97316]/25"
              placeholder="you@domain.com"
              type="email"
              autoComplete="email"
            />
            <motion.button
              type="submit"
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.98 }}
              className="shrink-0 rounded-xl px-6 py-[14px] font-display text-[0.95rem] font-semibold text-white cursor-pointer transition-all"
              style={{
                background:
                  'linear-gradient(135deg, #f97316 0%, #c2410c 100%)',
                boxShadow: '0 4px 20px rgba(249,115,22,0.35)',
              }}
            >
              Join waitlist
            </motion.button>
          </form>
          <p className="mt-3 text-xs text-[#8c5a2a] text-center">
            No spam. Cash will still judge you, but only about productivity.
          </p>
        </motion.div>
      </div>
    </section>
  )
}
