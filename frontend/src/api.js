const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function createSession(channel = 'web') {
  const res = await fetch(`${BASE_URL}/session/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel }),
  })
  if (!res.ok) throw new Error('Failed to create session')
  return res.json()
}

export async function getHistory(sessionId) {
  const res = await fetch(`${BASE_URL}/session/${sessionId}/history`)
  if (!res.ok) throw new Error(`Failed to load history: ${res.status}`)
  return res.json()
}

export async function sendMessage(sessionId, message, languageOverride = null) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      language_override: languageOverride,
    }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function streamMessage(sessionId, message, languageOverride = null, modelPreference = null, { onToken, onDone, onError }) {
  let res
  try {
    res = await fetch(`${BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        language_override: languageOverride,
        model_preference: modelPreference,
      }),
    })
  } catch {
    onError('Connection failed — check your internet connection.')
    return
  }

  if (!res.ok) {
    if (res.status === 429) onError('Too many requests — please wait a moment before trying again.')
    else if (res.status === 404) onError('Session not found — please refresh the page.')
    else onError('Something went wrong. Please try again.')
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        try {
          const event = JSON.parse(part.slice(6))
          if (event.type === 'token') onToken(event.content)
          else if (event.type === 'done') onDone(event)
          else if (event.type === 'error') onError(event.message)
        } catch {
          // Ignore malformed SSE lines
        }
      }
    }
  } catch {
    onError('Connection interrupted — please try again.')
  }
}
