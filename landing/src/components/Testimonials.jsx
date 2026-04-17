import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const testimonials = [
  {
    handle: 'sleep_deprived_dev',
    quote:
      "Set up Cash yesterday. She already rescheduled my standup because I 'looked tired in Slack.' She's not wrong.",
    avatar: 'https://cataas.com/cat/cute?width=120&height=120&position=center',
    time: '14m',
  },
  {
    handle: 'calendar_hostage',
    quote:
      "I asked for a reminder. She built a whole narrative arc about my procrastination. 10/10 would get judged again.",
    avatar: 'https://cataas.com/cat/orange?width=120&height=120&position=center',
    time: '52m',
  },
  {
    handle: 'leg_day_skipper',
    quote:
      "Cash has reminded me about leg day for 47 days straight. She added it to my calendar as 'optional trauma.'",
    avatar: 'https://cataas.com/cat/kitten?width=120&height=120&position=center',
    time: '2h',
  },
  {
    handle: 'ramen_budget',
    quote:
      "She categorized my expenses and sent me a pie chart that was literally just 'cope purchases.' I felt seen. I hated it.",
    avatar: 'https://cataas.com/cat/funny?width=120&height=120&position=center',
    time: '4h',
  },
  {
    handle: 'inbox_zero_lies',
    quote:
      "Inbox zero lasted 11 minutes. Cash left a voice note pretending to be proud. It was sarcastic. I cried a little.",
    avatar: 'https://cataas.com/cat/white?width=120&height=120&position=center',
    time: '6h',
  },
  {
    handle: 'claude_max_refund',
    quote:
      "It's like having a coworker who lives in Telegram, remembers everything, and thinks your OKRs are a cry for help.",
    avatar: 'https://cataas.com/cat/black?width=120&height=120&position=center',
    time: '9h',
  },
]

function Avatar({ avatar, handle }) {
  return (
    <div
      className="shrink-0 w-11 h-11 rounded-full overflow-hidden border-2 border-black/5 bg-[#fff7ed]"
      style={{
        boxShadow: '0 4px 10px rgba(249,115,22,0.22)',
      }}
    >
      <img
        src={avatar}
        alt={`${handle} avatar`}
        className="w-full h-full object-cover"
        loading="lazy"
      />
    </div>
  )
}

function TestimonialCard({ t }) {
  return (
    <div
      className="testimonial-card group/card flex items-start gap-3 shrink-0 min-w-[18rem] max-w-[22rem] sm:min-w-[20rem] sm:max-w-[25rem] rounded-xl border border-[rgba(124,45,18,0.18)] bg-white/95 p-4 backdrop-blur-md shadow-sm transition-all duration-300 hover:border-[#f97316]/60 hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(249,115,22,0.22)]"
    >
      <Avatar avatar={t.avatar} handle={t.handle} />
      <div className="flex flex-col gap-1.5 min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[0.78rem]">
          <span className="font-display font-semibold text-[#c2410c]">
            @{t.handle}
          </span>
          <span
            className="inline-flex items-center justify-center text-[0.7rem] leading-none"
            title="Cash-verified"
            aria-label="Cash-verified"
          >
            😼
          </span>
          <span className="text-[#8c5a2a]">·</span>
          <span className="text-[#8c5a2a]">{t.time}</span>
        </div>
        <p className="text-[0.9rem] leading-[1.5] text-[#5c2e0a] line-clamp-3">
          &ldquo;{t.quote}&rdquo;
        </p>
      </div>
    </div>
  )
}

export default function Testimonials() {
  const { ref, isInView } = useScrollReveal()

  const half = Math.ceil(testimonials.length / 2)
  const rowA = [...testimonials.slice(0, half), ...testimonials.slice(0, half)]
  const rowB = [...testimonials.slice(half), ...testimonials.slice(half)]

  return (
    <section
      ref={ref}
      className="relative py-16 md:py-24 text-[#1a0f05] overflow-hidden border-y border-[rgba(124,45,18,0.1)]"
      style={{
        background:
          'radial-gradient(1200px circle at 12% -10%, rgba(249,115,22,0.07), transparent 58%), radial-gradient(900px circle at 88% -12%, rgba(217,119,6,0.06), transparent 56%), #fff7ed',
      }}
    >
      <div className="max-w-[860px] mx-auto px-6">
        <motion.div
          className="flex items-center gap-4 mb-5"
          initial={{ opacity: 0, y: 14 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.45 }}
        >
          <h2 className="font-display text-[1.4rem] font-semibold tracking-tight flex items-center gap-2.5">
            <span className="text-[#f97316] font-bold" aria-hidden>
              ⟩
            </span>
            <span>What my friends say about Cash</span>
          </h2>
        </motion.div>

        <div className="flex items-center gap-2 text-sm text-[#8c5a2a] mb-6 pl-[1.35rem]">
          <span className="relative flex w-1.5 h-1.5">
            <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-75 animate-ping" />
            <span className="relative w-1.5 h-1.5 rounded-full bg-[#10b981]" />
          </span>
          <span>
            (all these are Cash in a trench coat. still true.)
          </span>
        </div>

        <div
          className="testimonials-track -mx-6"
          aria-label="Social quotes about Cash"
        >
          <div className="testimonials-marquee-track" style={{ animationDuration: '45s' }}>
            {rowA.map((t, i) => (
              <TestimonialCard key={`a-${t.handle}-${i}`} t={t} />
            ))}
          </div>
          <div
            className="testimonials-marquee-track reverse"
            style={{ animationDuration: '55s' }}
          >
            {rowB.map((t, i) => (
              <TestimonialCard key={`b-${t.handle}-${i}`} t={t} />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
