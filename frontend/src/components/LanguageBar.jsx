import ModelPicker from './ModelPicker'

const LANGUAGES = {
  '': 'Auto-detect',
  eng: 'English',
  lug: 'Luganda',
  ach: 'Acholi',
  nyn: 'Runyankole',
  teo: 'Ateso',
  lgg: 'Lugbara',
}

export default function LanguageBar({ detectedLanguage, languageOverride, onOverride, modelPreference, onModelChange }) {
  const detectedName = LANGUAGES[detectedLanguage] || 'English'

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
          Responding in
        </span>
        <select
          value={languageOverride || ''}
          onChange={(e) => onOverride(e.target.value || null)}
          style={{
            background: '#161c17',
            border: '1px solid #2a3329',
            color: '#d4a853',
            fontSize: 11,
            borderRadius: 6,
            padding: '2px 20px 2px 6px',
            fontFamily: '"IBM Plex Mono", monospace',
            cursor: 'pointer',
            outline: 'none',
          }}
        >
          {Object.entries(LANGUAGES).map(([code, name]) => (
            <option key={code} value={code}>
              {code === '' && detectedLanguage
                ? `Auto (${detectedName})`
                : name}
            </option>
          ))}
        </select>
      </div>
      <ModelPicker modelPreference={modelPreference} onModelChange={onModelChange} />
    </div>
  )
}
