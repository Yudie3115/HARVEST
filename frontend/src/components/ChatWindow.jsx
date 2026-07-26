import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'

export default function ChatWindow({
  messages,
  isLoading,
  onShowSources,
  onAskQuestion,
  interactionsDisabled = isLoading,
}) {
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
        minHeight: 0,
      }}
    >
      <div
        style={{
          maxWidth: 780,
          margin: '0 auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onShowSources={onShowSources}
            onAskQuestion={onAskQuestion}
            interactionsDisabled={interactionsDisabled}
          />
        ))}
        <div ref={bottomRef} style={{ height: 4 }} />
      </div>
    </div>
  )
}
