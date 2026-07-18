import CashMark from './CashMark'

export default function AppLoader({ label = 'Loading Cash…' }: { label?: string }) {
  return (
    <div className="loading-screen" role="status" aria-live="polite">
      <span className="loading-mark" aria-hidden="true"><CashMark /></span>
      <span>{label}</span>
    </div>
  )
}
