import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'
import CashMascotEmbed from './CashMascotEmbed'

const VB_W = 200
const VB_H = 130

const HUB = {
  cx: 100,
  cy: 28,
  w: 44,
  h: 44,
}
const HUB_EXIT_X = HUB.cx
const HUB_EXIT_Y = HUB.cy + HUB.h / 2
const NODE_Y = 108
const CTRL_Y = (HUB_EXIT_Y + NODE_Y) / 2

const integrations = [
  {
    name: 'Google Calendar',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/google-calendar.svg',
  },
  {
    name: 'Gmail',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/gmail.svg',
  },
  {
    name: 'Google Drive',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/google-drive.svg',
  },
  { name: 'Notion', icon: 'https://cdn.simpleicons.org/notion/ffffff' },
  {
    name: 'Slack',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/slack.svg',
  },
  { name: 'X / Twitter', icon: 'https://cdn.simpleicons.org/x/ffffff' },
  { name: 'GitHub', icon: 'https://cdn.simpleicons.org/github/ffffff' },
  {
    name: 'Outlook',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/outlook.svg',
  },
  {
    name: 'Spotify',
    icon: 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/spotify.svg',
  },
]

const N = integrations.length
const X_START = 10
const X_END = 190
const nodeX = (i) => X_START + ((X_END - X_START) * i) / (N - 1)

function linePath(targetX) {
  const dy = NODE_Y - HUB_EXIT_Y
  const cp1y = HUB_EXIT_Y + dy * 0.45
  const cp2y = NODE_Y - dy * 0.35
  return `M ${HUB_EXIT_X},${HUB_EXIT_Y} C ${HUB_EXIT_X},${cp1y} ${targetX},${cp2y} ${targetX},${NODE_Y}`
}

