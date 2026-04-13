export default function TypingIndicator() {
  return (
    <div className="msg-enter" style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      <div
        style={{
          flexShrink: 0,
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: '#1e3a28',
          border: '1px solid #3d6b4f',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 14,
          marginTop: 2,
        }}
      >
        🌾
      </div>
      <div
        style={{
          padding: '12px 16px',
          borderRadius: '4px 16px 16px 16px',
          background: '#191f1a',
          border: '1px solid #2a3329',
          display: 'flex',
          alignItems: 'center',
          gap: 5,
        }}
      >
        <span className="dot-1" style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#4a7c59' }} />
        <span className="dot-2" style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#4a7c59' }} />
        <span className="dot-3" style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#4a7c59' }} />
      </div>
    </div>
  )
}
