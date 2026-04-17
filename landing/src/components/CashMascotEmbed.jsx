const SRC = '/assistant_cash_cat.html'

export default function CashMascotEmbed({ className = '', loading = 'lazy', title = 'Cash' }) {
  return (
    <iframe
      src={SRC}
      title={title}
      loading={loading}
      className={`block border-0 bg-transparent pointer-events-none min-h-0 ${className}`}
    />
  )
}
