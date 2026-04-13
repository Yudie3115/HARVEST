function SourceCard({ source, index }) {
  const siteName = source.site_name
    ? source.site_name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    : null

  const displayUrl = source.url
    ? source.url.replace(/^https?:\/\//, '').replace(/\/$/, '')
    : null

  return (
    <div
      style={{
        padding: '14px 16px',
        background: '#141a15',
        border: '1px solid #222e23',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      {/* Index + site badge row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: 11,
            color: '#d4a853',
            flexShrink: 0,
          }}
        >
          {['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩'][index] || `[${index + 1}]`}
        </span>
        {siteName && (
          <span
            style={{
              fontSize: 10,
              fontFamily: '"IBM Plex Mono", monospace',
              color: '#4a7c59',
              background: '#0f1e12',
              border: '1px solid #2a3a2a',
              borderRadius: 4,
              padding: '2px 7px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {siteName}
          </span>
        )}
      </div>

      {/* Title */}
      {source.title && (
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: '#d4cfc6',
            lineHeight: 1.45,
            fontFamily: 'Outfit, system-ui, sans-serif',
          }}
        >
          {source.title}
        </p>
      )}

      {/* URL */}
      {displayUrl && (
        <p
          style={{
            margin: 0,
            fontSize: 11,
            fontFamily: '"IBM Plex Mono", monospace',
            color: '#4a5a4a',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={source.url}
        >
          {displayUrl}
        </p>
      )}

      {/* Open link */}
      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            marginTop: 2,
            fontSize: 11,
            fontFamily: '"IBM Plex Mono", monospace',
            color: '#4a7c59',
            textDecoration: 'none',
            width: 'fit-content',
            transition: 'color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#6ab08a')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#4a7c59')}
        >
          Open source
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M2 8L8 2M8 2H4M8 2V6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </a>
      )}
    </div>
  )
}

export default function SourcesSidebar({ sources, onClose }) {
  const isOpen = !!sources?.length

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          zIndex: 40,
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'auto' : 'none',
          transition: 'opacity 0.2s ease',
        }}
      />

      {/* Sidebar panel */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: 'min(340px, 92vw)',
          background: '#0e1411',
          borderLeft: '1px solid #1e2a1e',
          zIndex: 50,
          display: 'flex',
          flexDirection: 'column',
          transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
          boxShadow: isOpen ? '-8px 0 32px rgba(0,0,0,0.4)' : 'none',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 16px',
            borderBottom: '1px solid #1e2a1e',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="15" viewBox="0 0 11 12" fill="none" style={{ color: '#4a7c59' }}>
              <rect x="1" y="1" width="7" height="9" rx="1" stroke="currentColor" strokeWidth="1.2" />
              <line x1="3" y1="4" x2="7" y2="4" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
              <line x1="3" y1="6.5" x2="7" y2="6.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
              <line x1="3" y1="9" x2="5.5" y2="9" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
            </svg>
            <span
              style={{
                fontFamily: 'Fraunces, Georgia, serif',
                fontSize: 15,
                color: '#e8e4da',
              }}
            >
              Sources
            </span>
            {sources?.length > 0 && (
              <span
                style={{
                  fontFamily: '"IBM Plex Mono", monospace',
                  fontSize: 11,
                  color: '#4a7c59',
                  background: '#0f1e12',
                  border: '1px solid #2a3a2a',
                  borderRadius: 10,
                  padding: '1px 7px',
                }}
              >
                {sources.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close sources"
            style={{
              background: 'none',
              border: 'none',
              color: '#4a5a4a',
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
              transition: 'color 0.15s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = '#e8e4da')}
            onMouseLeave={(e) => (e.currentTarget.style.color = '#4a5a4a')}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Source list */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '14px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          {sources?.map((src, i) => (
            <SourceCard key={i} source={src} index={i} />
          ))}
        </div>

        {/* Footer note */}
        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid #1e2a1e',
            flexShrink: 0,
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: 10,
              fontFamily: '"IBM Plex Mono", monospace',
              color: '#3a4a3a',
              lineHeight: 1.5,
            }}
          >
            Sources retrieved from the indexed knowledge base. Content may not reflect the most recent updates at each source.
          </p>
        </div>
      </div>
    </>
  )
}
