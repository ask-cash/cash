import { useMemo } from 'react'

const STAR_COUNT = 140
const SHOOTING_COUNT = 3

function seededRandom(seed) {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

function buildStars() {
  const rand = seededRandom(7)
  return Array.from({ length: STAR_COUNT }, (_, i) => {
    const r = rand()
    const size = r < 0.78 ? 1 : r < 0.95 ? 1.6 : 2.4
    const baseOpacity = 0.25 + rand() * 0.7
    return {
      id: i,
      x: rand() * 100,
      y: rand() * 100,
      size,
      min: baseOpacity * 0.3,
      max: baseOpacity,
      duration: 2.4 + rand() * 5.6,
      delay: rand() * 6,
      glow: size >= 2,
    }
  })
}

function buildShooters() {
  const rand = seededRandom(91)
  return Array.from({ length: SHOOTING_COUNT }, (_, i) => ({
    id: i,
    x: 5 + rand() * 80,
    y: 5 + rand() * 60,
    angle: -18 - rand() * 16,
    distanceX: 280 + rand() * 220,
    distanceY: -(80 + rand() * 140),
    duration: 1.6 + rand() * 1.2,
    delay: 4 + i * 7 + rand() * 5,
  }))
}

export default function Stars() {
  const stars = useMemo(buildStars, [])
  const shooters = useMemo(buildShooters, [])

  return (
    <div
      aria-hidden
      className="fixed inset-0 z-0 pointer-events-none overflow-hidden"
    >
      {/* Deep space base + nebula clouds */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(900px circle at 18% 18%, rgba(79,142,255,0.14), transparent 55%),' +
            'radial-gradient(800px circle at 84% 78%, rgba(168,85,247,0.10), transparent 55%),' +
            'radial-gradient(700px circle at 60% 50%, rgba(249,115,22,0.06), transparent 55%),' +
            'radial-gradient(1100px circle at 50% 110%, rgba(0,105,255,0.10), transparent 60%)',
        }}
      />

      {/* Faint star dust band — subtle diagonal glow like the milky way */}
      <div
        className="absolute inset-0 opacity-[0.35] mix-blend-screen"
        style={{
          background:
            'linear-gradient(115deg, transparent 35%, rgba(180,200,255,0.08) 48%, rgba(255,220,180,0.06) 55%, transparent 70%)',
        }}
      />

      {/* Stars */}
      {stars.map((s) => (
        <span
          key={s.id}
          className="absolute rounded-full bg-white"
          style={{
            left: `${s.x}%`,
            top: `${s.y}%`,
            width: `${s.size}px`,
            height: `${s.size}px`,
            opacity: s.min,
            boxShadow: s.glow
              ? '0 0 6px rgba(255,255,255,0.85), 0 0 12px rgba(180,200,255,0.45)'
              : 'none',
            animation: `star-twinkle ${s.duration}s ease-in-out ${s.delay}s infinite`,
            ['--star-min']: s.min,
            ['--star-max']: s.max,
          }}
        />
      ))}

      {/* Shooting stars */}
      {shooters.map((s) => (
        <span
          key={`shoot-${s.id}`}
          className="absolute"
          style={{
            left: `${s.x}%`,
            top: `${s.y}%`,
            width: '120px',
            height: '1px',
            background:
              'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.85) 60%, #fff 100%)',
            filter: 'drop-shadow(0 0 4px rgba(180,210,255,0.85))',
            transform: `rotate(${s.angle}deg)`,
            transformOrigin: 'right center',
            opacity: 0,
            animation: `shooting-star ${s.duration}s ease-out ${s.delay}s infinite`,
            ['--shoot-angle']: `${s.angle}deg`,
            ['--shoot-x']: `${s.distanceX}px`,
            ['--shoot-y']: `${s.distanceY}px`,
          }}
        />
      ))}

      {/* Vignette so edges feel deeper */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 100% 80% at 50% 50%, transparent 55%, rgba(0,0,0,0.45) 100%)',
        }}
      />
    </div>
  )
}
