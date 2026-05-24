import ModelPicker from './ModelPicker'

const LANGUAGE_NAMES = {
  eng: 'English',
  lug: 'Luganda',
  ach: 'Acholi',
  nyn: 'Runyankole',
  teo: 'Ateso',
  lgg: 'Lugbara',
}

export default function LanguageBar({ detectedLanguage, languageOverride, onOverride, modelPreference, onModelChange }) {
  const active = languageOverride || detectedLanguage || 'eng'
  const displayName = LANGUAGE_NAMES[active] || 'English'
  const isOverride = !!languageOverride

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        padding: '6px 16px',
        background: '#0c1410',
        borderTop: '1px solid #1a2318',
        borderBottom: '1px solid #1a2318',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: '#4a7c59',
            display: 'inline-block',
            boxShadow: '0 0 4px #4a7c5966',
          }}
        />
        <span
          style={{
            fontSize: 11,
            fontFamily: '"IBM Plex Mono", monospace',
            color: '#6a7d69',
          }}
        >
          Responding in{' '}
          <span style={{ color: '#d4a853' }}>{displayName}</span>
          {!isOverride && (
            <span style={{ color: '#3d5a3d' }}> · auto-detected</span>
          )}
        </span>
        {isOverride && (
          <button
            onClick={() => onOverride(null)}
            style={{
              fontSize: 11,
              fontFamily: '"IBM Plex Mono", monospace',
              color: '#4a7c59',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
              textDecoration: 'underline',
            }}
          >
            · clear
          </button>
        )}
      </div>
      <ModelPicker modelPreference={modelPreference} onModelChange={onModelChange} />
    </div>
  )
}
