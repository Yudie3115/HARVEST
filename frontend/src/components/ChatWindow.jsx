import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import TypingIndicator from './TypingIndicator'

export default function ChatWindow({ messages, isLoading, onShowSources }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
        minHeight: 0,
      }}
    >
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onShowSources={onShowSources} />
      ))}
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} style={{ height: 4 }} />
    </div>
  )
}
