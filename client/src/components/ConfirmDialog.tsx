import { useEffect, useId, useRef } from 'react'
import { XIcon } from './icons'

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  tone = 'primary',
  busy = false,
  hideCancel = false,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  cancelLabel?: string
  tone?: 'primary' | 'danger'
  busy?: boolean
  hideCancel?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      requestAnimationFrame(() => {
        if (hideCancel) confirmRef.current?.focus()
        else cancelRef.current?.focus()
      })
    }
    if (!open && dialog.open) dialog.close()
  }, [hideCancel, open])

  return (
    <dialog
      ref={dialogRef}
      className="dialog"
      data-tone={tone}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <div className="dialog__surface">
        <button
          type="button"
          className="icon-button dialog__close"
          aria-label="Close dialog"
          disabled={busy}
          onClick={onClose}
        >
          <XIcon />
        </button>
        <div className="dialog__icon" aria-hidden="true">{tone === 'danger' ? '!' : 'i'}</div>
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        <div className="dialog__actions">
          {!hideCancel && (
            <button ref={cancelRef} type="button" className="btn btn-ghost" disabled={busy} onClick={onClose}>
              {cancelLabel}
            </button>
          )}
          <button
            ref={confirmRef}
            type="button"
            className={`btn ${tone === 'danger' ? 'btn-danger' : 'btn-primary'}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy && <span className="spinner spinner--button" aria-hidden="true" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  )
}
