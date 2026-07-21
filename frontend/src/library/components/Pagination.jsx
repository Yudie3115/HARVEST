export default function Pagination({ offset, limit, total, onChange }) {
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)
  const canPrev = offset > 0
  const canNext = offset + limit < total

  const buttonStyle = (enabled) => ({
    padding: '6px 14px',
    borderRadius: 6,
    border: '1px solid #2a3329',
    background: enabled ? '#0f1a12' : 'transparent',
    color: enabled ? '#8ecfaa' : '#4a544a',
    fontSize: 13,
    fontFamily: 'Outfit, system-ui, sans-serif',
    cursor: enabled ? 'pointer' : 'default',
  })

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        marginTop: 20,
      }}
    >
      <span style={{ color: '#8a9489', fontSize: 12, fontFamily: '"IBM Plex Mono", monospace' }}>
        {from}–{to} of {total}
      </span>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          disabled={!canPrev}
          onClick={() => onChange(Math.max(0, offset - limit))}
          style={buttonStyle(canPrev)}
        >
          Prev
        </button>
        <button
          type="button"
          disabled={!canNext}
          onClick={() => onChange(offset + limit)}
          style={buttonStyle(canNext)}
        >
          Next
        </button>
      </div>
    </div>
  )
}
