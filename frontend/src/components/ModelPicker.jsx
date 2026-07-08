function modelLabel(model) {
  if (!model?.label) return 'Configured model'
  return model.label
}

function providerLabel(model) {
  if (!model?.sub) return model?.provider || 'Default'
  return model.sub
}

export default function ModelPicker({ modelPreference, models = [], onModelChange }) {
  const options = models.length ? models : [
    { value: modelPreference || 'default', label: 'Configured model', sub: 'Default' },
  ]

  if (options.length <= 1) {
    const model = options[0]
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minHeight: 24,
          padding: '2px 8px',
          borderRadius: 4,
          border: '1px solid #1a2318',
          background: '#101711',
        }}
        title={`${providerLabel(model)} ${modelLabel(model)}`}
      >
        <span
          style={{
            fontSize: 10,
            fontFamily: '"IBM Plex Mono", monospace',
            color: '#d4a853',
            fontWeight: 600,
            letterSpacing: 0,
            maxWidth: 150,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {modelLabel(model)}
        </span>
        <span
          style={{
            fontSize: 9,
            fontFamily: '"IBM Plex Mono", monospace',
            color: '#4a7c59',
            letterSpacing: 0,
          }}
        >
          {providerLabel(model)}
        </span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      {options.map((m) => {
        const active = modelPreference === m.value
        return (
          <button
            key={m.value}
            type="button"
            onClick={() => onModelChange(m.value)}
            title={`${providerLabel(m)} ${modelLabel(m)}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              minHeight: 24,
              padding: '2px 8px',
              borderRadius: 4,
              border: active ? '1px solid #4a7c59' : '1px solid #1a2318',
              background: active ? '#0e1f13' : 'transparent',
              cursor: 'pointer',
              transition: 'all 0.15s',
              maxWidth: 170,
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontFamily: '"IBM Plex Mono", monospace',
                color: active ? '#d4a853' : '#3d5a3d',
                fontWeight: active ? 600 : 400,
                letterSpacing: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {modelLabel(m)}
            </span>
            <span
              style={{
                fontSize: 9,
                fontFamily: '"IBM Plex Mono", monospace',
                color: active ? '#4a7c59' : '#2a3d2a',
                letterSpacing: 0,
                flexShrink: 0,
              }}
            >
              {providerLabel(m)}
            </span>
          </button>
        )
      })}
    </div>
  )
}
