const MODELS = [
  { value: 'groq', label: 'Llama 3.3', sub: 'Groq' },
  { value: 'openai', label: 'GPT-4o Mini', sub: 'OpenAI' },
]

export default function ModelPicker({ modelPreference, onModelChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      {MODELS.map((m) => {
        const active = modelPreference === m.value
        return (
          <button
            key={m.value}
            onClick={() => onModelChange(m.value)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '2px 8px',
              borderRadius: 4,
              border: active ? '1px solid #4a7c59' : '1px solid #1a2318',
              background: active ? '#0e1f13' : 'transparent',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontFamily: '"IBM Plex Mono", monospace',
                color: active ? '#d4a853' : '#3d5a3d',
                fontWeight: active ? 600 : 400,
                letterSpacing: '0.02em',
              }}
            >
              {m.label}
            </span>
            <span
              style={{
                fontSize: 9,
                fontFamily: '"IBM Plex Mono", monospace',
                color: active ? '#4a7c59' : '#2a3d2a',
              }}
            >
              {m.sub}
            </span>
          </button>
        )
      })}
    </div>
  )
}
