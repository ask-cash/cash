import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const features = [
  {
    icon: 'psychology',
    title: 'Remembers everything',
    cashQuote: "You said 'just one.' Four beers ago.",
    desc: "Tell her once. She files it forever. Expect to be reminded on day three of your 'new habit.'",
  },
  {
    icon: 'calendar_month',
    title: 'Calendar merge',
    cashQuote: "3 calendars. One view. You're welcome.",
    desc: 'Google + Outlook + whatever else you juggle — stitched into one screen. With opinions.',
  },
  {
    icon: 'bolt',
    title: 'Smart scheduling',
    cashQuote: "Moved gym to 6am. You said you'd go. Receipts attached.",
    desc: 'Auto-resolves conflicts. Rebooks when meetings collide. Guilt-trips you either way.',
  },
  {
    icon: 'interests',
    title: 'Habits & hobbies',
    cashQuote: "Day 47 of 'I'll learn guitar.' It's still in the case.",
    desc: "Tracks the streaks you break and the hobbies you swore you'd finally start. Gently judgy.",
  },
  {
    icon: 'task_alt',
    title: 'Task tracking',
    cashQuote: "'Quick task' — now four days old. Hello.",
    desc: "Unfinished tasks don't die. They follow you. No delete button, only accountability.",
  },
  {
    icon: 'chat_bubble',
    title: 'Natural language',
    cashQuote: "Just tell me. I'll handle it. Or judge you. Both.",
    desc: 'Talk to her like a friend. Claude AI under the hood — she understands context and sass.',
  },
]

export default function Features() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section
      id="features"
      ref={ref}
      className="relative py-20 md:py-28 overflow-hidden text-[#1a0f05]"
      style={{
        background:
          'radial-gradient(1000px circle at 88% 0%, rgba(249,115,22,0.06), transparent 55%), radial-gradient(900px circle at 10% 100%, rgba(217,119,6,0.05), transparent 55%), #ffffff',
      }}
    >
      <div className="max-w-[860px] mx-auto px-6">
        <motion.div
          className="text-center mb-12 md:mb-14"
          initial={{ opacity: 0, y: 14 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#c2410c] uppercase tracking-[0.22em] mb-4 inline-flex items-center gap-2">
            <span className="text-[#f97316]" aria-hidden>⟩</span>
            She&apos;s a whole ops team
          </p>
          <h2 className="font-display font-bold text-[2rem] sm:text-[2.4rem] md:text-[2.75rem] tracking-tight leading-[1.05]">
            What Cash actually{' '}
            <span className="hero-title-gradient">does.</span>
          </h2>
          <p className="mt-4 text-[#5c2e0a] text-[0.95rem] sm:text-base">
            Besides judging you.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {features.map((f, i) => (
            <motion.article
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.08 + i * 0.06 }}
              whileHover={{ y: -3 }}
              className="group relative rounded-2xl border border-[rgba(124,45,18,0.14)] bg-white/90 backdrop-blur-sm p-6 transition-all duration-300 hover:border-[#f97316]/50 hover:shadow-[0_12px_40px_rgba(249,115,22,0.14)]"
            >
              <span
                aria-hidden
                className="absolute top-4 right-5 font-display font-semibold text-[0.72rem] tracking-[0.15em] text-[#c2410c]/40 group-hover:text-[#c2410c] transition-colors"
              >
                {String(i + 1).padStart(2, '0')}
              </span>

              <div className="flex items-start gap-4">
                <span
                  className="shrink-0 flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-br from-[#fff7ed] to-[#ffedd5] border border-[rgba(124,45,18,0.1)] text-[#c2410c] group-hover:from-[#ffedd5] group-hover:to-[#fed7aa] group-hover:border-[#f97316]/30 transition-all"
                  aria-hidden
                >
                  <span
                    className="material-symbols-outlined text-[22px]"
                    style={{
                      fontVariationSettings:
                        "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 24",
                    }}
                  >
                    {f.icon}
                  </span>
                </span>

                <div className="min-w-0 flex-1">
                  <h3 className="font-sans font-bold text-[1.05rem] tracking-tight text-[#1a0f05]">
                    {f.title}
                  </h3>
                  <p className="mt-2 pl-3 border-l-2 border-[#f97316]/40 text-[0.88rem] font-medium leading-snug text-[#c2410c]">
                    {f.cashQuote}
                  </p>
                  <p className="mt-3 text-[0.9rem] leading-relaxed text-[#5c2e0a]">
                    {f.desc}
                  </p>
                </div>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  )
}
