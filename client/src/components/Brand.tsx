import CashMark from './CashMark'

export default function Brand({ className = '' }: { className?: string }) {
  return (
    <div className={['brand-lockup', className].filter(Boolean).join(' ')}>
      <span className="brand-lockup__mark"><CashMark /></span>
      <span>Cash</span>
    </div>
  )
}