export default function Integrations() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section
      id="integrations"
      ref={ref}
      className="relative py-20 md:py-28 text-[#f1f3f9]"
    >
      <div className="max-w-[1100px] mx-auto px-6">
        <motion.div
          className="text-center mb-12 md:mb-14"
          initial={{ opacity: 0, y: 14 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <p className="font-display text-[0.78rem] sm:text-[0.82rem] font-medium text-[#7fa9ff] uppercase tracking-[0.22em] mb-4 inline-flex items-center gap-2">
            <span className="text-[#7fa9ff]" aria-hidden>
              ⟩
            </span>
            Integrations
          </p>
          <h2 className="font-display font-bold text-2xl sm:text-3xl md:text-4xl tracking-tight leading-[1.05]">
            Paws in{' '}
            <span className="hero-title-gradient">everything.</span>
          </h2>
          <p className="mt-4 text-[#a8b0c0] text-sm sm:text-base">
            Every pet plugs into the apps you pretend to be productive with.
          </p>
        </motion.div>

        <div
          className="hidden md:block relative w-full max-w-[860px] mx-auto"
          style={{ aspectRatio: `${VB_W} / ${VB_H}` }}
        >
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            preserveAspectRatio="none"
            aria-hidden
          >
            <defs>
              {integrations.map((_, i) => (
                <clipPath key={`cp-${i}`} id={`rev-line-${i}`}>
                  <motion.rect
                    x={0}
                    y={HUB_EXIT_Y}
                    width={VB_W}
                    initial={{ height: 0 }}
                    animate={
                      isInView
                        ? { height: VB_H - HUB_EXIT_Y }
                        : { height: 0 }
                    }
                    transition={{
                      duration: 0.75,
                      delay: 0.4 + i * 0.1,
                      ease: [0.25, 0.4, 0.25, 1],
                    }}
                  />
                </clipPath>
              ))}
            </defs>
            {integrations.map((it, i) => (
              <path
                key={`line-${it.name}`}
                d={linePath(nodeX(i))}
                stroke="#7fa9ff"
                strokeWidth={0.5}
                strokeOpacity={0.9}
                strokeDasharray="2.4 1.8"
                strokeLinecap="round"
                fill="none"
                clipPath={`url(#rev-line-${i})`}
              />
            ))}
          </svg>

          <motion.div
            className="absolute"
            style={{
              left: `${((HUB.cx - HUB.w / 2) / VB_W) * 100}%`,
              top: `${((HUB.cy - HUB.h / 2) / VB_H) * 100}%`,
              width: `${(HUB.w / VB_W) * 100}%`,
              aspectRatio: `${HUB.w} / ${HUB.h}`,
            }}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            transition={{ duration: 0.55, delay: 0.1, ease: 'easeOut' }}
          >
            <div className="relative w-full h-full">
              <motion.span
                aria-hidden
                className="absolute -inset-4 rounded-full pointer-events-none"
                style={{
                  background:
                    'radial-gradient(circle, rgba(249,115,22,0.30) 0%, transparent 70%)',
                }}
                animate={{ scale: [1, 1.1, 1], opacity: [0.5, 0.2, 0.5] }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }}
              />
              <motion.div
                className="relative w-full h-full flex items-center justify-center"
                animate={{ rotate: [0, -3, 3, 0] }}
                transition={{
                  duration: 1.6,
                  repeat: Infinity,
                  repeatDelay: 3,
                  ease: 'easeInOut',
                }}
              >
                <CashMascotEmbed
                  className="w-full h-full"
                  loading="eager"
                />
                <span className="absolute bottom-1 right-2 flex w-3.5 h-3.5">
                  <span className="absolute inset-0 rounded-full bg-[#10b981] opacity-60 animate-ping" />
                  <span className="relative w-3.5 h-3.5 rounded-full bg-[#10b981] ring-[3px] ring-[#06080f]" />
                </span>
              </motion.div>
            </div>
          </motion.div>

          {integrations.map((it, i) => (
            <div
              key={it.name}
              className="absolute"
              style={{
                left: `${(nodeX(i) / VB_W) * 100}%`,
                top: `${(NODE_Y / VB_H) * 100}%`,
              }}
            >
              <motion.div
                title={it.name}
                className="-translate-x-1/2 -translate-y-1/2 w-12 h-12 rounded-xl bg-white/[0.05] border border-white/10 backdrop-blur-md flex items-center justify-center shadow-[0_6px_20px_rgba(0,0,0,0.35)] transition-colors duration-200 hover:border-[#4f8eff]/45 hover:bg-white/[0.08]"
                initial={{ opacity: 0, scale: 0.4 }}
                animate={
                  isInView ? { opacity: 1, scale: 1 } : { opacity: 0 }
                }
                transition={{
                  duration: 0.45,
                  delay: 0.4 + i * 0.1 + 0.5,
                  ease: [0.25, 1.25, 0.4, 1],
                }}
              >
                <img
                  src={it.icon}
                  alt={it.name}
                  loading="lazy"
                  className="w-6 h-6 object-contain"
                />
              </motion.div>
            </div>
          ))}
        </div>

        <div className="md:hidden flex flex-col items-center gap-10">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            transition={{ duration: 0.5 }}
            className="relative"
          >
            <span
              aria-hidden
              className="absolute -inset-4 rounded-full pointer-events-none"
              style={{
                background:
                  'radial-gradient(circle, rgba(249,115,22,0.28) 0%, transparent 70%)',
              }}
            />
            <CashMascotEmbed className="relative w-32 h-28" />
          </motion.div>

          <motion.div
            className="flex flex-wrap justify-center gap-3"
            initial={{ opacity: 0 }}
            animate={isInView ? { opacity: 1 } : {}}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            {integrations.map((item, i) => (
              <motion.div
                key={item.name}
                title={item.name}
                className="w-12 h-12 rounded-xl bg-white/[0.05] border border-white/10 backdrop-blur-md flex items-center justify-center shadow-[0_4px_14px_rgba(0,0,0,0.3)]"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={isInView ? { opacity: 1, scale: 1 } : {}}
                transition={{ duration: 0.3, delay: 0.25 + i * 0.04 }}
              >
                <img
                  src={item.icon}
                  alt={item.name}
                  loading="lazy"
                  className="w-6 h-6 object-contain"
                />
              </motion.div>
            ))}
          </motion.div>
        </div>

        <p className="mt-12 text-center text-[#6b7480] text-xs">
          More coming. Pets need access to everything. That&apos;s the deal.
        </p>
      </div>
    </section>
  )
}
