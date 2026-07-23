const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function createSession(channel = 'web') {
  const res = await fetch(`${BASE_URL}/session/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel }),
  })
  if (!res.ok) {
    const err = new Error('Failed to create session')
    err.status = res.status
    throw err
  }
  return res.json()
}

export async function getHistory(sessionId) {
  const res = await fetch(`${BASE_URL}/session/${sessionId}/history`)
  if (!res.ok) {
    const err = new Error(`Failed to load history: ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

export async function getFacets() {
  const res = await fetch(`${BASE_URL}/library/facets`)
  if (!res.ok) throw new Error(`Failed to load facets: ${res.status}`)
  return res.json()
}

export async function getDocuments({ topic, crop, region, q, offset = 0, limit = 20 } = {}) {
  const params = new URLSearchParams()
  if (topic) params.set('topic', topic)
  if (crop) params.set('crop', crop)
  if (region) params.set('region', region)
  if (q) params.set('q', q)
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  const res = await fetch(`${BASE_URL}/library/documents?${params.toString()}`)
  if (!res.ok) throw new Error(`Failed to load documents: ${res.status}`)
  return res.json()
}

export async function getDocumentDetail(id) {
  const res = await fetch(`${BASE_URL}/library/documents/${encodeURIComponent(id)}`)
  if (!res.ok) {
    const err = new Error(`Failed to load document: ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

export async function getCatalogue({ q, offset = 0, limit = 20 } = {}) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  if (q) params.set('q', q)
  const res = await fetch(`${BASE_URL}/catalogue?${params}`)
  if (!res.ok) throw new Error(`Failed to load catalogue: ${res.status}`)
  return res.json()
}

export async function getCatalogueEntry(id, language = 'eng') {
  const res = await fetch(
    `${BASE_URL}/catalogue/${encodeURIComponent(id)}?language=${encodeURIComponent(language)}`,
  )
  if (!res.ok) {
    const err = new Error(`Failed to load catalogue entry: ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

export async function markCatalogueHelpful(id) {
  const res = await fetch(`${BASE_URL}/catalogue/${encodeURIComponent(id)}/helpful`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to record feedback: ${res.status}`)
  return res.json()
}

export async function getChatModels() {
  const res = await fetch(`${BASE_URL}/chat/models`)
  if (!res.ok) throw new Error(`Failed to load chat models: ${res.status}`)
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
    return { ok: false, status: null }
  }

  if (!res.ok) {
    if (res.status === 429) onError('Too many requests — please wait a moment before trying again.')
    else if (res.status === 404) onError('Session expired — starting a new chat.')
    else onError('Something went wrong. Please try again.')
    return { ok: false, status: res.status }
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let streamErrorStatus = null

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
          else if (event.type === 'error') {
            streamErrorStatus = event.status || (event.code === 'session_not_found' ? 404 : null)
            onError(
              streamErrorStatus === 404
                ? 'Session expired — starting a new chat.'
                : event.message
            )
          }
        } catch {
          // Ignore malformed SSE lines
        }
      }
    }
  } catch {
    onError('Connection interrupted — please try again.')
    return { ok: false, status: null }
  }

  if (streamErrorStatus) return { ok: false, status: streamErrorStatus }
  return { ok: true, status: res.status }
}
