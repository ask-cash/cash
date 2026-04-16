import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

export default function ProfileCard() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="max-w-7xl mx-auto px-6 md:px-8 mb-32 md:mb-40">
      <div className="flex flex-col lg:flex-row items-center justify-center gap-12 md:gap-16">
        {/* ID Badge */}
        <motion.div
          className="w-full max-w-sm relative"
          initial={{ opacity: 0, x: -40, rotate: -3 }}
          animate={isInView ? { opacity: 1, x: 0, rotate: 0 } : {}}
          transition={{ duration: 0.7, type: 'spring' }}
        >
          <motion.div
            className="bg-white rounded-2xl overflow-hidden shadow-2xl relative"
            whileHover={{ scale: 1.02, rotate: 1, transition: { duration: 0.3 } }}
          >
            <div className="bg-linear-to-r from-primary via-secondary to-tertiary px-8 py-6 flex justify-between items-center">
              <span className="text-on-primary font-black tracking-widest text-lg">CASH ID</span>
              <span className="text-on-primary/40 text-xs font-mono">#001</span>
            </div>
            <div className="p-8 space-y-6">
              <div className="w-full aspect-square rounded-xl overflow-hidden bg-slate-100">
                <img
                  alt="Cash — employee ID photo of a regal cat with amber eyes"
                  className="w-full h-full object-cover"
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuDqnQbYl4eYSQHvvd_TURKpoKSkYLOzExXmXplXKiJy9kqd6ArJvKoU9gdQjYw1oHHB9cFnouQHGw8x89dQES3iEbolu_NNIXBZj8Ha2JxfCncdZeQk-4HXw2Zxmbx9N0_wTt6wUGNXcHihROsWXQPXebFL9NKn9ZScCaRvw8AAp31zDwl70x6xbXFDPwspFXx4TRD8zGUrfhP_evou8XJNWXfSrrTKXcXVyxwq7gXxHBYEzjSS2hG2qnZ1UeGXIV2_fH_Esc1tw_8"
                  loading="lazy"
                />
              </div>
              <div className="space-y-4 font-[var(--font-body)] text-slate-900">
                <div>
                  <p className="text-[10px] text-slate-400 uppercase font-bold tracking-widest">Name</p>
                  <p className="text-xl font-black">CASH</p>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase font-bold tracking-widest">Born</p>
                    <p className="text-sm font-bold">April 5th, 4:30 AM IST</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase font-bold tracking-widest">Birthplace</p>
                    <p className="text-sm font-bold">MacBook Pro</p>
                  </div>
                </div>
                <div className="border-t border-slate-100 pt-4">
                  <p className="text-[10px] text-slate-400 uppercase font-bold tracking-widest">Status</p>
                  <p className="text-sm font-bold text-orange-600 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-orange-600 animate-pulse" /> Judging You Right Now
                  </p>
                </div>
              </div>
            </div>
            <div className="h-12 bg-slate-900 w-full flex items-center justify-center gap-1 opacity-20">
              {[1, 0.5, 2, 1, 0.5, 1.5, 0.5].map((w, i) => (
                <div key={i} className="h-6 bg-white" style={{ width: `${w * 4}px` }} />
              ))}
            </div>
          </motion.div>
        </motion.div>

        {/* Profile details */}
        <motion.div
          className="flex-grow max-w-xl space-y-6"
          initial={{ opacity: 0, x: 40 }}
          animate={isInView ? { opacity: 1, x: 0 } : {}}
          transition={{ duration: 0.7, delay: 0.2 }}
        >
          <h2 className="text-3xl md:text-4xl font-[var(--font-headline)] font-black italic text-primary">
            "I did NOT wake up at 4:30 AM for this."
          </h2>
          <div className="space-y-4 text-base md:text-lg">
            {[
              ['Role:', 'AI Cat Assistant / Life Manager / Professional Judge'],
              ['Likes:', 'Treats, catnip, when Suhail sticks to the plan, good trades, gym days'],
              ['Dislikes:', 'Missed tasks, broken trading rules, skipped gym, your excuses'],
              ['Powered by:', 'Claude AI (she\'s smarter than both of us)'],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-4">
                <span className="font-bold text-secondary w-28 shrink-0">{label}</span>
                <span className="text-on-surface-variant">{value}</span>
              </div>
            ))}
          </div>
          <div className="pt-6">
            <div className="glass-panel p-6 rounded-xl border border-secondary/20">
              <p className="text-on-surface-variant text-sm mb-2 uppercase tracking-widest font-bold">Catchphrase</p>
              <p className="text-xl md:text-2xl font-[var(--font-headline)] font-black italic text-primary">
                "I did NOT wake up at 4:30 AM for this."
              </p>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
