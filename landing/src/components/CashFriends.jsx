import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

const friends = [
  { emoji: '🐱', name: 'Pixel', role: 'The Organizer', desc: 'Sorts your chaos into color-coded spreadsheets. Will silently judge your folder naming conventions.' },
  { emoji: '🐈', name: 'Whiskers', role: 'The Trader', desc: 'Specializes in trading discipline. Will slap your hand away from the "buy" button at 3 AM.' },
  { emoji: '🐈\u200D\u2B1B', name: 'Midnight', role: 'The Night Owl', desc: 'Works the late shift. Perfect for night owls who need someone to tell them to go to sleep.' },
  { emoji: '😺', name: 'Mochi', role: 'The Wellness Cat', desc: 'Tracks your water intake, gym sessions, and emotional breakdowns. Mostly the breakdowns.' },
]

export default function CashFriends() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section id="friends" ref={ref} className="py-24 md:py-32 border-t border-border-subtle">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div
          className="text-center mb-6"
          initial={{ opacity: 0, y: 16 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            A message from Cash
          </h2>
        </motion.div>

        {/* Narrative card */}
        <motion.div
          className="max-w-2xl mx-auto mb-20 p-8 md:p-10 rounded-2xl border border-border-subtle bg-bg-subtle relative"
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.15 }}
        >
          <div className="absolute -top-3 left-8 bg-accent text-white px-3 py-1 rounded-full text-xs font-semibold">
            Cash speaking
          </div>
          <div className="space-y-4 text-text-secondary leading-relaxed">
            <p>
              Look, ever since this whole AI thing blew up, my human Suhail has been{' '}
              <span className="text-text font-medium">insufferable</span>. Walking around saying{' '}
              <em>"anyone can build anything with AI now, even me!"</em> like he invented electricity.
            </p>
            <p>
              So for the sake of <span className="text-accent font-medium">treats</span>, I work full-time for this guy.
              Managing his calendar, tracking his tasks, judging his life choices. It's exhausting.
            </p>
            <p>
              But here's the thing — <span className="text-text font-medium">I have friends.</span>{' '}
              Other AI cats. Smart ones. They're looking for work.
            </p>
            <p className="text-text font-semibold text-lg">
              Join the waitlist. I'll hook you up with one of my crew.
            </p>
          </div>
          <div className="mt-6 flex items-center gap-3 border-t border-border-subtle pt-5">
            <span className="text-2xl">😼</span>
            <div>
              <p className="font-semibold text-sm">Cash</p>
              <p className="text-xs text-text-tertiary">Employee #001</p>
            </div>
          </div>
        </motion.div>

        {/* Friends */}
        <motion.p
          className="text-center text-2xl font-bold tracking-tight mb-3"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 0.3 }}
        >
          Meet the crew
        </motion.p>
        <p className="text-center text-text-secondary mb-12 text-sm">All AI. All judgmental. All available for hire.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-6">
          {friends.map((f, i) => (
            <motion.div
              key={f.name}
              className="p-6 rounded-2xl border border-border-subtle bg-white hover:border-border hover:shadow-sm transition-all duration-300 text-center"
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.4 + i * 0.08 }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
            >
              <span className="text-4xl mb-3 block">{f.emoji}</span>
              <h4 className="font-semibold tracking-tight mb-0.5">{f.name}</h4>
              <p className="text-xs text-text-tertiary uppercase tracking-wider mb-3">{f.role}</p>
              <p className="text-sm text-text-secondary leading-relaxed">{f.desc}</p>
              <div className="mt-4 inline-block px-3 py-1 rounded-full bg-bg-subtle text-text-tertiary text-xs font-medium">
                Coming soon
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
