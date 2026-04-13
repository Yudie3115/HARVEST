import { useState, useCallback } from 'react'
import { sendMessage } from '../api'

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

  const send = useCallback(
    async (text) => {
      if (!sessionId || !text.trim() || isLoading) return

      const userMsg = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: text.trim(),
        sources: [],
      }
      setMessages((prev) => [...prev, userMsg])
      setIsLoading(true)

      try {
        const data = await sendMessage(sessionId, text.trim(), languageOverride)
        setDetectedLanguage(data.detected_language || 'eng')
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: 'assistant',
            content: data.answer,
            detectedLanguage: data.detected_language,
            sources: data.sources || [],
          },
        ])
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: `e-${Date.now()}`,
            role: 'assistant',
            content: 'Sorry, something went wrong. Please try again.',
            detectedLanguage: 'eng',
            sources: [],
            isError: true,
          },
        ])
      } finally {
        setIsLoading(false)
      }
    },
    [sessionId, isLoading, languageOverride]
  )

  return { messages, isLoading, detectedLanguage, languageOverride, setLanguageOverride, send }
}
