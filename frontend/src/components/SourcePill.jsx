export default function SourcePill({ sources, onOpen }) {
  if (!sources?.length) return null

  return (
    <div style={{ marginTop: 8 }}>
      <button
        onClick={() => onOpen(sources)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 10px',
          borderRadius: 6,
          background: '#0f1a12',
          border: '1px solid #2a3329',
          color: '#6ab08a',
          fontSize: 11,
          fontFamily: '"IBM Plex Mono", monospace',
          cursor: 'pointer',
          minHeight: 28,
          transition: 'border-color 0.15s, color 0.15s',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#4a7c59'
          e.currentTarget.style.color = '#8ecfaa'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = '#2a3329'
          e.currentTarget.style.color = '#6ab08a'
        }}
        aria-label={`View ${sources.length} source${sources.length !== 1 ? 's' : ''}`}
      >
        <svg width="11" height="12" viewBox="0 0 11 12" fill="none" style={{ flexShrink: 0 }}>
          <rect x="1" y="1" width="7" height="9" rx="1" stroke="currentColor" strokeWidth="1.2" />
          <line x1="3" y1="4" x2="7" y2="4" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
          <line x1="3" y1="6.5" x2="7" y2="6.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
          <line x1="3" y1="9" x2="5.5" y2="9" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
        </svg>
        {sources.length} {sources.length === 1 ? 'source' : 'sources'}
      </button>
    </div>
  )
}
