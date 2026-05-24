import { useState, useCallback, useEffect } from 'react'
import { getHistory, streamMessage } from '../api'

const WELCOME = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Hello! I can answer questions about post-harvest practices — storage, pest control, handling, and more. Ask me anything.',
  detectedLanguage: 'eng',
  sources: [],
}

export function useChat(sessionId) {
  const [messages, setMessages] = useState([WELCOME])
  const [isLoading, setIsLoading] = useState(false)
  const [detectedLanguage, setDetectedLanguage] = useState('eng')
  const [languageOverride, setLanguageOverride] = useState(null)

  // Reload message history when sessionId becomes available (e.g. page refresh)
  useEffect(() => {
    if (!sessionId) return
    getHistory(sessionId)
      .then((data) => {
        if (!data.messages?.length) return
        const loaded = data.messages.map((msg, i) => ({
          id: `h-${i}`,
          role: msg.role,
          content: msg.content,
          detectedLanguage: msg.detected_language,
          sources: msg.sources || [],
        }))
        setMessages([WELCOME, ...loaded])
        // Restore detected language from the most recent assistant message
        const lastAssistant = [...loaded].reverse().find((m) => m.role === 'assistant')
        if (lastAssistant?.detectedLanguage) {
          setDetectedLanguage(lastAssistant.detectedLanguage)
        }
      })
      .catch(() => {
        // History load failure is non-fatal — keep welcome message
      })
  }, [sessionId])

  const send = useCallback(
    async (text) => {
      if (!sessionId || !text.trim() || isLoading) return

      const userMsg = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: text.trim(),
        sources: [],
      }
      const assistantMsgId = `a-${Date.now()}`

      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantMsgId, role: 'assistant', content: '', sources: [], isStreaming: true },
      ])
      setIsLoading(true)

      await streamMessage(sessionId, text.trim(), languageOverride, {
        onToken: (token) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, content: m.content + token } : m
            )
          )
        },
        onDone: (event) => {
          setDetectedLanguage(event.detected_language || 'eng')
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    // Replace streamed English tokens with the (potentially translated) final answer
                    content: event.answer || m.content,
                    sources: event.sources || [],
                    isStreaming: false,
                    noResults: event.no_results || false,
                  }
                : m
            )
          )
          setIsLoading(false)
        },
        onError: (message) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: message, isError: true, isStreaming: false }
                : m
            )
          )
          setIsLoading(false)
        },
      })
    },
    [sessionId, isLoading, languageOverride]
  )

  return { messages, isLoading, detectedLanguage, languageOverride, setLanguageOverride, send }
}
