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
