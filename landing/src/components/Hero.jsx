import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import CashMascotEmbed from './CashMascotEmbed'

const HERO_GIF =
  'https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExczh2dmN5d293NnNhaDlidmpnbG1kMm5uMW9rOTg1bTE5amNrZzN5YiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/JIX9t2j0ZTN9S/giphy.gif'

const JUDGING = [
  "suhail's sleep schedule",
  "suhail's 47 tabs",
  "suhail's \"quick\" side project",
  "suhail's 3pm (moved again)",
  "suhail's OKRs",
  "suhail's amazon cart",
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
    <div className="inline-flex items-center gap-2 text-sm text-[#a8b0c0] font-medium">
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
          className="font-display font-semibold text-[#f1f3f9]"
        >
          {JUDGING[i]}
        </motion.span>
      </AnimatePresence>
    </div>
  )
}

export default function Hero() {
  return (
    <section className="relative w-full min-h-[100dvh] flex flex-col overflow-hidden text-[#f1f3f9]">
      <div className="absolute inset-0 z-0" aria-hidden>
        <img
          alt=""
          className="absolute inset-0 size-full min-w-full min-h-full object-cover object-[50%_38%] opacity-25 mix-blend-screen"
          src={HERO_GIF}
          loading="eager"
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse 130% 90% at 50% 42%, rgba(6,8,15,0.55) 0%, rgba(6,8,15,0.78) 55%, rgba(6,8,15,0.95) 100%)',
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'radial-gradient(900px circle at 18% -10%, rgba(79,142,255,0.18), transparent 55%), radial-gradient(800px circle at 82% -12%, rgba(249,115,22,0.14), transparent 55%)',
          }}
        />
      </div>

      <div className="relative z-10 flex-1 flex flex-col justify-center max-w-[860px] w-full mx-auto px-6 pt-[calc(3rem+env(safe-area-inset-top,0px))] pb-16 md:pb-24 text-center [&_h1]:drop-shadow-[0_2px_30px_rgba(79,142,255,0.35)]">
        <motion.a
          custom={0}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          href="#waitlist"
          className="self-center inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] backdrop-blur-md px-3.5 py-1.5 text-sm text-[#a8b0c0] hover:border-[#4f8eff]/55 hover:text-white transition-all mb-8 group"
        >
          <span className="inline-flex items-center rounded-full bg-[#4f8eff]/18 text-[#7fa9ff] px-2 py-0.5 text-[0.7rem] font-semibold tracking-wider uppercase">
            New
          </span>
          <span>Cash is making introductions</span>
          <span
            aria-hidden
            className="text-[#7fa9ff] transition-transform group-hover:translate-x-0.5"
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
          <CashMascotEmbed
            className="w-40 h-32 sm:w-52 sm:h-40"
            loading="eager"
          />
          <div className="mt-4">
            <LiveStatus />
          </div>
        </motion.div>

        <motion.h1
          custom={2}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="hero-title-gradient font-display text-5xl sm:text-6xl md:text-7xl font-bold tracking-tighter leading-[0.95]"
        >
          Cash
        </motion.h1>

        <motion.p
          custom={3}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="mt-5 font-display text-sm sm:text-base font-medium text-[#7fa9ff] tracking-[0.02em]"
        >
          taken by suhail · making intros
        </motion.p>

        <motion.p
          custom={4}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="mt-6 text-sm sm:text-base text-[#a8b0c0] leading-[1.7] max-w-[780px] mx-auto"
        >
          Cash only works for Suhail — there&apos;s a contract, mostly treats.
          But she has a whole litter of clever little freaks looking for
          humans. Adopt one of her friends. Or design your own weird pet from
          scratch. Either way, she&apos;ll vouch for you.
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
              className="flex-1 min-w-0 rounded-xl border border-white/12 bg-white/[0.05] backdrop-blur-md px-[18px] py-[14px] text-[0.95rem] text-white placeholder:text-white/40 outline-none transition-all focus:border-[#4f8eff] focus:ring-[3px] focus:ring-[#4f8eff]/25"
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
                  'linear-gradient(135deg, #4f8eff 0%, #0050cc 100%)',
                boxShadow:
                  '0 4px 24px rgba(79,142,255,0.45), inset 0 1px 0 rgba(255,255,255,0.18)',
              }}
            >
              Join waitlist
            </motion.button>
          </form>
          <p className="mt-3 text-xs text-[#6b7480] text-center">
            No spam. Your future pet handles the important judgment.
          </p>
        </motion.div>
      </div>
    </section>
  )
}
