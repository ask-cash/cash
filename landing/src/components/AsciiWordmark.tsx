// The Cash wordmark as block ASCII (Calvin S figlet style). The brand's only
// "logo" — rendered as type, never as a vector, per the terminal-native system.
const CASH = `╔═╗┌─┐┌─┐┬ ┬
║  ├─┤└─┐├─┤
╚═╝┴ ┴└─┘┴ ┴`

export default function AsciiWordmark({ className }: { className?: string }) {
  return (
    <pre className={className} aria-label="Cash" role="img">
      {CASH}
    </pre>
  )
}
