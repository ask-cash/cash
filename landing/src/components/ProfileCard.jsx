import { motion } from 'framer-motion'
import { useScrollReveal } from '../hooks/useScrollReveal'

export default function ProfileCard() {
  const { ref, isInView } = useScrollReveal()

  return (
    <section ref={ref} className="relative py-24 md:py-32 text-[#f1f3f9]">
      <div className="max-w-7xl mx-auto px-6 md:px-8">
        <div className="flex flex-col lg:flex-row items-center justify-center gap-12 md:gap-16">
          {/* ID Badge — kept light to read like a physical artifact floating in space */}
          <motion.div
            className="w-full max-w-sm relative"
            initial={{ opacity: 0, x: -40, rotate: -3 }}
            animate={isInView ? { opacity: 1, x: 0, rotate: 0 } : {}}
            transition={{ duration: 0.7, type: 'spring' }}
          >
            <motion.div
              className="bg-white rounded-2xl overflow-hidden shadow-[0_40px_100px_-20px_rgba(79,142,255,0.45),0_8px_28px_-8px_rgba(0,0,0,0.55)] relative"
              whileHover={{ scale: 1.02, rotate: 1, transition: { duration: 0.3 } }}
            >
              <div
                className="px-8 py-6 flex justify-between items-center"
                style={{
                  background:
                    'linear-gradient(135deg, #f97316 0%, #ec4899 50%, #4f8eff 100%)',
                }}
              >
                <span className="text-white font-black tracking-widest text-lg">CASH ID</span>
                <span className="text-white/55 text-xs font-mono">#001</span>
              </div>
              <div className="p-8 space-y-6">
                <div className="w-full aspect-square rounded-xl overflow-hidden bg-[#f1ecdf]">
                  <img
                    alt="Cash — employee ID photo of a regal cat with amber eyes"
                    className="w-full h-full object-cover"
                    src="https://lh3.googleusercontent.com/aida-public/AB6AXuDqnQbYl4eYSQHvvd_TURKpoKSkYLOzExXmXplXKiJy9kqd6ArJvKoU9gdQjYw1oHHB9cFnouQHGw8x89dQES3iEbolu_NNIXBZj8Ha2JxfCncdZeQk-4HXw2Zxmbx9N0_wTt6wUGNXcHihROsWXQPXebFL9NKn9ZScCaRvw8AAp31zDwl70x6xbXFDPwspFXx4TRD8zGUrfhP_evou8XJNWXfSrrTKXcXVyxwq7gXxHBYEzjSS2hG2qnZ1UeGXIV2_fH_Esc1tw_8"
                    loading="lazy"
                  />
                </div>
                <div className="space-y-4 text-[#1a1f36]">
                  <div>
                    <p className="text-[10px] text-[#8b92a1] uppercase font-bold tracking-widest">Name</p>
                    <p className="text-xl font-black">CASH</p>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-[10px] text-[#8b92a1] uppercase font-bold tracking-widest">Born</p>
                      <p className="text-sm font-bold">April 5th, 4:30 AM IST</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#8b92a1] uppercase font-bold tracking-widest">Birthplace</p>
                      <p className="text-sm font-bold">MacBook Pro</p>
                    </div>
                  </div>
                  <div className="border-t border-[#efe9d9] pt-4">
                    <p className="text-[10px] text-[#8b92a1] uppercase font-bold tracking-widest">Status</p>
                    <p className="text-sm font-bold text-[#f97316] flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#f97316] animate-pulse" /> Judging You Right Now
                    </p>
                  </div>
                </div>
              </div>
              <div className="h-12 bg-[#06080f] w-full flex items-center justify-center gap-1 opacity-30">
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
            <h2 className="text-3xl md:text-4xl font-display font-black italic text-[#f1f3f9]">
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
                  <span className="font-bold text-[#7fa9ff] w-28 shrink-0">{label}</span>
                  <span className="text-[#a8b0c0]">{value}</span>
                </div>
              ))}
            </div>
            <div className="pt-6">
              <div className="p-6 rounded-xl border border-white/12 bg-white/[0.04] backdrop-blur-md shadow-[0_12px_36px_-12px_rgba(0,0,0,0.55)]">
                <p className="text-[#6b7480] text-sm mb-2 uppercase tracking-widest font-bold">Catchphrase</p>
                <p className="text-xl md:text-2xl font-display font-black italic text-[#f1f3f9]">
                  "I did NOT wake up at 4:30 AM for this."
                </p>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
