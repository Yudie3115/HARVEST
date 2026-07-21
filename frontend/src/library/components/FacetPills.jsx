// Single-select facet pills, grouped by category (Topics / Crops / Regions).
// Clicking the already-active pill in a group clears that group's filter;
// clicking a different pill replaces it. Matches the backend's single-value
// topic/crop/region query params — no multi-select.
const GROUPS = [
  { key: 'topics', param: 'topic', label: 'Topics' },
  { key: 'crops', param: 'crop', label: 'Crops' },
  { key: 'regions', param: 'region', label: 'Regions' },
]

export default function FacetPills({ facets, selected, onToggle }) {
  if (!facets) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 20 }}>
      {GROUPS.map(({ key, param, label }) => {
        const values = facets[key] || []
        if (values.length === 0) return null
        return (
          <div key={key}>
            <div
              style={{
                fontFamily: '"IBM Plex Mono", monospace',
                fontSize: 11,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: '#8a9489',
                marginBottom: 6,
              }}
            >
              {label}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {values.map(({ value, count }) => {
                const isActive = selected[param] === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => onToggle(param, value)}
                    aria-pressed={isActive}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '5px 10px',
                      borderRadius: 999,
                      border: isActive ? '1px solid #6ab08a' : '1px solid #2a3329',
                      background: isActive ? '#1e3a28' : '#0f1a12',
                      color: isActive ? '#8ecfaa' : '#d4cfc6',
                      fontSize: 12,
                      fontFamily: 'Outfit, system-ui, sans-serif',
                      cursor: 'pointer',
                      minHeight: 28,
                      transition: 'border-color 0.15s, color 0.15s, background 0.15s',
                    }}
                  >
                    {value}
                    <span
                      style={{
                        fontFamily: '"IBM Plex Mono", monospace',
                        fontSize: 11,
                        color: isActive ? '#6ab08a' : '#8a9489',
                      }}
                    >
                      ({count})
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
