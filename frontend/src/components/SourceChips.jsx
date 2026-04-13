const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩']

export default function SourceChips({ sources }) {
  if (!sources?.length) return null

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
      {sources.map((src, i) => (
        <a
          key={i}
          href={src.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          title={src.title}
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
            textDecoration: 'none',
            minHeight: 28,
            transition: 'border-color 0.15s',
            maxWidth: 180,
            overflow: 'hidden',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#4a7c59')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#2a3329')}
        >
          <span style={{ color: '#d4a853', flexShrink: 0 }}>{CIRCLED[i] || `[${i + 1}]`}</span>
          <span
            style={{
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              textOverflow: 'ellipsis',
            }}
          >
            {src.site_name || src.title || 'Source'}
          </span>
        </a>
      ))}
    </div>
  )
}
