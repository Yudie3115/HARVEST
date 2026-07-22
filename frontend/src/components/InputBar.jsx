import { useState, useRef, useCallback } from 'react'

export default function InputBar({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  const handleSend = useCallback(() => {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [value, disabled, onSend])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e) => {
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 96) + 'px'
    setValue(el.value)
  }

  const canSend = value.trim().length > 0 && !disabled

  return (
    <div
      style={{
        padding: '12px 16px',
        background: '#0e1411',
        borderTop: '1px solid #1e2a1e',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          maxWidth: 780,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'flex-end',
          gap: 10,
        }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Ask about post-harvest practices…"
          style={{
            flex: 1,
            background: '#141a15',
            border: '1px solid #252e25',
            color: '#e8e4da',
            fontSize: 15,
            lineHeight: 1.5,
            borderRadius: 12,
            padding: '10px 14px',
            resize: 'none',
            fontFamily: 'Outfit, system-ui, sans-serif',
            outline: 'none',
            minHeight: 44,
            maxHeight: 96,
            overflowY: 'auto',
            opacity: disabled ? 0.5 : 1,
            transition: 'border-color 0.15s',
          }}
          onFocus={(e) => (e.target.style.borderColor = '#3d6b4f')}
          onBlur={(e) => (e.target.style.borderColor = '#252e25')}
        />
        <button
          onClick={handleSend}
          disabled={!canSend}
          style={{
            flexShrink: 0,
            width: 44,
            height: 44,
            borderRadius: 12,
            background: canSend ? '#3d6b4f' : '#1a2318',
            border: 'none',
            color: canSend ? '#e8e4da' : '#3d4a3d',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: canSend ? 'pointer' : 'not-allowed',
            transition: 'background 0.15s, transform 0.1s',
          }}
          onMouseEnter={(e) => { if (canSend) e.currentTarget.style.background = '#4a7c59' }}
          onMouseLeave={(e) => { if (canSend) e.currentTarget.style.background = '#3d6b4f' }}
          onMouseDown={(e) => { if (canSend) e.currentTarget.style.transform = 'scale(0.93)' }}
          onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)' }}
          aria-label="Send message"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2 8h12M9 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}
