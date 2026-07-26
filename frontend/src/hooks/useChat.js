import { useState, useCallback, useEffect } from 'react'
import { getChatModels, getHistory, streamMessage } from '../api'

const MODEL_STORAGE_KEY = 'phk_model_preference'
const FALLBACK_MODEL_OPTIONS = [
  { value: 'ollama', label: 'Configured model', sub: 'Default', provider: 'ollama', is_default: true },
]

const WELCOME = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Hello! I can answer questions about post-harvest practices — storage, pest control, handling, and more. Ask me anything.',
  detectedLanguage: 'eng',
  sources: [],
}

export function useChat(
  sessionId,
  { token, initialQuestion, onInitialQuestionConsumed, onSessionExpired, onAccessError } = {},
) {
  const [messages, setMessages] = useState([WELCOME])
  const [isLoading, setIsLoading] = useState(false)
  const [detectedLanguage, setDetectedLanguage] = useState('eng')
  const [languageOverride, setLanguageOverride] = useState(null)
  const [modelPreference, setModelPreferenceState] = useState(
    () => localStorage.getItem(MODEL_STORAGE_KEY) || null
  )
  const [modelOptions, setModelOptions] = useState(FALLBACK_MODEL_OPTIONS)
  const [historyReady, setHistoryReady] = useState(false)

  const setModelPreference = useCallback((value) => {
    if (value) localStorage.setItem(MODEL_STORAGE_KEY, value)
    else localStorage.removeItem(MODEL_STORAGE_KEY)
    setModelPreferenceState(value)
  }, [])

  useEffect(() => {
    getChatModels()
      .then((data) => {
        const options = data.options?.length ? data.options : FALLBACK_MODEL_OPTIONS
        const defaultOption = options.find((option) => option.is_default) || options[0]
        const savedPreference = localStorage.getItem(MODEL_STORAGE_KEY)
        const savedIsValid = savedPreference && options.some((option) => option.value === savedPreference)

        setModelOptions(options)
        if (savedIsValid) {
          setModelPreferenceState(savedPreference)
        } else {
          localStorage.removeItem(MODEL_STORAGE_KEY)
          setModelPreferenceState(defaultOption.value)
        }
      })
      .catch(() => {
        setModelOptions(FALLBACK_MODEL_OPTIONS)
        setModelPreferenceState((current) => current || FALLBACK_MODEL_OPTIONS[0].value)
      })
  }, [])

  // Reload message history when sessionId becomes available (e.g. page refresh)
  useEffect(() => {
    if (!sessionId) {
      setHistoryReady(false)
      return
    }
    let cancelled = false
    setHistoryReady(false)
    getHistory(sessionId, token)
      .then((data) => {
        if (cancelled) return
        if (!data.messages?.length) return
        const loaded = data.messages.map((msg, i) => ({
          id: `h-${i}`,
          role: msg.role,
          content: msg.content,
          detectedLanguage: msg.detected_language,
          sources: msg.sources || [],
          suggestedQuestions: msg.suggested_questions || [],
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
      .finally(() => {
        if (!cancelled) setHistoryReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, token])

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
        {
          id: assistantMsgId,
          role: 'assistant',
          content: '',
          sources: [],
          suggestedQuestions: [],
          isStreaming: true,
          researchStage: 'preparing',
        },
      ])
      setIsLoading(true)

      const streamIntoMessage = (activeSessionId) =>
        streamMessage(activeSessionId, text.trim(), languageOverride, modelPreference, token, {
          onStatus: (event) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      researchStage: event.stage,
                      researchSourceCount: event.source_count,
                    }
                  : m
              )
            )
          },
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
                      suggestedQuestions: event.suggested_questions || [],
                      isStreaming: false,
                      researchStage: null,
                      noResults: event.no_results || false,
                    }
                  : m
              )
            )
            setIsLoading(false)
          },
          onError: (message, error) => {
            if (error?.code) onAccessError?.(error)
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      content: message,
                      isError: true,
                      isStreaming: false,
                      researchStage: null,
                    }
                  : m
              )
            )
            setIsLoading(false)
          },
        })

      const result = await streamIntoMessage(sessionId)
      if (result?.status === 404 && onSessionExpired) {
        try {
          const nextSessionId = await onSessionExpired()
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: '',
                    isError: false,
                    isStreaming: true,
                    researchStage: 'preparing',
                  }
                : m
            )
          )
          setIsLoading(true)
          await streamIntoMessage(nextSessionId)
        } catch {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: 'Could not start a new chat session. Please refresh the page.',
                    isError: true,
                    isStreaming: false,
                  }
                : m
            )
          )
          setIsLoading(false)
        }
      }
    },
    [
      sessionId,
      isLoading,
      languageOverride,
      modelPreference,
      onSessionExpired,
      onAccessError,
      token,
    ]
  )

  useEffect(() => {
    if (!sessionId || !initialQuestion || isLoading || !historyReady) return
    onInitialQuestionConsumed?.()
    send(initialQuestion)
  }, [
    sessionId,
    initialQuestion,
    isLoading,
    historyReady,
    onInitialQuestionConsumed,
    send,
  ])

  return {
    messages,
    isLoading,
    detectedLanguage,
    languageOverride,
    setLanguageOverride,
    modelPreference,
    setModelPreference,
    modelOptions,
    send,
  }
}
