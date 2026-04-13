const LANGUAGES = {
  '': 'Auto-detect',
  eng: 'English',
  lug: 'Luganda',
  ach: 'Acholi',
  nyn: 'Runyankole',
  teo: 'Ateso',
  lgg: 'Lugbara',
}

export default function Header({ languageOverride, onLanguageChange }) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: '1px solid #1e2a1e',
        background: 'rgba(14,20,17,0.96)',
        backdropFilter: 'blur(8px)',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: '#1e3a28',
            border: '1px solid #3d6b4f',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
          }}
        >
          🌾
        </div>
        <div>
          <span
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontSize: 17,
              color: '#e8e4da',
              letterSpacing: '-0.3px',
            }}
          >
            PostHarvest
          </span>
          <span
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontSize: 17,
              color: '#d4a853',
              fontStyle: 'italic',
              marginLeft: 5,
            }}
          >
            AI
          </span>
        </div>
      </div>

      <select
        value={languageOverride || ''}
        onChange={(e) => onLanguageChange(e.target.value || null)}
        style={{
          background: '#161c17',
          border: '1px solid #2a3329',
          color: '#8a9489',
          fontSize: 11,
          borderRadius: 8,
          padding: '5px 24px 5px 10px',
          fontFamily: '"IBM Plex Mono", monospace',
          cursor: 'pointer',
          outline: 'none',
        }}
      >
        {Object.entries(LANGUAGES).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </header>
  )
}
