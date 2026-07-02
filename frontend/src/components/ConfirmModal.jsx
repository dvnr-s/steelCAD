/**
 * useConfirm — drop-in replacement for window.confirm().
 *
 * Usage:
 *   const { confirm, ConfirmDialog } = useConfirm()
 *   // in JSX: {ConfirmDialog}
 *   // in handler: if (await confirm('Delete this?')) { ... }
 */
/* eslint-disable react-refresh/only-export-components --
 * This module intentionally co-locates the useConfirm hook with its ConfirmModal
 * component; the hook is the public API. Fast-refresh granularity is not a concern here. */
import { useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

function ConfirmModal({ message, title = 'Are you sure?', confirmLabel = 'Confirm', onConfirm, onCancel }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1100, backdropFilter: 'blur(4px)',
      }}
      onClick={onCancel}
    >
      <div
        className="card modal-card"
        style={{ '--modal-w': '400px', padding: 24 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center" style={{ justifyContent: 'space-between', marginBottom: 16 }}>
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} style={{ color: 'var(--c-error)', flexShrink: 0 }} />
            <h3 id="confirm-title" style={{ margin: 0 }}>{title}</h3>
          </div>
          <button className="btn btn-ghost btn-sm btn-icon" onClick={onCancel} aria-label="Cancel">
            <X size={15} />
          </button>
        </div>

        <p style={{ color: 'var(--c-text-muted)', marginBottom: 24, lineHeight: 1.5 }}>
          {message}
        </p>

        <div className="flex items-center gap-2" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={onCancel} autoFocus>Cancel</button>
          <button
            className="btn btn-danger"
            onClick={onConfirm}
            style={{ background: 'var(--c-error)', color: '#fff', borderColor: 'var(--c-error)' }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function useConfirm() {
  const [dialog, setDialog] = useState(null)

  const confirm = (message, options = {}) =>
    new Promise((resolve) => {
      setDialog({ message, options, resolve })
    })

  const handleConfirm = () => {
    dialog?.resolve(true)
    setDialog(null)
  }

  const handleCancel = () => {
    dialog?.resolve(false)
    setDialog(null)
  }

  const ConfirmDialog = dialog ? (
    <ConfirmModal
      message={dialog.message}
      title={dialog.options.title}
      confirmLabel={dialog.options.confirmLabel}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  ) : null

  return { confirm, ConfirmDialog }
}
