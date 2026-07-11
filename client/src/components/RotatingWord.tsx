import { useEffect, useState } from 'react'

// A green <em> that cross-fades through a list of words (blueprint §4.4).
// A hidden sizer reserves the width of the longest word so the line never
// reflows as it cycles.
export default function RotatingWord({ words, interval = 2400 }: { words: string[]; interval?: number }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % words.length), interval)
    return () => clearInterval(t)
  }, [words.length, interval])

  const longest = words.reduce((a, b) => (b.length > a.length ? b : a), '')

  return (
    <em>
      <span className="rotating-wrap">
        <span className="rotating-sizer" aria-hidden="true">{longest}</span>
        <span className="rotating-word" key={i}>{words[i]}</span>
      </span>
    </em>
  )
}
