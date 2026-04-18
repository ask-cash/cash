import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'
import CashMascotEmbed from './CashMascotEmbed'

const testimonials = [
  {
    handle: 'sleep_deprived_dev',
    quote:
      "Adopted my pet yesterday. She already rescheduled my standup because I 'looked tired in Slack.' She's not wrong.",
    avatar: 'https://cataas.com/cat/cute?width=120&height=120&position=center',
    time: '14m',
  },
  {
    handle: 'calendar_hostage',
    quote:
      "Asked my pet for a reminder. She built a whole narrative arc about my procrastination. 10/10 would get judged again.",
    avatar: 'https://cataas.com/cat/orange?width=120&height=120&position=center',
    time: '52m',
  },
  {
    handle: 'leg_day_skipper',
    quote:
      "My pet has reminded me about leg day for 47 days straight. She added it to my calendar as 'optional trauma.'",
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
      "Inbox zero lasted 11 minutes. My pet left a voice note pretending to be proud. It was sarcastic. I cried a little.",
    avatar: 'https://cataas.com/cat/white?width=120&height=120&position=center',
    time: '6h',
  },
  {
    handle: 'okr_skeptic',
    quote:
      "It's like having a coworker who lives in Telegram, remembers everything, and thinks your OKRs are a cry for help.",
    avatar: 'https://cataas.com/cat/black?width=120&height=120&position=center',
    time: '9h',
  },
]

function Avatar({ avatar, handle }) {
  return (
    <div
      className="shrink-0 w-11 h-11 rounded-full overflow-hidden border border-white/15 bg-white/5"
      style={{
        boxShadow: '0 4px 12px rgba(0,0,0,0.45)',
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
    <div className="testimonial-card group/card flex items-start gap-3 shrink-0 min-w-[18rem] max-w-[22rem] sm:min-w-[20rem] sm:max-w-[25rem] rounded-xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-md shadow-[0_8px_28px_rgba(0,0,0,0.30)] transition-all duration-300 hover:border-[#4f8eff]/45 hover:-translate-y-0.5 hover:shadow-[0_14px_40px_rgba(79,142,255,0.22)]">
      <Avatar avatar={t.avatar} handle={t.handle} />
      <div className="flex flex-col gap-1.5 min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[0.78rem]">
          <span className="font-display font-semibold text-[#f1f3f9]">
            @{t.handle}
          </span>
          <span
            className="inline-flex items-center justify-center leading-none"
            title="Cash-verified"
            aria-label="Cash-verified"
          >
            <CashMascotEmbed className="w-4 h-3.5" title="Cash-verified" />
          </span>
          <span className="text-[#6b7480]">·</span>
          <span className="text-[#6b7480]">{t.time}</span>
        </div>
        <p className="text-[0.9rem] leading-[1.5] text-[#a8b0c0] line-clamp-3">
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
      className="relative py-16 md:py-24 text-[#f1f3f9] overflow-hidden"
    >
      <div className="max-w-[860px] mx-auto px-6">
        <motion.div
          className="flex items-center gap-4 mb-5"
          initial={{ opacity: 0, y: 14 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.45 }}
        >
          <h2 className="font-display text-[1.4rem] font-semibold tracking-tight flex items-center gap-2.5">
            <span className="text-[#7fa9ff] font-bold" aria-hidden>
              ⟩
            </span>
            <span>What humans say about their pets</span>
          </h2>
        </motion.div>

        <div className="flex items-center gap-2 text-sm text-[#a8b0c0] mb-6 pl-[1.35rem]">
          <span className="relative flex w-1.5 h-1.5">
            <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-75 animate-ping" />
            <span className="relative w-1.5 h-1.5 rounded-full bg-[#10b981]" />
          </span>
          <span>(yes, all these pets are Cash in a trench coat. still true.)</span>
        </div>

        <div
          className="testimonials-track -mx-6"
          aria-label="Social quotes about Cash"
        >
          <div
            className="testimonials-marquee-track"
            style={{ animationDuration: '45s' }}
          >
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
