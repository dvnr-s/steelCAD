/**
 * Text input for a dimension in feet. Displays feet-and-inches (5'6") and
 * accepts either decimal feet or ft-in on entry (5.5, 5'6", 5ft 6in, 66").
 * Commits on blur / Enter; Escape or an unparseable value reverts to the
 * last good value.
 */
import { useRef, useState } from 'react'
import { fmtFtIn, parseFt } from '../lib/format'

export default function DimensionInput({ value, onCommit, disabled, style, title, placeholder, autoFocus }) {
  // null = not editing (render the formatted prop); string = live draft.
  const [draft, setDraft] = useState(null)
  const cancelled = useRef(false)

  const commit = (e) => {
    setDraft(null)
    if (cancelled.current) { cancelled.current = false; return }
    const parsed = parseFt(e.target.value)
    if (parsed == null || parsed === Number(value)) return
    onCommit(parsed)
  }

  return (
    <input
      type="text"
      value={draft ?? fmtFtIn(value)}
      disabled={disabled}
      title={title}
      placeholder={placeholder}
      autoFocus={autoFocus}
      style={style}
      onFocus={(e) => { setDraft(e.target.value); e.target.select() }}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); e.target.blur() }
        if (e.key === 'Escape') { cancelled.current = true; e.target.blur() }
      }}
    />
  )
}
